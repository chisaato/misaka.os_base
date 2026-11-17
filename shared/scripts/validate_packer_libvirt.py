#!/usr/bin/env python3
"""逐台通过主仓生命周期消费 Packer 成品；日志只写持久状态目录。"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

import yaml


REPO = Path(__file__).resolve().parents[2]
SUPPORT = REPO / 'shared/molecule/libvirt'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    state = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
    root = state / 'misaka-os-base/validation' / (
        'packer-libvirt-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ') + f'-{os.getpid()}')
    root.mkdir(parents=True, mode=0o700)
    print(f'持久证据目录: {root}', flush=True)
    env = dict(os.environ, LC_ALL='C.UTF-8', ANSIBLE_NOCOLOR='1',
               ANSIBLE_COLLECTIONS_PATH=str(REPO / '.dev'),
               MOLECULE_PROJECT_DIRECTORY=str(REPO / 'collections/os_base'))
    # 不让继承的 Ansible 日志路径把输出写回 /tmp 或外部回调。
    env.pop('ANSIBLE_LOG_PATH', None)
    env.pop('ANSIBLE_CALLBACKS_ENABLED', None)
    ansible = str(REPO / '.venv/bin/ansible-playbook')
    virsh = ['virsh', '-c', 'qemu:///system']

    def host_state():
        return {'domains': subprocess.check_output(virsh + ['list', '--all', '--uuid'], text=True).strip(),
                'running': subprocess.check_output(virsh + ['list', '--uuid'], text=True).strip(),
                'network_uuid': subprocess.check_output(virsh + ['net-uuid', 'default'], text=True).strip()}

    baseline = host_state()
    assert not baseline['running'], '已有运行域，不启动第二台 VM'
    # 也拒绝同时运行不归 libvirt 管理的 Packer QEMU。
    processes = subprocess.run(['pgrep', '-a', '-f', '^(/[^ ]*/)?qemu-system-'], capture_output=True, text=True)
    assert processes.returncode == 1, '已有 QEMU 进程，不启动第二台 VM'
    (root / 'host-before.json').write_text(json.dumps(baseline, indent=2))
    results = []
    for image_arg in args.images:
        image = image_arg.resolve(strict=True)
        manifest_path = Path(str(image) + '.manifest.yml')
        source = yaml.safe_load(manifest_path.read_text())
        major = str(source['version']).split('.')[0]
        assert source['os'] == 'debian' and major in ['12', '13']
        evidence = root / ('debian' + major)
        evidence.mkdir(mode=0o700)
        (evidence / 'image.manifest.yml').write_text(manifest_path.read_text())
        before_sha = digest(image)
        assert before_sha == source['sha256'], '成品摘要与 manifest 不符'
        assert host_state() == baseline, '上一个 VM 未清理或宿主状态改变'
        env['MOLECULE_SCENARIO_NAME'] = 'packer-local-debian' + major
        with tempfile.TemporaryDirectory(prefix='misaka-packer-libvirt-') as temporary:
            work = Path(temporary)
            config = work / 'instance.yml'
            settings = {'molecule_instance_config': str(config),
                        'molecule_yml': {'driver': {'libvirt': {
                            'libvirt_image_source': 'local-manifest', 'libvirt_image_path': str(image),
                            'libvirt_disk_gib': 20, 'libvirt_expected_major': major,
                            'libvirt_evidence_root': str(evidence / 'lifecycle')}},
                            'platforms': [{'name': 'debian' + major}]}}
            variables = work / 'variables.json'
            variables.write_text(json.dumps(settings))

            def play(label, playbook, inventory='localhost,', extra=None):
                command = [ansible, '-i', str(inventory), str(playbook), '-e', '@' + str(variables)]
                if extra:
                    command += ['-e', json.dumps(extra)]
                with (evidence / (label + '.log')).open('w') as log:
                    result = subprocess.run(command, cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT)
                assert result.returncode == 0, f'{label} 失败，查看 {evidence}；不启动下一台'
                return (evidence / (label + '.log')).read_text()

            # 失败保留现场及临时 inventory/config，以便按所有权核对后恢复；不盲删域。
            try:
                play('create', SUPPORT / 'create.yml')
                instance = yaml.safe_load(config.read_text())[0]
                owned = yaml.safe_load(Path(instance['manifest']).read_text())
                xml = subprocess.check_output(virsh + ['dumpxml', instance['domain']], text=True)
                (evidence / 'domain.xml').write_text(xml)
                assert 'machine="pc-q35' in xml or "machine='pc-q35" in xml
                assert 'pflash' in xml and Path(owned['nvram']).is_file()
                (evidence / 'ownership.yml').write_text(yaml.safe_dump(owned))
                inventory = work / 'inventory.yml'
                inventory.write_text(yaml.safe_dump({'all': {'hosts': {'debian' + major: {
                    'ansible_host': instance['address'], 'ansible_user': instance['user'],
                    'ansible_ssh_private_key_file': instance['identity_file'],
                    'ansible_ssh_common_args': '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'}}}}))
                extra = {'validation_major': major, 'validation_evidence': str(evidence)}
                play('converge', SUPPORT / 'image_converge.playbook.yml', inventory, extra)
                idem = play('idempotence', SUPPORT / 'image_converge.playbook.yml', inventory, extra)
                assert re.search(r'changed=0\s+unreachable=0\s+failed=0', idem), '第二次 converge 不是零变更'
                play('verify', SUPPORT / 'image_verify.playbook.yml', inventory, extra)
                play('destroy', SUPPORT / 'destroy.yml')
                assert not Path(owned['overlay']).parent.exists(), '运行目录未删除'
                assert host_state() == baseline, '清理后宿主域或网络 UUID 改变'
                assert digest(image) == before_sha, '成品被修改'
                archived = list((evidence / 'lifecycle').glob('*/debian*/serial.log'))
                assert len(archived) == 1 and archived[0].stat().st_size > 0, '未保留串口证据'
                results.append({'image': str(image), 'version': str(source['version']), 'sha256': before_sha,
                                'passed': True, 'idempotent': True, 'destroyed': True,
                                'source_unchanged': True, 'evidence': str(evidence)})
                (root / 'results.json').write_text(json.dumps(results, indent=2))
                print(f'Debian {source["version"]}: 通过且已清理', flush=True)
            except BaseException:
                # 仅保存路径配置，不复制临时密钥或 NoCloud seed。
                for file in work.glob('*.yml'):
                    (evidence / ('recovery-' + file.name)).write_text(file.read_text())
                (evidence / 'recovery-variables.json').write_text(variables.read_text())
                raise
    (root / 'host-after.json').write_text(json.dumps(host_state(), indent=2))


if __name__ == '__main__':
    main()

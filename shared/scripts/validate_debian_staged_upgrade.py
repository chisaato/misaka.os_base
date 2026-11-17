#!/usr/bin/env python3
"""一台空载 UEFI Debian 12→13：安装前闸门、人工交替、SSH 中断与独立证据。

复用主仓 local-manifest 生命周期，不构建镜像，不修改宿主网络。
失败保留自己 VM 与临时控制配置以便诊断；仅 --cleanup 显式按清单清理。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time

import yaml

REPO = Path(__file__).resolve().parents[2]
SUPPORT = REPO / 'shared/molecule/libvirt'
ANSIBLE = REPO / '.venv/bin/ansible-playbook'
VIRSH = ['virsh', '-c', 'qemu:///system']


def host_state():
    return {key: subprocess.check_output(VIRSH + command, text=True).strip()
            for key, command in {'domains': ['list', '--all', '--uuid'],
                                 'running': ['list', '--uuid'], 'network_uuid': ['net-uuid', 'default']}.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path, nargs='?', default=Path('/mnt/cache-mix/packer-templates/output/debian-uefi/debian-12.15-amd64.qcow2'))
    parser.add_argument('--cleanup', type=Path, help='失败运行持久证据目录；只清理其记录的实例')
    parser.add_argument('--manual-install', action='store_true', help='人工执行 full APT，再由角色收养；与中断 worker 场景分轮运行')
    args = parser.parse_args()
    os.umask(0o077)
    env = dict(os.environ, LC_ALL='C.UTF-8', ANSIBLE_NOCOLOR='1',
               ANSIBLE_COLLECTIONS_PATH=str(REPO / '.dev'),
               MOLECULE_PROJECT_DIRECTORY=str(REPO / 'collections/os_base'),
               MOLECULE_SCENARIO_NAME='debian-staged-upgrade')
    env.pop('ANSIBLE_LOG_PATH', None)
    env.pop('ANSIBLE_CALLBACKS_ENABLED', None)
    if args.cleanup:
        evidence = args.cleanup.resolve(strict=True)
        work = Path((evidence / 'control-directory.txt').read_text().strip())
        with (evidence / 'destroy.log').open('w') as log:
            subprocess.run([str(ANSIBLE), '-i', 'localhost,', str(SUPPORT / 'destroy.yml'),
                            '-e', '@' + str(work / 'variables.json')], cwd=REPO, env=env,
                           stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, check=True)
        return
    baseline = host_state()
    assert not baseline['running'], '已有运行 VM，本次不启动另一台'
    assert subprocess.run(['pgrep', '-f', '^(/[^ ]*/)?qemu-system-'], capture_output=True).returncode == 1
    state = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
    evidence = state / 'misaka-os-base/validation' / ('debian-staged-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    evidence.mkdir(parents=True, mode=0o700)
    print('持久证据: ' + str(evidence), flush=True)
    work = Path(tempfile.mkdtemp(prefix='debian-staged-', dir='/tmp/opencode'))
    (evidence / 'control-directory.txt').write_text(str(work) + '\n')
    (evidence / 'host-before.json').write_text(json.dumps(baseline, indent=2))
    manifest_path = Path(str(args.image) + '.manifest.yml')
    manifest = yaml.safe_load(manifest_path.read_text())
    with args.image.open('rb') as stream:
        source_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    assert source_hash == manifest['sha256'] and str(manifest['version']).startswith('12.')
    (evidence / 'image.manifest.yml').write_text(manifest_path.read_text())
    config = work / 'instance.yml'
    settings = {'molecule_instance_config': str(config), 'molecule_yml': {'driver': {'libvirt': {
        'libvirt_image_source': 'local-manifest', 'libvirt_image_path': str(args.image.resolve()),
        'libvirt_disk_gib': 24, 'libvirt_expected_major': '12',
        'libvirt_evidence_root': str(evidence / 'lifecycle')}}, 'platforms': [{'name': 'debian12'}]}}
    variables = work / 'variables.json'
    variables.write_text(json.dumps(settings))
    role_play = work / 'upgrade.yml'
    role_play.write_text(yaml.safe_dump([{'name': 'Debian 在线升级验证', 'hosts': 'all', 'become': True,
        'gather_facts': False, 'roles': ['misaka.os_base.debian_dist_upgrade']}], allow_unicode=True))
    inventory = work / 'inventory.yml'
    results = {'tested_profile': 'Packer Debian 12.15 amd64 ISO, UEFI, empty, single VM, Debian repositories only',
               'passed': False, 'manual_install': args.manual_install, 'checks': []}
    base_vars = {'host_geo': {'country': 'cn'}, 'debian_repo_mirror_list': ['mirrors.ustc.edu.cn'],
                 'debian_dist_upgrade_wait_delay': 3, 'debian_dist_upgrade_delay': 2,
                 'debian_dist_upgrade_tested_profile': results['tested_profile']}

    def play(label, playbook, extra=None, local=False, expected=0, cwd=REPO):
        command = [str(ANSIBLE), '-i', 'localhost,' if local else str(inventory), str(playbook)]
        command += ['-e', '@' + str(variables)] if local else ['-e', json.dumps(dict(base_vars, **(extra or {})))]
        with (evidence / (label + '.log')).open('w') as log:
            result = subprocess.run(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        assert (result.returncode == 0) == (expected == 0), label + ' 返回码异常，见持久日志'
        results['checks'].append(label)
        (evidence / 'results.json').write_text(json.dumps(results, indent=2))
        return (evidence / (label + '.log')).read_text()

    instance = None
    ssh_args = []

    def ssh(command, check=True):
        result = subprocess.run(ssh_args + [command], text=True, capture_output=True, env=env, stdin=subprocess.DEVNULL)
        if check and result.returncode:
            raise RuntimeError(result.stderr + result.stdout)
        return result

    def facts(label):
        code = "import hashlib,json,os,pathlib; p=pathlib.Path; print(json.dumps({'os':p('/etc/os-release').read_text(),'boot_id':p('/proc/sys/kernel/random/boot_id').read_text().strip(),'kernel':os.uname().release,'status_sha':hashlib.sha256(p('/var/lib/dpkg/status').read_bytes()).hexdigest(),'efi':p('/sys/firmware/efi').is_dir(),'machine':p('/etc/machine-id').read_text()}))"
        result = ssh('sudo python3 -c ' + __import__('shlex').quote(code))
        payload = json.loads(result.stdout)
        (evidence / (label + '.json')).write_text(json.dumps(payload, indent=2))
        return payload

    try:
        play('create', SUPPORT / 'create.yml', local=True)
        instance = yaml.safe_load(config.read_text())[0]
        owned = yaml.safe_load(Path(instance['manifest']).read_text())
        (evidence / 'ownership.yml').write_text(yaml.safe_dump(owned))
        (evidence / 'domain.xml').write_text(subprocess.check_output(VIRSH + ['dumpxml', instance['domain']], text=True))
        inventory.write_text(yaml.safe_dump({'all': {'hosts': {'debian12': {
            'ansible_host': instance['address'], 'ansible_user': instance['user'],
            'ansible_ssh_private_key_file': instance['identity_file'],
            'ansible_ssh_common_args': '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'}}}}))
        ssh_args = ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
                    '-o', 'ConnectTimeout=10', '-i', instance['identity_file'], instance['user'] + '@' + instance['address']]
        before = facts('before')
        assert before['efi'] and 'VERSION_ID="12"' in before['os']
        play('status-readonly', role_play, {'debian_dist_upgrade_action': 'status'})
        assert ssh('sudo test ! -e /var/lib/misaka/dist-upgrade/debian.json && sudo test ! -e /usr/local/lib/misaka-dist-upgrade/debian_upgrade.py').returncode == 0
        play('target-conflict', role_play, {'debian_dist_upgrade_target_version': 14}, expected=1)
        # 使用真实 POSIX APT 锁注入：是忙，不是损坏；随后只停止此测试单元。
        lock_code = "import fcntl,time; f=open('/var/lib/dpkg/lock-frontend','r+'); fcntl.lockf(f,fcntl.LOCK_EX); time.sleep(180)"
        ssh('sudo systemd-run --quiet --unit=misaka-debian-test-lock python3 -c ' + __import__('shlex').quote(lock_code))
        time.sleep(1)
        lock_log = play('existing-apt-lock', role_play, expected=1)
        assert '"phase": "busy"' in lock_log, 'APT 锁负例必须实际命中忙碌状态'
        ssh('sudo systemctl stop misaka-debian-test-lock')
        # 仅在自己的空载 VM 注入未配置的假包；finally 原样恢复，不执行 dpkg 修复。
        ssh('sudo cp /var/lib/dpkg/status /var/lib/dpkg/misaka-validation-status.saved; sudo chmod 0600 /var/lib/dpkg/misaka-validation-status.saved')
        try:
            entry = '\nPackage: misaka-validation-unconfigured\nStatus: install ok unpacked\nPriority: optional\nSection: misc\nArchitecture: all\nVersion: 1\nMaintainer: Validation <validation@example.invalid>\nDescription: failure gate injection\n\n'
            ssh('printf %s ' + __import__('shlex').quote(entry) + ' | sudo tee -a /var/lib/dpkg/status >/dev/null')
            abnormal_log = play('dpkg-audit-preflight', role_play, expected=1)
            assert '"phase": "needs_human"' in abnormal_log
        finally:
            ssh('sudo cp /var/lib/dpkg/misaka-validation-status.saved /var/lib/dpkg/status; sudo rm /var/lib/dpkg/misaka-validation-status.saved')
        assert facts('after-audit-restored')['status_sha'] == before['status_sha']
        play('target-update-error', role_play, {'debian_repo_mirror_list': ['127.0.0.1:9'],
             'debian_dist_upgrade_retries': 1}, expected=1)
        assert facts('after-update-failure')['status_sha'] == before['status_sha']
        # 管理员审阅失败证据后显式移走失败 active，角色从不自行清除。
        failed_active = ssh('sudo cat /var/lib/misaka/dist-upgrade/debian-jobs/active.json').stdout
        (evidence / 'failed-update-active.json').write_text(failed_active)
        failed_job = json.loads(failed_active)
        failed_result = json.loads(ssh('sudo cat /var/lib/misaka/dist-upgrade/debian-jobs/' + failed_job['id'] + '.json').stdout)
        assert not failed_result['ok'] and 'APT 返回' in failed_result['error'], '必须是真实目标 update 错误'
        ssh('sudo mv /var/lib/misaka/dist-upgrade/debian-jobs/active.json /var/lib/misaka/dist-upgrade/debian-jobs/failed-update-active.saved')
        play('default-download-gate', role_play)
        gate = json.loads(ssh('sudo python3 /usr/local/lib/misaka-dist-upgrade/debian_upgrade.py probe').stdout)
        assert gate['phase'] == 'downloaded' and gate['target_indexes'], '必须是真实下载回执，不能仅凭包状态未变通过'
        (evidence / 'download-gate-probe.json').write_text(json.dumps(gate, indent=2))
        downloaded = facts('downloaded')
        assert downloaded['status_sha'] == before['status_sha'] and downloaded['boot_id'] == before['boot_id']
        active_marker_sha = ssh('sudo sha256sum /var/lib/misaka/dist-upgrade/debian.json').stdout.split()[0]
        play('active-target-conflict', role_play, {'debian_dist_upgrade_target_version': 14}, expected=1)
        assert ssh('sudo sha256sum /var/lib/misaka/dist-upgrade/debian.json').stdout.split()[0] == active_marker_sha
        play('skip-false-still-no-install', role_play, {'debian_dist_upgrade_skip_reboot': False})
        assert facts('skip-false')['status_sha'] == before['status_sha']
        play('explicit-minimal', role_play, {'debian_dist_upgrade_until': 'minimal_upgraded'})
        minimal = facts('minimal')
        assert minimal['boot_id'] == before['boot_id'] and minimal['status_sha'] != before['status_sha']
        if args.manual_install:
            active = json.loads(ssh('sudo cat /var/lib/misaka/dist-upgrade/debian-jobs/active.json').stdout)
            # 此命令由测试 play 之外的管理员执行，不调用角色 worker/marker。
            command = ('DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l UCF_FORCE_CONFFOLD=1 '
                       'APT_LISTCHANGES_FRONTEND=none apt-get -y '
                       '-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold dist-upgrade '
                       '> /var/log/misaka-debian-manual-full.log 2>&1; '
                       'rc=$?; printf "%s\\n" "$rc" > /var/lib/misaka/debian-manual-full.result; exit "$rc"')
            ssh('sudo systemd-run --quiet --no-block --unit=misaka-debian-manual-full '
                '--property=Type=oneshot --property=TimeoutStartSec=infinity /bin/sh -c ' + __import__('shlex').quote(command))
            (evidence / 'manual-command.json').write_text(json.dumps({'command': command}, indent=2))
            for _ in range(1200):
                result = ssh('sudo cat /var/lib/misaka/debian-manual-full.result', check=False)
                if result.returncode == 0 and result.stdout.strip():
                    break
                time.sleep(3)
            (evidence / 'manual-full.log').write_text(ssh('sudo cat /var/log/misaka-debian-manual-full.log', check=False).stdout)
            assert result.returncode == 0 and result.stdout.strip() == '0', '人工 full 命令失败或无完成证据'
            results['checks'].append('manual-apt-full')
        else:
            # 真实 full worker 已活跃时杀掉自己的控制进程组，再换控制工作目录。
            full_extra = dict(base_vars, debian_dist_upgrade_until='full_upgraded')
            with (evidence / 'interrupted-full-controller.log').open('w') as log:
                controller = subprocess.Popen([str(ANSIBLE), '-i', str(inventory), str(role_play),
                    '-e', json.dumps(full_extra)], cwd=REPO, env=env, stdout=log,
                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
                active = None
                for _ in range(240):
                    raw = ssh('sudo cat /var/lib/misaka/dist-upgrade/debian-jobs/active.json', check=False)
                    if raw.returncode == 0:
                        candidate = json.loads(raw.stdout)
                        if candidate['stage'] == 'full':
                            state = ssh('systemctl show ' + candidate['unit'] + ' --property=ActiveState --value', check=False).stdout.strip()
                            processes = ssh('sudo pgrep -a -x apt-get', check=False).stdout.splitlines()
                            actual_apt = [line for line in processes if 'dist-upgrade' in line and '--download-only' not in line and ' -s ' not in line]
                            if state in {'active', 'activating'} and actual_apt:
                                active = dict(candidate, observed_apt_processes=actual_apt)
                                break
                    if controller.poll() is not None:
                        raise RuntimeError('full 控制端在注入前已结束，不能伪称中断覆盖')
                    time.sleep(1)
                assert active, '没有观察到真实活跃的 full worker'
                os.killpg(controller.pid, signal.SIGTERM)
                controller.wait(timeout=30)
            (evidence / 'interrupted-job.json').write_text(json.dumps(active, indent=2))
        work_b = work / 'new-controller'
        work_b.mkdir(mode=0o700)
        play('adopt-full-new-controller', role_play, {'debian_dist_upgrade_until': 'full_upgraded'}, cwd=work_b)
        assert json.loads(ssh('sudo cat /var/lib/misaka/dist-upgrade/debian-jobs/active.json').stdout)['id'] == active['id']
        pending = facts('pending-reboot')
        assert pending['boot_id'] == before['boot_id'] and 'VERSION_ID="13"' in pending['os']
        # 人工重启后由新控制端收养；不靠 Ansible reboot 的返回值证明重启。
        ssh('sudo systemd-run --quiet --on-active=3 --unit=misaka-debian-manual-reboot /usr/bin/systemctl reboot')
        time.sleep(8)
        for _ in range(180):
            response = ssh('cat /proc/sys/kernel/random/boot_id', check=False)
            if response.returncode == 0 and response.stdout.strip() != before['boot_id']:
                break
            time.sleep(3)
        after = facts('after-reboot')
        assert after['boot_id'] != before['boot_id'] and after['machine'] == before['machine'] and after['efi']
        play('complete', role_play, {'debian_dist_upgrade_until': 'completed'}, cwd=work_b)
        idem = play('idempotence', role_play, {'debian_dist_upgrade_until': 'completed'}, cwd=work_b)
        assert re.search(r'changed=0\s+unreachable=0\s+failed=0', idem)
        # 独立读取执行器只读 probe，不重新调用角色。
        probe = json.loads(ssh('sudo python3 /usr/local/lib/misaka-dist-upgrade/debian_upgrade.py probe').stdout)
        (evidence / 'independent-verify.json').write_text(json.dumps(probe, indent=2))
        assert probe['phase'] == 'completed' and not probe['audit'].strip()
        assert not probe['full_plan']['changes'] and not probe['minimal_plan']['changes']
        assert probe['kernel']['running_target'] and probe['sources'] == 'target'
        (evidence / 'original-completed-marker.json').write_text(ssh('sudo cat /var/lib/misaka/dist-upgrade/debian.json').stdout)
        # 目标无 marker 不可声称曾重启；显式重启边界可建立新证据。
        ssh('sudo mv /var/lib/misaka/dist-upgrade/debian.json /var/lib/misaka/dist-upgrade/debian-completed.saved')
        orphan = json.loads(ssh('sudo python3 /usr/local/lib/misaka-dist-upgrade/debian_upgrade.py probe').stdout)
        assert orphan['phase'] == 'full_upgraded'
        (evidence / 'target-without-marker.json').write_text(json.dumps(orphan, indent=2))
        play('target-no-marker-default-no-reboot', role_play, cwd=work_b)
        assert facts('orphan-default')['boot_id'] == after['boot_id']
        play('explicit-reboot', role_play, {'debian_dist_upgrade_until': 'reboot_requested'}, cwd=work_b)
        play('recomplete', role_play, {'debian_dist_upgrade_until': 'completed'}, cwd=work_b)
        idem = play('final-idempotence', role_play, {'debian_dist_upgrade_until': 'completed'}, cwd=work_b)
        assert re.search(r'changed=0\s+unreachable=0\s+failed=0', idem)
        # 保留原票要求：真实目标 OS 上把源反转为 bookworm，marker 必须降级。
        source_before = ssh('sudo cat /etc/apt/sources.list.d/debian.sources').stdout
        marker_before = ssh('sudo sha256sum /var/lib/misaka/dist-upgrade/debian.json').stdout.split()[0]
        stable = facts('before-source-reversal')
        ssh('sudo cp /etc/apt/sources.list.d/debian.sources /var/lib/misaka/debian-sources-validation.saved')
        try:
            reverse = "from pathlib import Path; p=Path('/etc/apt/sources.list.d/debian.sources'); p.write_text(p.read_text().replace('trixie', 'bookworm'))"
            ssh('sudo python3 -c ' + __import__('shlex').quote(reverse))
            play('source-reversal-status-readonly', role_play, {'debian_dist_upgrade_action': 'status'}, cwd=work_b)
            assert ssh('sudo sha256sum /var/lib/misaka/dist-upgrade/debian.json').stdout.split()[0] == marker_before
            play('source-reversal-demote', role_play, {'debian_dist_upgrade_until': 'preflight'}, cwd=work_b)
            demoted = json.loads(ssh('sudo cat /var/lib/misaka/dist-upgrade/debian.json').stdout)
            assert demoted['stage'] == 'preflight' and 'demoted' in demoted['history'][-1]['note']
            (evidence / 'demoted-marker.json').write_text(json.dumps(demoted, indent=2))
        finally:
            ssh('sudo cp /var/lib/misaka/debian-sources-validation.saved /etc/apt/sources.list.d/debian.sources; sudo rm /var/lib/misaka/debian-sources-validation.saved')
        assert ssh('sudo cat /etc/apt/sources.list.d/debian.sources').stdout == source_before
        play('restore-source-complete', role_play, {'debian_dist_upgrade_until': 'completed'}, cwd=work_b)
        idem = play('post-reversal-idempotence', role_play, {'debian_dist_upgrade_until': 'completed'}, cwd=work_b)
        assert re.search(r'changed=0\s+unreachable=0\s+failed=0', idem)
        restored = facts('after-source-reversal')
        assert restored['boot_id'] == stable['boot_id'] and restored['status_sha'] == stable['status_sha']
        results['passed'] = True
    finally:
        if instance and ssh_args:
            (evidence / 'guest-marker.json').write_text(ssh('sudo cat /var/lib/misaka/dist-upgrade/debian.json', check=False).stdout)
            (evidence / 'guest-jobs.log').write_text(ssh('sudo find /var/lib/misaka/dist-upgrade/debian-jobs -maxdepth 1 -type f -exec sh -c \'echo === "$1"; cat "$1"\' sh {} \\;', check=False).stdout)
        (evidence / 'results.json').write_text(json.dumps(results, indent=2))
    play('destroy', SUPPORT / 'destroy.yml', local=True)
    assert not Path(owned['overlay']).parent.exists(), '自己的 overlay 运行目录未清理'
    assert not Path(owned['nvram']).exists(), '自己的 NVRAM 未清理'
    assert host_state() == baseline
    (evidence / 'host-after.json').write_text(json.dumps(host_state(), indent=2))
    with args.image.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == source_hash
    results.update(destroyed=True, source_unchanged=True, overlay_nvram_cleaned=True, source_sha256=source_hash)
    (evidence / 'results.json').write_text(json.dumps(results, indent=2))
    print('通过并清理: ' + str(evidence), flush=True)


if __name__ == '__main__':
    main()

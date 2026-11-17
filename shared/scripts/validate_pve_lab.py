#!/usr/bin/env python3
"""空载 PVE 8 基线与 8→9 实验；所有输出持久化，只管理本轮清单中的一台 VM。"""
import argparse
import datetime
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET

import yaml

REPO = Path(__file__).resolve().parents[2]
SUPPORT = REPO / 'shared/molecule/libvirt'
LAB = REPO / 'shared/molecule/pve_lab'
ANSIBLE = str(REPO / '.venv/bin/ansible-playbook')
VIRSH = ['virsh', '-c', 'qemu:///system']
SOURCE = Path('/mnt/cache-mix/packer-templates/output/debian-uefi/debian-12.15-amd64.qcow2')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def host_state():
    return {key: subprocess.check_output(VIRSH + args, text=True).strip() for key, args in {
        'domains': ['list', '--all', '--uuid'], 'running': ['list', '--uuid'],
        'network_uuid': ['net-uuid', 'default']}.items()}


def private_runtime(directory):
    """PVE 磁盘含系统自身 PKI；临时 staging 也只让控制用户和 qemu 读取。"""
    capabilities = ET.fromstring(subprocess.check_output(VIRSH + ['capabilities'], text=True))
    label = capabilities.findtext("./host/secmodel[model='dac']/baselabel") or ''
    match = re.fullmatch(r'\+?(\d+):\+?\d+', label)
    assert match, '无法确定 qemu DAC UID，拒绝公开 PVE 基盘'
    directory.chmod(0o700)
    subprocess.run(['setfacl', '-m', 'u:' + match.group(1) + ':rx', str(directory)], check=True)


class Lab:
    def __init__(self, root, image, major='12'):
        self.root = root
        self.work = Path(tempfile.mkdtemp(prefix='pve-lab-', dir='/tmp/opencode'))
        private_runtime(self.work)
        (root / 'control-directory.txt').write_text(str(self.work))
        self.env = dict(os.environ, LC_ALL='C.UTF-8', ANSIBLE_NOCOLOR='1', ANSIBLE_COLLECTIONS_PATH=str(REPO / '.dev'),
                        MOLECULE_PROJECT_DIRECTORY=str(REPO / 'collections/os_base'), MOLECULE_SCENARIO_NAME='pve-lab')
        self.env.pop('ANSIBLE_LOG_PATH', None); self.env.pop('ANSIBLE_CALLBACKS_ENABLED', None)
        self.settings = {'molecule_instance_config': str(self.work / 'instance.yml'), 'molecule_yml': {
            'driver': {'libvirt': {'libvirt_image_source': 'local-manifest', 'libvirt_image_path': str(image),
                                  'libvirt_expected_major': major, 'libvirt_disk_gib': 40, 'libvirt_memory_mib': 6144,
                                  'libvirt_cache_root': str(self.work / 'cache'),
                                  'libvirt_evidence_root': str(root / 'lifecycle')}}, 'platforms': [{'name': 'pve-lab'}]}}
        self.variables = self.work / 'variables.json'; self.variables.write_text(json.dumps(self.settings))
        self.inventory = self.work / 'inventory.yml'
        self.base_vars = {'host_geo': {'country': 'cn'}, 'debian_repo_mirror_list': ['mirrors.ustc.edu.cn'],
                          'pve_on_debian_mirror': 'mirrors.ustc.edu.cn', 'pve_on_debian_manage_resolv_conf': False,
                          'pve_init_apt_mirror': 'mirrors.ustc.edu.cn', 'pve_init_auto_debian_init': False}

    def play(self, label, path, local=False, extra=None, expect=0):
        command = [ANSIBLE, '-i', 'localhost,' if local else str(self.inventory), str(path), '-e',
                   '@' + str(self.variables) if local else json.dumps(dict(self.base_vars, **(extra or {})))]
        with (self.root / (label + '.log')).open('w') as log:
            result = subprocess.run(command, cwd=REPO, env=self.env, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT)
        assert (result.returncode == 0) == (expect == 0), f'{label} 失败，查看 {self.root}'
        return (self.root / (label + '.log')).read_text()

    def create(self):
        assert not host_state()['running'], '有其他运行 VM，不擅停、不另启动'
        assert subprocess.run(['pgrep', '-f', '^(/[^ ]*/)?qemu-system-'], capture_output=True).returncode == 1
        self.play('create', SUPPORT / 'create.yml', local=True)
        self.connect()
        (self.root / 'ownership.yml').write_text(yaml.safe_dump(self.owned))
        (self.root / 'domain.xml').write_text(subprocess.check_output(VIRSH + ['dumpxml', self.instance['domain']], text=True))
        (self.root / 'leases.log').write_text(subprocess.check_output(VIRSH + ['net-dhcp-leases', 'default', '--mac', self.owned['mac']], text=True))

    def connect(self):
        self.instance = yaml.safe_load((self.work / 'instance.yml').read_text())[0]
        self.owned = yaml.safe_load(Path(self.instance['manifest']).read_text())
        private_runtime(Path(self.owned['overlay']).parent)
        self.ssh_args = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null',
                         '-o', 'ConnectTimeout=10', '-i', self.instance['identity_file'],
                         self.instance['user'] + '@' + self.instance['address']]
        self.inventory.write_text(yaml.safe_dump({'all': {'hosts': {'pve-lab': {
            'ansible_host': self.instance['address'], 'ansible_user': self.instance['user'],
            'ansible_ssh_private_key_file': self.instance['identity_file'],
            'ansible_ssh_common_args': '-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'}}}}))

    @classmethod
    def attach(cls, root):
        work = Path((root / 'control-directory.txt').read_text())
        variables = work / 'variables.json'
        settings = json.loads(variables.read_text())
        # __init__ 会新建运行目录；续接只读取原有清单，不认领其他域。
        self = cls.__new__(cls)
        self.root, self.work, self.variables, self.settings = root, work, variables, settings
        self.inventory = work / 'inventory.yml'
        self.env = dict(os.environ, LC_ALL='C.UTF-8', ANSIBLE_NOCOLOR='1', ANSIBLE_COLLECTIONS_PATH=str(REPO / '.dev'),
                        MOLECULE_PROJECT_DIRECTORY=str(REPO / 'collections/os_base'), MOLECULE_SCENARIO_NAME='pve-lab')
        self.env.pop('ANSIBLE_LOG_PATH', None); self.env.pop('ANSIBLE_CALLBACKS_ENABLED', None)
        self.base_vars = {'host_geo': {'country': 'cn'}, 'debian_repo_mirror_list': ['mirrors.ustc.edu.cn'],
                          'pve_on_debian_mirror': 'mirrors.ustc.edu.cn', 'pve_on_debian_manage_resolv_conf': False,
                          'pve_init_apt_mirror': 'mirrors.ustc.edu.cn', 'pve_init_auto_debian_init': False}
        self.connect()
        assert self.owned['owner'] == 'misaka-molecule-libvirt'
        return self

    def ssh(self, command, check=True, stdin=None):
        kwargs = {'input': stdin} if stdin is not None else {'stdin': subprocess.DEVNULL}
        result = subprocess.run(self.ssh_args + [command], text=True, capture_output=True, **kwargs)
        if check and result.returncode:
            raise RuntimeError(command + '\n' + result.stdout + result.stderr)
        return result

    def install_helpers(self):
        self.ssh('sudo mkdir -p /usr/local/lib/misaka-pve-lab; sudo chmod 0700 /usr/local/lib/misaka-pve-lab')
        for name in ['apt_worker.py', 'probe.py']:
            self.ssh('sudo tee /usr/local/lib/misaka-pve-lab/' + name + ' >/dev/null', stdin=(LAB / name).read_text())
            self.ssh('sudo chmod 0600 /usr/local/lib/misaka-pve-lab/' + name)

    def apt(self, stage):
        start = self.ssh('sudo python3 /usr/local/lib/misaka-pve-lab/apt_worker.py start --stage ' + stage)
        job = json.loads(start.stdout)
        (self.root / (stage + '-job.json')).write_text(json.dumps(job, indent=2))
        self.observe_apt(stage, job)

    def observe_apt(self, stage, job):
        # 续接只观察原 job；绝不再次执行 start 或 APT。
        observer = (REPO / 'collections/os_base/roles/debian_dist_upgrade/files/observe_job.sh').read_text()
        observer = observer.replace('/var/lib/misaka/dist-upgrade/debian-jobs', '/var/lib/misaka/pve-lab/jobs')
        observer = observer.replace('misaka-debian-', 'misaka-pve-lab-')
        observer = observer.replace('misaka-pve-lab-prepare-*|misaka-pve-lab-download-*|misaka-pve-lab-minimal-*|misaka-pve-lab-full-*',
                                    'misaka-pve-lab-update-*|misaka-pve-lab-base-*|misaka-pve-lab-kernel-*|misaka-pve-lab-grub-*|misaka-pve-lab-remove-debian-*|misaka-pve-lab-download9-*|misaka-pve-lab-upgrade9-*')
        for _ in range(2400):
            active = self.ssh('sudo cat /var/lib/misaka/pve-lab/jobs/active.json', check=False)
            if active.returncode == 255:
                time.sleep(3)
                continue
            assert active.returncode == 0 and json.loads(active.stdout)['id'] == job['id'], 'guest job 已变化，拒绝认领'
            result = self.ssh('sudo /bin/sh -s', check=False, stdin=observer)
            if result.returncode not in {75, 255}:
                break
            time.sleep(3)
        else:
            raise RuntimeError('观察超时；原 worker 可能仍运行，保留现场，不启动新事务')
        (self.root / (stage + '-result.log')).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, f'{stage} worker 失败，禁止自动修复；见持久结果'
        self.archive_jobs()

    def archive_jobs(self):
        result = self.ssh('sudo find /var/lib/misaka/pve-lab/jobs -maxdepth 1 -type f -exec sh -c \'echo === "$1"; cat "$1"\' sh {} \\;', check=False)
        name = 'apt-jobs.log' if result.returncode == 0 else 'apt-jobs-archive-error.log'
        (self.root / name).write_text(result.stdout + result.stderr)

    def reboot(self, label):
        before = self.ssh('cat /proc/sys/kernel/random/boot_id').stdout.strip()
        self.ssh('sudo systemd-run --quiet --on-active=3 --unit=misaka-pve-lab-reboot-' + label + ' systemctl reboot')
        time.sleep(8)
        for _ in range(240):
            self.refresh_lease()
            result = self.ssh('cat /proc/sys/kernel/random/boot_id', check=False)
            if result.returncode == 0 and result.stdout.strip() != before:
                break
            time.sleep(3)
        assert result.returncode == 0 and result.stdout.strip() != before, '重启未完成'

    def refresh_lease(self):
        result = subprocess.run(VIRSH + ['domifaddr', self.instance['domain'], '--source', 'lease'],
                                text=True, capture_output=True, env=self.env)
        match = re.search(re.escape(self.owned['mac']) + r'\s+ipv4\s+([0-9.]+)/', result.stdout)
        if match and match.group(1) != self.instance['address']:
            self.instance['address'] = match.group(1)
            self.ssh_args[-1] = self.instance['user'] + '@' + match.group(1)
            config = yaml.safe_load((self.work / 'instance.yml').read_text())
            config[0]['address'] = match.group(1)
            (self.work / 'instance.yml').write_text(yaml.safe_dump(config))
            inventory = yaml.safe_load(self.inventory.read_text())
            inventory['all']['hosts']['pve-lab']['ansible_host'] = match.group(1)
            self.inventory.write_text(yaml.safe_dump(inventory))
            (self.root / 'updated-lease.log').write_text(result.stdout)

    def probe(self, label, major):
        for _ in range(120):
            ready = self.ssh('systemctl is-active pve-cluster pveproxy pvedaemon pvestatd', check=False)
            if ready.returncode == 0 and ready.stdout.splitlines() == ['active'] * 4:
                break
            time.sleep(2)
        assert ready.returncode == 0 and ready.stdout.splitlines() == ['active'] * 4, 'PVE 服务未就绪：' + ready.stdout + ready.stderr
        data = json.loads(self.ssh('sudo python3 /usr/local/lib/misaka-pve-lab/probe.py').stdout)
        (self.root / (label + '.json')).write_text(json.dumps(data, indent=2))
        assert data['os'] == ('12' if major == '8' else '13')
        assert data['pveversion'].startswith('pve-manager/' + major + '.')
        assert data['efi'] and data['kernel_from_proxmox_meta'] and data['meta_at_candidate']
        assert not data['audit'] and not data['pending_plan']
        assert all(state == 'active' for state in data['services'].values())
        assert data['etc_pve_fstype'].startswith('fuse'), '/etc/pve 必须实际挂载为 pmxcfs'
        assert not data['has_cluster_config'] and data['guests'] == []
        assert any(not ipaddress.ip_address(ip).is_loopback for ip in data['addresses'])
        return data

    def shutdown(self, clean=False):
        # 清理测试公钥后不能再新建 SSH；清理和请求关机必须在同一已认证连接完成。
        prefix = 'sudo cloud-init clean --logs --seed && sudo rm -f /home/molecule/.ssh/authorized_keys && sudo sync && ' if clean else ''
        self.ssh(prefix + 'sudo systemd-run --quiet --on-active=2 --unit=misaka-pve-lab-poweroff systemctl poweroff')
        self.wait_off()

    def wait_off(self):
        for _ in range(150):
            if subprocess.run(VIRSH + ['dominfo', self.instance['domain']], capture_output=True).returncode:
                return
            time.sleep(2)
        raise RuntimeError('未干净关机，拒绝处理磁盘')

    def destroy(self):
        self.play('destroy', SUPPORT / 'destroy.yml', local=True)
        assert not Path(self.owned['overlay']).parent.exists()
        assert not Path(self.owned['nvram']).exists()
        cache = Path(self.settings['molecule_yml']['driver']['libvirt'].get('libvirt_cache_root', ''))
        if cache == self.work / 'cache':
            assert str(self.work).startswith('/tmp/opencode/pve-lab-')
            source = Path(self.settings['molecule_yml']['driver']['libvirt']['libvirt_image_path'])
            expected = 'local-' + sha(source) + '.qcow2'
            for image in (cache / 'base').iterdir():
                assert image.name == expected and image.is_file(), '缓存中有非本轮文件，拒绝删除'
                image.unlink()
            for directory in sorted((p for p in cache.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
                directory.rmdir()
            cache.rmdir()


def baseline(root):
    before = host_state(); (root / 'host-before.json').write_text(json.dumps(before, indent=2))
    source_sha = sha(SOURCE)
    (root / 'source.manifest.yml').write_text(Path(str(SOURCE) + '.manifest.yml').read_text())
    # 在原镜像以外提供坏 manifest，证明真实 local-manifest 校验在创建域前拒绝。
    bad = root / 'bad-manifest.yml'
    payload = yaml.safe_load(Path(str(SOURCE) + '.manifest.yml').read_text()); payload['sha256'] = '0' * 64
    bad.write_text(yaml.safe_dump(payload))
    command = ['python3', str(REPO / 'shared/scripts/libvirt_assets.py'), 'local-manifest', '--image', str(SOURCE), '--manifest', str(bad)]
    with (root / 'manifest-rejection.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    assert result.returncode != 0 and host_state() == before
    lab = Lab(root, SOURCE)
    try:
        lab.create(); lab.install_helpers()
        # 单独调用真实角色的 hostname 前置门禁，不让坏 hostname 进入安装。
        original = lab.ssh('sudo cat /etc/hosts').stdout
        try:
            lab.ssh("printf '127.0.0.1 localhost pve-lab\\n' | sudo tee /etc/hosts >/dev/null")
            guard = lab.work / 'hostname-guard.yml'
            guard.write_text(yaml.safe_dump([{'name': 'Hostname 前置负例', 'hosts': 'all', 'become': True,
                'gather_facts': True, 'roles': ['misaka.os_base.pve_on_debian']}]))
            lab.play('hostname-rejection', guard, expect=1)
        finally:
            lab.ssh('sudo tee /etc/hosts >/dev/null', stdin=original)
        lab.play('prepare', LAB / 'prepare.yml')
        lab.apt('update'); lab.apt('base'); lab.apt('kernel')
        lab.reboot('kernel8')
        assert lab.ssh('uname -r').stdout.strip().endswith('-pve')
        lab.play('install', LAB / 'install.yml')
        lab.apt('remove-debian')
        lab.ssh('sudo update-grub')
        lab.apt('base')
        lab.reboot('pve8')
        first = lab.probe('baseline-verified', '8')
        assert first['pveversion'].startswith('pve-manager/8.4.')
        lab.play('role-converge-after-boot', LAB / 'install.yml')
        idem = lab.play('role-idempotence', LAB / 'install.yml')
        assert re.search(r'changed=0\s+unreachable=0\s+failed=0', idem)
        # 只清除测试用户的注入公钥和 cloud-init seed 缓存，不改 PVE 自身配置/身份。
        lab.shutdown(clean=True)
        artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700)
        target = artifacts / 'pve8.4-uefi.qcow2'
        with (root / 'export.log').open('w') as log:
            subprocess.run(['qemu-img', 'convert', '-p', '-O', 'qcow2', lab.owned['overlay'], str(target)], stdout=log, stderr=subprocess.STDOUT, check=True)
        target.chmod(0o400)
        manifest = {'schema': 1, 'sha256': sha(target), 'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'source': {'image': SOURCE.name, 'sha256': source_sha}, 'os': 'debian', 'version': '12', 'uefi': True,
                    'builder': {'name': 'misaka-empty-pve-baseline', 'script': 'shared/scripts/validate_pve_lab.py'},
                    'pve_version': first['pveversion'], 'tested_profile': 'UEFI, single node, empty, no Ceph/cluster/shared storage'}
        Path(str(target) + '.manifest.yml').write_text(yaml.safe_dump(manifest))
        lab.destroy()
        verify_reuse(root, target, first)
        assert host_state() == before and sha(SOURCE) == source_sha
        (root / 'host-after.json').write_text(json.dumps(host_state(), indent=2))
        (root / 'results.json').write_text(json.dumps({'passed': True, 'artifact': str(target), 'source_unchanged': True,
            'host_unchanged': True, 'baseline_sha256': manifest['sha256'], 'tested_profile': manifest['tested_profile']}, indent=2))
        print('PVE8 基线完成：' + str(target), flush=True)
    except BaseException:
        if hasattr(lab, 'ssh_args'):
            lab.archive_jobs()
        raise


def export_verified_baseline(root):
    """只续接已安装完成的同一 VM；没有重跑安装、没有断电事务恢复。"""
    lab = Lab.attach(root)
    before = json.loads((root / 'host-before.json').read_text())
    lab.install_helpers()
    first = lab.probe('baseline-verified', '8')
    assert first['pveversion'].startswith('pve-manager/8.4.')
    lab.play('role-converge-after-boot', LAB / 'install.yml')
    idem = lab.play('role-idempotence', LAB / 'install.yml')
    assert re.search(r'changed=0\s+unreachable=0\s+failed=0', idem)
    lab.shutdown(clean=True)
    artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700, exist_ok=True)
    target = artifacts / 'pve8.4-uefi.qcow2'
    assert not target.exists(), '不覆盖已有成品'
    with (root / 'export.log').open('w') as log:
        subprocess.run(['qemu-img', 'convert', '-p', '-O', 'qcow2', lab.owned['overlay'], str(target)],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    target.chmod(0o400)
    source_sha = sha(SOURCE)
    original = yaml.safe_load((root / 'source.manifest.yml').read_text())
    assert source_sha == original['sha256']
    manifest = {'schema': 1, 'sha256': sha(target), 'built_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'source': {'image': SOURCE.name, 'sha256': source_sha}, 'os': 'debian', 'version': '12', 'uefi': True,
                'builder': {'name': 'misaka-empty-pve-baseline', 'script': 'shared/scripts/validate_pve_lab.py'},
                'pve_version': first['pveversion'], 'tested_profile': 'UEFI, single node, empty, no Ceph/cluster/shared storage'}
    Path(str(target) + '.manifest.yml').write_text(yaml.safe_dump(manifest))
    lab.destroy()
    verify_reuse(root, target, first)
    assert host_state() == before
    (root / 'host-after.json').write_text(json.dumps(host_state(), indent=2))
    (root / 'results.json').write_text(json.dumps({'passed': True, 'artifact': str(target), 'source_unchanged': True,
        'host_unchanged': True, 'baseline_sha256': manifest['sha256'], 'tested_profile': manifest['tested_profile'],
        'continued_after_readonly_probe_fix': True}, indent=2))
    print('PVE8 基线完成：' + str(target), flush=True)


def verify_reuse(root, image, expected):
    """干净基线在新 overlay/新 seed/NVRAM 中重新启动，保留 PVE 身份和包起点。"""
    child = root / 'reuse'; child.mkdir(mode=0o700)
    before = host_state(); image_sha = sha(image)
    lab = Lab(child, image)
    lab.create(); lab.install_helpers()
    data = lab.probe('reused-baseline', '8')
    assert data['machine_id'] == expected['machine_id']
    assert data['status_sha256'] == expected['status_sha256']
    assert data['boot_id'] != expected['boot_id']
    lab.shutdown(); lab.destroy()
    assert host_state() == before and sha(image) == image_sha
    (child / 'results.json').write_text(json.dumps({'passed': True, 'baseline_unchanged': True,
        'same_machine_id': True, 'same_package_state': True, 'new_boot': True}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['baseline', 'upgrade', 'export-baseline', 'upgrade-prerequisites'])
    parser.add_argument('--root', type=Path)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--until', choices=['preflight', 'sources', 'downloaded', 'installed', 'completed'], default='completed')
    args = parser.parse_args(); os.umask(0o077)
    root = args.root or Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state') / 'misaka-os-base/validation' / (
        'pve-' + args.action + '-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    print('持久证据：' + str(root), flush=True)
    if args.action == 'baseline':
        baseline(root)
    elif args.action == 'export-baseline':
        export_verified_baseline(root)
    elif args.action == 'upgrade-prerequisites':
        from pve_upgrade_experiment import standard_prerequisites
        standard_prerequisites(root)
    else:
        from pve_upgrade_experiment import upgrade
        upgrade(root, args.image, args.until)


if __name__ == '__main__':
    main()

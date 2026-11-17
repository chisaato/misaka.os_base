#!/usr/bin/env python3
"""独立读取 PVE 实验事实，不导入 Debian 升级判断，不改 /etc/pve。"""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess


def read_command(args, optional=False):
    result = subprocess.run(args, text=True, capture_output=True, env=dict(os.environ, LC_ALL='C'))
    if result.returncode and not optional:
        raise RuntimeError(f'{args}: {result.stdout}{result.stderr}')
    return result.stdout.strip()


def installed(name):
    result = read_command(['dpkg-query', '-W', '-f=${db:Status-Status}\t${Version}\t${Depends}', name], optional=True)
    parts = result.split('\t', 2)
    return parts if len(parts) == 3 and parts[0] == 'installed' else None


def kernel_closure(name, found=None):
    found = set() if found is None else found
    if name in found or not installed(name):
        return found
    found.add(name)
    for dependency in re.findall(r'\b(?:proxmox|pve)-kernel-[0-9][a-zA-Z0-9.+-]*', installed(name)[2]):
        kernel_closure(dependency, found)
    return found


def main():
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    pve = read_command(['pveversion'])
    kernel = os.uname().release
    owner = read_command(['dpkg-query', '-S', '/boot/vmlinuz-' + kernel]).split(': ', 1)[0]
    closure = kernel_closure('proxmox-default-kernel')
    meta = installed('proxmox-default-kernel')
    policy = read_command(['apt-cache', '-o', 'Dir::Cache::pkgcache=', 'policy', 'proxmox-default-kernel'])
    candidate = re.search(r'^\s*Candidate:\s*(\S+)', policy, re.M)
    plans = read_command(['apt-get', '-o', 'Debug::NoLocking=1', '-o', 'Dir::Cache::pkgcache=', '-s', 'dist-upgrade'])
    audit = read_command(['dpkg', '--audit'])
    services = {name: read_command(['systemctl', 'is-active', name]) for name in
                ['pve-cluster', 'pveproxy', 'pvedaemon', 'pvestatd']}
    addresses = sorted({row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
    # 只列公共顶层文件名，不读取 priv 或任何密钥内容。
    directory = sorted(path.name for path in Path('/etc/pve').iterdir())
    # Debian 上的空载安装可以尚无 storage.cfg；不为验收手工创建配置。
    storage = Path('/etc/pve/storage.cfg').read_text() if Path('/etc/pve/storage.cfg').is_file() else None
    pve_fs = read_command(['findmnt', '-n', '-o', 'FSTYPE', '/etc/pve'])
    payload = {'os': release.get('VERSION_ID', '').strip('"'), 'pveversion': pve,
               'pve_packages': read_command(['pveversion', '-v']),
               'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
               'machine_id': Path('/etc/machine-id').read_text().strip(), 'kernel': kernel,
               'kernel_owner': owner, 'kernel_metapackage': meta, 'kernel_candidate': candidate.group(1) if candidate else None,
               'kernel_dependency_closure': sorted(closure), 'kernel_from_proxmox_meta': owner in closure and kernel.endswith('-pve'),
               'meta_at_candidate': bool(meta and candidate and meta[1] == candidate.group(1)),
               'services': services, 'etc_pve_entries': directory, 'etc_pve_fstype': pve_fs, 'storage_cfg': storage,
               'has_cluster_config': Path('/etc/pve/corosync.conf').exists(),
               'efi': Path('/sys/firmware/efi').is_dir(), 'efi_variables': read_command(['efibootmgr', '-v']),
               'hostname': socket.gethostname(), 'addresses': addresses, 'audit': audit,
               'pending_plan': [line for line in plans.splitlines() if re.match(r'^(Inst|Conf|Remv) ', line)],
               'status_sha256': hashlib.sha256(Path('/var/lib/dpkg/status').read_bytes()).hexdigest(),
               'guests': json.loads(read_command(['pvesh', 'get', '/cluster/resources', '--type', 'vm', '--output-format', 'json']))}
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

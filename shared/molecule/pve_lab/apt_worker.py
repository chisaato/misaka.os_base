#!/usr/bin/env python3
"""空载 PVE 实验专用的持久 APT worker；不是生产升级角色。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path('/var/lib/misaka/pve-lab')
JOBS = ROOT / 'jobs'
ENV = dict(os.environ, LC_ALL='C', DEBIAN_FRONTEND='noninteractive',
           APT_LISTCHANGES_FRONTEND='none', NEEDRESTART_MODE='l', UCF_FORCE_CONFFOLD='1')
APT = ['apt-get', '-o', 'Dpkg::Options::=--force-confdef', '-o', 'Dpkg::Options::=--force-confold']
COMMANDS = {'update': APT + ['-o', 'APT::Update::Error-Mode=any', 'update'],
            'base': APT + ['-y', 'dist-upgrade'],
            'kernel': APT + ['-y', 'install', 'proxmox-default-kernel'],
            'grub': APT + ['-y', 'install', '--reinstall', 'grub-efi-amd64'],
            'remove-debian': APT + ['-y', 'remove', 'linux-image-amd64', 'linux-image-6.1*'],
            'download9': APT + ['-y', '--download-only', 'dist-upgrade'],
            'upgrade9': APT + ['-y', 'dist-upgrade']}


def status_hash():
    return hashlib.sha256(Path('/var/lib/dpkg/status').read_bytes()).hexdigest()


def checker_ok(text, rc):
    text = re.sub(r'\x1b\[[0-9;]*m', '', text)
    return (rc == 0 and bool(re.search(r'^FAILURES:\s*0\s*$', text, re.M))
            and bool(re.search(r'^TOTAL:\s*[1-9]\d*\s*$', text, re.M))
            and not re.search(r'^FAIL:', text, re.M)
            and not re.search(r'^FAILURES:\s*[1-9]\d*\s*$', text, re.M))


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temp.chmod(0o600)
    temp.replace(path)


def healthy():
    # APT/dpkg 的 POSIX 锁即使由其他名称的进程持有，也只表示忙，不是损坏。
    locked_inodes = set()
    for name in ['/var/lib/dpkg/lock', '/var/lib/dpkg/lock-frontend',
                 '/var/lib/apt/lists/lock', '/var/cache/apt/archives/lock']:
        path = Path(name)
        if path.exists():
            info = path.stat()
            locked_inodes.add((os.major(info.st_dev), os.minor(info.st_dev), info.st_ino))
    for line in Path('/proc/locks').read_text().splitlines():
        for item in line.split():
            if re.fullmatch(r'[0-9a-fA-F]+:[0-9a-fA-F]+:\d+', item):
                major, minor, inode = item.split(':')
                if (int(major, 16), int(minor, 16), int(inode)) in locked_inodes:
                    raise RuntimeError('APT/dpkg 锁正被占用，只是忙，不自动修复或重复启动')
    for proc in Path('/proc').glob('[0-9]*/comm'):
        try:
            if proc.read_text().strip() in {'apt', 'apt-get', 'dpkg', 'unattended-upgr'}:
                raise RuntimeError('APT/dpkg 正忙，不是数据库损坏；不重复启动')
        except FileNotFoundError:
            pass
    audit = subprocess.run(['dpkg', '--audit'], capture_output=True, text=True)
    if audit.returncode or (audit.stdout + audit.stderr).strip():
        raise RuntimeError('dpkg audit 异常，需人工处理，不自动修复：' + audit.stdout + audit.stderr)


def run_worker(stage, job_id):
    before = status_hash()
    result = JOBS / (job_id + '.json')
    try:
        healthy()
        if stage == 'remove-debian' and not os.uname().release.endswith('-pve'):
            raise RuntimeError('必须先启动 Proxmox 内核，才允许移除 Debian 内核')
        if stage == 'upgrade9':
            approval = json.loads((ROOT / 'approval.json').read_text())
            if not approval['passed'] or approval['status_sha256'] != before:
                raise RuntimeError('pve8to9 预检未通过或包状态已变化，拒绝升级')
            plan = subprocess.run(APT + ['-s', 'dist-upgrade'], env=ENV, text=True, capture_output=True, check=True)
            if re.search(r'^Remv proxmox-ve\b', plan.stdout, re.M):
                raise RuntimeError('升级计划将移除 proxmox-ve，拒绝执行；按官方文档检查仓库')
        log = JOBS / (job_id + '.log')
        with log.open('w') as output:
            output.write(json.dumps(COMMANDS[stage]) + '\n'); output.flush()
            attempts = 3 if stage in {'update', 'download9'} else 1
            for attempt in range(attempts):
                completed = subprocess.run(COMMANDS[stage], env=ENV, stdout=output, stderr=subprocess.STDOUT)
                if completed.returncode == 0:
                    break
                if attempt + 1 < attempts:
                    time.sleep(10)
            if completed.returncode:
                raise RuntimeError(f'APT 返回 {completed.returncode}；见 {log}，不自动修复或重试安装')
        after = status_hash()
        if stage in {'update', 'download9'} and before != after:
            raise RuntimeError('更新索引/下载阶段发生包状态变化，停止')
        audit = subprocess.run(['dpkg', '--audit'], text=True, capture_output=True)
        if audit.returncode or (audit.stdout + audit.stderr).strip():
            raise RuntimeError('事务结束后 dpkg audit 异常，需人工处理')
        write(result, {'ok': True, 'stage': stage, 'before_status': before, 'after_status': after,
                       'boot_id_at_end': Path('/proc/sys/kernel/random/boot_id').read_text().strip()})
    except Exception as exc:
        write(result, {'ok': False, 'stage': stage, 'error': str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'worker', 'approve'])
    parser.add_argument('--stage', choices=COMMANDS)
    parser.add_argument('--job-id')
    parser.add_argument('--report')
    parser.add_argument('--rc', type=int, default=0)
    args = parser.parse_args(); os.umask(0o077)
    if args.action == 'approve':
        report = Path(args.report).read_text()
        passed = checker_ok(report, args.rc)
        write(ROOT / 'approval.json', {'passed': passed, 'status_sha256': status_hash(),
                                      'report_sha256': hashlib.sha256(report.encode()).hexdigest()})
        if not passed:
            raise RuntimeError('pve8to9 --full 未通过，拒绝切源/升级')
        print(json.dumps({'passed': True})); return
    if args.action == 'worker':
        run_worker(args.stage, args.job_id); return
    healthy()
    if args.stage == 'upgrade9':
        approval = json.loads((ROOT / 'approval.json').read_text())
        if not approval['passed'] or approval['status_sha256'] != status_hash():
            raise RuntimeError('pve8to9 闸门阻断，未启动 APT')
    if (JOBS / 'active.json').exists():
        old = json.loads((JOBS / 'active.json').read_text())
        result = JOBS / (old['id'] + '.json')
        if not result.exists() or not json.loads(result.read_text())['ok']:
            raise RuntimeError('前一 worker 仍活跃、失败或无结果，禁止重复启动；先人工检查')
    job_id = uuid.uuid4().hex
    unit = 'misaka-pve-lab-' + args.stage + '-' + job_id
    write(JOBS / 'active.json', {'id': job_id, 'stage': args.stage, 'unit': unit})
    subprocess.run(['systemd-run', '--quiet', '--no-block', '--unit=' + unit,
                    '--property=Type=oneshot', '--property=TimeoutStartSec=infinity',
                    '/usr/bin/python3', '/usr/local/lib/misaka-pve-lab/apt_worker.py', 'worker',
                    '--stage', args.stage, '--job-id', job_id], check=True)
    print(json.dumps({'id': job_id, 'unit': unit}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr); sys.exit(2)

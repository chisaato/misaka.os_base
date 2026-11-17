#!/usr/bin/env python3
"""Debian 在线升级：只读事实、APT 安装闸门、持久 systemd worker。

不接管断电半事务，不自动修复 dpkg，不实现双 Play 并发协议。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path('/var/lib/misaka/dist-upgrade')
MARKER = ROOT / 'debian.json'
JOBS = ROOT / 'debian-jobs'
ACTIVE = JOBS / 'active.json'
BIN = '/usr/local/lib/misaka-dist-upgrade/debian_upgrade.py'
STAGES = ('preflight', 'prepared', 'downloaded', 'minimal_upgraded',
          'full_upgraded', 'reboot_requested', 'verified', 'completed')
RANK = {stage: index for index, stage in enumerate(STAGES)}
ENV = dict(os.environ, LC_ALL='C', DEBIAN_FRONTEND='noninteractive',
           APT_LISTCHANGES_FRONTEND='none', NEEDRESTART_MODE='l', UCF_FORCE_CONFFOLD='1')
CACHE_OPTIONS = ['-o', 'Dir::Cache::pkgcache=', '-o', 'Dir::Cache::srcpkgcache=']
APT = ['apt-get'] + CACHE_OPTIONS + ['-o', 'Dpkg::Options::=--force-confdef',
       '-o', 'Dpkg::Options::=--force-confold']


def run(argv, timeout=120):
    return subprocess.run(argv, text=True, capture_output=True, env=ENV,
                          check=False, timeout=timeout)


def checked(argv):
    result = run(argv)
    if result.returncode:
        raise RuntimeError(f'{argv}: {result.stderr or result.stdout}')
    return result.stdout


def read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError(f'读取 {path} 失败，需人工处理，不自动覆盖：{exc}') from exc


def digest(data):
    return hashlib.sha256(data).hexdigest()


def snapshot():
    """下载前后核对 dpkg 状态、包维护文件及 dpkg 日志，不能只信退出码。"""
    parts = []
    for base in (Path('/var/lib/dpkg/status'), Path('/var/lib/dpkg/info'),
                 Path('/var/lib/dpkg/updates'), Path('/var/log/dpkg.log')):
        files = sorted(base.rglob('*')) if base.is_dir() else [base]
        for path in files:
            if path.is_file():
                parts.append(str(path).encode() + b'\0' + path.read_bytes())
    return digest(b'\0'.join(parts))


def archive_fingerprint():
    """缓存被人工 clean 后下载事实降级；流式散列避免把全部 deb 装进内存。"""
    value = hashlib.sha256()
    for path in sorted(Path('/var/cache/apt/archives').glob('*.deb')):
        value.update(path.name.encode() + b'\0')
        with path.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                value.update(chunk)
    return value.hexdigest()


def sources():
    suites = []
    paths = [Path('/etc/apt/sources.list')]
    paths += sorted(Path('/etc/apt/sources.list.d').glob('*.list'))
    paths += sorted(Path('/etc/apt/sources.list.d').glob('*.sources'))
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text()
        if path.suffix == '.sources':
            for stanza in re.split(r'\n\s*\n', text):
                fields = {}
                key = None
                for line in stanza.splitlines():
                    if not line.strip() or line.lstrip().startswith('#'):
                        continue
                    if line[0].isspace() and key:
                        fields[key] += ' ' + line.strip()
                    elif ':' in line:
                        key, value = line.split(':', 1)
                        fields[key.lower()] = value.strip()
                        key = key.lower()
                if fields.get('enabled', 'yes').lower() != 'no':
                    suites.extend(fields.get('suites', '').split())
        else:
            for line in text.splitlines():
                match = re.match(r'^\s*deb(?:-src)?\s+(?:\[[^]]*\]\s+)?\S+\s+(\S+)', line)
                if match:
                    suites.append(match.group(1))
    if suites and all(s in {'trixie', 'trixie-updates', 'trixie-security'} for s in suites):
        return 'target', suites
    # Packer 基线启用 bookworm-backports；切源时不把 backports 迁移到目标。
    if suites and all(s in {'bookworm', 'bookworm-updates', 'bookworm-security', 'bookworm-backports'} for s in suites):
        return 'source', suites
    return 'conflict', suites


def source_fingerprint():
    paths = [Path('/etc/apt/sources.list')]
    paths += sorted(Path('/etc/apt/sources.list.d').glob('*.list'))
    paths += sorted(Path('/etc/apt/sources.list.d').glob('*.sources'))
    return digest(b''.join(str(path).encode() + path.read_bytes() for path in paths if path.is_file()))


def target_indexes(suites):
    """空索引时模拟计划也为空，绝不能把它当成已升级。"""
    codenames = set()
    root = Path('/var/lib/apt/lists')
    for path in list(root.glob('*_InRelease')) + list(root.glob('*_Release')):
        match = re.search(r'^Codename:\s*(\S+)\s*$', path.read_text(), re.MULTILINE)
        if match:
            codenames.add(match.group(1))
    packages = any(path.is_file() for path in root.glob('*_Packages*'))
    return bool(suites) and set(suites).issubset(codenames) and packages


def package_busy():
    """只读 /proc/locks；已有锁表示忙，不是数据库损坏。"""
    keys = set()
    for name in ('/var/lib/dpkg/lock', '/var/lib/dpkg/lock-frontend',
                 '/var/cache/apt/archives/lock', '/var/lib/apt/lists/lock'):
        path = Path(name)
        if path.exists():
            stat = path.stat()
            keys.add((os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino))
    for line in Path('/proc/locks').read_text().splitlines():
        for word in line.split():
            if re.fullmatch(r'[0-9a-fA-F]+:[0-9a-fA-F]+:\d+', word):
                a, b, inode = word.split(':')
                if (int(a, 16), int(b, 16), int(inode)) in keys:
                    return True
    # 捕捉已经启动但尚未获得 APT 锁的程序。
    for path in Path('/proc').glob('[0-9]*/comm'):
        try:
            if path.read_text().strip() in {'apt', 'apt-get', 'dpkg', 'unattended-upgr'}:
                return True
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    return False


def job_state():
    job = read_json(ACTIVE)
    if not job:
        return None
    result = read_json(JOBS / (job['id'] + '.json'))
    state = run(['systemctl', 'show', job['unit'], '--property=ActiveState', '--value']).stdout.strip()
    return dict(job, result=result, live=state in {'active', 'activating', 'reloading'})


def plan(command):
    text = checked(APT + ['-o', 'Debug::NoLocking=1', '-s', command])
    lines = [line for line in text.splitlines() if re.match(r'^(Inst|Conf|Remv) ', line)]
    return {'changes': lines, 'sha256': digest('\n'.join(lines).encode())}


def target_candidate(policy, candidate):
    """candidate 的来源必须是 trixie suite，不能仅凭版本或已装 metapackage。"""
    selected = False
    for line in policy.splitlines():
        header = re.match(r'^\s*(?:\*\*\*\s+)?(\S+)\s+\d+\s*$', line)
        if header:
            selected = header.group(1) == candidate
        elif selected and re.search(r'\s(?:trixie|trixie-updates|trixie-security)/main\s', line):
            return True
    return False


def kernel_evidence():
    """从实际 metapackage 依赖及 candidate 推导内核，不硬编码 6.12。"""
    meta = run(['dpkg-query', '-W', '-f=${db:Status-Status}\t${Version}\t${Depends}', 'linux-image-amd64'])
    if meta.returncode or not meta.stdout.startswith('installed\t'):
        return {'ready': False, 'reason': 'linux-image-amd64_not_installed'}
    _, installed, dependencies = meta.stdout.split('\t', 2)
    policy = checked(['apt-cache'] + CACHE_OPTIONS + ['policy', 'linux-image-amd64'])
    match = re.search(r'^\s*Candidate:\s*(\S+)', policy, re.MULTILINE)
    packages = re.findall(r'\blinux-image-(\d[^ ,(]+)', dependencies)
    if not match or not packages or installed != match.group(1):
        return {'ready': False, 'reason': 'kernel_metapackage_not_candidate', 'installed': installed}
    kernels = []
    for suffix in packages:
        package = 'linux-image-' + suffix
        status = run(['dpkg-query', '-W', '-f=${db:Status-Status}', package])
        if status.returncode == 0 and status.stdout == 'installed' and Path('/boot/vmlinuz-' + suffix).is_file():
            kernels.append(suffix)
    running = os.uname().release
    # 同时核对目标 APT 索引确实提供此 metapackage 版本。
    show = checked(['apt-cache'] + CACHE_OPTIONS + ['show', 'linux-image-amd64=' + installed])
    target_available = (bool(re.search(r'^Version: ' + re.escape(installed) + '$', show, re.MULTILINE))
                        and target_candidate(policy, installed))
    return {'ready': bool(kernels) and target_available, 'installed': installed,
            'candidate': match.group(1), 'installed_kernels': kernels,
            'running': running, 'running_target': running in kernels}


def derive(observed, marker):
    """事实优先，下载回执必须仍匹配当前 dpkg 与 APT 计划。"""
    if observed.get('busy'):
        return 'busy'
    if observed.get('abnormal'):
        return 'needs_human'
    if observed['sources'] == 'conflict':
        return 'conflict'
    if observed['sources'] != 'target':
        return 'preflight'
    if not observed.get('target_indexes'):
        return 'preflight'
    if (observed['os'] == '13' and not observed['full_plan']['changes']
            and observed['kernel'].get('ready')):
        baseline = (marker or {}).get('evidence', {}).get('reboot_boot_id') or (marker or {}).get('evidence', {}).get('baseline_boot_id')
        reboot_proven = bool(baseline and baseline != observed['boot_id'])
        if reboot_proven and observed['kernel'].get('running_target') and not observed['reboot_required']:
            return 'completed' if (marker or {}).get('stage') == 'completed' else 'verified'
        return 'full_upgraded'
    # 没有成功 update 的对应回执时先准备；失败后留下的空计划不是最小升级事实。
    if (marker or {}).get('evidence', {}).get('prepared_config') != observed['source_config']:
        return 'preflight'
    receipt = (marker or {}).get('evidence', {}).get('download', {})
    downloaded = (receipt.get('snapshot') == observed['snapshot']
                  and receipt.get('plan') == observed['full_plan']['sha256']
                  and receipt.get('sources') == observed['source_config']
                  and receipt.get('archives') == observed['archives']
                  and receipt.get('lists') == observed['lists'])
    evidence = (marker or {}).get('evidence', {})
    changed_since_claim = bool(evidence.get('baseline_snapshot') and evidence['baseline_snapshot'] != observed['snapshot'])
    if not observed['minimal_plan']['changes'] and (
            downloaded or evidence.get('minimal_snapshot') == observed['snapshot'] or changed_since_claim):
        return 'minimal_upgraded'
    if downloaded:
        return 'downloaded'
    if ((marker or {}).get('evidence', {}).get('prepared_sources') == observed['suites']
            and (marker or {}).get('evidence', {}).get('prepared_config') == observed['source_config']):
        return 'prepared'
    return 'preflight'


def probe():
    marker = read_json(MARKER)
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    machine = Path('/etc/machine-id').read_text().strip()
    if not re.fullmatch('[0-9a-fA-F]{32}', machine):
        raise RuntimeError('machine-id 非法')
    source, suites = sources()
    observed = {'os': release.get('VERSION_ID', '').strip('"'), 'sources': source, 'source_config': source_fingerprint(),
                'target_indexes': target_indexes(suites),
                'pve_unsupported': Path('/usr/bin/pveversion').exists(),
                'suites': suites, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                'machine': digest(machine.encode())[:16], 'job': job_state(),
                'reboot_required': Path('/run/reboot-required').exists()}
    job = observed['job']
    observed['busy'] = bool(job and job['live']) or package_busy()
    if observed['busy']:
        observed['phase'] = 'busy'
        return observed
    audit = run(['dpkg', '--audit'])
    statuses = checked(['dpkg-query', '-W', '-f=${db:Status-Abbrev} ${binary:Package}\n'])
    partial = [line for line in statuses.splitlines() if len(line) >= 3 and
               (line[1] not in 'inc' or line[2] != ' ')]
    observed['audit'] = audit.stdout + audit.stderr
    observed['held_packages'] = checked(['apt-mark'] + CACHE_OPTIONS + ['showhold']).splitlines()
    observed['abnormal'] = bool(audit.returncode or observed['audit'].strip() or partial or observed['held_packages']
                                or (job and (not job['result'] or not job['result']['ok'])))
    observed['partial_packages'] = partial
    observed['snapshot'] = snapshot()
    observed['archives'] = archive_fingerprint()
    observed['lists'] = digest(b''.join(str(p).encode() + p.read_bytes()
                                       for p in sorted(Path('/var/lib/apt/lists').glob('*'))
                                       if p.is_file() and p.name != 'lock'))
    if source == 'target' and not observed['abnormal']:
        observed['minimal_plan'] = plan('upgrade')
        observed['full_plan'] = plan('dist-upgrade')
        observed['kernel'] = kernel_evidence()
    observed['phase'] = derive(observed, marker)
    if observed['pve_unsupported'] or observed['os'] not in {'12', '13'} or (marker and (
            marker.get('family') != 'debian' or marker.get('target', {}).get('release') != '13'
            or marker.get('machine', {}).get('id_sha256_16') != observed['machine'])):
        observed['phase'] = 'conflict'
    return observed


def atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    os.chmod(temp, 0o600)
    temp.replace(path)


def record(stage, evidence=None, note=''):
    # 复用发行版中立的 seq 校验与原子写；不调用 Fedora decide/离线阶段。
    from dist_upgrade_state import marker_write, new_operation_id
    previous = read_json(MARKER)
    marker = dict(previous or {})
    seq = int(marker.get('seq', 0))
    marker.update(schema=1, family='debian', seq=seq + 1, stage=stage)
    marker.setdefault('source', {'release': (evidence or {}).get('baseline_os', '12')})
    marker.setdefault('operation_id', new_operation_id('debian', marker['source']['release'], '13'))
    marker.setdefault('target', {'release': '13'})
    marker.setdefault('machine', {'id_sha256_16': digest(Path('/etc/machine-id').read_text().strip().encode())[:16]})
    marker['evidence'] = dict(marker.get('evidence', {}), **(evidence or {}))
    if (evidence or {}).get('tested_profile'):
        marker['tested_profile'] = evidence['tested_profile']
    marker['history'] = marker.get('history', []) + [{'seq': seq + 1, 'stage': stage, 'note': note,
                                                   'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}]
    marker_write(MARKER, marker, seq)
    return marker


def ensure_healthy(observed):
    if observed['phase'] in {'needs_human', 'conflict', 'busy'}:
        raise RuntimeError(json.dumps(observed, ensure_ascii=False))


def choose(observed, until):
    job = observed.get('job')
    if job and job['live']:
        # 仅观察已存在的 worker，不以新请求重启事务。
        return job['stage']
    ensure_healthy(observed)
    phase = observed['phase']
    if RANK[phase] >= RANK[until]:
        return 'pause'
    if phase == 'preflight':
        return 'prepare'
    if phase == 'prepared':
        return 'download'
    if phase == 'downloaded':
        return 'minimal'
    if phase == 'minimal_upgraded':
        return 'full'
    if phase == 'full_upgraded':
        return 'reboot' if RANK[until] >= RANK['reboot_requested'] else 'pause'
    if phase == 'verified':
        return 'finish'
    return 'pause'


def claim(profile):
    observed = probe()
    previous = read_json(MARKER)
    if observed['phase'] == 'busy' and observed.get('job') and observed['job']['live'] and previous:
        return {'changed': False, 'phase': 'busy'}
    ensure_healthy(observed)
    if not previous:
        if shutil.disk_usage('/').free < 5 * 1024**3:
            raise RuntimeError('根分区可用空间不足 5 GiB')
        record(observed['phase'], {'baseline_os': observed['os'], 'baseline_boot_id': observed['boot_id'], 'baseline_snapshot': observed['snapshot'],
                             'tested_profile': profile}, 'claim; target-without-marker does not prove prior reboot')
        return {'changed': True, 'phase': observed['phase']}
    # completed 的事实若倒退，不能继续相信旧标记。
    if RANK.get(previous.get('stage'), -1) > RANK.get(observed['phase'], -1):
        record(observed['phase'], note='demoted from real facts')
        return {'changed': True, 'phase': observed['phase']}
    if RANK.get(previous.get('stage'), -1) < RANK.get(observed['phase'], -1):
        record(observed['phase'], note='adopted from joint real facts')
        return {'changed': True, 'phase': observed['phase']}
    return {'changed': False, 'phase': observed['phase']}


def start(stage, retries, delay):
    observed = probe()
    current = observed.get('job')
    if current and current['live']:
        if current['stage'] != stage:
            raise RuntimeError('已有其他阶段仍活跃，拒绝启动')
        return {'changed': False, 'job': current}
    ensure_healthy(observed)
    # 再次检查阶段，而不是信任控制端的过时 next。
    if stage != 'prepare' and choose(observed, 'completed') != stage:
        raise RuntimeError('阶段事实已变化，重新运行角色；拒绝过时事务')
    if stage == 'prepare' and observed['sources'] != 'target':
        raise RuntimeError('目标源没有完整切换')
    job_id = uuid.uuid4().hex
    job = {'id': job_id, 'stage': stage, 'unit': 'misaka-debian-' + stage + '-' + job_id,
           'boot_id': observed['boot_id']}
    atomic(ACTIVE, job)
    command = ['systemd-run', '--quiet', '--no-block', '--unit=' + job['unit'],
               '--property=Type=oneshot', '--property=TimeoutStartSec=infinity',
               '/usr/bin/python3', BIN, 'worker', '--stage', stage,
               '--job-id', job_id, '--retries', str(retries), '--delay', str(delay)]
    result = run(command)
    if result.returncode:
        atomic(JOBS / (job_id + '.json'), {'ok': False, 'error': result.stderr})
        raise RuntimeError(result.stderr)
    return {'changed': True, 'job': job}


def worker(stage, job_id, retries, delay):
    # 在线升级可能替换系统 Python；所有 marker 依赖须在 APT 启动前驻留内存。
    __import__('dist_upgrade_state')
    log = JOBS / (job_id + '.log')
    before = snapshot()
    commands = {
        'prepare': APT + ['-o', 'APT::Update::Error-Mode=any', 'update'],
        'download': APT + ['-y', '--download-only', 'dist-upgrade'],
        # apt-get upgrade 已默认禁止安装新包；不是 apt upgrade --without-new-pkgs。
        'minimal': APT + ['-y', '--no-remove', 'upgrade'],
        'full': APT + ['-y', 'dist-upgrade'],
    }
    result_path = JOBS / (job_id + '.json')
    try:
        if package_busy():
            raise RuntimeError('APT/dpkg 已忙，未启动新事务（不是数据库损坏）')
        if stage in {'minimal', 'full'}:
            meta = run(['dpkg-query', '-W', '-f=${db:Status-Status}', 'linux-image-amd64'])
            if meta.returncode or meta.stdout != 'installed':
                raise RuntimeError('安装前拒绝：本期仅验证标准 linux-image-amd64，不接管自定义/其他架构内核')
        if stage == 'minimal':
            minimal = plan('upgrade')
            if any(line.startswith('Remv ') or (line.startswith('Inst ') and ' [' not in line)
                   for line in minimal['changes']):
                raise RuntimeError('最小升级计划包含新增/移除包，拒绝执行')
        with log.open('w') as stream:
            os.chmod(log, 0o600)
            attempts = retries if stage in {'prepare', 'download'} else 1
            for attempt in range(attempts):
                stream.write(json.dumps(commands[stage]) + '\n')
                stream.flush()
                result = subprocess.run(commands[stage], stdout=stream, stderr=subprocess.STDOUT,
                                        env=ENV, check=False)
                if result.returncode == 0:
                    break
                if attempt + 1 < attempts:
                    time.sleep(delay)
            if result.returncode:
                raise RuntimeError(f'APT 返回 {result.returncode}，见 {log}；需人工处理，不自动修复/重试安装')
        after = snapshot()
        if stage in {'prepare', 'download'} and before != after:
            raise RuntimeError('准备/下载阶段 dpkg 状态或维护文件/日志变化，拒绝声称未安装')
        audit = run(['dpkg', '--audit'])
        if audit.returncode or (audit.stdout + audit.stderr).strip():
            raise RuntimeError('dpkg audit 异常，需人工处理：' + audit.stdout + audit.stderr)
        if stage == 'prepare':
            if not target_indexes(sources()[1]):
                raise RuntimeError('update 后目标 Release/Packages 索引不完整，不把空计划当成升级事实')
            record('prepared', {'prepared_sources': sources()[1], 'prepared_config': source_fingerprint(), 'prepare_snapshot': after})
        elif stage == 'download':
            full_plan = plan('dist-upgrade')
            lists = digest(b''.join(str(p).encode() + p.read_bytes()
                                    for p in sorted(Path('/var/lib/apt/lists').glob('*'))
                                    if p.is_file() and p.name != 'lock'))
            record('downloaded', {'download': {'snapshot': after, 'before_snapshot': before,
                                               'plan': full_plan['sha256'], 'lists': lists,
                                               'sources': source_fingerprint(),
                                               'archives': archive_fingerprint(),
                                               'command': commands[stage]}})
        elif stage == 'minimal':
            if plan('upgrade')['changes']:
                raise RuntimeError('最小升级结束后仍有待处理最小事务，停止自动推进')
            record('minimal_upgraded', {'minimal_snapshot': after}, 'full plan must be recalculated after minimal')
        elif stage == 'full':
            os_target = bool(re.search(r'^VERSION_ID="?13"?$', Path('/etc/os-release').read_text(), re.MULTILINE))
            if not os_target or plan('dist-upgrade')['changes'] or not kernel_evidence()['ready']:
                raise RuntimeError('完整升级命令返回后目标 OS/APT/内核包联合事实不足，停止自动推进')
            record('full_upgraded', {'full_snapshot': after,
                                     'reboot_boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()})
        atomic(result_path, {'ok': True, 'stage': stage, 'before_snapshot': before, 'after_snapshot': after})
    except Exception as exc:
        atomic(result_path, {'ok': False, 'stage': stage, 'error': str(exc)})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['probe', 'claim', 'next', 'start', 'wait', 'worker', 'reboot-intent', 'finish'])
    parser.add_argument('--until', choices=STAGES, default='downloaded')
    parser.add_argument('--stage', choices=['prepare', 'download', 'minimal', 'full'])
    parser.add_argument('--profile', default='')
    parser.add_argument('--job-id')
    parser.add_argument('--retries', type=int, default=3)
    parser.add_argument('--delay', type=int, default=10)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == 'probe':
            output = probe()
        elif args.command == 'claim':
            output = claim(args.profile)
        elif args.command == 'next':
            observed = probe()
            output = {'phase': observed['phase'], 'step': choose(observed, args.until), 'until': args.until}
        elif args.command == 'start':
            output = start(args.stage, max(1, args.retries), args.delay)
        elif args.command == 'wait':
            job = job_state()
            if not job or job['stage'] != args.stage:
                raise RuntimeError('没有对应持久 worker')
            if job['live']:
                print(json.dumps({'running': True, 'job': job}))
                return 75
            if not job['result'] or not job['result']['ok']:
                raise RuntimeError(json.dumps(job, ensure_ascii=False))
            output = job
        elif args.command == 'worker':
            worker(args.stage, args.job_id, max(1, args.retries), args.delay)
            output = {'ok': True}
        elif args.command == 'reboot-intent':
            observed = probe()
            ensure_healthy(observed)
            if observed['phase'] != 'full_upgraded':
                raise RuntimeError('升级未完整或已不需要重启，拒绝重启')
            record('reboot_requested', {'reboot_boot_id': observed['boot_id']}, 'explicit reboot boundary')
            output = {'changed': True}
        elif args.command == 'finish':
            observed = probe()
            ensure_healthy(observed)
            if observed['phase'] not in {'verified', 'completed'}:
                raise RuntimeError('联合事实不足，不能证明完成：' + json.dumps(observed))
            changed = observed['phase'] != 'completed'
            if changed:
                record('completed', {'verification': observed}, 'joint facts; no autoremove')
            output = {'changed': changed}
        print(json.dumps(output, ensure_ascii=False))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())

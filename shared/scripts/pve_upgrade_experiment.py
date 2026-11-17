#!/usr/bin/env python3
"""票 07 空载实验，显式阶段边界；不导出为生产升级角色。"""
import datetime
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import time

import yaml

from validate_pve_lab import Lab, LAB, REPO, VIRSH, host_state, sha, verify_reuse


def gate_ok(text, rc):
    spec = importlib.util.spec_from_file_location('pve_lab_worker', LAB / 'apt_worker.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module.checker_ok(text, rc)


def checklist(lab, label, require=True):
    result = lab.ssh('sudo pve8to9 --full', check=False)
    name = label
    attempt = 1
    while (lab.root / (name + '.log')).exists():
        attempt += 1; name = label + '-attempt' + str(attempt)
    (lab.root / (name + '.log')).write_text(result.stdout + result.stderr)
    (lab.root / (name + '-rc.json')).write_text(json.dumps({'returncode': result.returncode,
        'passed': gate_ok(result.stdout, result.returncode)}, indent=2))
    if require and not gate_ok(result.stdout, result.returncode):
        raise RuntimeError(f'{label}: pve8to9 FAIL 或检查不完整，真正阻断；先按官方提示处理，不能绕过')
    return result


def restart_clean(lab):
    assert subprocess.run(VIRSH + ['dominfo', lab.instance['domain']], capture_output=True).returncode != 0
    xml = Path(lab.owned['overlay']).parent / 'domain.xml'
    assert xml.exists() and lab.owned['owner'] == 'misaka-molecule-libvirt'
    subprocess.run(VIRSH + ['create', str(xml)], check=True)
    for _ in range(180):
        lab.refresh_lease()
        result = lab.ssh('true', check=False)
        if result.returncode == 0:
            return
        time.sleep(3)
    raise RuntimeError('干净检查点重启后 SSH 未恢复')


def standard_prerequisites(root):
    """仅响应本次真实 checker 的两个警告，不拆服务、不改 /etc/pve。"""
    report = (root / 'preflight-initial.log').read_text()
    assert '70-persistent-net.rules' in report and 'Removable bootloader found' in report
    lab = Lab.attach(root)
    lab.install_helpers()
    lab.probe('before-standard-prerequisites', '8')
    lab.play('standard-prerequisites', LAB / 'prerequisites.yml')
    lab.apt('grub')
    update = lab.ssh('sudo pveupdate', check=False)
    (root / 'pve-update-cache.log').write_text(update.stdout + update.stderr)
    assert update.returncode == 0, '标准 PVE 更新缓存命令失败，需查看原始日志'
    checklist(lab, 'preflight-after-standard-prerequisites')
    lab.probe('after-standard-prerequisites', '8')


def upgrade(root, image, until='completed'):
    assert image and image.is_file(), '必须提供已验收的 PVE8 基线'
    manifest = yaml.safe_load(Path(str(image) + '.manifest.yml').read_text())
    original_sha = sha(image)
    assert original_sha == manifest['sha256']
    state_path = root / 'phases.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'completed': []}
    def done(name):
        state['completed'].append(name); state_path.write_text(json.dumps(state, indent=2))
        print('完成阶段：' + name, flush=True)

    if (root / 'control-directory.txt').exists():
        lab = Lab.attach(root)
        before = json.loads((root / 'host-before.json').read_text())
    else:
        before = host_state(); (root / 'host-before.json').write_text(json.dumps(before, indent=2))
        lab = Lab(root, image); lab.create(); lab.install_helpers()
    (root / 'baseline.manifest.yml').write_text(Path(str(image) + '.manifest.yml').read_text())
    try:
        if not (root / 'upgrade9-job.json').exists():
            lab.install_helpers()
        checkpoint = root / 'artifacts/pve8-checkpoint.qcow2'
        if 'checkpoint' not in state['completed'] and checkpoint.exists():
            # 导出后的只读核验中断可续接，但必须重新核对成品和真实 guest，不靠阶段文件跳闸门。
            metadata = yaml.safe_load(Path(str(checkpoint) + '.manifest.yml').read_text())
            assert sha(checkpoint) == metadata['sha256']
            assert metadata['source']['sha256'] == original_sha
            start = json.loads((root / 'starting-pve8.json').read_text())
            restored = lab.probe('after-clean-checkpoint-restart', '8')
            assert restored['status_sha256'] == start['status_sha256'] and restored['machine_id'] == start['machine_id']
            assert restored['boot_id'] != start['boot_id']
            result = checklist(lab, 'preflight-before-sources')
            lab.ssh('sudo tee /var/lib/misaka/pve-lab/preflight.log >/dev/null', stdin=result.stdout)
            lab.ssh('sudo python3 /usr/local/lib/misaka-pve-lab/apt_worker.py approve --report /var/lib/misaka/pve-lab/preflight.log')
            done('checkpoint')
        if 'checkpoint' not in state['completed']:
            start = lab.probe('starting-pve8', '8')
            assert start['pveversion'].startswith('pve-manager/8.4.')
            result = checklist(lab, 'preflight-initial')
            # 在同一真实 VM 的真实推进入口注入 FAIL 报告，证明没有启动 APT。
            fixture = re.sub(r'^FAILURES:\s*0\s*$', 'FAILURES: 1', result.stdout, flags=re.M) + '\nFAIL: validation gate fixture\n'
            lab.ssh('sudo tee /var/lib/misaka/pve-lab/fail-fixture.log >/dev/null', stdin=fixture)
            refused = lab.ssh('sudo python3 /usr/local/lib/misaka-pve-lab/apt_worker.py approve --report /var/lib/misaka/pve-lab/fail-fixture.log', check=False)
            assert refused.returncode != 0
            failed_start = lab.ssh('sudo python3 /usr/local/lib/misaka-pve-lab/apt_worker.py start --stage upgrade9', check=False)
            (root / 'fail-gate-refusal.log').write_text(refused.stdout + refused.stderr + failed_start.stdout + failed_start.stderr)
            assert failed_start.returncode != 0
            after_gate = lab.probe('after-fail-gate', '8')
            assert after_gate['status_sha256'] == start['status_sha256'] and after_gate['boot_id'] == start['boot_id']
            lab.ssh('sudo tee /var/lib/misaka/pve-lab/preflight.log >/dev/null', stdin=result.stdout)
            lab.ssh('sudo python3 /usr/local/lib/misaka-pve-lab/apt_worker.py approve --report /var/lib/misaka/pve-lab/preflight.log')
            done('preflight')
            if until == 'preflight': return
            # 清理注入凭据缓存后在干净关机点导出，不在 APT 事务中断电。
            lab.shutdown(clean=True)
            artifacts = root / 'artifacts'; artifacts.mkdir(mode=0o700)
            checkpoint = artifacts / 'pve8-checkpoint.qcow2'
            with (root / 'checkpoint-export.log').open('w') as log:
                subprocess.run(['qemu-img', 'convert', '-p', '-O', 'qcow2', lab.owned['overlay'], str(checkpoint)],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
            checkpoint.chmod(0o400)
            metadata = dict(manifest, sha256=sha(checkpoint), built_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            source={'baseline': image.name, 'sha256': original_sha},
                            builder={'name': 'misaka-pve8-clean-checkpoint'})
            Path(str(checkpoint) + '.manifest.yml').write_text(yaml.safe_dump(metadata))
            restart_clean(lab)
            restored = lab.probe('after-clean-checkpoint-restart', '8')
            assert restored['status_sha256'] == start['status_sha256'] and restored['machine_id'] == start['machine_id']
            result = checklist(lab, 'preflight-before-sources')
            lab.ssh('sudo tee /var/lib/misaka/pve-lab/preflight.log >/dev/null', stdin=result.stdout)
            lab.ssh('sudo python3 /usr/local/lib/misaka-pve-lab/apt_worker.py approve --report /var/lib/misaka/pve-lab/preflight.log')
            done('checkpoint')
        else:
            start = json.loads((root / 'starting-pve8.json').read_text())
            checkpoint = root / 'artifacts/pve8-checkpoint.qcow2'
        if 'sources' not in state['completed']:
            lab.play('switch-sources', LAB / 'upgrade_sources.yml')
            lab.apt('update')
            policy = lab.ssh('apt-cache policy').stdout
            (root / 'target-policy.log').write_text(policy)
            assert 'trixie' in policy and 'bookworm' not in policy
            done('sources')
        if until == 'sources': return
        if 'downloaded' not in state['completed']:
            lab.apt('download9'); done('downloaded')
        if until == 'downloaded': return
        if 'installed' not in state['completed']:
            existing = root / 'upgrade9-job.json'
            if existing.exists():
                lab.observe_apt('upgrade9', json.loads(existing.read_text()))
            else:
                lab.apt('upgrade9')
            done('installed')
        # 即使控制端在安装后退出，续跑也必须再次通过复检，不能借阶段文件绕过 FAIL。
        if 'rebooted' not in state['completed']:
            checklist(lab, 'post-install-pre-reboot')
        if until == 'installed': return
        if 'rebooted' not in state['completed']:
            lab.reboot('pve9'); done('rebooted')
        verified = lab.probe('pve9-verified', '9')
        transaction = json.loads(lab.ssh('sudo cat /var/lib/misaka/pve-lab/jobs/active.json').stdout)
        completion = json.loads(lab.ssh('sudo cat /var/lib/misaka/pve-lab/jobs/' + transaction['id'] + '.json').stdout)
        assert verified['boot_id'] != completion['boot_id_at_end']
        assert verified['machine_id'] == start['machine_id']
        checklist(lab, 'post-reboot-full')
        lab.archive_jobs(); lab.shutdown(); lab.destroy()
        verify_reuse(root, checkpoint, start)
        assert sha(image) == original_sha and host_state() == before
        (root / 'host-after.json').write_text(json.dumps(host_state(), indent=2))
        done('completed')
        (root / 'results.json').write_text(json.dumps({'passed': True, 'baseline_unchanged': True,
            'checkpoint_restored_to_same_pve8': True, 'host_unchanged': True, 'pveversion': verified['pveversion'],
            'kernel': verified['kernel'], 'tested_profile': 'UEFI empty single node; no cluster/Ceph/shared storage; not production'}, indent=2))
        print('PVE8→9 空载验证完成：' + str(root), flush=True)
    except BaseException:
        lab.archive_jobs()
        raise

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]


def module(name):
    path = ROOT / 'shared/molecule/pve_lab' / (name + '.py')
    spec = importlib.util.spec_from_file_location('pve_lab_' + name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize(('text', 'rc', 'expected'), [
    ('TOTAL: 45\nFAILURES: 0\n', 0, True),
    ('TOTAL: 45\nWARNINGS: 2\nFAILURES: 0\n', 0, True),
    ('TOTAL: 45\nFAILURES: 1\n', 0, False),
    ('TOTAL: 45\nFAILURES: 0\nFAIL: unsafe\n', 0, False),
    ('TOTAL: 45\nFAILURES: 0\n', 1, False),
    ('', 0, False),
    ('FAILURES: 0\n', 0, False),
    ('TOTAL: 45\nFAILURES: 0\nFAILURES: 1\n', 0, False),
    ('TOTAL: 0\nFAILURES: 0\n', 0, False),
])
def test_preflight_gate(text, rc, expected):
    assert module('apt_worker').checker_ok(text, rc) is expected


def test_proxmox_kernel_dependency_closure_is_not_debian_kernel(monkeypatch):
    probe = module('probe')
    packages = {
        'proxmox-default-kernel': ['installed', '9.2', 'proxmox-kernel-6.99'],
        'proxmox-kernel-6.99': ['installed', '6.99.8', 'proxmox-kernel-6.99.8-1-pve-signed | proxmox-kernel-6.99.8-1-pve'],
        'proxmox-kernel-6.99.8-1-pve-signed': ['installed', '6.99.8', 'proxmox-kernel-helper'],
    }
    monkeypatch.setattr(probe, 'installed', lambda name: packages.get(name))
    assert probe.kernel_closure('proxmox-default-kernel') == set(packages)
    assert 'linux-image-amd64' not in (ROOT / 'shared/molecule/pve_lab/probe.py').read_text()


def test_no_manual_etc_pve_write_or_unsafe_transaction_relaunch():
    runner = (ROOT / 'shared/scripts/validate_pve_lab.py').read_text()
    assert 'cloud-init clean --logs --seed' in runner
    assert "target.chmod(0o400)" in runner
    probe = (ROOT / 'shared/molecule/pve_lab/probe.py').read_text()
    assert "Path('/etc/pve/storage.cfg').read_text()" in probe
    assert '.write_text(' not in probe


def test_pve_init_uses_derived_country_default():
    main = (ROOT / 'collections/os_base/roles/pve_init/tasks/main.yml').read_text()
    tasks = (ROOT / 'collections/os_base/roles/pve_init/tasks/debian.yml').read_text()
    assert "host_geo.country | default('cn')" in main
    assert 'host_geo.country' not in tasks


def script_module(name, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'shared/scripts'))
    spec = importlib.util.spec_from_file_location('pve_script_' + name, ROOT / 'shared/scripts' / (name + '.py'))
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


def test_checker_preserves_failed_attempt_when_rerun_passes(tmp_path, monkeypatch):
    experiment = script_module('pve_upgrade_experiment', monkeypatch)
    reports = iter([SimpleNamespace(stdout='TOTAL: 4\nFAILURES: 1\nFAIL: test\n', stderr='', returncode=0),
                    SimpleNamespace(stdout='TOTAL: 4\nFAILURES: 0\n', stderr='', returncode=0)])
    lab = SimpleNamespace(root=tmp_path, ssh=lambda *args, **kwargs: next(reports))
    with pytest.raises(RuntimeError):
        experiment.checklist(lab, 'check')
    experiment.checklist(lab, 'check')
    assert 'FAIL: test' in (tmp_path / 'check.log').read_text()
    assert json.loads((tmp_path / 'check-attempt2-rc.json').read_text())['passed']


def test_cleanup_and_shutdown_use_same_authenticated_ssh(monkeypatch):
    runner = script_module('validate_pve_lab', monkeypatch)
    lab = runner.Lab.__new__(runner.Lab)
    commands = []
    lab.ssh = lambda cmd: commands.append(cmd)
    lab.wait_off = lambda: None
    lab.shutdown(clean=True)
    assert len(commands) == 1
    assert 'cloud-init clean --logs --seed &&' in commands[0]
    assert 'authorized_keys && sudo sync && sudo systemd-run' in commands[0]


@pytest.mark.parametrize('mac_match', [True, False])
def test_lease_refresh_follows_only_owned_mac(tmp_path, monkeypatch, mac_match):
    import yaml
    runner = script_module('validate_pve_lab', monkeypatch)
    lab = runner.Lab.__new__(runner.Lab)
    lab.instance = {'address': '192.0.2.10', 'domain': 'mol-test', 'user': 'molecule'}
    lab.owned = {'mac': '52:54:00:11:22:33'}; lab.env = {}; lab.work = tmp_path; lab.root = tmp_path
    lab.ssh_args = ['ssh', 'molecule@192.0.2.10']; lab.inventory = tmp_path / 'inventory.yml'
    lab.inventory.write_text(yaml.safe_dump({'all': {'hosts': {'pve-lab': {'ansible_host': '192.0.2.10'}}}}))
    (tmp_path / 'instance.yml').write_text(yaml.safe_dump([lab.instance]))
    mac = lab.owned['mac'] if mac_match else '52:54:00:99:88:77'
    monkeypatch.setattr(runner.subprocess, 'run', lambda *args, **kwargs:
                        SimpleNamespace(stdout=f'vnet0 {mac} ipv4 192.0.2.11/24\n', returncode=0))
    lab.refresh_lease()
    assert lab.instance['address'] == ('192.0.2.11' if mac_match else '192.0.2.10')


def test_posix_apt_lock_is_busy_before_database_audit(tmp_path, monkeypatch):
    worker = module('apt_worker')
    lock = tmp_path / 'var/lib/dpkg/lock-frontend'; lock.parent.mkdir(parents=True); lock.write_text('')
    (tmp_path / 'proc').mkdir()
    info = lock.stat()
    key = f'{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino}'
    (tmp_path / 'proc/locks').write_text(f'1: POSIX ADVISORY WRITE 123 {key} 0 EOF\n')
    monkeypatch.setattr(worker, 'Path', lambda value: tmp_path / str(value).lstrip('/'))
    with pytest.raises(RuntimeError, match='只是忙'):
        worker.healthy()


def test_resume_still_requires_post_install_checker_before_reboot():
    text = (ROOT / 'shared/scripts/pve_upgrade_experiment.py').read_text()
    section = text.split("done('installed')", 1)[1]
    assert section.index("if 'rebooted' not in state['completed']:") < section.index("checklist(lab, 'post-install-pre-reboot')")
    assert section.index("checklist(lab, 'post-install-pre-reboot')") < section.index("lab.reboot('pve9')")


def test_probe_waits_for_every_service_not_any_active(tmp_path, monkeypatch):
    runner = script_module('validate_pve_lab', monkeypatch)
    lab = runner.Lab.__new__(runner.Lab)
    answers = iter([
        SimpleNamespace(returncode=0, stdout='active\nactivating\nactive\nactive\n', stderr=''),
        SimpleNamespace(returncode=0, stdout='active\n' * 4, stderr=''),
        SimpleNamespace(returncode=0, stdout='{}', stderr=''),
    ])
    calls = []
    lab.ssh = lambda command, **kwargs: (calls.append(command), next(answers))[1]
    lab.root = tmp_path
    monkeypatch.setattr(runner.time, 'sleep', lambda _: None)
    with pytest.raises(KeyError):
        lab.probe('ready', '8')
    assert len(calls) == 3
    assert calls[:2] == ['systemctl is-active pve-cluster pveproxy pvedaemon pvestatd'] * 2


def test_observer_reconnects_to_same_job_without_starting_apt(tmp_path, monkeypatch):
    runner = script_module('validate_pve_lab', monkeypatch)
    lab = runner.Lab.__new__(runner.Lab); lab.root = tmp_path
    replies = iter([
        SimpleNamespace(returncode=255, stdout='', stderr='reset'),
        SimpleNamespace(returncode=0, stdout='{"id":"same"}', stderr=''),
        SimpleNamespace(returncode=255, stdout='', stderr='reset'),
        SimpleNamespace(returncode=0, stdout='{"id":"same"}', stderr=''),
        SimpleNamespace(returncode=0, stdout='{"ok":true}', stderr=''),
    ])
    commands = []
    lab.ssh = lambda cmd, **kwargs: (commands.append(cmd), next(replies))[1]
    lab.archive_jobs = lambda: None
    monkeypatch.setattr(runner.time, 'sleep', lambda _: None)
    lab.observe_apt('upgrade9', {'id': 'same'})
    assert len(commands) == 5
    assert all(' start ' not in cmd and 'apt-get' not in cmd for cmd in commands)


def test_observer_refuses_different_guest_job(tmp_path, monkeypatch):
    runner = script_module('validate_pve_lab', monkeypatch)
    lab = runner.Lab.__new__(runner.Lab); lab.root = tmp_path
    lab.ssh = lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout='{"id":"other"}', stderr='')
    with pytest.raises(AssertionError, match='guest job 已变化'):
        lab.observe_apt('upgrade9', {'id': 'same'})

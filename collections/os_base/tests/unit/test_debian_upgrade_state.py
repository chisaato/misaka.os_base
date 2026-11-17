"""Debian 在线阶段契约；不把 Fedora offline marker 当作 APT 事实。"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


PATH = Path(__file__).resolve().parents[2] / 'roles/debian_dist_upgrade/files/debian_upgrade.py'
spec = importlib.util.spec_from_file_location('debian_upgrade', PATH)
debian = importlib.util.module_from_spec(spec)
spec.loader.exec_module(debian)


@pytest.fixture
def observed():
    return {'os': '12', 'sources': 'target', 'suites': ['trixie', 'trixie-updates', 'trixie-security'],
            'boot_id': 'before', 'snapshot': 'dpkg', 'lists': 'lists', 'source_config': 'sources', 'target_indexes': True,
            'reboot_required': False, 'archives': 'archives',
            'minimal_plan': {'changes': ['Inst base-files [12] (13 Debian:13/stable)'], 'sha256': 'min'},
            'full_plan': {'changes': ['Inst base-files [12] (13 Debian:13/stable)'], 'sha256': 'full'},
            'kernel': {'ready': False, 'running_target': False}}


def downloaded(observed):
    return {'stage': 'downloaded', 'evidence': {
        'baseline_boot_id': 'before', 'prepared_sources': observed['suites'], 'prepared_config': 'sources',
        'download': {'snapshot': 'dpkg', 'lists': 'lists', 'plan': 'full', 'sources': 'sources', 'archives': 'archives'}}}


def test_default_and_skip_false_do_not_license_install():
    text = (PATH.parents[1] / 'tasks/00_validate.yml').read_text()
    assert "or 'downloaded'" in text
    assert 'skip_reboot' not in text.split('ansible.builtin.set_fact:')[1]


@pytest.mark.parametrize('current', ['12', '13'])
def test_default_target_does_not_drift_after_manual_upgrade(jinja_env, debian_defaults, current):
    target = jinja_env.from_string(debian_defaults['debian_dist_upgrade_target_version']).render(
        ansible_facts={'distribution_major_version': current})
    assert int(target) == 13


def test_download_receipt_requires_same_dpkg_plan_and_indices(observed):
    marker = downloaded(observed)
    assert debian.derive(observed, marker) == 'downloaded'
    for key in ['snapshot', 'lists', 'archives']:
        altered = dict(observed, **{key: 'changed'})
        assert debian.derive(altered, marker) == 'prepared'
    observed['full_plan']['sha256'] = 'changed'
    assert debian.derive(observed, marker) == 'prepared'


def test_marker_never_proves_upgrade_alone(observed):
    assert debian.derive(observed, {'stage': 'completed'}) == 'preflight'
    observed['sources'] = 'source'
    assert debian.derive(observed, {'stage': 'completed'}) == 'preflight'


def test_source_uri_change_invalidates_update_and_download_receipts(observed):
    marker = downloaded(observed)
    observed['source_config'] = 'new-uri'
    assert debian.derive(observed, marker) == 'preflight'


def test_empty_indices_and_empty_plan_are_not_minimal_upgrade(observed):
    observed.update(target_indexes=False, minimal_plan={'changes': []}, full_plan={'changes': []})
    assert debian.derive(observed, downloaded(observed)) == 'preflight'


def test_no_successful_update_receipt_must_prepare_first(observed):
    observed['minimal_plan'] = {'changes': []}
    assert debian.derive(observed, {'stage': 'completed'}) == 'preflight'


def test_noop_minimal_still_downloads_full_plan_before_default_pause(observed):
    observed['minimal_plan'] = {'changes': []}
    marker = {'evidence': {'prepared_config': 'sources', 'prepared_sources': observed['suites'],
                           'baseline_snapshot': observed['snapshot']}}
    assert debian.derive(observed, marker) == 'prepared'
    assert debian.derive(observed, downloaded(observed)) == 'minimal_upgraded'


def test_kernel_candidate_must_come_from_target_suite():
    policy = '''linux-image-amd64:
  Installed: 6.1.1
  Candidate: 6.1.1
  Version table:
 *** 6.1.1 500
        500 https://arbitrary.example/debian bookworm/main amd64 Packages
        100 /var/lib/dpkg/status
     6.12.1 500
        500 https://arbitrary.example/debian trixie/main amd64 Packages
'''
    assert not debian.target_candidate(policy, '6.1.1')
    assert debian.target_candidate(policy, '6.12.1')


@pytest.mark.parametrize('reboot_flag', [True, False])
def test_target_release_or_reboot_required_not_sufficient(observed, reboot_flag):
    observed.update(os='13', reboot_required=reboot_flag)
    assert debian.derive(observed, downloaded(observed)) == 'downloaded'


def test_full_requires_clean_plan_and_actual_kernel_candidate(observed):
    observed.update(os='13', full_plan={'changes': [], 'sha256': 'empty'})
    assert debian.derive(observed, None) != 'full_upgraded'
    observed['kernel'] = {'ready': True, 'running_target': False}
    assert debian.derive(observed, None) == 'full_upgraded'


def test_target_without_marker_never_claims_previous_reboot(observed):
    observed.update(os='13', full_plan={'changes': [], 'sha256': 'empty'},
                    kernel={'ready': True, 'running_target': True}, boot_id='after')
    assert debian.derive(observed, None) == 'full_upgraded'
    assert debian.derive(observed, {'evidence': {'baseline_boot_id': 'before'}}) == 'verified'


def test_running_kernel_and_boot_id_jointly_required(observed):
    observed.update(os='13', full_plan={'changes': [], 'sha256': 'empty'},
                    kernel={'ready': True, 'running_target': True})
    marker = downloaded(observed)
    assert debian.derive(observed, marker) == 'full_upgraded'
    observed['boot_id'] = 'after'
    assert debian.derive(observed, marker) == 'verified'
    observed['kernel']['running_target'] = False
    assert debian.derive(observed, marker) == 'full_upgraded'


def test_busy_is_not_corruption(observed):
    observed.update(busy=True, abnormal=True)
    assert debian.derive(observed, None) == 'busy'


def test_abnormal_transaction_prevents_fact_adoption(observed):
    observed.update(abnormal=True, os='13')
    assert debian.derive(observed, downloaded(observed)) == 'needs_human'


def test_minimal_and_full_have_separate_explicit_gates(observed, monkeypatch):
    marker = downloaded(observed)
    monkeypatch.setattr(debian, 'read_json', lambda _: marker)
    observed['phase'] = 'downloaded'
    assert debian.choose(observed, 'downloaded') == 'pause'
    assert debian.choose(observed, 'minimal_upgraded') == 'minimal'
    observed['phase'] = 'minimal_upgraded'
    assert debian.choose(observed, 'minimal_upgraded') == 'pause'
    assert debian.choose(observed, 'full_upgraded') == 'full'
    observed['phase'] = 'full_upgraded'
    assert debian.choose(observed, 'full_upgraded') == 'pause'
    assert debian.choose(observed, 'reboot_requested') == 'reboot'


def test_existing_live_worker_is_observed_not_replaced(observed, monkeypatch):
    monkeypatch.setattr(debian, 'read_json', lambda _: {})
    observed.update(phase='busy', job={'live': True, 'stage': 'full'})
    assert debian.choose(observed, 'full_upgraded') == 'full'


def test_apt_get_semantics_and_no_automatic_repair():
    text = PATH.read_text()
    assert "'--no-remove', 'upgrade'" in text
    assert "'--download-only', 'dist-upgrade'" in text
    assert "'APT::Update::Error-Mode=any'" in text
    assert "'--without-new-pkgs'" not in text
    assert "'autoremove'" not in text
    assert "'--configure'" not in text


def test_status_task_excludes_mutating_executor():
    text = (PATH.parents[1] / 'tasks/main.yml').read_text()
    assert "when: debian_dist_upgrade_action == 'advance'" in text
    assert 'ignore_errors' not in text


def test_deb822_disabled_stanzas_do_not_conflict(tmp_path, monkeypatch):
    (tmp_path / 'sources.list.d').mkdir()
    (tmp_path / 'sources.list').write_text('# deb https://old.example bookworm main\n')
    (tmp_path / 'sources.list.d/debian.sources').write_text('''Types: deb
URIs: https://any.example/debian
Suites: trixie trixie-updates
 trixie-security
Components: main

Types: deb
URIs: https://old.example
Suites: bookworm
Enabled: no
''')
    path_class = Path
    monkeypatch.setattr(debian, 'Path', lambda value: path_class(str(value).replace('/etc/apt', str(tmp_path))))
    assert debian.sources() == ('target', ['trixie', 'trixie-updates', 'trixie-security'])


def test_source_backports_allowed_but_not_migrated(tmp_path, monkeypatch):
    (tmp_path / 'sources.list.d').mkdir()
    source = tmp_path / 'sources.list'
    source.write_text('deb [signed-by=/key] https://any.example bookworm main\ndeb https://any.example bookworm-backports main\n')
    path_class = Path
    monkeypatch.setattr(debian, 'Path', lambda value: path_class(str(value).replace('/etc/apt', str(tmp_path))))
    assert debian.sources()[0] == 'source'
    source.write_text('deb https://any.example trixie main\ndeb https://any.example trixie-backports main\n')
    assert debian.sources()[0] == 'conflict'


def test_worker_observation_does_not_require_python_during_upgrade():
    main = (PATH.parents[1] / 'tasks/main.yml').read_text()
    steps = (PATH.parents[1] / 'tasks/step.yml').read_text()
    assert main.index('ansible.builtin.raw:') < main.index('ansible.builtin.setup:')
    assert 'ansible.builtin.raw:' in steps
    observer = (PATH.parent / 'observe_job.sh').read_text()
    assert 'systemctl show' in observer
    assert '观察命令暂不可用' in observer
    assert 'observe_job.sh' in steps
    assert "__import__('dist_upgrade_state')" in PATH.read_text()
    playbook = PATH.parents[3] / 'playbooks/debian_dist_upgrade.yml'
    assert 'gather_facts: false' in playbook.read_text()


@pytest.mark.parametrize(('systemctl_rc', 'state', 'result', 'expected'), [
    (127, 'shared library temporarily missing', None, 75),
    (0, 'activating', None, 75),
    (0, 'inactive', None, 2),
    (127, 'must not matter after durable result', {'ok': True}, 0),
    (127, 'must not matter after durable result', {'ok': False, 'error': 'manual repair needed'}, 2),
])
def test_shell_observer_never_confuses_observation_failure_with_completion(
        tmp_path, systemctl_rc, state, result, expected):
    job_id = 'a' * 32
    unit = 'misaka-debian-full-' + job_id
    (tmp_path / 'active.json').write_text(json.dumps({'id': job_id, 'unit': unit}, indent=2))
    if result is not None:
        (tmp_path / (job_id + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    fake = tmp_path / 'systemctl'
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "{state}"\nexit {systemctl_rc}\n')
    fake.chmod(0o700)
    script = (PATH.parent / 'observe_job.sh').read_text().replace('/var/lib/misaka/dist-upgrade/debian-jobs', str(tmp_path))
    process = subprocess.run(['/bin/sh'], input=script, text=True, capture_output=True,
                             env=dict(os.environ, PATH=str(tmp_path)))
    assert process.returncode == expected, process.stdout + process.stderr
    if systemctl_rc and result is None:
        assert '观察命令暂不可用' in process.stdout


def test_target_without_marker_adopts_full_facts_immediately_but_not_past_reboot(monkeypatch):
    observed = {'phase': 'full_upgraded', 'os': '13', 'boot_id': 'current-boot', 'snapshot': 'dpkg'}
    recorded = []
    monkeypatch.setattr(debian, 'probe', lambda: observed)
    monkeypatch.setattr(debian, 'read_json', lambda _: None)
    monkeypatch.setattr(debian.shutil, 'disk_usage', lambda _: SimpleNamespace(free=10 * 1024**3))
    monkeypatch.setattr(debian, 'record', lambda stage, evidence, note: recorded.append((stage, evidence)))
    assert debian.claim('empty-profile')['changed']
    assert recorded[0][0] == 'full_upgraded'
    assert recorded[0][1]['baseline_boot_id'] == 'current-boot'

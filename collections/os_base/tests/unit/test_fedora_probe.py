from __future__ import annotations

import importlib.util
from pathlib import Path
from subprocess import CompletedProcess

import pytest


PATH = Path(__file__).resolve().parents[2] / 'roles/fedora_dist_upgrade/files/probe_fedora.py'
SPEC = importlib.util.spec_from_file_location('fedora_probe', PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


@pytest.mark.parametrize('status,pending', [
    ('download-complete', True), ('ready', True),
    ('download-incomplete', False), ('transaction-incomplete', True),
])
def test_real_dnf5_state_format(monkeypatch, tmp_path, status, pending):
    monkeypatch.setattr(probe, 'OFFLINE_DIR', tmp_path)
    (tmp_path / 'offline-transaction-state.toml').write_text(
        f'[offline-transaction-state]\nstatus = "{status}"\ntarget_releasever = "44"\n'
    )
    result, raw = probe._pending()
    assert (result is not None) is pending
    if result:
        assert result['releasever'] == '44'
        assert len(result['sha256']) == 64


def test_unknown_state_is_not_silently_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, 'OFFLINE_DIR', tmp_path)
    (tmp_path / 'offline-transaction-state.toml').write_text(
        '[offline-transaction-state]\nstatus = "surprise"\ntarget_releasever = "44"\n'
    )
    with pytest.raises(ValueError):
        probe._pending()


@pytest.mark.parametrize('rows,bad', [
    ('kernel-core x86_64 installonlypkg(kernel)\nkernel-core x86_64 installonlypkg(kernel)\n', False),
    ('glibc x86_64 glibc\nglibc i686 glibc\n', False),
    ('gpg-pubkey (none) gpg-pubkey\ngpg-pubkey (none) gpg-pubkey\n', False),
    ('glibc x86_64 glibc\nglibc x86_64 glibc\n', True),
])
def test_installonly_and_multilib_are_not_corruption(monkeypatch, rows, bad):
    monkeypatch.setattr(probe, '_run', lambda argv: CompletedProcess(argv, 0, rows, ''))
    assert probe._duplicates() is bad

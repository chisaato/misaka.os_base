from __future__ import annotations

import importlib.util
import json
import threading
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT.parents[1] / "shared" / "scripts" / "libvirt_assets.py"
_SPEC = importlib.util.spec_from_file_location(
    "dist_upgrade_state",
    ROOT / "roles" / "dist_upgrade_state" / "files" / "dist_upgrade_state.py",
)
state = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(state)


def _request(**overrides):
    base = {
        "action": "advance",
        "until": "completed",
        "target": 44,
        "target_was_explicit": True,
        "stable_releases": [43, 44],
        "releases_ok": True,
        "caller_token": "caller",
        "now": 1000,
        "abandon_confirm": None,
        "retry_reboot": False,
        "retry_confirm": None,
    }
    base.update(overrides)
    return base


def _observed(**overrides):
    base = {
        "os": "43",
        "pending": None,
        "boot_id": "boot-a",
        "machine_id_sha256_16": "machine",
        "rpm_abnormal": False,
        "dnf_check_abnormal": False,
        "now": 1000,
    }
    base.update(overrides)
    return base


def _marker(stage="prepared", **overrides):
    base = {
        "schema": 1,
        "family": "fedora",
        "operation_id": "fedora-43to44-id",
        "seq": 2,
        "machine": {"id_sha256_16": "machine"},
        "source": {"release": "43"},
        "target": {"release": "44"},
        "stage": stage,
        "intent": None,
    }
    base.update(overrides)
    return base


@pytest.fixture(scope="session")
def assets():
    import importlib.util

    spec = importlib.util.spec_from_file_location("libvirt_assets", ASSETS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestStableReleases:
    def test_ignores_beta_and_rawhide(self):
        payload = [
            {"version": "44"},
            {"version": "45 Beta"},
            {"version": "Rawhide"},
            {"version": 43},
            {"version": "43 Beta"},
        ]
        assert state.stable_releases(payload) == [43, 44]

    def test_rejects_non_list(self):
        with pytest.raises(state.StateError):
            state.stable_releases({"version": "44"})

    def test_target_absent_refuses_advance(self):
        result = state.decide(_observed(), None, _request(stable_releases=[43], target=44))
        assert result["ok"] is False
        assert result["reason"] == "target_not_stable"

    def test_network_failure_refuses_advance_but_status_reports_fact(self):
        refused = state.decide(_observed(), None, _request(releases_ok=False))
        assert refused["reason"] == "releases_unavailable"
        reported = state.decide(_observed(os="44"), None, _request(action="status", releases_ok=False, target=44))
        assert reported["ok"] is True
        assert reported["phase"] == "upgraded"
        assert reported["side_effects"] == []


class TestReportTable:
    def test_record_preserves_profile_across_controller_change(self):
        previous = _marker('downloaded', tested_profile={'load':'none','image':'fedora43'})
        built = state.build_marker(previous, _observed(os='44'), 'verified', 'adopted',
                                   {'target':44,'tested_profile':{}}, '2026-10-23T00:00:00Z')
        assert built['marker']['tested_profile'] == previous['tested_profile']
        assert built['marker']['operation_id'] == previous['operation_id']
        assert built['expect_seq'] == previous['seq']

    def test_explicit_until_limits_legacy_post_but_default_alias_does_not(self):
        implicit = state.decide(_observed(os='44'), None, _request(until='downloaded'))
        assert implicit['side_effects'] == ['finalize']
        explicit = state.decide(_observed(os='44'), None, _request(until='downloaded', until_was_explicit=True))
        assert explicit['side_effects'] == []

    def test_adopt_manual_download(self):
        result = state.decide(
            _observed(pending={"releasever": "44", "sha256": "abc"}),
            _marker("prepared"),
            _request(until="downloaded"),
        )
        assert result["decision"] == "adopt"
        assert result["phase"] == "downloaded"
        assert result["side_effects"] == []
        assert "download" not in result["side_effects"]

    def test_manual_download_other_release_refuses(self):
        result = state.decide(
            _observed(pending={"releasever": "45", "sha256": "abc"}),
            _marker("prepared"),
            _request(),
        )
        assert result["ok"] is False
        assert result["reason"] == "pending_conflict"
        assert result["side_effects"] == []

    def test_manual_reboot_stays_downloaded(self):
        result = state.decide(
            _observed(pending={"releasever": "44"}, boot_id="boot-b"),
            _marker("downloaded", intent=None),
            _request(until="downloaded"),
        )
        assert result["phase"] == "downloaded"
        assert result["decision"] == "pause"
        assert result["side_effects"] == []

    def test_reboot_failed_does_not_retry(self):
        result = state.decide(
            _observed(pending={"releasever": "44"}, boot_id="boot-b"),
            _marker("reboot_requested", intent={"action": "reboot", "boot_id": "boot-a"}),
            _request(),
        )
        assert result["decision"] == "reboot_failed"
        assert result["side_effects"] == []

    def test_retry_reboot_requires_operation_id(self):
        marker = _marker("reboot_requested", intent={"action": "reboot", "boot_id": "boot-a"})
        denied = state.decide(
            _observed(pending={"releasever": "44"}, boot_id="boot-b"),
            marker,
            _request(retry_reboot=True, retry_confirm="wrong"),
        )
        assert denied["side_effects"] == []
        allowed = state.decide(
            _observed(pending={"releasever": "44"}, boot_id="boot-b"),
            marker,
            _request(retry_reboot=True, retry_confirm=marker["operation_id"]),
        )
        assert allowed["side_effects"] == ["reboot"]

    def test_adopt_completed_manual_upgrade(self):
        result = state.decide(_observed(os="44"), _marker("downloaded"), _request())
        assert result["decision"] == "adopt"
        assert result["side_effects"] == ["verify"]

    def test_demote_when_pending_disappears(self):
        result = state.decide(_observed(pending=None), _marker("downloaded"), _request(until="prepared"))
        assert result["decision"] == "demote"
        assert result["phase"] == "prepared"
        assert result["history_result"] == "demoted"
        assert result["side_effects"] == []

    def test_demote_then_download_when_continuing(self):
        result = state.decide(_observed(pending=None), _marker("downloaded"), _request())
        assert result["decision"] == "demote"
        assert result["side_effects"] == ["download"]

    def test_stale_completed_marker(self):
        result = state.decide(_observed(os="43"), _marker("completed"), _request())
        assert result["decision"] == "stale"
        assert result["archive"] is True
        assert result["side_effects"] == ["claim"]

    def test_target_conflict_and_machine_mismatch(self):
        conflict = state.decide(_observed(), _marker("prepared"), _request(target=45, stable_releases=[43, 44, 45]))
        assert conflict["reason"] == "target_conflict"
        mismatch = state.decide(_observed(machine_id_sha256_16="other"), _marker("prepared"), _request())
        assert mismatch["reason"] == "machine_mismatch"
        assert mismatch["side_effects"] == []

    def test_downgrade_refuses(self):
        result = state.decide(_observed(os="44"), None, _request(target=43, stable_releases=[43, 44]))
        assert result["reason"] == "target_downgrade"

    def test_cached_fact_is_not_an_input(self):
        # 调用方若把缓存版本当 os 传入才会错；真实 os-release 为 44 时不得停在 43。
        result = state.decide(_observed(os="44"), _marker("downloaded"), _request(until="verified"))
        assert result["phase"] == "verified"
        assert result["side_effects"] == ["verify"]

    def test_legacy_post_without_marker_on_target(self):
        result = state.decide(_observed(os="44"), None, _request())
        assert result["decision"] == "legacy_post"
        assert result["phase"] == "already_target"
        assert result["mutate"] is False
        assert result["side_effects"] == ["finalize"]

    def test_reboot_not_issued_reissues_without_demote(self):
        result = state.decide(
            _observed(pending={"releasever": "44"}, boot_id="boot-a"),
            _marker("reboot_requested", intent={"action": "reboot", "boot_id": "boot-a"}),
            _request(),
        )
        assert result["side_effects"] == ["reboot"]
        assert result["history_result"] != "demoted"

    def test_completed_is_noop(self):
        result = state.decide(_observed(os="44"), _marker("completed"), _request())
        assert result["phase"] == "completed"
        assert result["side_effects"] == []
        assert result["mutate"] is False


class TestStatus:
    @pytest.mark.parametrize(
        ("observed", "marker", "extra", "reason"),
        [
            (_observed(), None, {}, "source_without_pending"),
            (_observed(pending={"releasever": "44"}), _marker("downloaded"), {}, "pending_matches_target"),
            (_observed(), _marker("downloaded"), {}, "source_without_pending"),
            (_observed(os="44"), _marker("prepared"), {}, "os_is_target"),
            (_observed(), _marker("prepared"), {"target": 45}, "target_conflict"),
            (_observed(machine_id_sha256_16="nope"), _marker("prepared"), {}, "machine_mismatch"),
        ],
    )
    def test_status_is_readonly(self, observed, marker, extra, reason):
        result = state.decide(observed, marker, _request(action="status", **extra))
        assert result["ok"] is True
        assert result["mutate"] is False
        assert result["side_effects"] == []
        assert result["reason"] == reason

    def test_corrupt_marker_status_still_reports_fact(self):
        result = state.decide(_observed(os="44", marker_corrupt=True), {"broken": True}, _request(action="status"))
        assert result["reason"] == "marker_corrupt"
        assert result["phase"] == "upgraded"

    def test_corrupt_marker_advance_refuses(self):
        result = state.decide(_observed(marker_corrupt=True), None, _request())
        assert result["ok"] is False
        assert result["reason"] == "marker_corrupt"

    def test_live_lock_and_stale_lock(self):
        live = {
            "token": "other",
            "lease_until": 2000,
            "holder_alive": True,
            "worker_alive": False,
        }
        held = state.decide(_observed(lock=live), _marker(), _request())
        assert held["reason"] == "lock_held"
        assert held["side_effects"] == []
        stale = dict(live, holder_alive=False, lease_until=10)
        taken = state.decide(_observed(lock=stale), _marker("prepared"), _request(until="prepared"))
        assert taken["takeover"] is True
        assert taken["ok"] is True
        status = state.decide(_observed(lock=live), None, _request(action="status"))
        assert status["reason"] == "lock_held"
        expired = state.decide(_observed(lock=stale), None, _request(action="status"))
        assert expired["reason"] == "lock_stale"

    def test_worker_blocks_takeover_even_if_holder_died(self):
        lock = {"token": "other", "lease_until": 1, "holder_alive": False, "worker_alive": True}
        result = state.decide(_observed(lock=lock), _marker(), _request())
        assert result["reason"] == "lock_held"


class TestLockAndSeq:
    def test_two_acquirers_one_wins_and_takeover_after_exit(self, tmp_path: Path):
        root = tmp_path / "dist-upgrade"
        lease = int(__import__("time").time()) + 60
        first = state.lock_acquire(root, "a", "boot", lease, "c1")
        try:
            assert first["acquired"] is True
            second = state.lock_acquire(root, "b", "boot", lease, "c2")
            assert second["acquired"] is False
            assert second["owner"]["token"] == "a"
            with pytest.raises(state.StateError):
                state.lock_takeover(root, "b", "boot", lease, "c2", now=1)
            owner = root / "lock.d" / "owner"
            payload = json.loads(owner.read_text(encoding="utf-8"))
            os_mod = __import__("os")
            os_mod.kill(int(payload["holder_pid"]), 15)
            payload["holder_pid"] = 2**22
            owner.write_text(json.dumps(payload), encoding="utf-8")
            taken = state.lock_takeover(root, "b", "boot-b", lease, "c2", now=1)
            assert taken["acquired"] is True
            assert taken["takeover"] is True
            assert (root / "lock.d.stale-1").is_dir()
        finally:
            owner = state.read_owner(root / "lock.d")
            if owner:
                state._kill_holder(owner)
                state.lock_release(root, owner["token"])

    def test_concurrent_mkdir_has_single_winner(self, tmp_path: Path):
        root = tmp_path / "dist-upgrade"
        results: list[bool] = []

        def attempt(token: str) -> None:
            outcome = state.lock_acquire(root, token, "boot", 50, token)
            results.append(outcome["acquired"])

        threads = [threading.Thread(target=attempt, args=(str(i),)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert results.count(True) == 1

    def test_seq_mismatch_does_not_overwrite(self, tmp_path: Path):
        path = tmp_path / "fedora.json"
        state.marker_write(path, {"seq": 1, "stage": "prepared"}, 0)
        with pytest.raises(state.StateError):
            state.marker_write(path, {"seq": 3, "stage": "downloaded"}, 2)
        assert json.loads(path.read_text(encoding="utf-8"))["seq"] == 1
        state.marker_write(path, {"seq": 2, "stage": "downloaded"}, 1)
        assert json.loads(path.read_text(encoding="utf-8"))["stage"] == "downloaded"


class TestLibvirtAssets:
    def test_firmware_fixture_requires_unique_4m(self, assets, tmp_path: Path):
        code = tmp_path / "OVMF_CODE_4M.qcow2"
        varstore = tmp_path / "OVMF_VARS_4M.qcow2"
        code.write_bytes(b"code")
        varstore.write_bytes(b"vars")
        spec = {
            "interface-types": ["uefi"],
            "mapping": {
                "device": "flash",
                "mode": "split",
                "executable": {"filename": str(code), "format": "qcow2"},
                "nvram-template": {"filename": str(varstore), "format": "qcow2"},
            },
            "targets": [{"architecture": "x86_64", "machines": ["pc-q35-*"]}],
            "features": [],
        }
        (tmp_path / "50-edk2-4m-nosb.json").write_text(json.dumps(spec), encoding="utf-8")
        chosen = assets.discover_firmware(tmp_path)
        assert chosen["loader_format"] == "qcow2"
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(assets.DiscoverError):
            assets.discover_firmware(empty)

    def test_fedora_checksum_matches_generic_only(self, assets):
        generic = "a" * 64
        uki = "b" * 64
        text = f"""
-----BEGIN PGP SIGNED MESSAGE-----
SHA256 (Fedora-Cloud-Base-Generic-43-1.6.x86_64.qcow2) = {generic}
SHA256 (Fedora-Cloud-Base-UEFI-UKI-43-1.6.x86_64.qcow2) = {uki}
-----BEGIN PGP SIGNATURE-----
"""
        names = assets.fedora_checksum_filename(
            '<a href="Fedora-Cloud-43-1.6-x86_64-CHECKSUM">x</a><a href="Fedora-Cloud-Base-Generic-43-1.6.x86_64.qcow2">y</a>',
            "43",
        )
        assert names == ["Fedora-Cloud-43-1.6-x86_64-CHECKSUM"]
        found = assets.fedora_checksum_names(text, r"^Fedora-Cloud-Base-Generic-43-[0-9.]+[.]x86_64[.]qcow2$")
        assert [item["filename"] for item in found] == ["Fedora-Cloud-Base-Generic-43-1.6.x86_64.qcow2"]

    def test_debian_sha_and_manifest(self, assets, tmp_path: Path):
        names = assets.debian_image_names('<a href="debian-13-generic-amd64.qcow2">', r"^debian-13-generic-amd64[.]qcow2$")
        assert names == ["debian-13-generic-amd64.qcow2"]
        digest = assets.debian_sha512("abc  debian-13-generic-amd64.qcow2\n", "debian-13-generic-amd64.qcow2")
        assert digest == []
        digest = assets.debian_sha512("ab" * 64 + "  debian-13-generic-amd64.qcow2\n", "debian-13-generic-amd64.qcow2")
        assert len(digest) == 1
        image = tmp_path / "demo.qcow2"
        image.write_bytes(b"payload")
        sha = assets.file_sha256(image)
        manifest = tmp_path / "demo.qcow2.manifest.yml"
        manifest.write_text(
            "schema: 1\nsha256: deadbeef\nbuilt_at: 2026-10-23T00:00:00Z\n"
            "source:\n  iso: debian.iso\nos: debian\nversion: '12'\nuefi: true\nbuilder:\n  name: packer\n",
            encoding="utf-8",
        )
        with pytest.raises(assets.DiscoverError):
            assets.parse_local_manifest(manifest.read_text(encoding="utf-8"))
        manifest.write_text(
            f"schema: 1\nsha256: {sha}\nbuilt_at: 2026-10-23T00:00:00Z\n"
            "source:\n  iso: debian.iso\nos: debian\nversion: '12'\nuefi: false\nbuilder:\n  name: packer\n",
            encoding="utf-8",
        )
        with pytest.raises(assets.DiscoverError):
            assets.parse_local_manifest(manifest.read_text(encoding="utf-8"))
        manifest.write_text(
            f"schema: 1\nsha256: {sha}\nbuilt_at: 2026-10-23T00:00:00Z\n"
            "source:\n  iso: debian.iso\nos: debian\nversion: '12'\nuefi: true\nbuilder:\n  name: packer\n",
            encoding="utf-8",
        )
        parsed = assets.parse_local_manifest(manifest.read_text(encoding="utf-8"))
        assert parsed["uefi"] is True

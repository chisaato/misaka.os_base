#!/usr/bin/env python3
"""发行版中立的升级 marker 判定与目录锁。

锁是设计目标：本模块提供 mkdir 互斥与陈旧接管，不宣称内核级事务。
事实阶段由调用方传入的探测结果推导；本文件不执行 dnf。
"""

from __future__ import annotations

import argparse
import fcntl
import functools
import hashlib
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path


STAGES = (
    "preflight",
    "prepared",
    "downloaded",
    "reboot_requested",
    "verified",
    "completed",
)
STAGE_RANK = {name: index for index, name in enumerate(STAGES)}


class StateError(Exception):
    """拒绝继续，且不应产生副作用。"""


def stable_releases(payload) -> list[int]:
    """只保留纯数字版本。Beta / Rawhide / 空格条目全部忽略。"""
    if not isinstance(payload, list):
        raise StateError("releases.json 必须是数组")
    found: list[int] = []
    for item in payload:
        version = item.get("version") if isinstance(item, dict) else item
        if isinstance(version, bool):
            continue
        if isinstance(version, int):
            found.append(version)
            continue
        if isinstance(version, str) and version.isdigit():
            found.append(int(version))
    return sorted(set(found))


def machine_id_hash(machine_id: str) -> str:
    text = machine_id.strip()
    if not text:
        raise StateError("machine-id 为空，拒绝作为身份")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def new_operation_id(family: str, source: str, target: str, now: float | None = None) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now if now is not None else time.time()))
    return f"{family}-{source}to{target}-{stamp}-{secrets.token_hex(3)}"


def _lock_is_live(lock: dict | None, now: int) -> bool:
    """租约未过且持有者仍在，或 dnf/rpm 仍在跑时，锁视为活着。"""
    if not lock:
        return False
    lease_ok = int(now) < int(lock.get("lease_until") or 0)
    holder_alive = bool(lock.get("holder_alive"))
    worker_alive = bool(lock.get("worker_alive"))
    if worker_alive:
        return True
    return lease_ok and holder_alive


def _pending_release(observed: dict) -> str | None:
    pending = observed.get("pending")
    if not pending:
        return None
    release = pending.get("releasever")
    if release is None or str(release).strip() == "":
        return ""
    return str(release)


def _marker_target(marker: dict | None, fallback: int) -> int:
    if not marker or not isinstance(marker.get("target"), dict):
        return fallback
    return int(marker["target"]["release"])


def _marker_source(marker: dict | None, observed: dict) -> str:
    if marker and isinstance(marker.get("source"), dict) and marker["source"].get("release") is not None:
        return str(marker["source"]["release"])
    return str(observed.get("os"))


def derive_fact(observed: dict, marker: dict | None, target: int) -> dict:
    """由实时事实得到阶段。marker 只用于识别 intent / 来源，不抬高阶段。"""
    os_release = str(observed.get("os"))
    source = _marker_source(marker, observed)
    target_s = str(target)
    pending_release = _pending_release(observed)
    intent = (marker or {}).get("intent") if isinstance((marker or {}).get("intent"), dict) else None
    boot_id = str(observed.get("boot_id") or "")
    abnormal = bool(observed.get("rpm_abnormal") or observed.get("dnf_check_abnormal"))

    if marker and os_release not in {source, target_s}:
        return {"phase": "refuse", "reason": "version_outside", "fact_rank": -1}
    if abnormal or (os_release == target_s and pending_release):
        return {"phase": "needs_human", "reason": "rpm_or_pending_abnormal", "fact_rank": -1}
    if (
        intent
        and intent.get("action") == "reboot"
        and os_release == source
        and boot_id
        and boot_id != str(intent.get("boot_id") or "")
        and pending_release == target_s
    ):
        return {"phase": "reboot_failed", "reason": "offline_reboot_returned_to_source", "fact_rank": STAGE_RANK["downloaded"]}
    if os_release == target_s and not pending_release:
        return {"phase": "upgraded", "reason": "os_is_target", "fact_rank": STAGE_RANK["verified"]}
    if pending_release == target_s and os_release == source:
        if (
            intent
            and intent.get("action") == "reboot"
            and boot_id
            and boot_id == str(intent.get("boot_id") or "")
        ):
            return {"phase": "downloaded", "reason": "reboot_not_issued", "fact_rank": STAGE_RANK["downloaded"]}
        return {"phase": "downloaded", "reason": "pending_matches_target", "fact_rank": STAGE_RANK["downloaded"]}
    if pending_release not in {None, target_s} and os_release == source:
        return {"phase": "refuse", "reason": "pending_conflict", "fact_rank": -1}
    if os_release == source and not pending_release:
        stage = (marker or {}).get("stage")
        if stage == "prepared":
            return {"phase": "prepared", "reason": "marker_prepared_and_idle", "fact_rank": STAGE_RANK["prepared"]}
        if stage == "preflight":
            return {"phase": "preflight", "reason": "marker_preflight", "fact_rank": STAGE_RANK["preflight"]}
        if (
            intent
            and intent.get("action") == "reboot"
            and boot_id
            and boot_id == str(intent.get("boot_id") or "")
        ):
            # 意图已写但 boot_id 未变：重启命令尚未发出，事实仍停在下载完成。
            return {"phase": "downloaded", "reason": "reboot_not_issued", "fact_rank": STAGE_RANK["downloaded"]}
    return {"phase": "idle", "reason": "source_without_pending", "fact_rank": STAGE_RANK["preflight"]}


def _base_result(**kwargs) -> dict:
    result = {
        "ok": True,
        "decision": "status",
        "phase": "idle",
        "reason": "",
        "side_effects": [],
        "mutate": False,
        "takeover": False,
        "archive": False,
        "history_result": "",
        "effective_target": None,
    }
    result.update(kwargs)
    return result


def decide(observed: dict, marker: dict | None, request: dict) -> dict:
    """事实 + marker + 请求 → 下一步。status 永远不要求 mutate。"""
    if not isinstance(observed, dict) or not isinstance(request, dict):
        raise StateError("observed/request 必须是映射")
    action = str(request.get("action") or "advance")
    if action not in {"status", "advance", "abandon"}:
        raise StateError(f"未知 action：{action}")
    until = str(request.get("until") or "completed")
    if until not in STAGE_RANK:
        raise StateError(f"未知 until：{until}")
    now = int(request.get("now") or observed.get("now") or 0)
    caller = str(request.get("caller_token") or "")
    lock = observed.get("lock") if isinstance(observed.get("lock"), dict) else None
    takeover = False
    if lock and lock.get("token") and lock.get("token") != caller:
        if _lock_is_live(lock, now):
            if action == "status":
                return _base_result(
                    decision="status",
                    phase="locked",
                    reason="lock_held",
                    effective_target=request.get("target"),
                )
            return _base_result(ok=False, decision="refuse", phase="locked", reason="lock_held", effective_target=request.get("target"))
        takeover = True

    corrupt = bool(observed.get("marker_corrupt"))
    if action == "status":
        if corrupt:
            fact = derive_fact(observed, None, int(request.get("target") or 0))
            return _base_result(decision="status", phase=fact["phase"], reason="marker_corrupt", effective_target=request.get("target"))
        target = int(request["target"]) if request.get("target") is not None else _marker_target(marker, 0)
        fact = derive_fact(observed, marker, target) if target else {"phase": "idle", "reason": "no_target"}
        reason = fact.get("reason") or ""
        if marker and marker.get("machine", {}).get("id_sha256_16") not in {None, observed.get("machine_id_sha256_16")}:
            reason = "machine_mismatch"
        elif marker and request.get("target") is not None and int(marker["target"]["release"]) != int(request["target"]):
            reason = "target_conflict"
        elif takeover:
            reason = "lock_stale"
        return _base_result(
            decision="status",
            phase=fact.get("phase", "idle"),
            reason=reason,
            takeover=takeover,
            effective_target=target or None,
        )

    if not request.get("releases_ok", True):
        return _base_result(ok=False, decision="refuse", reason="releases_unavailable")
    stables = request.get("stable_releases") or []
    requested_target = request.get("target")
    if requested_target is None:
        return _base_result(ok=False, decision="refuse", reason="target_missing")
    target = int(requested_target)
    if target not in [int(item) for item in stables]:
        return _base_result(ok=False, decision="refuse", reason="target_not_stable", effective_target=target)

    if corrupt:
        return _base_result(ok=False, decision="refuse", reason="marker_corrupt", effective_target=target)

    if action == "abandon":
        if not marker:
            return _base_result(ok=False, decision="refuse", reason="no_marker", effective_target=target)
        if request.get("abandon_confirm") != marker.get("operation_id"):
            return _base_result(ok=False, decision="refuse", reason="abandon_confirm_mismatch", effective_target=target)
        return _base_result(
            decision="abandon",
            phase="abandoned",
            reason="confirmed",
            mutate=True,
            archive=True,
            takeover=takeover,
            history_result="abandoned",
            effective_target=_marker_target(marker, target),
        )

    if marker and marker.get("machine", {}).get("id_sha256_16") != observed.get("machine_id_sha256_16"):
        return _base_result(ok=False, decision="refuse", reason="machine_mismatch", effective_target=target)
    if marker and int(marker["target"]["release"]) != target:
        if request.get("target_was_explicit", True):
            return _base_result(ok=False, decision="refuse", reason="target_conflict", effective_target=target)
        target = int(marker["target"]["release"])
    elif marker:
        target = int(marker["target"]["release"])

    os_release = str(observed.get("os") or "")
    if os_release.isdigit() and int(os_release) > target:
        return _base_result(ok=False, decision="refuse", reason="target_downgrade", effective_target=target)
    if os_release.isdigit() and target - int(os_release) > 2:
        return _base_result(ok=False, decision="refuse", reason="version_gap", effective_target=target)

    fact = derive_fact(observed, marker, target)
    if fact["phase"] == "refuse":
        return _base_result(ok=False, decision="refuse", phase="refuse", reason=fact["reason"], takeover=takeover, effective_target=target)
    if fact["phase"] == "needs_human":
        return _base_result(decision="needs_human", phase="needs_human", reason=fact["reason"], takeover=takeover, effective_target=target)
    if fact["phase"] == "reboot_failed":
        confirmed = bool(request.get("retry_reboot")) and request.get("retry_confirm") == (marker or {}).get("operation_id")
        if not confirmed:
            return _base_result(
                decision="reboot_failed",
                phase="reboot_failed",
                reason=fact["reason"],
                takeover=takeover,
                effective_target=target,
            )
        return _base_result(
            decision="advance",
            phase="reboot_failed",
            reason="retry_confirmed",
            side_effects=["reboot"],
            mutate=True,
            takeover=takeover,
            history_result="retry_reboot",
            effective_target=target,
        )

    if fact["phase"] == "upgraded" and not marker:
        # D4：已在目标且无 marker 时保持旧行为，仍允许 finalize，不另造 operation。
        effects = ["finalize"] if (
            not request.get("until_was_explicit", False)
            or STAGE_RANK[until] >= STAGE_RANK["completed"]
        ) else []
        return _base_result(
            decision="legacy_post",
            phase="already_target",
            reason="no_marker_on_target",
            side_effects=effects,
            mutate=False,
            effective_target=target,
        )

    if marker and marker.get("stage") == "completed" and os_release != str(target):
        return _base_result(
            decision="stale",
            phase="idle",
            reason="completed_marker_stale",
            side_effects=["claim"],
            mutate=True,
            archive=True,
            takeover=takeover,
            history_result="stale",
            effective_target=target,
        )

    marker_stage = marker.get("stage") if marker else None
    fact_rank = int(fact["fact_rank"])
    marker_rank = STAGE_RANK.get(marker_stage, -1)
    history = ""
    phase = fact["phase"]
    reboot_not_issued = fact.get("reason") == "reboot_not_issued"
    if marker_stage == "completed" and phase == "upgraded":
        phase = "completed"
    elif phase == "upgraded" and marker_stage == "verified":
        phase = "verified"
    elif (
        marker
        and marker_rank > fact_rank
        and not reboot_not_issued
        and phase not in {"upgraded", "reboot_failed"}
    ):
        phase = "prepared" if fact_rank < STAGE_RANK["downloaded"] else fact["phase"]
        history = "demoted"
    elif marker and fact_rank > marker_rank and phase in {"downloaded", "upgraded"}:
        history = "adopted"
    elif not marker and phase == "downloaded":
        history = "adopted"

    if phase == "completed":
        return _base_result(
            decision="pause",
            phase="completed",
            reason="already_completed",
            takeover=takeover,
            effective_target=target,
        )

    # done_rank 是已经有事实支撑的阶段。upgraded 只说明系统已到目标，verify 仍要跑。
    done_rank = {
        "idle": -1,
        "preflight": STAGE_RANK["preflight"],
        "prepared": STAGE_RANK["prepared"],
        "downloaded": STAGE_RANK["downloaded"],
        "upgraded": STAGE_RANK["reboot_requested"],
        "verified": STAGE_RANK["verified"],
        "completed": STAGE_RANK["completed"],
    }[phase]
    next_step = {
        "idle": "claim",
        "preflight": "prepare",
        "prepared": "download",
        "downloaded": "reboot",
        "upgraded": "verify",
        "verified": "finalize",
    }[phase]

    if done_rank >= STAGE_RANK[until]:
        return _base_result(
            decision="adopt" if history == "adopted" else ("demote" if history == "demoted" else "pause"),
            phase=phase if phase != "upgraded" else "verified",
            reason="until_reached" if not history else history,
            mutate=bool(history),
            takeover=takeover,
            history_result=history,
            effective_target=target,
        )
    reported = {
        "idle": "preflight",
        "upgraded": "verified",
    }.get(phase, phase)
    return _base_result(
        decision="adopt" if history == "adopted" else ("demote" if history == "demoted" else "advance"),
        phase=reported,
        reason=history or fact["reason"],
        side_effects=[next_step],
        mutate=True,
        takeover=takeover,
        history_result=history or "ok",
        effective_target=target,
    )


def _owner_path(lock_dir: Path) -> Path:
    return lock_dir / "owner"


def read_owner(lock_dir: Path) -> dict | None:
    path = _owner_path(lock_dir)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = Path(f'/proc/{pid}/stat')
    try:
        if stat.read_text().rsplit(')', 1)[1].split()[0] == 'Z':
            return False
    except FileNotFoundError:
        return False
    return True


def _process_start(pid: int) -> str:
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except FileNotFoundError:
        return ''


def _serialize_lock_metadata(func):
    """仅串行化 mkdir/接管的元数据窗口；全角色互斥仍由 lock.d 保持。"""
    @functools.wraps(func)
    def guarded(root: Path, *args, **kwargs):
        root.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o700)
        fd = os.open(root / '.lockguard', os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            return func(root, *args, **kwargs)
        finally:
            os.close(fd)
    return guarded


@_serialize_lock_metadata
def lock_acquire(root: Path, token: str, boot_id: str, lease_until: int, controller: str) -> dict:
    """mkdir 取得目录锁。已存在则返回 held，不覆盖 owner。"""
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    lock_dir = root / "lock.d"
    try:
        lock_dir.mkdir()
    except FileExistsError:
        owner = read_owner(lock_dir) or {}
        owner["holder_alive"] = _pid_alive(int(owner.get("holder_pid") or 0))
        return {"acquired": False, "owner": owner}
    seconds = max(1, int(lease_until) - int(time.time()))
    # 独立会话，避免 ansible script 退出时把持有者一起收走。
    holder = subprocess.Popen(  # noqa: S603 - 参数固定为 sleep
        ["sleep", str(seconds)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    payload = {
        "token": token,
        "boot_id": boot_id,
        "lease_until": int(lease_until),
        "controller": controller,
        "holder_pid": holder.pid,
        "holder_start": _process_start(holder.pid),
    }
    temp = lock_dir / "owner.tmp"
    temp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(_owner_path(lock_dir))
    return {"acquired": True, "owner": payload}


@_serialize_lock_metadata
def lock_takeover(root: Path, token: str, boot_id: str, lease_until: int, controller: str, now: int | None = None) -> dict:
    """调用方已判定锁陈旧：先改名再 mkdir。活锁拒绝接管。"""
    root.mkdir(parents=True, exist_ok=True)
    lock_dir = root / "lock.d"
    if lock_dir.exists():
        owner = read_owner(lock_dir)
        stamp = int(now if now is not None else time.time())
        if owner:
            owner["holder_alive"] = _pid_alive(int(owner.get("holder_pid") or 0))
            owner["worker_alive"] = subprocess.run(
                ["pgrep", "-x", "dnf|dnf5|rpm"], capture_output=True, check=False
            ).returncode == 0
            boot_changed = owner.get("boot_id") != boot_id
            if (owner['worker_alive'] or (_lock_is_live(owner, stamp) and not boot_changed)) and owner.get("token") != token:
                raise StateError("锁仍有效，拒绝接管")
        stale = root / f"lock.d.stale-{stamp}"
        lock_dir.replace(stale)
    acquired = lock_acquire.__wrapped__(root, token, boot_id, lease_until, controller)
    if not acquired["acquired"]:
        raise StateError("接管后仍未取得锁")
    acquired["takeover"] = True
    return acquired


def _kill_holder(owner: dict) -> None:
    pid = int(owner.get("holder_pid") or 0)
    if not _pid_alive(pid):
        return
    if not owner.get('holder_start') or _process_start(pid) != owner['holder_start']:
        return
    cmdline = ""
    cmdline_path = Path(f"/proc/{pid}/cmdline")
    if cmdline_path.exists():
        cmdline = cmdline_path.read_bytes().replace(b"\x00", b" ").decode("utf-8", "replace")
    if "sleep" not in cmdline:
        return
    os.kill(pid, signal.SIGTERM)


@_serialize_lock_metadata
def lock_refresh(root: Path, token: str, boot_id: str, lease_until: int, controller: str) -> dict:
    """同一 token 续租。不放开目录，避免刷新窗口被别人 mkdir。"""
    lock_dir = root / "lock.d"
    owner = read_owner(lock_dir) if lock_dir.exists() else None
    if not owner or owner.get("token") != token:
        raise StateError("不能刷新不属于自己的锁")
    _kill_holder(owner)
    seconds = max(1, int(lease_until) - int(time.time()))
    holder = subprocess.Popen(
        ["sleep", str(seconds)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    payload = {
        "token": token,
        "boot_id": boot_id,
        "lease_until": int(lease_until),
        "controller": controller,
        "holder_pid": holder.pid,
        "holder_start": _process_start(holder.pid),
    }
    temp = lock_dir / "owner.tmp"
    temp.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(_owner_path(lock_dir))
    return {"refreshed": True, "owner": payload}


@_serialize_lock_metadata
def lock_release(root: Path, token: str) -> dict:
    lock_dir = root / "lock.d"
    owner = read_owner(lock_dir) if lock_dir.exists() else None
    if not owner:
        return {"released": False, "reason": "absent"}
    if owner.get("token") != token:
        raise StateError("token 不匹配，拒绝释放他人的锁")
    _kill_holder(owner)
    for child in list(lock_dir.iterdir()):
        if child.is_file() or child.is_symlink():
            child.unlink()
    lock_dir.rmdir()
    return {"released": True}


def build_marker(previous: dict | None, observed: dict, stage: str, history_result: str, request: dict, now_iso: str) -> dict:
    """生成下一次要原子写入的 marker。不在这里写盘。"""
    if stage not in STAGES and stage != "abandoned":
        raise StateError(f"无法记录阶段：{stage}")
    previous = previous or {}
    seq = int(previous.get("seq") or 0) + 1
    source = str((previous.get("source") or {}).get("release") or request.get("source") or observed.get("os"))
    target = str((previous.get("target") or {}).get("release") or request.get("target"))
    operation_id = previous.get("operation_id") or new_operation_id(
        str(request.get("family") or "fedora"), source, target
    )
    evidence = dict(previous.get("evidence") or {})
    evidence.update(request.get("evidence") or {})
    history = list(previous.get("history") or [])
    history.append({"seq": seq, "stage": stage, "at": now_iso, "result": history_result, "note": request.get("note") or ""})
    if "intent" in request:
        intent = request.get("intent")
    else:
        intent = previous.get("intent")
    marker = {
        "schema": 1,
        "family": str(request.get("family") or previous.get("family") or "fedora"),
        "operation_id": operation_id,
        "seq": seq,
        "machine": {
            "id_sha256_16": observed.get("machine_id_sha256_16"),
            "hostname": observed.get("hostname") or "",
        },
        "source": {"release": source},
        "target": {"release": target},
        "created_at": previous.get("created_at") or now_iso,
        "stage": stage,
        "intent": intent,
        "evidence": evidence,
        "history": history,
        "tested_profile": request.get("tested_profile") or previous.get("tested_profile"),
    }
    return {"expect_seq": int(previous.get("seq") or 0), "marker": marker}


def marker_write(path: Path, payload: dict, expect_seq: int | None) -> dict:
    """校验 seq 后原子替换。不一致则失败，不覆盖。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    current_seq = None
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
        current_seq = int(current.get("seq") or 0)
        if expect_seq is None or current_seq != int(expect_seq):
            raise StateError(f"seq 不一致，拒绝覆盖：当前 {current_seq}，期望 {expect_seq}")
    elif expect_seq not in {None, 0}:
        raise StateError("marker 不存在，但期望 seq 不是 0")
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temp, 0o600)
    temp.replace(path)
    os.chmod(path, 0o600)
    return {"written": True, "seq": payload.get("seq")}


def _load_json(path: str | None) -> dict | None:
    if not path:
        raw = sys.stdin.read()
        if not raw.strip():
            return None
        data = json.loads(raw)
    else:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data is None:
        return None
    if not isinstance(data, dict):
        raise StateError("JSON 必须是对象")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="dist-upgrade marker 判定与目录锁")
    sub = parser.add_subparsers(dest="command", required=True)

    decide_cmd = sub.add_parser("decide")
    decide_cmd.add_argument("--observed", required=True)
    decide_cmd.add_argument("--request", required=True)
    decide_cmd.add_argument("--marker")

    acquire = sub.add_parser("lock-acquire")
    acquire.add_argument("--root", required=True)
    acquire.add_argument("--token", required=True)
    acquire.add_argument("--boot-id", required=True)
    acquire.add_argument("--lease-until", required=True, type=int)
    acquire.add_argument("--controller", required=True)

    takeover = sub.add_parser("lock-takeover")
    takeover.add_argument("--root", required=True)
    takeover.add_argument("--token", required=True)
    takeover.add_argument("--boot-id", required=True)
    takeover.add_argument("--lease-until", required=True, type=int)
    takeover.add_argument("--controller", required=True)
    takeover.add_argument("--now", type=int)

    release = sub.add_parser("lock-release")
    release.add_argument("--root", required=True)
    release.add_argument("--token", required=True)

    refresh = sub.add_parser("lock-refresh")
    refresh.add_argument("--root", required=True)
    refresh.add_argument("--token", required=True)
    refresh.add_argument("--boot-id", required=True)
    refresh.add_argument("--lease-until", required=True, type=int)
    refresh.add_argument("--controller", required=True)

    build = sub.add_parser("build-marker")
    build.add_argument("--previous")
    build.add_argument("--observed", required=True)
    build.add_argument("--request", required=True)
    build.add_argument("--stage", required=True)
    build.add_argument("--result", required=True)
    build.add_argument("--now", required=True)

    read = sub.add_parser("lock-read")
    read.add_argument("--root", required=True)

    write = sub.add_parser("marker-write")
    write.add_argument("--path", required=True)
    write.add_argument("--payload", required=True)
    write.add_argument("--expect-seq", type=int)

    args = parser.parse_args(argv)
    try:
        if args.command == "decide":
            observed = _load_json(args.observed) or {}
            request = _load_json(args.request) or {}
            marker = _load_json(args.marker) if args.marker else None
            sys.stdout.write(json.dumps(decide(observed, marker, request), ensure_ascii=False, sort_keys=True) + "\n")
        elif args.command == "lock-acquire":
            sys.stdout.write(json.dumps(lock_acquire(Path(args.root), args.token, args.boot_id, args.lease_until, args.controller), sort_keys=True) + "\n")
        elif args.command == "lock-takeover":
            sys.stdout.write(
                json.dumps(
                    lock_takeover(Path(args.root), args.token, args.boot_id, args.lease_until, args.controller, args.now),
                    sort_keys=True,
                )
                + "\n"
            )
        elif args.command == "lock-release":
            sys.stdout.write(json.dumps(lock_release(Path(args.root), args.token), sort_keys=True) + "\n")
        elif args.command == "lock-refresh":
            sys.stdout.write(
                json.dumps(
                    lock_refresh(Path(args.root), args.token, args.boot_id, args.lease_until, args.controller),
                    sort_keys=True,
                )
                + "\n"
            )
        elif args.command == "build-marker":
            previous = _load_json(args.previous) if args.previous else None
            observed = _load_json(args.observed) or {}
            request = _load_json(args.request) or {}
            sys.stdout.write(json.dumps(build_marker(previous, observed, args.stage, args.result, request, args.now), ensure_ascii=False, sort_keys=True) + "\n")
        elif args.command == "lock-read":
            owner = read_owner(Path(args.root) / "lock.d")
            if owner:
                owner["holder_alive"] = _pid_alive(int(owner.get("holder_pid") or 0))
            elif (Path(args.root) / 'lock.d').exists():
                owner = {'token':'unpublished','lease_until':0,'holder_alive':False}
            sys.stdout.write(json.dumps({"owner": owner}, sort_keys=True) + "\n")
        elif args.command == "marker-write":
            payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
            sys.stdout.write(json.dumps(marker_write(Path(args.path), payload, args.expect_seq), sort_keys=True) + "\n")
    except (StateError, OSError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""读取 Fedora 升级事实。只打印 JSON，不修改系统。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path


OFFLINE_DIR = Path("/usr/lib/sysimage/libdnf5/offline")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, check=False, text=True, capture_output=True, timeout=120)


def _find_releasever(text: str) -> str | None:
    for line in text.splitlines():
        lowered = line.strip().lower()
        if lowered.startswith("releasever"):
            return line.split(":", 1)[-1].strip().strip('"')
    return None


def _hash_offline() -> str | None:
    if not OFFLINE_DIR.is_dir():
        return None
    files = sorted(path for path in OFFLINE_DIR.rglob("*") if path.is_file())
    if not files:
        return None
    digest = hashlib.sha256()
    for path in files:
        digest.update(str(path.relative_to(OFFLINE_DIR)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _toml_value(text: str, key: str) -> str | None:
    matched = re.search(rf'^{re.escape(key)}\s*=\s*"([^"]*)"', text, re.MULTILINE)
    if matched:
        return matched.group(1)
    matched = re.search(rf"^{re.escape(key)}\s*=\s*'([^']*)'", text, re.MULTILINE)
    if matched:
        return matched.group(1)
    matched = re.search(rf"^{re.escape(key)}\s*=\s*([^\s#]+)", text, re.MULTILINE)
    return matched.group(1) if matched else None


def _pending() -> tuple[dict | None, str]:
    """直接读取 dnf5 状态，避免 status 子命令创建离线目录。"""
    state_path = OFFLINE_DIR / "offline-transaction-state.toml"
    if not state_path.exists():
        return None, "No offline transaction state file."
    state_text = state_path.read_text(encoding="utf-8")
    data = tomllib.loads(state_text)["offline-transaction-state"]
    status = data["status"]
    if status == "download-incomplete":
        return None, status
    if status not in {"download-complete", "ready", "transaction-incomplete"}:
        raise ValueError(f"未知离线事务状态：{status}")
    release = str(data["target_releasever"])
    if not release.isdigit():
        raise ValueError("离线事务没有纯数字 target_releasever")
    return {"releasever": release, "sha256": _hash_offline(), "status": status}, status


def _duplicates() -> bool:
    """内核等 installonly 包本来就可以并存。只把其余重复包当成异常。"""
    try:
        result = _run(["rpm", "-qa", "--qf", "%{NAME} %{ARCH} [%{PROVIDENAME} ]\n"])
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise RuntimeError("无法读取 rpm 数据库，拒绝将探测失败当成健康")
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    counted: dict[tuple[str, str], int] = {}
    for line in result.stdout.splitlines():
        row = line.split()
        if len(row) < 2:
            continue
        if row[0] == 'gpg-pubkey':
            continue
        if any(provide.startswith('installonlypkg(') for provide in row[2:]):
            continue
        key = (row[0], row[1])
        counted[key] = counted.get(key, 0) + 1
    return any(count > 1 for count in counted.values())


def _first_json(text: str) -> dict:
    """ansible script 可能在 JSON 后附加控制字符。只解析第一段对象。"""
    decoder = json.JSONDecoder()
    payload, _ = decoder.raw_decode(text.lstrip())
    if not isinstance(payload, dict):
        raise ValueError("探测结果不是 JSON 对象")
    return payload


def main() -> None:
    os_release: dict[str, str] = {}
    for line in _read(Path("/etc/os-release")).splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        os_release[key] = value.strip().strip('"')
    machine_id = _read(Path("/etc/machine-id"))
    if not re.fullmatch('[0-9a-fA-F]{32}', machine_id):
        raise ValueError("machine-id 为空或非法，拒绝 claim")
    pending, status_text = _pending()
    check_text = ""
    check_abnormal = False
    check_abnormal = bool(pending and pending["status"] == "transaction-incomplete")
    payload = {
        "os": os_release.get("VERSION_ID") or "",
        "hostname": _read(Path("/etc/hostname")) if Path("/etc/hostname").is_file() else "",
        "boot_id": _read(Path("/proc/sys/kernel/random/boot_id")),
        "machine_id_sha256_16": hashlib.sha256(machine_id.encode("utf-8")).hexdigest()[:16],
        "kernel": os.uname().release,
        "pending": pending,
        "rpm_abnormal": _duplicates(),
        "dnf_check_abnormal": check_abnormal,
        "offline_status": status_text,
        "failed_units": [],
    }
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

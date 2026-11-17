#!/usr/bin/env python3
"""libvirt 测试驱动的固件与镜像发现。

只打印一行 JSON。失败时向 stderr 写原因并以状态 2 退出。
不回退到 BIOS，不猜测多条命中。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from pathlib import Path


class DiscoverError(Exception):
    """发现结果不可用。"""


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def discover_firmware(firmware_dir: Path) -> dict:
    """从 *-nosb.json 中选出唯一的 x86_64 4M split flash UEFI 固件。"""
    if not firmware_dir.is_dir():
        raise DiscoverError(f"固件描述目录不存在：{firmware_dir}")
    matches: list[dict] = []
    for path in sorted(firmware_dir.glob("*-nosb.json")):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DiscoverError(f"无法解析固件描述 {path}: {exc}") from exc
        mapping = spec.get("mapping") or {}
        executable = mapping.get("executable") or {}
        nvram = mapping.get("nvram-template") or {}
        targets = spec.get("targets") or []
        arches = {item.get("architecture") for item in targets if isinstance(item, dict)}
        machines: list[str] = []
        for item in targets:
            if isinstance(item, dict):
                machines.extend(item.get("machines") or [])
        features = set(spec.get("features") or [])
        code_name = str(executable.get("filename") or "")
        vars_name = str(nvram.get("filename") or "")
        if "uefi" not in (spec.get("interface-types") or []):
            continue
        if mapping.get("device") != "flash" or mapping.get("mode") != "split":
            continue
        if "x86_64" not in arches:
            continue
        if not any(machine.startswith("pc-q35-") or machine == "pc-q35-*" for machine in machines):
            continue
        if "secure-boot" in features:
            continue
        if "4M" not in code_name and "4M" not in vars_name:
            continue
        if not executable.get("format") or not nvram.get("format"):
            continue
        matches.append(
            {
                "description": str(path),
                "loader": code_name,
                "loader_format": str(executable.get("format")),
                "nvram_template": vars_name,
                "nvram_format": str(nvram.get("format")),
            }
        )
    if len(matches) != 1:
        raise DiscoverError(
            f"{firmware_dir} 中符合 x86_64/4M/nosb/q35 的 UEFI 描述不是唯一一项：{matches}"
        )
    chosen = matches[0]
    for key in ("loader", "nvram_template"):
        if not Path(chosen[key]).is_file():
            raise DiscoverError(f"固件文件不存在：{chosen[key]}")
    return chosen


_QCOW_HREF = re.compile(r'href="([^"]+\.qcow2)"')
_SHA512_LINE = re.compile(r"^([0-9a-fA-F]{128})\s+\*?(\S+)\s*$")
_BSD_SHA256 = re.compile(r"^SHA256 \(([^)]+)\) = ([0-9a-fA-F]{64})\s*$", re.MULTILINE)


def debian_image_names(index_html: str, pattern: str) -> list[str]:
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise DiscoverError(f"镜像名模式非法：{exc}") from exc
    names = sorted(set(_QCOW_HREF.findall(index_html)))
    return [name for name in names if compiled.fullmatch(name)]


def debian_sha512(text: str, filename: str) -> list[str]:
    found: list[str] = []
    for line in text.splitlines():
        match = _SHA512_LINE.match(line.strip())
        if match and match.group(2) == filename:
            found.append(match.group(1).lower())
    return found


def fedora_checksum_filename(index_html: str, release: str) -> list[str]:
    """目录里的校验文件不是固定的 CHECKSUM，而是 Fedora-Cloud-<release>-<点版本>-x86_64-CHECKSUM。"""
    if not str(release).isdigit():
        raise DiscoverError(f"Fedora release 必须是纯数字，实际 {release}")
    pattern = re.compile(rf'Fedora-Cloud-{release}-[0-9.]+-x86_64-CHECKSUM')
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.names = set()

        def handle_starttag(self, tag, attrs):
            if tag.lower() != 'a':
                return
            href = dict(attrs).get('href') or ''
            name = unquote(urlsplit(href).path.rsplit('/', 1)[-1])
            if pattern.fullmatch(name):
                self.names.add(name)

    links = Links()
    links.feed(index_html)
    return sorted(links.names)


def fedora_checksum_names(text: str, pattern: str) -> list[dict[str, str]]:
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise DiscoverError(f"镜像名模式非法：{exc}") from exc
    found: list[dict[str, str]] = []
    for name, digest in _BSD_SHA256.findall(text):
        if compiled.fullmatch(name):
            found.append({"filename": name, "sha256": digest.lower()})
    return found


def parse_local_manifest(text: str) -> dict:
    """校验票 01/05 约定的 local-manifest。摘要比对由调用方对镜像文件执行。"""
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - 运行环境保证有 pyyaml
        raise DiscoverError("缺少 PyYAML，无法读取 manifest") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DiscoverError(f"manifest 不是合法 YAML：{exc}") from exc
    if not isinstance(data, dict):
        raise DiscoverError("manifest 必须是映射")
    required = ("schema", "sha256", "built_at", "source", "os", "version", "uefi", "builder")
    missing = [key for key in required if key not in data]
    if missing:
        raise DiscoverError(f"manifest 缺少字段：{missing}")
    if data["schema"] != 1:
        raise DiscoverError(f"manifest schema 必须为 1，实际 {data['schema']}")
    digest = str(data["sha256"])
    if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        raise DiscoverError("manifest sha256 不是 64 位十六进制")
    if data["uefi"] is not True:
        raise DiscoverError("manifest uefi 必须为 true，拒绝非 UEFI 镜像")
    if not isinstance(data["source"], dict) or not data["source"]:
        raise DiscoverError("manifest source 必须是非空映射")
    if not isinstance(data["builder"], dict) or not data["builder"]:
        raise DiscoverError("manifest builder 必须是非空映射")
    if not str(data["os"]).strip() or str(data["version"]).strip() == "":
        raise DiscoverError("manifest os/version 不能为空")
    if not str(data["built_at"]).strip():
        raise DiscoverError("manifest built_at 不能为空")
    data["sha256"] = digest.lower()
    data["version"] = str(data["version"])
    return data


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_text(args: argparse.Namespace) -> str:
    if args.file:
        return Path(args.file).read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def _cmd_firmware(args: argparse.Namespace) -> None:
    _emit(discover_firmware(Path(args.dir)))


def _cmd_debian_names(args: argparse.Namespace) -> None:
    names = debian_image_names(_read_text(args), args.pattern)
    if len(names) != 1:
        raise DiscoverError(f"Debian 目录中匹配 {args.pattern} 的 qcow2 不是唯一一项：{names}")
    _emit({"filename": names[0]})


def _cmd_debian_sha512(args: argparse.Namespace) -> None:
    found = debian_sha512(_read_text(args), args.name)
    if len(found) != 1:
        raise DiscoverError(f"SHA512SUMS 中 {args.name} 的摘要不是唯一一项：{found}")
    _emit({"filename": args.name, "sha512": found[0]})


def _cmd_fedora_checksum_name(args: argparse.Namespace) -> None:
    found = fedora_checksum_filename(_read_text(args), args.release)
    if len(found) != 1:
        raise DiscoverError(f"目录中 Fedora {args.release} 的 CHECKSUM 不是唯一一项：{found}")
    _emit({"filename": found[0]})


def _cmd_fedora_checksum(args: argparse.Namespace) -> None:
    found = fedora_checksum_names(_read_text(args), args.pattern)
    if len(found) != 1:
        raise DiscoverError(f"CHECKSUM 中匹配 {args.pattern} 的条目不是唯一一项：{found}")
    _emit(found[0])


def _cmd_local_manifest(args: argparse.Namespace) -> None:
    image = Path(args.image)
    manifest = Path(args.manifest) if args.manifest else Path(str(image) + ".manifest.yml")
    if not image.is_file():
        raise DiscoverError(f"镜像不存在：{image}")
    if not manifest.is_file():
        raise DiscoverError(f"manifest 不存在：{manifest}")
    parsed = parse_local_manifest(manifest.read_text(encoding="utf-8"))
    actual = file_sha256(image)
    if actual != parsed["sha256"]:
        raise DiscoverError(f"manifest 摘要不符。期望 {parsed['sha256']}，实际 {actual}")
    _emit(
        {
            "filename": image.name,
            "image": str(image),
            "manifest": str(manifest),
            "sha256": actual,
            "os": parsed["os"],
            "version": parsed["version"],
            "uefi": True,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="发现 UEFI 固件与测试镜像")
    sub = parser.add_subparsers(dest="command", required=True)

    firmware = sub.add_parser("firmware")
    firmware.add_argument("--dir", required=True)
    firmware.set_defaults(func=_cmd_firmware)

    debian_names = sub.add_parser("debian-names")
    debian_names.add_argument("--pattern", required=True)
    debian_names.add_argument("--file")
    debian_names.set_defaults(func=_cmd_debian_names)

    debian_sha = sub.add_parser("debian-sha512")
    debian_sha.add_argument("--name", required=True)
    debian_sha.add_argument("--file")
    debian_sha.set_defaults(func=_cmd_debian_sha512)

    fedora_name = sub.add_parser("fedora-checksum-name")
    fedora_name.add_argument("--release", required=True)
    fedora_name.add_argument("--file")
    fedora_name.set_defaults(func=_cmd_fedora_checksum_name)

    fedora = sub.add_parser("fedora-checksum")
    fedora.add_argument("--pattern", required=True)
    fedora.add_argument("--file")
    fedora.set_defaults(func=_cmd_fedora_checksum)

    manifest = sub.add_parser("local-manifest")
    manifest.add_argument("--image", required=True)
    manifest.add_argument("--manifest")
    manifest.set_defaults(func=_cmd_local_manifest)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except DiscoverError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

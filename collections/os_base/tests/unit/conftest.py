from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from jinja2 import Environment, FileSystemLoader


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEBIAN_REPO_TEMPLATES = PROJECT_ROOT / "roles" / "debian_repo" / "templates"
DEBIAN_DIST_UPGRADE_VARS = PROJECT_ROOT / "roles" / "debian_dist_upgrade" / "vars" / "main.yml"
DEBIAN_DIST_UPGRADE_DEFAULTS = PROJECT_ROOT / "roles" / "debian_dist_upgrade" / "defaults" / "main.yml"
FEDORA_DIST_UPGRADE_DEFAULTS = PROJECT_ROOT / "roles" / "fedora_dist_upgrade" / "defaults" / "main.yml"


@pytest.fixture(scope="session")
def jinja_env() -> Environment:
    loader = FileSystemLoader(str(DEBIAN_REPO_TEMPLATES))
    env = Environment(loader=loader, autoescape=False)

    def _version_test(actual: str, expected: str, operator: str) -> bool:
        def _parse(v: str) -> tuple:
            parts = v.strip().split(".")
            return tuple(int(p) for p in parts)

        a = _parse(actual)
        b = _parse(expected)

        if operator in ("==", "eq"):
            return a == b
        if operator in ("!=", "ne"):
            return a != b
        if operator in (">", "gt"):
            return a > b
        if operator in (">=", "ge"):
            return a >= b
        if operator in ("<", "lt"):
            return a < b
        if operator in ("<=", "le"):
            return a <= b
        msg = f"Unsupported operator: {operator}"
        raise ValueError(msg)

    env.tests["version"] = _version_test
    return env


@pytest.fixture
def base_context() -> dict:
    return {
        "debian_repo_mirror_list": [
            "mirrors.tencent.com",
            "mirrors.ustc.edu.cn",
        ],
        "debian_repo_apt_mirror": "deb.debian.org",
        "debian_repo_apt_security_mirror": "security.debian.org",
        "debian_repo_enable_testing": False,
        "debian_repo_enable_unstable": False,
        "debian_repo_set_apt_src_repo": False,
        # debian_repo 目标版本契约变量（由 debian_dist_upgrade include_role vars 注入）
        "debian_repo_target_codename": "trixie",
        "debian_repo_target_major_version": "13",
        "ansible_facts": {
            "distribution_release": "trixie",
        },
        "debian_version": "13",
    }


@pytest.fixture(scope="session")
def debian_codename_map() -> dict:
    with open(DEBIAN_DIST_UPGRADE_VARS, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["debian_dist_upgrade_codename_map"]


@pytest.fixture(scope="session")
def debian_defaults() -> dict:
    with open(DEBIAN_DIST_UPGRADE_DEFAULTS, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="session")
def fedora_defaults() -> dict:
    with open(FEDORA_DIST_UPGRADE_DEFAULTS, encoding="utf-8") as f:
        return yaml.safe_load(f)

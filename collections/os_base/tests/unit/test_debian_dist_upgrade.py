from __future__ import annotations

import pytest


class TestCodenameMap:
    def test_has_all_expected_entries(self, debian_codename_map: dict):
        assert "11" in debian_codename_map
        assert "12" in debian_codename_map
        assert "13" in debian_codename_map
        assert "14" in debian_codename_map

    def test_correct_values(self, debian_codename_map: dict):
        assert debian_codename_map["10"] == "buster"
        assert debian_codename_map["11"] == "bullseye"
        assert debian_codename_map["12"] == "bookworm"
        assert debian_codename_map["13"] == "trixie"
        assert debian_codename_map["14"] == "forky"

    def test_monotonic_increasing(self, debian_codename_map: dict):
        versions = sorted(int(k) for k in debian_codename_map)
        for i in range(len(versions) - 1):
            assert versions[i + 1] == versions[i] + 1


class TestDefaults:
    def test_source_version_from_facts(self, debian_defaults: dict):
        tmpl = debian_defaults["debian_dist_upgrade_source_version"]
        assert "distribution_major_version" in tmpl

    def test_target_version_is_plus_one(self, debian_defaults: dict):
        tmpl = debian_defaults["debian_dist_upgrade_target_version"]
        assert "int + 1" in tmpl

    def test_skip_reboot_default_true(self, debian_defaults: dict):
        assert debian_defaults["debian_dist_upgrade_skip_reboot"] is True


class TestTemplateRenderingCN:
    _TEMPLATE = "sources-debian-cn.sources.j2"

    def test_suites_use_trixie(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template(self._TEMPLATE).render(base_context)
        assert "trixie" in rendered
        assert "bookworm" not in rendered

    def test_security_suite_is_trixie_security(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template(self._TEMPLATE).render(base_context)
        assert "trixie-security" in rendered

    def test_backports_not_present(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template(self._TEMPLATE).render(base_context)
        assert "backports" not in rendered

    def test_includes_non_free_firmware(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template(self._TEMPLATE).render(base_context)
        assert "non-free-firmware" in rendered

    def test_mirror_list_expanded(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template(self._TEMPLATE).render(base_context)
        assert rendered.count("Types: deb") == 4

    def test_signed_by_present(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template(self._TEMPLATE).render(base_context)
        assert "Signed-By:" in rendered

    def test_testing_and_unstable_absent(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template(self._TEMPLATE).render(base_context)
        assert "testing" not in rendered
        assert "unstable" not in rendered


class TestTemplateRenderingOfficial:
    _TEMPLATE = "sources-debian.sources.j2"

    def test_suites_use_trixie(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template(self._TEMPLATE).render(base_context)
        assert "trixie" in rendered
        assert "bookworm" not in rendered

    def test_uses_official_mirrors(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template(self._TEMPLATE).render(base_context)
        assert "deb.debian.org" in rendered
        assert "security.debian.org" in rendered

    def test_signed_by_present(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template(self._TEMPLATE).render(base_context)
        assert "Signed-By:" in rendered


class TestFormatSelection:
    def test_version_13_uses_deb822(self, jinja_env, base_context: dict):
        rendered = jinja_env.get_template("sources-debian-cn.sources.j2").render(base_context)
        assert "Types: deb" in rendered
        assert "Suites:" in rendered
        assert "Components:" in rendered
        assert "Signed-By:" in rendered

    def test_version_12_uses_legacy(self, jinja_env):
        ctx = {
            "debian_repo_mirror_list": ["mirrors.tencent.com"],
            "debian_repo_apt_mirror": "deb.debian.org",
            "debian_repo_apt_security_mirror": "security.debian.org",
            "debian_repo_enable_testing": False,
            "debian_repo_enable_unstable": False,
            "debian_repo_set_apt_src_repo": False,
            # debian_repo 目标版本契约变量
            "debian_repo_target_codename": "bookworm",
            "debian_repo_target_major_version": "12",
            "ansible_facts": {"distribution_release": "bookworm"},
            "debian_version": "12",
        }
        rendered = jinja_env.get_template("sources-debian-cn.list.j2").render(ctx)
        assert "deb https" in rendered
        assert "Types: deb" not in rendered


class TestValidateLogic:
    def test_target_codename_defined(self, debian_codename_map: dict):
        for current_ver_str, _ in [
            ("11", "bookworm"),
            ("12", "trixie"),
        ]:
            target_ver = str(int(current_ver_str) + 1)
            assert target_ver in debian_codename_map


class TestFedoraSkipReboot:
    def test_fedora_skip_reboot_default_true(self, fedora_defaults: dict):
        assert fedora_defaults["fedora_dist_upgrade_skip_reboot"] is True


class TestIdempotency:
    def test_rerender_produces_same_output(self, jinja_env, base_context: dict):
        first = jinja_env.get_template("sources-debian-cn.sources.j2").render(base_context)
        second = jinja_env.get_template("sources-debian-cn.sources.j2").render(base_context)
        assert first == second

    def test_rerender_official_produces_same_output(self, jinja_env, base_context: dict):
        first = jinja_env.get_template("sources-debian.sources.j2").render(base_context)
        second = jinja_env.get_template("sources-debian.sources.j2").render(base_context)
        assert first == second


class TestDefaultsCompleteness:
    REQUIRED_DEBIAN_KEYS = [
        "debian_dist_upgrade_target_version",
        "debian_dist_upgrade_target_codename",
        "debian_dist_upgrade_source_version",
        "debian_dist_upgrade_source_codename",
        "debian_dist_upgrade_skip_reboot",
    ]

    def test_debian_has_all_required_vars(self, debian_defaults: dict):
        for key in self.REQUIRED_DEBIAN_KEYS:
            assert key in debian_defaults

    REQUIRED_FEDORA_KEYS = [
        "fedora_dist_upgrade_target_release",
        "fedora_dist_upgrade_needs_upgrade",
        "fedora_dist_upgrade_skip_reboot",
        "fedora_dist_upgrade_download_retries",
    ]

    def test_fedora_has_all_required_vars(self, fedora_defaults: dict):
        for key in self.REQUIRED_FEDORA_KEYS:
            assert key in fedora_defaults

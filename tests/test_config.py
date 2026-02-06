"""Tests for proxy server configuration."""

from __future__ import annotations

from pathlib import Path

from third_wheel.server.config import (
    PatchRule,
    ProxyConfig,
    RenameRule,
    load_config,
    parse_rename_arg,
)


class TestPatchRule:
    """Test PatchRule dataclass."""

    def test_basic_creation(self) -> None:
        rule = PatchRule(package="anemoi-datasets", old_dep="zarr", new_dep="zarr_v2")
        assert rule.package == "anemoi-datasets"
        assert rule.old_dep == "zarr"
        assert rule.new_dep == "zarr_v2"
        assert rule.version_spec is None

    def test_with_version_spec(self) -> None:
        rule = PatchRule(
            package="anemoi-datasets",
            old_dep="zarr",
            new_dep="zarr_v2",
            version_spec="==0.5.31",
        )
        assert rule.version_spec == "==0.5.31"


class TestProxyConfigGetPatchRule:
    """Test ProxyConfig.get_patch_rule() method."""

    def test_exact_match(self) -> None:
        config = ProxyConfig(
            patches=[PatchRule(package="anemoi-datasets", old_dep="zarr", new_dep="zarr_v2")]
        )
        rule = config.get_patch_rule("anemoi-datasets")
        assert rule is not None
        assert rule.old_dep == "zarr"

    def test_normalized_match_underscore(self) -> None:
        """PEP 503: underscores, hyphens, and dots are equivalent."""
        config = ProxyConfig(
            patches=[PatchRule(package="anemoi-datasets", old_dep="zarr", new_dep="zarr_v2")]
        )
        rule = config.get_patch_rule("anemoi_datasets")
        assert rule is not None

    def test_normalized_match_case(self) -> None:
        config = ProxyConfig(
            patches=[PatchRule(package="anemoi-datasets", old_dep="zarr", new_dep="zarr_v2")]
        )
        rule = config.get_patch_rule("Anemoi-Datasets")
        assert rule is not None

    def test_no_match(self) -> None:
        config = ProxyConfig(
            patches=[PatchRule(package="anemoi-datasets", old_dep="zarr", new_dep="zarr_v2")]
        )
        assert config.get_patch_rule("other-package") is None

    def test_empty_patches(self) -> None:
        config = ProxyConfig()
        assert config.get_patch_rule("anything") is None


class TestLoadConfigPatches:
    """Test load_config with [patches] TOML section."""

    def test_load_patches_from_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("""\
[proxy]
host = "0.0.0.0"
port = 9000

[[proxy.upstreams]]
url = "https://pypi.org/simple/"

[patches]
anemoi-datasets = { old_dep = "zarr", new_dep = "zarr_v2" }
""")
        cfg = load_config(config_path=config_file)

        assert cfg.host == "0.0.0.0"
        assert cfg.port == 9000
        assert len(cfg.patches) == 1
        assert cfg.patches[0].package == "anemoi-datasets"
        assert cfg.patches[0].old_dep == "zarr"
        assert cfg.patches[0].new_dep == "zarr_v2"

    def test_load_patches_with_version(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("""\
[proxy]
[[proxy.upstreams]]
url = "https://pypi.org/simple/"

[patches]
anemoi-datasets = { old_dep = "zarr", new_dep = "zarr_v2", version = "==0.5.31" }
""")
        cfg = load_config(config_path=config_file)

        assert cfg.patches[0].version_spec == "==0.5.31"

    def test_load_multiple_patches(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.toml"
        config_file.write_text("""\
[proxy]
[[proxy.upstreams]]
url = "https://pypi.org/simple/"

[patches]
anemoi-datasets = { old_dep = "zarr", new_dep = "zarr_v2" }
other-pkg = { old_dep = "numpy", new_dep = "numpy_v1" }
""")
        cfg = load_config(config_path=config_file)

        assert len(cfg.patches) == 2
        packages = {p.package for p in cfg.patches}
        assert packages == {"anemoi-datasets", "other-pkg"}

    def test_load_patches_and_renames(self, tmp_path: Path) -> None:
        """Patches and renames can coexist in the same config."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""\
[proxy]
[[proxy.upstreams]]
url = "https://pypi.org/simple/"

[renames]
zarr = { name = "zarr_v2", version = "<=2.18.7" }

[patches]
anemoi-datasets = { old_dep = "zarr", new_dep = "zarr_v2" }
""")
        cfg = load_config(config_path=config_file)

        assert len(cfg.renames) == 1
        assert cfg.renames[0].original == "zarr"
        assert cfg.renames[0].new_name == "zarr_v2"

        assert len(cfg.patches) == 1
        assert cfg.patches[0].package == "anemoi-datasets"

    def test_cli_host_port_override(self, tmp_path: Path) -> None:
        """CLI host/port=None should NOT override config file values."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""\
[proxy]
host = "0.0.0.0"
port = 9000

[[proxy.upstreams]]
url = "https://pypi.org/simple/"
""")
        # Simulate CLI with defaults of None (not set)
        cfg = load_config(config_path=config_file, host=None, port=None)

        assert cfg.host == "0.0.0.0"
        assert cfg.port == 9000

    def test_cli_host_port_explicit_override(self, tmp_path: Path) -> None:
        """Explicit CLI host/port should override config file values."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("""\
[proxy]
host = "0.0.0.0"
port = 9000

[[proxy.upstreams]]
url = "https://pypi.org/simple/"
""")
        cfg = load_config(config_path=config_file, host="127.0.0.1", port=8080)

        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8080

    def test_no_config_file(self) -> None:
        """Loading without a config file returns defaults."""
        cfg = load_config()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8000
        assert cfg.patches == []
        assert cfg.renames == []


class TestParseRenameArg:
    """Test parse_rename_arg for completeness."""

    def test_basic(self) -> None:
        rule = parse_rename_arg("icechunk=icechunk_v1")
        assert rule.original == "icechunk"
        assert rule.new_name == "icechunk_v1"
        assert rule.version_spec is None

    def test_with_version(self) -> None:
        rule = parse_rename_arg("icechunk=icechunk_v1:<2")
        assert rule.original == "icechunk"
        assert rule.new_name == "icechunk_v1"
        assert rule.version_spec == "<2"

    def test_invalid_format(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="Invalid rename format"):
            parse_rename_arg("no-equals-sign")


class TestProxyConfigVirtualPackages:
    """Test get_virtual_packages includes only renames, not patches."""

    def test_virtual_packages_from_renames(self) -> None:
        config = ProxyConfig(
            renames=[RenameRule(original="zarr", new_name="zarr_v2")],
            patches=[PatchRule(package="anemoi-datasets", old_dep="zarr", new_dep="zarr_v2")],
        )
        virtual = config.get_virtual_packages()
        assert "zarr_v2" in virtual
        # Patched packages are not virtual — they keep their original name
        assert "anemoi-datasets" not in virtual

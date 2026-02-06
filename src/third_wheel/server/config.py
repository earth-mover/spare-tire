"""Configuration management for the proxy server."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003 - used at runtime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


def _normalize_name(name: str) -> str:
    """Normalize a package name according to PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


@dataclass
class RenameRule:
    """A rule for renaming a package."""

    original: str
    """Original package name (e.g., 'icechunk')."""

    new_name: str
    """New package name (e.g., 'icechunk_v1')."""

    version_spec: str | None = None
    """Optional PEP 440 version specifier (e.g., '<2')."""


@dataclass
class PatchRule:
    """A rule for patching dependency references in a package."""

    package: str
    """Package to patch (e.g., 'anemoi-datasets')."""

    old_dep: str
    """Dependency name to replace (e.g., 'zarr')."""

    new_dep: str
    """Replacement dependency name (e.g., 'zarr_v2')."""

    version_spec: str | None = None
    """Optional PEP 440 version specifier for the package to patch (e.g., '==0.5.31')."""


@dataclass
class ProxyConfig:
    """Configuration for the proxy server."""

    host: str = "127.0.0.1"
    """Host to bind to."""

    port: int = 8000
    """Port to listen on."""

    upstreams: list[str] = field(default_factory=list)
    """Upstream index URLs in priority order."""

    renames: list[RenameRule] = field(default_factory=list)
    """Package rename rules."""

    patches: list[PatchRule] = field(default_factory=list)
    """Package patch rules."""

    def get_patch_rule(self, package: str) -> PatchRule | None:
        """Get the patch rule for a package name."""
        normalized = _normalize_name(package)
        for rule in self.patches:
            if _normalize_name(rule.package) == normalized:
                return rule
        return None

    def get_rename_rule(self, new_name: str) -> RenameRule | None:
        """Get the rename rule for a virtual package name.

        Handles PEP 503 name normalization (icechunk_v1 == icechunk-v1).
        """
        normalized = _normalize_name(new_name)
        for rule in self.renames:
            if _normalize_name(rule.new_name) == normalized:
                return rule
        return None

    def get_original_for_renamed(self, new_name: str) -> str | None:
        """Get the original package name for a renamed package."""
        rule = self.get_rename_rule(new_name)
        return rule.original if rule else None

    def is_renamed_package(self, name: str) -> bool:
        """Check if a package name is a renamed virtual package.

        Handles PEP 503 name normalization.
        """
        return self.get_rename_rule(name) is not None

    def get_virtual_packages(self) -> list[str]:
        """Get list of virtual package names from rename rules."""
        return [rule.new_name for rule in self.renames]


def parse_rename_arg(arg: str) -> RenameRule:
    """Parse a rename argument in format 'original=new_name:version_spec'.

    Examples:
        'icechunk=icechunk_v1' -> RenameRule('icechunk', 'icechunk_v1', None)
        'icechunk=icechunk_v1:<2' -> RenameRule('icechunk', 'icechunk_v1', '<2')
    """
    if "=" not in arg:
        msg = f"Invalid rename format: {arg!r}. Expected 'original=new_name[:version]'"
        raise ValueError(msg)

    original, rest = arg.split("=", 1)

    if ":" in rest:
        new_name, version_spec = rest.split(":", 1)
    else:
        new_name = rest
        version_spec = None

    return RenameRule(
        original=original.strip(),
        new_name=new_name.strip(),
        version_spec=version_spec.strip() if version_spec else None,
    )


def load_config(
    config_path: Path | None = None,
    upstreams: Sequence[str] | None = None,
    renames: Sequence[str] | None = None,
    host: str | None = None,
    port: int | None = None,
) -> ProxyConfig:
    """Load configuration from file and CLI overrides.

    Args:
        config_path: Optional path to TOML config file
        upstreams: CLI upstream URLs (override config)
        renames: CLI rename rules as 'original=new_name:version' strings
        host: CLI host override
        port: CLI port override

    Returns:
        ProxyConfig with merged settings
    """
    config = ProxyConfig()

    # Load from config file if provided
    if config_path is not None:
        with config_path.open("rb") as f:
            data = tomllib.load(f)

        proxy_section = data.get("proxy", {})
        config.host = proxy_section.get("host", config.host)
        config.port = proxy_section.get("port", config.port)

        # Load upstreams
        for upstream in proxy_section.get("upstreams", []):
            if isinstance(upstream, dict):
                config.upstreams.append(upstream["url"])
            else:
                config.upstreams.append(upstream)

        # Load renames
        renames_section = data.get("renames", {})
        for original, rename_config in renames_section.items():
            if isinstance(rename_config, dict):
                config.renames.append(
                    RenameRule(
                        original=original,
                        new_name=rename_config["name"],
                        version_spec=rename_config.get("version"),
                    )
                )
            else:
                # Simple format: original = "new_name"
                config.renames.append(RenameRule(original=original, new_name=rename_config))

        # Load patches
        patches_section = data.get("patches", {})
        for package, patch_config in patches_section.items():
            if isinstance(patch_config, dict):
                config.patches.append(
                    PatchRule(
                        package=package,
                        old_dep=patch_config["old_dep"],
                        new_dep=patch_config["new_dep"],
                        version_spec=patch_config.get("version"),
                    )
                )

    # Apply CLI overrides
    if upstreams:
        config.upstreams = list(upstreams)

    if renames:
        config.renames = [parse_rename_arg(r) for r in renames]

    if host is not None:
        config.host = host

    if port is not None:
        config.port = port

    return config

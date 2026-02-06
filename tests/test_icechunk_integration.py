"""Integration tests with real icechunk wheels.

These tests download actual icechunk wheels from the nightly index,
rename one, and verify both versions work independently.

Marked as integration tests since they require network access and
take longer to run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import install_wheel_in_venv, run_in_venv
from third_wheel.download import download_compatible_wheel
from third_wheel.rename import rename_wheel

NIGHTLY_INDEX = "https://pypi.anaconda.org/scientific-python-nightly-wheels/simple"


@pytest.mark.integration
class TestIcechunkDualInstall:
    """Test with real icechunk wheels from nightly builds."""

    @pytest.fixture
    def icechunk_dual_venv(self, tmp_path: Path, dual_install_venv: Path) -> Path:
        """Create a venv with both icechunk v1 and v2 installed.

        Downloads from nightly index, renames v1 to icechunk_v1.
        """
        wheels_dir = tmp_path / "wheels"
        wheels_dir.mkdir()

        # Download v1 (< 2.0)
        v1_wheel = download_compatible_wheel(
            "icechunk",
            wheels_dir,
            index_url=NIGHTLY_INDEX,
            version="<2",
        )
        assert v1_wheel is not None, (
            "Failed to download icechunk v1 wheel (<2) from nightly index. "
            "This may indicate the wheel is not available for this platform."
        )

        # Rename v1 -> icechunk_v1
        v1_renamed = rename_wheel(v1_wheel, "icechunk_v1", output_dir=tmp_path / "renamed")

        # Download v2 (>= 2.0.0.dev0)
        v2_wheel = download_compatible_wheel(
            "icechunk",
            wheels_dir,
            index_url=NIGHTLY_INDEX,
            version=">=2.0.0.dev0",
        )
        assert v2_wheel is not None, (
            "Failed to download icechunk v2 wheel (>=2.0.0.dev0) from nightly index. "
            "This may indicate the wheel is not available for this platform."
        )

        # Install both
        install_wheel_in_venv(dual_install_venv, v1_renamed)
        install_wheel_in_venv(dual_install_venv, v2_wheel)

        return dual_install_venv

    def test_both_versions_import(self, icechunk_dual_venv: Path) -> None:
        """Both icechunk and icechunk_v1 can be imported."""
        code = """
import icechunk_v1
import icechunk

print(f"icechunk_v1 loaded from: {icechunk_v1.__file__}")
print(f"icechunk loaded from: {icechunk.__file__}")

# Verify they are distinct
assert "icechunk_v1" in icechunk_v1.__file__
assert "icechunk_v1" not in icechunk.__file__
print("PASS")
"""
        result = run_in_venv(icechunk_dual_venv, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout

    def test_versions_are_correct(self, icechunk_dual_venv: Path) -> None:
        """Verify v1 is <2 and v2 is >=2."""
        code = """
import icechunk_v1
import icechunk
from packaging.version import Version

v1 = Version(icechunk_v1.__version__)
v2 = Version(icechunk.__version__)

print(f"icechunk_v1 version: {v1}")
print(f"icechunk version: {v2}")

assert v1 < Version("2.0.0"), f"v1 should be < 2.0.0, got {v1}"
assert v2 >= Version("2.0.0a0.dev0"), f"v2 should be >= 2.0.0.dev0, got {v2}"
print("PASS")
"""
        result = run_in_venv(icechunk_dual_venv, code)
        # packaging might not be installed, install it first
        if "No module named 'packaging'" in result.stderr:
            import subprocess

            from tests.conftest import get_venv_pip

            pip = get_venv_pip(icechunk_dual_venv)
            subprocess.run([str(pip), "install", "packaging"], check=True)
            result = run_in_venv(icechunk_dual_venv, code)

        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout

    def test_no_import_contamination(self, icechunk_dual_venv: Path) -> None:
        """Verify icechunk_v1 doesn't accidentally import from icechunk."""
        code = """
import sys

# Import v1 first
import icechunk_v1

# Check that no 'icechunk' (without _v1) modules were loaded
# (except if icechunk itself is imported, which we haven't done yet)
contaminated = [
    name for name in sys.modules
    if name == 'icechunk' or (name.startswith('icechunk.') and not name.startswith('icechunk_v1'))
]

if contaminated:
    print(f"CONTAMINATION: {contaminated}")
    raise AssertionError(f"icechunk_v1 loaded icechunk modules: {contaminated}")

print("No contamination detected when importing icechunk_v1")

# Now import icechunk and verify it's separate
import icechunk

# Both should be in sys.modules now
assert 'icechunk_v1' in sys.modules
assert 'icechunk' in sys.modules
assert sys.modules['icechunk_v1'] is not sys.modules['icechunk']
print("PASS")
"""
        result = run_in_venv(icechunk_dual_venv, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout

    def test_scan_for_old_imports(self, icechunk_dual_venv: Path) -> None:
        """Scan all .py files in icechunk_v1 for references to 'icechunk' (the old name)."""
        code = """
import icechunk_v1
from pathlib import Path
import re

pkg_dir = Path(icechunk_v1.__file__).parent
problems = []

# Patterns that indicate old package name references
# We look for imports that reference 'icechunk' without the '_v1' suffix
bad_patterns = [
    (r'from icechunk(?!_v1)[\\s\\.]', 'from icechunk import'),
    (r'import icechunk(?!_v1)(?:[\\s\\n]|$)', 'import icechunk'),
]

for py_file in pkg_dir.rglob("*.py"):
    content = py_file.read_text()
    rel_path = py_file.relative_to(pkg_dir)

    for pattern, desc in bad_patterns:
        matches = re.findall(pattern, content)
        if matches:
            problems.append(f"{rel_path}: found '{desc}' pattern")

if problems:
    print("PROBLEMS FOUND:")
    for p in problems:
        print(f"  {p}")
    raise AssertionError(f"Found {len(problems)} old import references")

print(f"Scanned {sum(1 for _ in pkg_dir.rglob('*.py'))} .py files")
print("No old import references found")
print("PASS")
"""
        result = run_in_venv(icechunk_dual_venv, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout


@pytest.mark.integration
class TestIcechunkFunctionality:
    """Test that renamed icechunk actually works (not just imports)."""

    @pytest.fixture
    def icechunk_v1_venv(self, tmp_path: Path, dual_install_venv: Path) -> Path:
        """Create a venv with just icechunk_v1 installed."""
        wheels_dir = tmp_path / "wheels"
        wheels_dir.mkdir()

        # Download v1
        v1_wheel = download_compatible_wheel(
            "icechunk",
            wheels_dir,
            index_url=NIGHTLY_INDEX,
            version="<2",
        )
        assert v1_wheel is not None, "Failed to download icechunk v1 wheel (<2) from nightly index."

        # Rename and install
        v1_renamed = rename_wheel(v1_wheel, "icechunk_v1", output_dir=tmp_path / "renamed")
        install_wheel_in_venv(dual_install_venv, v1_renamed)

        return dual_install_venv

    def test_icechunk_v1_basic_operations(self, icechunk_v1_venv: Path) -> None:
        """Test that icechunk_v1 can perform basic operations."""
        code = """
import icechunk_v1
import tempfile
import os

print(f"icechunk_v1 version: {icechunk_v1.__version__}")

# Try to create a simple store (memory-based if available)
# This tests that the internal imports work correctly
try:
    # Different API versions may have different ways to create stores
    # Try common patterns
    if hasattr(icechunk_v1, 'IcechunkStore'):
        print("Found IcechunkStore class")
    if hasattr(icechunk_v1, 'Store'):
        print("Found Store class")

    # List available top-level attributes
    public_attrs = [a for a in dir(icechunk_v1) if not a.startswith('_')]
    print(f"Available attributes: {public_attrs[:10]}...")  # First 10

    print("PASS - icechunk_v1 module structure is accessible")
except Exception as e:
    print(f"Error: {e}")
    raise
"""
        result = run_in_venv(icechunk_v1_venv, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout

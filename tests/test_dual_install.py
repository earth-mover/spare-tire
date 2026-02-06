"""Tests for dual-package installation isolation.

These tests verify that when a package is renamed and both the original
and renamed versions are installed, they remain completely isolated with
no import cross-contamination.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import (
    create_test_wheel,
    install_wheel_in_venv,
    run_in_venv,
)
from third_wheel.rename import rename_wheel


class TestDualInstallIsolation:
    """Test that both packages can be installed and remain isolated."""

    @pytest.fixture
    def dual_venv_with_packages(self, tmp_path: Path, dual_install_venv: Path) -> Path:
        """Create a venv with both mypkg (v2) and mypkg_v1 (renamed v1) installed."""
        # Create v1 wheel and rename it
        v1_wheel = create_test_wheel(tmp_path, "mypkg", "1.0.0")
        v1_renamed = rename_wheel(v1_wheel, "mypkg_v1", output_dir=tmp_path / "renamed")

        # Create v2 wheel
        v2_wheel = create_test_wheel(tmp_path, "mypkg", "2.0.0")

        # Install both
        install_wheel_in_venv(dual_install_venv, v1_renamed)
        install_wheel_in_venv(dual_install_venv, v2_wheel)

        return dual_install_venv

    def test_both_packages_import_independently(self, dual_venv_with_packages: Path) -> None:
        """Both packages load without errors and return correct versions."""
        code = """
import mypkg_v1
import mypkg

print(f"v1: {mypkg_v1.get_version()}")
print(f"v2: {mypkg.get_version()}")

assert mypkg_v1.get_version() == "1.0.0", f"Expected 1.0.0, got {mypkg_v1.get_version()}"
assert mypkg.get_version() == "2.0.0", f"Expected 2.0.0, got {mypkg.get_version()}"
print("PASS")
"""
        result = run_in_venv(dual_venv_with_packages, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout

    def test_module_files_are_distinct(self, dual_venv_with_packages: Path) -> None:
        """Each package's modules come from correct location."""
        code = """
import mypkg_v1.core
import mypkg.core

v1_file = mypkg_v1.core.__file__
v2_file = mypkg.core.__file__

print(f"v1 core: {v1_file}")
print(f"v2 core: {v2_file}")

assert "mypkg_v1" in v1_file, f"v1 path should contain mypkg_v1: {v1_file}"
assert "mypkg" in v2_file and "mypkg_v1" not in v2_file, f"v2 path issue: {v2_file}"
assert v1_file != v2_file, "Files should be different"
print("PASS")
"""
        result = run_in_venv(dual_venv_with_packages, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout

    def test_internal_imports_stay_isolated(self, dual_venv_with_packages: Path) -> None:
        """When mypkg_v1.core imports utils, it gets v1 utils, not v2."""
        code = """
import mypkg_v1.core
import mypkg.core

# core.py imports from utils and exposes get_helper_version()
# This tests the import chain: core -> utils

v1_helper_version = mypkg_v1.core.get_helper_version()
v2_helper_version = mypkg.core.get_helper_version()

print(f"v1 helper version: {v1_helper_version}")
print(f"v2 helper version: {v2_helper_version}")

assert v1_helper_version == "1.0.0", f"v1 core got wrong utils: {v1_helper_version}"
assert v2_helper_version == "2.0.0", f"v2 core got wrong utils: {v2_helper_version}"
print("PASS")
"""
        result = run_in_venv(dual_venv_with_packages, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout

    def test_deep_submodule_isolation(self, dual_venv_with_packages: Path) -> None:
        """Nested submodules resolve correctly."""
        code = """
import mypkg_v1.sub.feature
import mypkg.sub.feature

# feature.py imports from core, testing cross-package import chains

v1_core = mypkg_v1.sub.feature.core_version()
v2_core = mypkg.sub.feature.core_version()

print(f"v1 feature's core version: {v1_core}")
print(f"v2 feature's core version: {v2_core}")

assert v1_core == "1.0.0", f"v1 submodule got wrong core: {v1_core}"
assert v2_core == "2.0.0", f"v2 submodule got wrong core: {v2_core}"
print("PASS")
"""
        result = run_in_venv(dual_venv_with_packages, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout

    def test_sys_modules_are_separate(self, dual_venv_with_packages: Path) -> None:
        """Both packages have separate entries in sys.modules."""
        code = """
import sys
import mypkg_v1
import mypkg
import mypkg_v1.core
import mypkg.core
import mypkg_v1.utils
import mypkg.utils

# Check that all expected modules are present
expected_v1 = ['mypkg_v1', 'mypkg_v1.core', 'mypkg_v1.utils']
expected_v2 = ['mypkg', 'mypkg.core', 'mypkg.utils']

for mod in expected_v1:
    assert mod in sys.modules, f"Missing {mod} in sys.modules"
    print(f"Found: {mod}")

for mod in expected_v2:
    assert mod in sys.modules, f"Missing {mod} in sys.modules"
    print(f"Found: {mod}")

# Verify they are distinct objects
assert sys.modules['mypkg_v1'] is not sys.modules['mypkg']
assert sys.modules['mypkg_v1.core'] is not sys.modules['mypkg.core']
print("PASS")
"""
        result = run_in_venv(dual_venv_with_packages, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout


class TestNoLeakedReferences:
    """Test that renamed package has no references to old name."""

    def test_no_old_imports_in_renamed_package(
        self, tmp_path: Path, dual_install_venv: Path
    ) -> None:
        """Scan installed mypkg_v1 for any 'from mypkg ' or 'import mypkg' references."""
        # Create and rename
        v1_wheel = create_test_wheel(tmp_path, "mypkg", "1.0.0")
        v1_renamed = rename_wheel(v1_wheel, "mypkg_v1", output_dir=tmp_path / "renamed")

        # Install
        install_wheel_in_venv(dual_install_venv, v1_renamed)

        # Scan for old imports
        code = """
import mypkg_v1
from pathlib import Path
import re

pkg_dir = Path(mypkg_v1.__file__).parent
problems = []

# Patterns that should NOT appear (old package name imports)
bad_patterns = [
    r'from mypkg\\s',      # from mypkg import
    r'from mypkg\\.',      # from mypkg.x import
    r'import mypkg\\n',    # import mypkg
    r'import mypkg\\.',    # import mypkg.x
    r"^import mypkg$",     # import mypkg at end of file
]

for py_file in pkg_dir.rglob("*.py"):
    content = py_file.read_text()
    rel_path = py_file.relative_to(pkg_dir)

    for pattern in bad_patterns:
        if re.search(pattern, content, re.MULTILINE):
            problems.append(f"{rel_path}: matches '{pattern}'")

if problems:
    print("PROBLEMS FOUND:")
    for p in problems:
        print(f"  {p}")
    raise AssertionError(f"Found {len(problems)} leaked references")

print("No leaked references found")
print("PASS")
"""
        result = run_in_venv(dual_install_venv, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout


class TestLazyImports:
    """Test that lazy imports (inside functions) resolve correctly."""

    def test_lazy_import_isolation(self, tmp_path: Path, dual_install_venv: Path) -> None:
        """Imports inside functions resolve to the correct package."""
        # Create wheels with lazy imports
        v1_wheel_path = tmp_path / "lazypkg-1.0.0-py3-none-any.whl"
        v2_wheel_path = tmp_path / "lazypkg-2.0.0-py3-none-any.whl"

        import zipfile

        # v1 wheel
        with zipfile.ZipFile(v1_wheel_path, "w") as zf:
            init_content = '''
__version__ = "1.0.0"

def lazy_get_utils():
    """Lazy import of utils module."""
    from lazypkg.utils import get_tag
    return get_tag()
'''
            zf.writestr("lazypkg/__init__.py", init_content)

            utils_content = """
def get_tag():
    return "v1-utils"
"""
            zf.writestr("lazypkg/utils.py", utils_content)

            zf.writestr(
                "lazypkg-1.0.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: lazypkg\nVersion: 1.0.0\n",
            )
            zf.writestr(
                "lazypkg-1.0.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            zf.writestr("lazypkg-1.0.0.dist-info/RECORD", "")

        # v2 wheel
        with zipfile.ZipFile(v2_wheel_path, "w") as zf:
            init_content = '''
__version__ = "2.0.0"

def lazy_get_utils():
    """Lazy import of utils module."""
    from lazypkg.utils import get_tag
    return get_tag()
'''
            zf.writestr("lazypkg/__init__.py", init_content)

            utils_content = """
def get_tag():
    return "v2-utils"
"""
            zf.writestr("lazypkg/utils.py", utils_content)

            zf.writestr(
                "lazypkg-2.0.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: lazypkg\nVersion: 2.0.0\n",
            )
            zf.writestr(
                "lazypkg-2.0.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            zf.writestr("lazypkg-2.0.0.dist-info/RECORD", "")

        # Rename v1 and install both
        v1_renamed = rename_wheel(v1_wheel_path, "lazypkg_v1", output_dir=tmp_path / "renamed")
        install_wheel_in_venv(dual_install_venv, v1_renamed)
        install_wheel_in_venv(dual_install_venv, v2_wheel_path)

        # Test lazy imports
        code = """
import lazypkg_v1
import lazypkg

v1_result = lazypkg_v1.lazy_get_utils()
v2_result = lazypkg.lazy_get_utils()

print(f"v1 lazy import result: {v1_result}")
print(f"v2 lazy import result: {v2_result}")

assert v1_result == "v1-utils", f"v1 lazy import got: {v1_result}"
assert v2_result == "v2-utils", f"v2 lazy import got: {v2_result}"
print("PASS")
"""
        result = run_in_venv(dual_install_venv, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout


class TestRelativeImports:
    """Test that relative imports still work after renaming."""

    def test_relative_imports_work(self, tmp_path: Path, dual_install_venv: Path) -> None:
        """Relative imports (from . import x) continue to work after rename."""
        wheel_path = tmp_path / "relpkg-1.0.0-py3-none-any.whl"

        import zipfile

        with zipfile.ZipFile(wheel_path, "w") as zf:
            # Use relative imports throughout
            init_content = """
__version__ = "1.0.0"

from .core import main_func
from . import utils

def get_version():
    return __version__

def get_utils_tag():
    return utils.get_tag()
"""
            zf.writestr("relpkg/__init__.py", init_content)

            core_content = """
from .utils import get_tag

def main_func():
    return f"main with {get_tag()}"
"""
            zf.writestr("relpkg/core.py", core_content)

            utils_content = """
def get_tag():
    return "relpkg-v1"
"""
            zf.writestr("relpkg/utils.py", utils_content)

            # Submodule with relative parent import
            sub_init = """
from ..core import main_func
from . import feature

def get_main():
    return main_func()
"""
            zf.writestr("relpkg/sub/__init__.py", sub_init)

            feature_content = """
from ..utils import get_tag

def feature_tag():
    return f"feature: {get_tag()}"
"""
            zf.writestr("relpkg/sub/feature.py", feature_content)

            zf.writestr(
                "relpkg-1.0.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: relpkg\nVersion: 1.0.0\n",
            )
            zf.writestr(
                "relpkg-1.0.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            )
            zf.writestr("relpkg-1.0.0.dist-info/RECORD", "")

        # Rename and install
        renamed = rename_wheel(wheel_path, "relpkg_v1", output_dir=tmp_path / "renamed")
        install_wheel_in_venv(dual_install_venv, renamed)

        # Test that relative imports work
        code = """
import relpkg_v1
import relpkg_v1.sub
import relpkg_v1.sub.feature

# Test various relative import chains
print(f"version: {relpkg_v1.get_version()}")
print(f"utils tag: {relpkg_v1.get_utils_tag()}")
print(f"main func: {relpkg_v1.main_func()}")
print(f"sub main: {relpkg_v1.sub.get_main()}")
print(f"feature tag: {relpkg_v1.sub.feature.feature_tag()}")

assert relpkg_v1.get_version() == "1.0.0"
assert "relpkg-v1" in relpkg_v1.get_utils_tag()
assert "relpkg-v1" in relpkg_v1.main_func()
print("PASS")
"""
        result = run_in_venv(dual_install_venv, code)
        assert result.returncode == 0, f"Failed: {result.stderr}\n{result.stdout}"
        assert "PASS" in result.stdout

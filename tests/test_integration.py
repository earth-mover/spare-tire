"""Integration tests for wheel renaming.

These tests verify that all internal imports are correctly updated
when renaming a wheel package.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from third_wheel.rename import rename_wheel


def create_multi_module_wheel(tmp_path: Path, name: str = "testpkg") -> Path:
    """Create a wheel with multiple modules that import each other."""
    wheel_name = f"{name}-0.1.0-py3-none-any.whl"
    wheel_path = tmp_path / wheel_name

    with zipfile.ZipFile(wheel_path, "w") as zf:
        # Main package __init__.py with internal imports
        zf.writestr(
            f"{name}/__init__.py",
            f'''"""Main package."""
from {name}.core import CoreClass
from {name}.utils import helper_function
from {name} import submodule

__version__ = "0.1.0"
__all__ = ["CoreClass", "helper_function", "submodule"]
''',
        )

        # Core module
        zf.writestr(
            f"{name}/core.py",
            f'''"""Core functionality."""
from {name}.utils import helper_function

class CoreClass:
    def __init__(self):
        self.value = helper_function()
''',
        )

        # Utils module
        zf.writestr(
            f"{name}/utils.py",
            '''"""Utility functions."""

def helper_function():
    return 42
''',
        )

        # Submodule package
        zf.writestr(
            f"{name}/submodule/__init__.py",
            f'''"""Submodule package."""
from {name}.submodule.feature import Feature
''',
        )

        zf.writestr(
            f"{name}/submodule/feature.py",
            f'''"""Feature module."""
from {name}.core import CoreClass

class Feature:
    def __init__(self):
        self.core = CoreClass()
''',
        )

        # dist-info
        zf.writestr(
            f"{name}-0.1.0.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1.0\n",
        )
        zf.writestr(
            f"{name}-0.1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        zf.writestr(f"{name}-0.1.0.dist-info/RECORD", "")

    return wheel_path


def create_wheel_with_compiled_extension(
    tmp_path: Path,
    name: str = "compiled_pkg",
    use_underscore_prefix: bool = True,
) -> Path:
    """Create a wheel that simulates having a compiled extension."""
    wheel_name = f"{name}-0.1.0-cp312-cp312-linux_x86_64.whl"
    wheel_path = tmp_path / wheel_name

    ext_name = f"_{name}_native" if use_underscore_prefix else f"{name}_native"

    with zipfile.ZipFile(wheel_path, "w") as zf:
        # Main package importing from the "extension"
        zf.writestr(
            f"{name}/__init__.py",
            f'''"""Package with compiled extension."""
from {name}.{ext_name} import native_function

__version__ = "0.1.0"
''',
        )

        # Fake .so file (just for structure testing, not actually loadable)
        zf.writestr(f"{name}/{ext_name}.cpython-312-x86_64-linux-gnu.so", b"fake binary")

        # Type stubs
        zf.writestr(
            f"{name}/{ext_name}.pyi",
            """def native_function() -> int: ...
""",
        )

        # dist-info
        zf.writestr(
            f"{name}-0.1.0.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1.0\n",
        )
        zf.writestr(
            f"{name}-0.1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: false\n"
            "Tag: cp312-cp312-linux_x86_64\n",
        )
        zf.writestr(f"{name}-0.1.0.dist-info/RECORD", "")

    return wheel_path


class TestImportUpdates:
    """Test that all import patterns are correctly updated."""

    def test_from_pkg_import(self, tmp_path: Path) -> None:
        """Test 'from pkg import x' is updated."""
        wheel_path = create_multi_module_wheel(tmp_path)
        result = rename_wheel(wheel_path, "testpkg_v1", output_dir=tmp_path / "out")

        with zipfile.ZipFile(result) as zf:
            content = zf.read("testpkg_v1/__init__.py").decode()
            assert "from testpkg_v1.core import CoreClass" in content
            assert "from testpkg.core" not in content

    def test_from_pkg_submodule_import(self, tmp_path: Path) -> None:
        """Test 'from pkg.submodule import x' is updated."""
        wheel_path = create_multi_module_wheel(tmp_path)
        result = rename_wheel(wheel_path, "testpkg_v1", output_dir=tmp_path / "out")

        with zipfile.ZipFile(result) as zf:
            content = zf.read("testpkg_v1/submodule/__init__.py").decode()
            assert "from testpkg_v1.submodule.feature import Feature" in content

    def test_import_pkg(self, tmp_path: Path) -> None:
        """Test 'import pkg' is updated."""
        wheel_path = tmp_path / "mypkg-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr(
                "mypkg/__init__.py",
                "import mypkg as mp\n",
            )
            zf.writestr("mypkg-0.1.0.dist-info/METADATA", "Name: mypkg\nVersion: 0.1.0\n")
            zf.writestr("mypkg-0.1.0.dist-info/WHEEL", "")
            zf.writestr("mypkg-0.1.0.dist-info/RECORD", "")

        result = rename_wheel(wheel_path, "mypkg_v1", output_dir=tmp_path / "out")

        with zipfile.ZipFile(result) as zf:
            content = zf.read("mypkg_v1/__init__.py").decode()
            assert "import mypkg_v1 as mp" in content
            assert "import mypkg as" not in content

    def test_cross_module_imports(self, tmp_path: Path) -> None:
        """Test that imports across different modules are all updated."""
        wheel_path = create_multi_module_wheel(tmp_path)
        result = rename_wheel(wheel_path, "testpkg_v1", output_dir=tmp_path / "out")

        with zipfile.ZipFile(result) as zf:
            # Check core.py
            core = zf.read("testpkg_v1/core.py").decode()
            assert "from testpkg_v1.utils import helper_function" in core

            # Check submodule/feature.py
            feature = zf.read("testpkg_v1/submodule/feature.py").decode()
            assert "from testpkg_v1.core import CoreClass" in feature


class TestCompiledExtensions:
    """Test handling of wheels with compiled extensions."""

    def test_underscore_prefix_extension(self, tmp_path: Path) -> None:
        """Test wheel with underscore-prefix extension is properly renamed."""
        wheel_path = create_wheel_with_compiled_extension(
            tmp_path, "compiled", use_underscore_prefix=True
        )
        result = rename_wheel(wheel_path, "compiled_v1", output_dir=tmp_path / "out")

        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()

            # Package dir renamed
            assert any(n.startswith("compiled_v1/") for n in names)
            assert not any(n.startswith("compiled/") for n in names)

            # Extension file keeps its name (just in new directory)
            assert "compiled_v1/_compiled_native.cpython-312-x86_64-linux-gnu.so" in names

            # Imports updated
            init = zf.read("compiled_v1/__init__.py").decode()
            assert "from compiled_v1._compiled_native import native_function" in init

    def test_no_underscore_prefix_extension(self, tmp_path: Path) -> None:
        """Test wheel with no underscore-prefix extension (still renamed, may not work)."""
        wheel_path = create_wheel_with_compiled_extension(
            tmp_path, "compiled", use_underscore_prefix=False
        )
        result = rename_wheel(wheel_path, "compiled_v1", output_dir=tmp_path / "out")

        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()

            # Extension file keeps its original name
            assert "compiled_v1/compiled_native.cpython-312-x86_64-linux-gnu.so" in names


class TestMetadata:
    """Test that metadata files are correctly updated."""

    def test_metadata_name_updated(self, tmp_path: Path) -> None:
        """Test METADATA Name field is updated."""
        wheel_path = create_multi_module_wheel(tmp_path)
        result = rename_wheel(wheel_path, "testpkg_v1", output_dir=tmp_path / "out")

        with zipfile.ZipFile(result) as zf:
            metadata = zf.read("testpkg_v1-0.1.0.dist-info/METADATA").decode()
            assert "Name: testpkg_v1" in metadata
            assert "Name: testpkg\n" not in metadata

    def test_record_regenerated(self, tmp_path: Path) -> None:
        """Test RECORD file is regenerated with correct hashes."""
        wheel_path = create_multi_module_wheel(tmp_path)
        result = rename_wheel(wheel_path, "testpkg_v1", output_dir=tmp_path / "out")

        with zipfile.ZipFile(result) as zf:
            record = zf.read("testpkg_v1-0.1.0.dist-info/RECORD").decode()

            # All files in new location should be in RECORD
            assert "testpkg_v1/__init__.py" in record
            assert "testpkg_v1/core.py" in record
            assert "testpkg_v1-0.1.0.dist-info/METADATA" in record

            # Old names should not be present
            assert "testpkg/__init__.py" not in record
            assert "testpkg-0.1.0.dist-info" not in record

            # Hashes should be present (sha256=...)
            lines = [ln for ln in record.split("\n") if ln.strip()]
            for line in lines:
                if not line.endswith(",,"):  # RECORD itself has no hash
                    assert "sha256=" in line


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_preserves_non_import_references(self, tmp_path: Path) -> None:
        """Test that string references to package name are NOT updated."""
        wheel_path = tmp_path / "pkg-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr(
                "pkg/__init__.py",
                """from pkg.core import x
PACKAGE_NAME = "pkg"  # This should NOT be updated
""",
            )
            zf.writestr("pkg/core.py", "x = 1\n")
            zf.writestr("pkg-0.1.0.dist-info/METADATA", "Name: pkg\nVersion: 0.1.0\n")
            zf.writestr("pkg-0.1.0.dist-info/WHEEL", "")
            zf.writestr("pkg-0.1.0.dist-info/RECORD", "")

        result = rename_wheel(wheel_path, "pkg_v1", output_dir=tmp_path / "out")

        with zipfile.ZipFile(result) as zf:
            content = zf.read("pkg_v1/__init__.py").decode()
            # Import is updated
            assert "from pkg_v1.core import x" in content
            # String is NOT updated (expected behavior - we only update imports)
            assert 'PACKAGE_NAME = "pkg"' in content

    def test_handles_empty_files(self, tmp_path: Path) -> None:
        """Test that empty Python files are handled."""
        wheel_path = tmp_path / "pkg-0.1.0-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr("pkg/__init__.py", "")
            zf.writestr("pkg-0.1.0.dist-info/METADATA", "Name: pkg\nVersion: 0.1.0\n")
            zf.writestr("pkg-0.1.0.dist-info/WHEEL", "")
            zf.writestr("pkg-0.1.0.dist-info/RECORD", "")

        result = rename_wheel(wheel_path, "pkg_v1", output_dir=tmp_path / "out")

        with zipfile.ZipFile(result) as zf:
            content = zf.read("pkg_v1/__init__.py").decode()
            assert content == ""

    def test_complex_version_string(self, tmp_path: Path) -> None:
        """Test handling of complex version strings like dev versions."""
        wheel_path = tmp_path / "pkg-1.2.3.dev4+gabcdef-py3-none-any.whl"
        with zipfile.ZipFile(wheel_path, "w") as zf:
            zf.writestr("pkg/__init__.py", "from pkg.core import x\n")
            zf.writestr("pkg/core.py", "x = 1\n")
            zf.writestr(
                "pkg-1.2.3.dev4+gabcdef.dist-info/METADATA",
                "Name: pkg\nVersion: 1.2.3.dev4+gabcdef\n",
            )
            zf.writestr("pkg-1.2.3.dev4+gabcdef.dist-info/WHEEL", "")
            zf.writestr("pkg-1.2.3.dev4+gabcdef.dist-info/RECORD", "")

        result = rename_wheel(wheel_path, "pkg_v1", output_dir=tmp_path / "out")

        assert result.name == "pkg_v1-1.2.3.dev4+gabcdef-py3-none-any.whl"
        with zipfile.ZipFile(result) as zf:
            assert "pkg_v1-1.2.3.dev4+gabcdef.dist-info/METADATA" in zf.namelist()

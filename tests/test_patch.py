"""Tests for wheel patching functionality."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from spare_tire.patch import (
    _update_dependency_references,
    patch_wheel,
    patch_wheel_from_bytes,
)


class TestUpdateDependencyReferences:
    """Test the regex-based import rewriting."""

    def test_import_statement(self) -> None:
        content = b"import zarr\n"
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        assert result == b"import zarr_v2\n"

    def test_from_import(self) -> None:
        content = b"from zarr import Array\n"
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        assert result == b"from zarr_v2 import Array\n"

    def test_from_submodule_import(self) -> None:
        content = b"from zarr.storage import FSStore\n"
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        assert result == b"from zarr_v2.storage import FSStore\n"

    def test_dotted_usage(self) -> None:
        content = b"arr = zarr.zeros((10,))\n"
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        assert result == b"arr = zarr_v2.zeros((10,))\n"

    def test_preserves_file_extension(self) -> None:
        """The .zarr file extension should NOT be rewritten."""
        content = b'path = "data.zarr"\n'
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        assert result == b'path = "data.zarr"\n'

    def test_preserves_file_extension_in_glob(self) -> None:
        """Glob patterns like *.zarr should NOT be rewritten."""
        content = b'files = glob("*.zarr")\n'
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        assert result == b'files = glob("*.zarr")\n'

    def test_preserves_path_slash_zarr(self) -> None:
        """Path components like /zarr/ should be rewritten (word boundary matches)."""
        content = b'path = "/data/zarr/array"\n'
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        # This does get rewritten since / triggers word boundary but not preceded by .
        assert b"zarr_v2" in result

    def test_word_boundary_no_partial_match(self) -> None:
        """Should not match partial names like 'lazy_zarr'."""
        content = b"from lazy_zarr import something\n"
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        # lazy_zarr should NOT become lazy_zarr_v2 (_ is a word char, no boundary)
        assert result == b"from lazy_zarr import something\n"

    def test_no_change_when_absent(self) -> None:
        content = b"import numpy\n"
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        assert result == content

    def test_multiple_references(self) -> None:
        content = b"import zarr\nfrom zarr.storage import FSStore\narr = zarr.zeros((10,))\n"
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        assert b"import zarr_v2\n" in result
        assert b"from zarr_v2.storage" in result
        assert b"zarr_v2.zeros" in result

    def test_metadata_requires_dist(self) -> None:
        """Requires-Dist lines in METADATA should be rewritten."""
        content = b"Requires-Dist: zarr (>=2.0)\n"
        result = _update_dependency_references(content, "zarr", "zarr_v2")
        assert result == b"Requires-Dist: zarr_v2 (>=2.0)\n"


def _create_wheel_with_dep(tmp_path: Path, pkg_name: str, dep_name: str) -> Path:
    """Helper: create a wheel that imports a dependency."""
    wheel_name = f"{pkg_name}-1.0.0-py3-none-any.whl"
    wheel_path = tmp_path / wheel_name

    with zipfile.ZipFile(wheel_path, "w") as zf:
        zf.writestr(
            f"{pkg_name}/__init__.py",
            f"""\"\"\"Package {pkg_name}.\"\"\"
import {dep_name}
from {dep_name}.storage import FSStore

__version__ = "1.0.0"

def get_store():
    return {dep_name}.open("data.zarr")
""",
        )

        zf.writestr(
            f"{pkg_name}/io.py",
            f"""\"\"\"IO module.\"\"\"
from {dep_name} import Array
from {dep_name}.convenience import open as zarr_open

def read(path):
    return {dep_name}.open(path)
""",
        )

        # A non-Python file (should not be patched)
        zf.writestr(
            f"{pkg_name}/data/config.yaml",
            f"backend: {dep_name}\nformat: .zarr\n",
        )

        zf.writestr(
            f"{pkg_name}-1.0.0.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: {pkg_name}\nVersion: 1.0.0\nRequires-Dist: {dep_name}\n",
        )
        zf.writestr(
            f"{pkg_name}-1.0.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        zf.writestr(f"{pkg_name}-1.0.0.dist-info/RECORD", "")

    return wheel_path


class TestPatchWheel:
    """Test patch_wheel on actual wheel files."""

    def test_basic_patch(self, tmp_path: Path) -> None:
        wheel_path = _create_wheel_with_dep(tmp_path, "mypkg", "zarr")
        output_dir = tmp_path / "output"

        result_path, patched_files = patch_wheel(
            wheel_path, "zarr", "zarr_v2", output_dir=output_dir
        )

        assert result_path.exists()
        # Wheel name stays the same (we're patching, not renaming)
        assert result_path.name == "mypkg-1.0.0-py3-none-any.whl"

        # Should have patched the .py files
        assert "mypkg/__init__.py" in patched_files
        assert "mypkg/io.py" in patched_files

        # Non-Python files should not be in patched list
        assert "mypkg/data/config.yaml" not in patched_files

    def test_patched_content(self, tmp_path: Path) -> None:
        wheel_path = _create_wheel_with_dep(tmp_path, "mypkg", "zarr")
        output_dir = tmp_path / "output"

        result_path, _ = patch_wheel(wheel_path, "zarr", "zarr_v2", output_dir=output_dir)

        with zipfile.ZipFile(result_path) as zf:
            init = zf.read("mypkg/__init__.py").decode()
            assert "import zarr_v2" in init
            assert "from zarr_v2.storage import FSStore" in init
            assert "zarr_v2.open" in init
            # .zarr extension preserved
            assert '"data.zarr"' in init

            io_mod = zf.read("mypkg/io.py").decode()
            assert "from zarr_v2 import Array" in io_mod
            assert "from zarr_v2.convenience" in io_mod

    def test_non_python_files_untouched(self, tmp_path: Path) -> None:
        wheel_path = _create_wheel_with_dep(tmp_path, "mypkg", "zarr")
        output_dir = tmp_path / "output"

        result_path, _ = patch_wheel(wheel_path, "zarr", "zarr_v2", output_dir=output_dir)

        with zipfile.ZipFile(result_path) as zf:
            config = zf.read("mypkg/data/config.yaml").decode()
            # YAML config should not be modified (not a .py file)
            assert "backend: zarr\n" in config

    def test_record_regenerated(self, tmp_path: Path) -> None:
        wheel_path = _create_wheel_with_dep(tmp_path, "mypkg", "zarr")
        output_dir = tmp_path / "output"

        result_path, _ = patch_wheel(wheel_path, "zarr", "zarr_v2", output_dir=output_dir)

        with zipfile.ZipFile(result_path) as zf:
            record = zf.read("mypkg-1.0.0.dist-info/RECORD").decode()
            # All files should be in RECORD
            assert "mypkg/__init__.py" in record
            assert "mypkg/io.py" in record
            assert "mypkg/data/config.yaml" in record
            # RECORD should have hashes
            lines = [ln for ln in record.split("\n") if ln.strip()]
            for line in lines:
                if not line.endswith(",,"):
                    assert "sha256=" in line

    def test_output_dir_default(self, tmp_path: Path) -> None:
        """When no output_dir, writes to same directory as input."""
        wheel_path = _create_wheel_with_dep(tmp_path, "mypkg", "zarr")

        result_path, _ = patch_wheel(wheel_path, "zarr", "zarr_v2")

        assert result_path.parent == tmp_path
        assert result_path.exists()

    def test_error_wheel_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            patch_wheel(tmp_path / "nonexistent.whl", "zarr", "zarr_v2")

    def test_error_not_a_wheel(self, tmp_path: Path) -> None:
        not_wheel = tmp_path / "something.tar.gz"
        not_wheel.write_text("not a wheel")
        with pytest.raises(ValueError, match="Not a wheel"):
            patch_wheel(not_wheel, "zarr", "zarr_v2")

    def test_error_same_name(self, tmp_path: Path) -> None:
        wheel_path = _create_wheel_with_dep(tmp_path, "mypkg", "zarr")
        with pytest.raises(ValueError, match="same"):
            patch_wheel(wheel_path, "zarr", "zarr")

    def test_no_matching_references(self, tmp_path: Path) -> None:
        """Patching a wheel with no references to the dep returns empty list."""
        wheel_path = _create_wheel_with_dep(tmp_path, "mypkg", "zarr")
        output_dir = tmp_path / "output"

        result_path, patched_files = patch_wheel(
            wheel_path, "nonexistent_dep", "new_dep", output_dir=output_dir
        )

        assert result_path.exists()
        assert patched_files == []


class TestPatchWheelFromBytes:
    """Test in-memory patching via patch_wheel_from_bytes."""

    def test_basic_patch_from_bytes(self, tmp_path: Path) -> None:
        wheel_path = _create_wheel_with_dep(tmp_path, "mypkg", "zarr")
        wheel_bytes = wheel_path.read_bytes()

        patched_bytes, patched_files = patch_wheel_from_bytes(wheel_bytes, "zarr", "zarr_v2")

        assert len(patched_bytes) > 0
        assert "mypkg/__init__.py" in patched_files
        assert "mypkg/io.py" in patched_files

        # Verify we can open the result as a valid zip
        import io

        with zipfile.ZipFile(io.BytesIO(patched_bytes)) as zf:
            init = zf.read("mypkg/__init__.py").decode()
            assert "import zarr_v2" in init

    def test_same_name_returns_unchanged(self) -> None:
        """When old_dep == new_dep, return original bytes unchanged."""
        fake_bytes = b"not actually a wheel"
        result_bytes, patched_files = patch_wheel_from_bytes(fake_bytes, "zarr", "zarr")
        assert result_bytes == fake_bytes
        assert patched_files == []

    def test_roundtrip_consistency(self, tmp_path: Path) -> None:
        """patch_wheel and patch_wheel_from_bytes should produce equivalent results."""
        wheel_path = _create_wheel_with_dep(tmp_path, "mypkg", "zarr")
        wheel_bytes = wheel_path.read_bytes()
        output_dir = tmp_path / "output"

        # Patch via file
        file_result, file_patched = patch_wheel(
            wheel_path, "zarr", "zarr_v2", output_dir=output_dir
        )
        # Patch via bytes
        bytes_result, bytes_patched = patch_wheel_from_bytes(wheel_bytes, "zarr", "zarr_v2")

        # Same files should have been patched
        assert sorted(file_patched) == sorted(bytes_patched)

        # Both outputs should contain the same file contents
        import io

        with (
            zipfile.ZipFile(file_result) as zf_file,
            zipfile.ZipFile(io.BytesIO(bytes_result)) as zf_bytes,
        ):
            assert sorted(zf_file.namelist()) == sorted(zf_bytes.namelist())
            for name in zf_file.namelist():
                assert zf_file.read(name) == zf_bytes.read(name)

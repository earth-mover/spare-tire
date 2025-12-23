"""Core wheel renaming logic."""

from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator


def _normalize_name(name: str) -> str:
    """Normalize a package name according to PEP 503."""
    return re.sub(r"[-_.]+", "_", name).lower()


def _compute_record_hash(data: bytes) -> str:
    """Compute SHA256 hash in RECORD format (base64 urlsafe, no padding)."""
    import base64

    digest = hashlib.sha256(data).digest()
    return "sha256=" + base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _parse_wheel_filename(filename: str) -> dict[str, str]:
    """Parse a wheel filename into its components.

    Format: {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl
    """
    name = Path(filename).stem  # Remove .whl
    parts = name.split("-")

    if len(parts) < 5:
        raise ValueError(f"Invalid wheel filename: {filename}")

    # Check if there's a build tag (starts with a digit)
    if len(parts) >= 6 and parts[2][0].isdigit():
        return {
            "distribution": parts[0],
            "version": parts[1],
            "build": parts[2],
            "python": parts[3],
            "abi": parts[4],
            "platform": parts[5],
        }
    else:
        return {
            "distribution": parts[0],
            "version": parts[1],
            "build": "",
            "python": parts[2],
            "abi": parts[3],
            "platform": parts[4],
        }


def _build_wheel_filename(components: dict[str, str]) -> str:
    """Build a wheel filename from components."""
    parts = [components["distribution"], components["version"]]
    if components.get("build"):
        parts.append(components["build"])
    parts.extend([components["python"], components["abi"], components["platform"]])
    return "-".join(parts) + ".whl"


def _iter_wheel_files(wheel_path: Path) -> Iterator[tuple[str, bytes]]:
    """Iterate over all files in a wheel, yielding (name, content) tuples."""
    with zipfile.ZipFile(wheel_path, "r") as zf:
        for name in zf.namelist():
            yield name, zf.read(name)


def _update_metadata(content: bytes, _old_name: str, new_name: str) -> bytes:
    """Update the METADATA file with the new package name."""
    text = content.decode("utf-8")
    lines = text.split("\n")
    new_lines = []

    for line in lines:
        if line.startswith("Name:"):
            # Replace the package name
            new_lines.append(f"Name: {new_name}")
        else:
            new_lines.append(line)

    return "\n".join(new_lines).encode("utf-8")


def _update_python_imports(content: bytes, old_name: str, new_name: str) -> bytes:
    """Update Python file imports that reference the old package name.

    This handles common patterns like:
    - from old_name import ...
    - import old_name
    - from old_name.submodule import ...
    """
    text = content.decode("utf-8")

    # Pattern to match imports (be careful not to replace partial matches)
    # Only replace if old_name is a complete module name (word boundary)
    patterns = [
        (rf"\bfrom {re.escape(old_name)}(\s|\.)", rf"from {new_name}\1"),
        (rf"\bimport {re.escape(old_name)}\b", f"import {new_name}"),
    ]

    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)

    return text.encode("utf-8")


def rename_wheel(
    wheel_path: Path,
    new_name: str,
    output_dir: Path | None = None,
    *,
    update_imports: bool = True,
) -> Path:
    """Rename a wheel package.

    Args:
        wheel_path: Path to the input wheel file
        new_name: New package name (e.g., "icechunk_v1")
        output_dir: Output directory for the renamed wheel (default: same as input)
        update_imports: Whether to update import statements in Python files

    Returns:
        Path to the renamed wheel file
    """
    if not wheel_path.exists():
        raise FileNotFoundError(f"Wheel not found: {wheel_path}")

    if not wheel_path.suffix == ".whl":
        raise ValueError(f"Not a wheel file: {wheel_path}")

    # Parse the original wheel filename
    components = _parse_wheel_filename(wheel_path.name)
    old_name = components["distribution"]
    old_name_normalized = _normalize_name(old_name)
    new_name_normalized = _normalize_name(new_name)

    if old_name_normalized == new_name_normalized:
        raise ValueError(f"New name '{new_name}' is the same as old name '{old_name}'")

    # Determine output path
    if output_dir is None:
        output_dir = wheel_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    components["distribution"] = new_name_normalized
    new_wheel_name = _build_wheel_filename(components)
    output_path = output_dir / new_wheel_name

    # Process the wheel
    # Collect all files with their new names and contents
    files: dict[str, bytes] = {}

    # Old and new dist-info directory names
    old_dist_info = f"{old_name_normalized}-{components['version']}.dist-info"
    new_dist_info = f"{new_name_normalized}-{components['version']}.dist-info"

    # Old and new data directory names (if present)
    old_data_dir = f"{old_name_normalized}-{components['version']}.data"
    new_data_dir = f"{new_name_normalized}-{components['version']}.data"

    for name, content in _iter_wheel_files(wheel_path):
        new_file_name = name

        # Rename the package directory
        if name.startswith(f"{old_name_normalized}/") or name == old_name_normalized:
            new_file_name = new_name_normalized + name[len(old_name_normalized) :]

        # Rename the dist-info directory
        elif name.startswith(f"{old_dist_info}/") or name == old_dist_info:
            new_file_name = new_dist_info + name[len(old_dist_info) :]

        # Rename the data directory (if present)
        elif name.startswith(f"{old_data_dir}/") or name == old_data_dir:
            new_file_name = new_data_dir + name[len(old_data_dir) :]

        # Update file contents as needed
        new_content = content

        # Update METADATA file
        if new_file_name == f"{new_dist_info}/METADATA":
            new_content = _update_metadata(content, old_name, new_name)

        # Update Python files (imports)
        elif update_imports and new_file_name.endswith(".py"):
            new_content = _update_python_imports(content, old_name_normalized, new_name_normalized)

        # Skip the old RECORD file (we'll generate a new one)
        if name.endswith("/RECORD"):
            continue

        files[new_file_name] = new_content

    # Generate new RECORD file
    record_path = f"{new_dist_info}/RECORD"
    record_lines: list[str] = []

    for file_name, content in sorted(files.items()):
        file_hash = _compute_record_hash(content)
        file_size = len(content)
        record_lines.append(f"{file_name},{file_hash},{file_size}")

    # RECORD itself has no hash
    record_lines.append(f"{record_path},,")
    record_content = "\n".join(record_lines).encode("utf-8")
    files[record_path] = record_content

    # Write the new wheel
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_name, content in sorted(files.items()):
            zf.writestr(file_name, content)

    return output_path


def inspect_wheel(wheel_path: Path) -> dict[str, object]:
    """Inspect a wheel and return information about its structure.

    This is useful for understanding the wheel structure before renaming,
    especially for compiled extensions.
    """
    if not wheel_path.exists():
        raise FileNotFoundError(f"Wheel not found: {wheel_path}")

    components = _parse_wheel_filename(wheel_path.name)

    info: dict[str, object] = {
        "filename": wheel_path.name,
        "distribution": components["distribution"],
        "version": components["version"],
        "python_tag": components["python"],
        "abi_tag": components["abi"],
        "platform_tag": components["platform"],
        "files": [],
        "extensions": [],
        "has_underscore_prefix_extension": False,
    }

    files_list: list[str] = []
    extensions_list: list[dict[str, str]] = []

    with zipfile.ZipFile(wheel_path, "r") as zf:
        for name in zf.namelist():
            files_list.append(name)

            # Check for compiled extensions
            if any(name.endswith(ext) for ext in (".so", ".pyd", ".dylib")):
                ext_name = Path(name).stem.split(".")[
                    0
                ]  # e.g., _icechunk from _icechunk.cpython-311-darwin
                has_underscore = ext_name.startswith("_")
                extensions_list.append(
                    {
                        "path": name,
                        "module_name": ext_name,
                        "has_underscore_prefix": str(has_underscore),
                    }
                )
                if has_underscore:
                    info["has_underscore_prefix_extension"] = True

    info["files"] = files_list
    info["extensions"] = extensions_list

    return info

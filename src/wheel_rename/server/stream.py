"""Wheel streaming and on-the-fly renaming."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wheel_rename.server.upstream import UpstreamClient


async def rename_wheel_bytes(
    wheel_bytes: bytes,
    new_name: str,
) -> bytes:
    """Rename a wheel from bytes.

    Args:
        wheel_bytes: Original wheel bytes
        new_name: New package name

    Returns:
        Renamed wheel bytes
    """
    from wheel_rename.rename import rename_wheel_from_bytes

    return rename_wheel_from_bytes(wheel_bytes, new_name)


async def stream_and_rename_wheel(
    client: UpstreamClient,
    upstream_url: str,
    new_name: str,
) -> bytes:
    """Download wheel from upstream and rename it.

    This downloads the entire wheel into memory, renames it, and returns
    the renamed bytes. For very large wheels, this could use significant
    memory, but most wheels are <100MB which is acceptable.

    Args:
        client: Upstream client to download from
        upstream_url: URL of the original wheel
        new_name: New package name

    Returns:
        Renamed wheel bytes
    """
    # Download complete wheel
    wheel_bytes = await client.download_wheel(upstream_url)

    # Rename in memory
    return await rename_wheel_bytes(wheel_bytes, new_name)


def rewrite_wheel_filename(filename: str, original_name: str, new_name: str) -> str:
    """Rewrite a wheel filename with a new package name.

    Args:
        filename: Original wheel filename
        original_name: Original package name
        new_name: New package name

    Returns:
        Rewritten filename
    """
    # Wheel filenames are: {distribution}-{version}(-{build})?-{python}-{abi}-{platform}.whl
    # Replace the distribution (first part before first hyphen that's followed by a digit)
    parts = filename.split("-")
    if parts[0].lower().replace("_", "-") == original_name.lower().replace("_", "-"):
        parts[0] = new_name
    return "-".join(parts)


def original_filename_from_renamed(renamed_filename: str, original_name: str, new_name: str) -> str:
    """Get the original filename from a renamed filename.

    Args:
        renamed_filename: Renamed wheel filename
        original_name: Original package name
        new_name: New package name

    Returns:
        Original filename
    """
    # Reverse of rewrite_wheel_filename
    parts = renamed_filename.split("-")
    if parts[0].lower().replace("_", "-") == new_name.lower().replace("_", "-"):
        parts[0] = original_name
    return "-".join(parts)

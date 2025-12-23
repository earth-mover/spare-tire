"""Command-line interface for wheel-rename."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from wheel_rename.rename import inspect_wheel, rename_wheel


@click.group()
@click.version_option()
def main() -> None:
    """Rename Python wheel packages for multi-version installation."""
    pass


@main.command()
@click.argument("wheel_path", type=click.Path(exists=True, path_type=Path))
@click.argument("new_name")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output directory for the renamed wheel (default: same as input)",
)
@click.option(
    "--no-update-imports",
    is_flag=True,
    default=False,
    help="Do not update import statements in Python files",
)
def rename(
    wheel_path: Path,
    new_name: str,
    output: Path | None,
    no_update_imports: bool,
) -> None:
    """Rename a wheel package.

    WHEEL_PATH: Path to the wheel file to rename
    NEW_NAME: New package name (e.g., "icechunk_v1")
    """
    try:
        result = rename_wheel(
            wheel_path,
            new_name,
            output_dir=output,
            update_imports=not no_update_imports,
        )
        click.echo(f"Created: {result}")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.argument("wheel_path", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def inspect(wheel_path: Path, as_json: bool) -> None:
    """Inspect a wheel's structure.

    WHEEL_PATH: Path to the wheel file to inspect
    """
    try:
        info = inspect_wheel(wheel_path)

        if as_json:
            click.echo(json.dumps(info, indent=2))
        else:
            click.echo(f"Wheel: {info['filename']}")
            click.echo(f"Distribution: {info['distribution']}")
            click.echo(f"Version: {info['version']}")
            click.echo(f"Python: {info['python_tag']}")
            click.echo(f"ABI: {info['abi_tag']}")
            click.echo(f"Platform: {info['platform_tag']}")
            click.echo()

            extensions = info.get("extensions", [])
            if extensions:
                assert isinstance(extensions, list)
                click.echo(f"Compiled extensions ({len(extensions)}):")
                for ext in extensions:
                    assert isinstance(ext, dict)
                    prefix_info = (
                        " (underscore prefix - renamable)"
                        if ext.get("has_underscore_prefix") == "True"
                        else " (no underscore - may need rebuild)"
                    )
                    click.echo(f"  - {ext['path']}{prefix_info}")

                if info.get("has_underscore_prefix_extension"):
                    click.echo()
                    click.echo("This wheel uses underscore-prefix extensions.")
                    click.echo("Renaming should work correctly.")
                else:
                    click.echo()
                    click.echo("WARNING: This wheel has extensions without underscore prefix.")
                    click.echo("Renaming may cause import errors. Consider rebuilding from source.")
            else:
                click.echo("No compiled extensions found (pure Python wheel).")
                click.echo("Renaming should work correctly.")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

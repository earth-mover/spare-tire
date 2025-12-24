"""Command-line interface for spare-tire."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from spare_tire.download import download_compatible_wheel, list_wheels
from spare_tire.rename import inspect_wheel, rename_wheel

console = Console()
err_console = Console(stderr=True)


@click.group()
@click.version_option()
def main() -> None:
    """🛞 Spare Tire - Rename Python wheel packages for multi-version installation."""
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
    """🛞 Rename a wheel package.

    WHEEL_PATH: Path to the wheel file to rename
    NEW_NAME: New package name (e.g., "icechunk_v1")
    """
    try:
        with console.status(f"[bold blue]Renaming {wheel_path.name}..."):
            result = rename_wheel(
                wheel_path,
                new_name,
                output_dir=output,
                update_imports=not no_update_imports,
            )

        console.print(f"[green]🛞 Created:[/green] [bold]{result}[/bold]")

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("wheel_path", type=click.Path(exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def inspect(wheel_path: Path, as_json: bool) -> None:
    """🔧 Inspect a wheel's structure.

    WHEEL_PATH: Path to the wheel file to inspect
    """
    try:
        info = inspect_wheel(wheel_path)

        if as_json:
            click.echo(json.dumps(info, indent=2))
        else:
            # Create info table
            table = Table(show_header=False, box=None, padding=(0, 1))
            table.add_column("Key", style="dim")
            table.add_column("Value", style="bold")

            table.add_row("Wheel", str(info["filename"]))
            table.add_row("Distribution", str(info["distribution"]))
            table.add_row("Version", str(info["version"]))
            table.add_row("Python", str(info["python_tag"]))
            table.add_row("ABI", str(info["abi_tag"]))
            table.add_row("Platform", str(info["platform_tag"]))

            console.print(Panel(table, title="[bold]🛞 Wheel Info[/bold]", border_style="blue"))

            extensions = info.get("extensions", [])
            if extensions:
                assert isinstance(extensions, list)

                ext_table = Table(show_header=True, header_style="bold")
                ext_table.add_column("Extension", style="cyan")
                ext_table.add_column("Renamable", justify="center")

                for ext in extensions:
                    assert isinstance(ext, dict)
                    if ext.get("has_underscore_prefix") == "True":
                        status = "[green]✓ Yes[/green]"
                    else:
                        status = "[red]✗ No[/red]"
                    ext_table.add_row(ext["path"], status)

                console.print(ext_table)
                console.print()

                if info.get("has_underscore_prefix_extension"):
                    console.print(
                        Panel(
                            "[green]This wheel uses underscore-prefix extensions.\n"
                            "Renaming should work correctly.[/green]",
                            title="[bold green]🛞 Safe to Rename[/bold green]",
                            border_style="green",
                        )
                    )
                else:
                    console.print(
                        Panel(
                            "[yellow]This wheel has extensions without underscore prefix.\n"
                            "Renaming may cause import errors.\n"
                            "Consider rebuilding from source instead.[/yellow]",
                            title="[bold yellow]🔧 Warning[/bold yellow]",
                            border_style="yellow",
                        )
                    )
            else:
                console.print(
                    Panel(
                        "[green]No compiled extensions found (pure Python wheel).\n"
                        "Renaming should work correctly.[/green]",
                        title="[bold green]🛞 Safe to Rename[/bold green]",
                        border_style="green",
                    )
                )

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.argument("package")
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=Path(),
    help="Output directory for the downloaded wheel (default: current directory)",
)
@click.option(
    "-i",
    "--index-url",
    default="https://pypi.org/simple/",
    help="Base URL of the package index (default: PyPI)",
)
@click.option(
    "--version",
    "pkg_version",
    default=None,
    help="PEP 440 version specifier (e.g., '==1.0.0', '<2', '>=1.0,<2')",
)
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    help="List available wheels without downloading",
)
@click.option(
    "--rename",
    "rename_to",
    default=None,
    help="Rename the downloaded wheel to this package name",
)
@click.option(
    "--python-version",
    "python_version",
    default=None,
    help="Target Python version (e.g., '3.12'). Defaults to current interpreter.",
)
def download(
    package: str,
    output: Path,
    index_url: str,
    pkg_version: str | None,
    list_only: bool,
    rename_to: str | None,
    python_version: str | None,
) -> None:
    """🛞 Download a compatible wheel from a package index.

    PACKAGE: Name of the package to download

    Examples:

        spare-tire download numpy -o ./wheels/

        spare-tire download icechunk -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple

        spare-tire download requests --list

        spare-tire download icechunk --version "<2" --rename icechunk_v1 -o ./wheels/

        spare-tire download icechunk --python-version 3.12 -o ./wheels/
    """
    try:
        if list_only:
            from packaging.version import Version

            with console.status(f"[bold blue]Fetching wheel list for {package}..."):
                wheels = list_wheels(package, index_url)

            if not wheels:
                err_console.print(f"[red]🔧[/red] No wheels found for [bold]{package}[/bold]")
                sys.exit(1)

            table = Table(title=f"Available wheels for [bold]{package}[/bold]")
            table.add_column("Filename", style="cyan")
            table.add_column("Version", style="green")

            for wheel in sorted(
                wheels,
                key=lambda w: Version(w.version) if w.version else Version("0"),
                reverse=True,
            ):
                table.add_row(wheel.filename, wheel.version or "unknown")

            console.print(table)
        else:
            with console.status(f"[bold blue]Finding compatible wheel for {package}..."):
                result = download_compatible_wheel(
                    package,
                    output,
                    index_url=index_url,
                    version=pkg_version,
                    python_version=python_version,
                    show_progress=False,  # We use rich status instead
                )

            if result is None:
                err_console.print(
                    f"[red]🔧[/red] No compatible wheel found for [bold]{package}[/bold]"
                )
                sys.exit(1)

            console.print(f"[green]🛞 Downloaded:[/green] [bold]{result}[/bold]")

            # Optionally rename the wheel
            if rename_to:
                with console.status(f"[bold blue]Renaming to {rename_to}..."):
                    renamed = rename_wheel(result, rename_to, output_dir=output)
                # Remove the original downloaded wheel
                result.unlink()
                console.print(f"[green]🛞 Renamed:[/green] [bold]{renamed}[/bold]")

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


@main.command()
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    help="Path to TOML config file",
)
@click.option(
    "-u",
    "--upstream",
    multiple=True,
    help="Upstream index URL (can be specified multiple times)",
)
@click.option(
    "-r",
    "--rename",
    "renames",
    multiple=True,
    help="Rename rule: 'original=new_name[:version_spec]' (can be specified multiple times)",
)
@click.option(
    "--host",
    default="127.0.0.1",
    help="Host to bind to (default: 127.0.0.1)",
)
@click.option(
    "--port",
    default=8000,
    type=int,
    help="Port to listen on (default: 8000)",
)
def serve(
    config: Path | None,
    upstream: tuple[str, ...],
    renames: tuple[str, ...],
    host: str,
    port: int,
) -> None:
    """🛞 Start a PEP 503 proxy server with package renaming.

    The proxy server acts as a package index that can rename packages on-the-fly.
    This allows installing renamed packages via pip/uv.

    \b
    Examples:
        # Start with CLI options
        spare-tire serve \\
            -u https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \\
            -r "icechunk=icechunk_v1:<2"

        # Start with config file
        spare-tire serve -c proxy.toml

    \b
    Config file format (proxy.toml):
        [proxy]
        host = "127.0.0.1"
        port = 8000

        [[proxy.upstreams]]
        url = "https://pypi.org/simple/"

        [renames]
        icechunk = { name = "icechunk_v1", version = "<2" }
    """
    try:
        import uvicorn

        from spare_tire.server import create_app, load_config
    except ImportError as e:
        err_console.print(
            "[red]🔧 Error:[/red] Server dependencies not installed.\n"
            "Install with: [bold]pip install spare-tire[server][/bold]"
        )
        err_console.print(f"[dim]Missing: {e}[/dim]")
        sys.exit(1)

    try:
        # Load configuration
        cfg = load_config(
            config_path=config,
            upstreams=upstream if upstream else None,
            renames=renames if renames else None,
            host=host,
            port=port,
        )

        if not cfg.upstreams:
            err_console.print(
                "[red]🔧 Error:[/red] No upstream indexes configured.\n"
                "Use [bold]-u/--upstream[/bold] or config file."
            )
            sys.exit(1)

        if not cfg.renames:
            console.print(
                "[yellow]🔧 Warning:[/yellow] No rename rules configured.\n"
                "The proxy will only serve virtual packages from rename rules."
            )

        # Print startup info
        console.print(
            Panel.fit(
                f"[bold]🛞 spare-tire proxy[/bold]\n"
                f"Listening on: [cyan]http://{cfg.host}:{cfg.port}[/cyan]\n"
                f"Upstreams: {len(cfg.upstreams)}\n"
                f"Renames: {len(cfg.renames)}",
                border_style="blue",
            )
        )

        for rule in cfg.renames:
            version_info = f" ({rule.version_spec})" if rule.version_spec else ""
            console.print(
                f"  [dim]•[/dim] {rule.original} → [bold]{rule.new_name}[/bold]{version_info}"
            )

        console.print()

        # Create and run the app
        app = create_app(cfg)
        uvicorn.run(app, host=cfg.host, port=cfg.port, log_level="info")

    except Exception as e:
        err_console.print(f"[red]🔧 Error:[/red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

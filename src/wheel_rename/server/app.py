"""FastAPI application for the PEP 503 proxy server."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import RedirectResponse

from wheel_rename.server.config import ProxyConfig  # noqa: TC001 - used at runtime
from wheel_rename.server.html import generate_project_index, generate_root_index
from wheel_rename.server.stream import original_filename_from_renamed, stream_and_rename_wheel
from wheel_rename.server.upstream import UpstreamClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


def create_app(config: ProxyConfig) -> FastAPI:
    """Create a FastAPI application with the given configuration.

    Args:
        config: Proxy server configuration

    Returns:
        Configured FastAPI application
    """
    upstream_client: UpstreamClient | None = None

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        """Manage the upstream client lifecycle."""
        nonlocal upstream_client
        upstream_client = UpstreamClient(config)
        async with upstream_client:
            yield

    app = FastAPI(
        title="wheel-rename proxy",
        description="PEP 503 compatible package index with on-the-fly renaming",
        lifespan=lifespan,
    )

    def get_client() -> UpstreamClient:
        """Get the upstream client."""
        if upstream_client is None:
            msg = "Upstream client not initialized"
            raise RuntimeError(msg)
        return upstream_client

    @app.get("/")
    async def root() -> RedirectResponse:
        """Redirect root to /simple/."""
        return RedirectResponse(url="/simple/")

    @app.get("/simple/")
    async def simple_index() -> Response:
        """List all available projects.

        This includes:
        - All projects from upstream indexes
        - Virtual packages from rename rules (e.g., icechunk_v1)
        """
        # Start with virtual packages from rename rules
        projects = set(config.get_virtual_packages())

        # For a full proxy, we'd also fetch all projects from upstream
        # But that's expensive, so we only list our virtual packages
        # Real packages are fetched on-demand when their project page is requested

        html = generate_root_index(sorted(projects))
        return Response(content=html, media_type="text/html")

    @app.get("/simple/{project}/")
    async def project_index(project: str) -> Response:
        """List wheels for a project.

        If the project is a virtual renamed package:
        - Fetch the original package from upstream
        - Filter by version constraint
        - Rewrite filenames

        Otherwise:
        - Passthrough to upstream
        """
        client = get_client()

        # Check if this is a renamed virtual package
        rename_rule = config.get_rename_rule(project)

        if rename_rule:
            # Fetch the original package
            packages = await client.get_project_page(rename_rule.original, rename_rule)

            if not packages:
                raise HTTPException(
                    status_code=404,
                    detail=f"No packages found for {rename_rule.original}",
                )

            html = generate_project_index(project, packages, rename_rule)
        else:
            # Passthrough - fetch from upstream as-is
            packages = await client.get_project_page(project)

            if not packages:
                raise HTTPException(
                    status_code=404,
                    detail=f"Project not found: {project}",
                )

            html = generate_project_index(project, packages)

        return Response(content=html, media_type="text/html")

    @app.get("/simple/{project}/{filename}")
    async def download_wheel(project: str, filename: str) -> Response:
        """Download a wheel file.

        If the project is a renamed virtual package:
        - Map the filename back to original
        - Download from upstream
        - Rename on-the-fly
        - Return renamed wheel

        Otherwise:
        - Redirect to upstream URL
        """
        client = get_client()

        # Check if this is a renamed virtual package
        rename_rule = config.get_rename_rule(project)

        if rename_rule:
            # Map the renamed filename back to original
            original_filename = original_filename_from_renamed(
                filename, rename_rule.original, rename_rule.new_name
            )

            # Fetch packages to find the URL
            packages = await client.get_project_page(rename_rule.original, rename_rule)

            # Find the package URL
            upstream_url = client.find_package_url(packages, original_filename)

            if not upstream_url:
                raise HTTPException(
                    status_code=404,
                    detail=f"Package not found: {original_filename}",
                )

            # Download and rename
            renamed_bytes = await stream_and_rename_wheel(
                client, upstream_url, rename_rule.new_name
            )

            return Response(
                content=renamed_bytes,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )
        else:
            # Passthrough - find upstream URL and redirect
            packages = await client.get_project_page(project)

            # Find the package
            upstream_url = None
            for pkg in packages:
                if pkg["filename"] == filename:
                    upstream_url = pkg["url"]
                    break

            if not upstream_url:
                raise HTTPException(
                    status_code=404,
                    detail=f"Package not found: {filename}",
                )

            # Redirect to upstream
            return RedirectResponse(url=upstream_url, status_code=302)

    return app

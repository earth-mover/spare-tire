"""FastAPI application for the PEP 503 proxy server."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import RedirectResponse

from third_wheel.server.config import ProxyConfig  # noqa: TC001 - used at runtime
from third_wheel.server.html import generate_project_index, generate_root_index
from third_wheel.server.stream import (
    original_filename_from_renamed,
    stream_and_patch_wheel,
    stream_and_rename_wheel,
)
from third_wheel.server.upstream import UpstreamClient

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
        title="third-wheel proxy",
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
        # Virtual packages from rename rules + patched packages
        projects = set(config.get_virtual_packages())
        for rule in config.patches:
            projects.add(rule.package)

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
        patch_rule = config.get_patch_rule(project)

        if rename_rule:
            # Fetch the original package
            packages = await client.get_project_page(rename_rule.original, rename_rule)

            if not packages:
                raise HTTPException(
                    status_code=404,
                    detail=f"No packages found for {rename_rule.original}",
                )

            html = generate_project_index(project, packages, rename_rule)
        elif patch_rule:
            # Fetch the package from upstream — we'll patch it on download
            packages = await client.get_project_page(project)

            if not packages:
                raise HTTPException(
                    status_code=404,
                    detail=f"No packages found for {project}",
                )

            # Strip hashes — content will change after patching
            html = generate_project_index(project, packages, strip_hashes=True)
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
        patch_rule = config.get_patch_rule(project)

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
        elif patch_rule:
            # Fetch packages to find the URL
            packages = await client.get_project_page(project)
            upstream_url = client.find_package_url(packages, filename)

            if not upstream_url:
                raise HTTPException(
                    status_code=404,
                    detail=f"Package not found: {filename}",
                )

            # Download and patch
            patched_bytes = await stream_and_patch_wheel(
                client, upstream_url, patch_rule.old_dep, patch_rule.new_dep
            )

            return Response(
                content=patched_bytes,
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

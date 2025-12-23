"""PEP 503 HTML generation for the proxy server."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wheel_rename.server.config import RenameRule


def generate_root_index(projects: list[str]) -> str:
    """Generate the root /simple/ HTML page listing all projects.

    Args:
        projects: List of project names to include

    Returns:
        PEP 503 compliant HTML
    """
    links = "\n".join(
        f'    <a href="{project}/">{project}</a>' for project in sorted(set(projects))
    )
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta name="pypi:repository-version" content="1.0">
    <title>Simple Index</title>
</head>
<body>
{links}
</body>
</html>
"""


def generate_project_index(
    project: str,
    packages: list[dict[str, str | None]],
    rename_rule: RenameRule | None = None,
) -> str:
    """Generate the project page HTML listing all wheels.

    Args:
        project: Project name (may be renamed)
        packages: List of package dicts with 'filename', 'url', 'requires_python', 'hash'
        rename_rule: If set, rewrite filenames from original to new name

    Returns:
        PEP 503 compliant HTML
    """
    links = []
    for pkg in packages:
        filename = pkg["filename"]
        url = pkg.get("url", filename)

        # If this is a renamed package, rewrite the filename
        if rename_rule is not None:
            # Replace original name with new name in filename
            # e.g., icechunk-1.0.0-... -> icechunk_v1-1.0.0-...
            filename = filename.replace(f"{rename_rule.original}-", f"{rename_rule.new_name}-", 1)
            # URL points to ourselves for download (we'll rename on-the-fly)
            url = filename

        # Build anchor attributes
        attrs = [f'href="{url}"']

        if pkg.get("requires_python"):
            attrs.append(f'data-requires-python="{pkg["requires_python"]}"')

        if pkg.get("hash") and "#" not in url:
            # Append hash as fragment
            attrs[0] = f'href="{url}#{pkg["hash"]}"'

        link = f"    <a {' '.join(attrs)}>{filename}</a>"
        links.append(link)

    links_html = "\n".join(links)
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta name="pypi:repository-version" content="1.0">
    <title>Links for {project}</title>
</head>
<body>
    <h1>Links for {project}</h1>
{links_html}
</body>
</html>
"""

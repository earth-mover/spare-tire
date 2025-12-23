# Agent Instructions for wheel-rename

This document provides context and guidance for AI assistants working on the wheel-rename project.

## Project Overview

**wheel-rename** is a tool to rename Python wheel packages for multi-version installation. The primary use case is regression testing where you need both `icechunk` (v2) and `icechunk_v1` (renamed v1) installed simultaneously.

## Key Technical Concepts

### Wheel File Format (PEP 427)

- Wheels are ZIP files with `.whl` extension
- Structure: `{package}/`, `{package}-{version}.dist-info/`
- METADATA file contains package name, version, dependencies
- RECORD file contains SHA256 hashes of all files
- WHEEL file contains wheel metadata (generator, tags)

### Compiled Extensions Challenge

- `.so`/`.pyd` files contain `PyInit_{name}` symbol baked into binary
- This symbol MUST match the filename for Python to load the extension
- **Workaround**: If extension uses underscore prefix (e.g., `_icechunk_python.cpython-*.so`), parent directory can be renamed while keeping the `.so` filename unchanged
- Python imports `icechunk_v1._icechunk_python` and finds `PyInit__icechunk_python` correctly

### PEP 503 Simple Repository API

- Package indexes use this standard (PyPI, Anaconda.org)
- Root endpoint `/simple/` lists all projects
- Project endpoint `/simple/{project}/` lists all wheels
- Supports JSON variant (PEP 691) but HTML is most common

## Codebase Structure

```text
src/wheel_rename/
├── __init__.py      # Package exports
├── cli.py           # Click-based CLI with rich output
├── download.py      # PEP 503 index client using pypi-simple
├── rename.py        # Core wheel manipulation logic
└── server/          # (feature branch) Proxy server

tests/
├── conftest.py              # Shared fixtures for venv creation
├── test_rename.py           # Unit tests for rename functions
├── test_integration.py      # Import rewriting tests
├── test_dual_install.py     # Multi-package isolation tests
└── test_icechunk_integration.py  # Real icechunk wheel tests
```

## Important Functions

### `rename.py`

- `rename_wheel(wheel_path, new_name, output_dir, update_imports)` - Main entry point
- `_update_python_imports(content, old_name, new_name)` - Regex-based import rewriting
- `inspect_wheel(wheel_path)` - Analyze wheel structure, detect extensions
- `_compute_record_hash(data)` - SHA256 for RECORD file

### `download.py`

- `download_compatible_wheel(package, output_dir, index_url, version)` - Download best match
- `best_wheel(packages, compatible_tags)` - Select most compatible wheel
- `parse_wheel_tags(filename)` - Extract platform tags from wheel name

### `cli.py`

- Default command is `rename` when first arg ends with `.whl`
- Uses `DefaultToRename` custom Click group class
- Rich console output for nice formatting

## Testing Patterns

### Dual-Install Tests

Tests create isolated venvs and install both original and renamed packages to verify:

1. Both packages import without errors
2. Module `__file__` paths are distinct
3. Internal import chains stay within each package
4. No `sys.modules` contamination
5. No leaked references to old package name in renamed package

### Test Wheel Creation

Use `conftest.create_test_wheel()` to create synthetic wheels with version-tagged functions:

```python
v1_wheel = create_test_wheel(tmp_path, "mypkg", "1.0.0")
v1_renamed = rename_wheel(v1_wheel, "mypkg_v1", output_dir=tmp_path)
```

### Running Tests

```bash
uv run pytest tests/                     # All tests
uv run pytest tests/test_rename.py       # Unit tests only
uv run pytest -m integration             # Integration tests (slower, network)
```

## Common Tasks

### Adding a New CLI Command

1. Add function in `cli.py` with `@main.command()` decorator
2. Use Click options/arguments
3. Use `console.print()` for output, `err_console.print()` for errors
4. Handle exceptions and call `sys.exit(1)` on error

### Modifying Import Rewriting

The regex patterns in `_update_python_imports()` handle:

- `from pkg import x`
- `from pkg.submodule import x`
- `import pkg`
- `import pkg as alias`

Be careful with word boundaries (`\b`) to avoid partial matches.

### Adding Test Coverage

- Unit tests go in `test_rename.py`
- Import rewriting tests go in `test_integration.py`
- Multi-package isolation tests go in `test_dual_install.py`
- Real wheel tests go in `test_icechunk_integration.py` with `@pytest.mark.integration`

## Dependencies

Core:

- `click` - CLI framework
- `packaging` - Version parsing, platform tags
- `pypi-simple` - PEP 503 index client
- `rich` - Pretty terminal output

Server (optional, on feature branch):

- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `httpx` - Async HTTP client

## Git Workflow

- `main` branch has core rename/download/inspect functionality
- `feature/proxy-index` branch has the proxy server implementation
- Run `uv run ruff check src tests` before committing
- Pre-commit hooks handle formatting

## Environment

- Python 3.11+ required
- Use `uv` for environment management: `uv sync`, `uv run pytest`
- Ruff for linting and formatting
- Pyright for type checking (strict mode)

## Gotchas

1. **Anaconda.org doesn't provide digests** - Use `verify=False` when downloading
2. **Version specifiers with .dev releases** - Use `>=2.0.0.dev0` not `>=2.0.0a0` for dev releases
3. **pytest.skip() in fixtures** - Use assertions instead to avoid hiding failures
4. **pypi-simple is sync** - For async proxy, need to wrap or use httpx directly
5. **Wheel filenames must match internal metadata** - After renaming, filename, directory name, and METADATA Name must all match

## Useful Commands

```bash
# List available wheels for a package
uv run wheel-rename download icechunk --list -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple

# Inspect a wheel
uv run wheel-rename inspect ./icechunk-*.whl

# Rename a wheel
uv run wheel-rename ./icechunk-*.whl icechunk_v1 -o ./renamed/

# Download and rename in one step (manual)
uv run wheel-rename download icechunk -i ... --version "<2" -o ./wheels/
uv run wheel-rename ./wheels/icechunk-*.whl icechunk_v1 -o ./wheels/
```

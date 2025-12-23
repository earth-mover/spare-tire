# wheel-rename

A tool to rename Python wheel packages for multi-version installation.

## Use Case

When you need to install multiple versions of the same Python package in a single environment (e.g., for regression testing), you can use this tool to rename one version's wheel so both can coexist:

```python
# In your test code:
import icechunk_v1  # The v1 version
import icechunk     # The v2 version

# Test that v2 can read data written by v1
```

## Installation

```bash
# Use directly with uvx (recommended)
uvx wheel-rename --help

# Or install globally
pip install wheel-rename
```

## End-to-End Example: icechunk v1 + v2

Here's a complete example of setting up both icechunk versions for regression testing:

```bash
# 1. Download v1 wheel from nightly builds (no pip required!)
uvx wheel-rename download icechunk \
    -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \
    --version "<2" \
    -o ./wheels/

# 2. Inspect the wheel to verify it's renamable
uvx wheel-rename inspect ./wheels/icechunk-*.whl

# 3. Rename icechunk -> icechunk_v1
uvx wheel-rename ./wheels/icechunk-*.whl icechunk_v1 -o ./wheels/

# 4. Create a venv and install both versions
uv venv
uv pip install ./wheels/icechunk_v1-*.whl  # v1 as icechunk_v1
uv pip install icechunk                     # v2 from PyPI

# 5. Verify both work
uv run python -c "import icechunk_v1; print(f'v1: {icechunk_v1.__version__}')"
uv run python -c "import icechunk; print(f'v2: {icechunk.__version__}')"
```

## Commands

### rename (default)

Rename a wheel package. This is the default command when the first argument is a `.whl` file:

```bash
# These are equivalent:
wheel-rename <wheel_path> <new_name> [-o <output_dir>]
wheel-rename rename <wheel_path> <new_name> [-o <output_dir>]

# Examples:
wheel-rename icechunk-1.0.0-cp312-cp312-linux_x86_64.whl icechunk_v1
wheel-rename ./downloads/pkg.whl my_pkg_old -o ./renamed/
```

Options:
- `-o, --output`: Output directory (default: same as input)
- `--no-update-imports`: Don't update import statements in Python files

### download

Download a compatible wheel from a package index:

```bash
wheel-rename download <package> [-o <output_dir>] [-i <index_url>] [--version <spec>]

# Examples:
wheel-rename download numpy -o ./wheels/
wheel-rename download icechunk -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple
wheel-rename download requests --version ">=2.0,<3"
wheel-rename download icechunk --version "<2" -i https://pypi.anaconda.org/scientific-python-nightly-wheels/simple
```

Options:
- `-o, --output`: Output directory (default: current directory)
- `-i, --index-url`: Package index URL (default: PyPI)
- `--version`: PEP 440 version specifier (e.g., `==1.0.0`, `<2`, `>=1.0,<2`)
- `--list`: List available wheels without downloading

### inspect

Inspect a wheel's structure before renaming:

```bash
wheel-rename inspect <wheel_path> [--json]

# Example output:
# Wheel: icechunk-1.1.14-cp312-cp312-macosx_11_0_arm64.whl
# Distribution: icechunk
# Version: 1.1.14
#
# Compiled extensions (1):
#   - icechunk/_icechunk_python.cpython-312-darwin.so (underscore prefix - renamable)
#
# This wheel uses underscore-prefix extensions.
# Renaming should work correctly.
```

## How It Works

1. **Extracts** the wheel (which is a ZIP file)
2. **Renames** the package directory (`pkg/` → `pkg_v1/`)
3. **Renames** the `.dist-info` directory
4. **Updates METADATA** with the new package name
5. **Updates imports** in all Python files (`from pkg import` → `from pkg_v1 import`)
6. **Regenerates RECORD** with new file paths and SHA256 hashes
7. **Repacks** as a new wheel with the renamed filename

## Compiled Extensions

For wheels with compiled extensions (`.so`/`.pyd` files), renaming works **only if** the extension uses an underscore-prefix naming pattern:

| Pattern | Example | Renamable? |
|---------|---------|------------|
| `_modulename.cpython-*.so` | `_icechunk_python.cpython-312-darwin.so` | ✅ Yes |
| `modulename.cpython-*.so` | `icechunk.cpython-312-darwin.so` | ❌ No |

### Why underscore prefix matters

Python's import system requires the `PyInit_<name>` function inside the `.so` file to match the filename. When you have `_mymodule.cpython-*.so`:

- Python looks for `PyInit__mymodule` (matches!)
- The parent package directory can be renamed freely
- `from newpkg._mymodule import ...` works because the `.so` name is unchanged

If the extension doesn't use the underscore prefix pattern, the tool will warn you and you should rebuild from source instead.

## Limitations

- **Compiled extensions without underscore prefix**: Cannot be renamed without rebuilding
- **Hardcoded package names in strings**: Not automatically updated (only import statements are)
- **Entry points**: Updated in metadata but external scripts may need adjustment

## Development

```bash
# Clone and setup
git clone <repo>
cd wheel-rename
uv sync --all-extras

# Run tests
uv run pytest

# Lint and format
uv run ruff check src tests
uv run ruff format src tests
```

## License

BSD-3-Clause

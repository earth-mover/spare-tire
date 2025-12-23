# wheel-rename

A tool to rename Python wheel packages for multi-version installation.

## Use Case

When you need to install multiple versions of the same Python package in a single environment (e.g., for regression testing), you can use this tool to rename one version's wheel so both can coexist:

```bash
# Rename icechunk v1 wheel to icechunk_v1
uvx wheel-rename rename icechunk-1.0.0-cp311-cp311-macosx_arm64.whl icechunk_v1

# Now you can install both:
pip install ./icechunk_v1-1.0.0-cp311-cp311-macosx_arm64.whl
pip install icechunk  # v2 from PyPI
```

## Installation

```bash
# Use directly with uvx
uvx wheel-rename --help

# Or install
pip install wheel-rename
```

## Commands

### rename

Rename a wheel package:

```bash
wheel-rename rename <wheel_path> <new_name> [-o <output_dir>]
```

### inspect

Inspect a wheel's structure to check if it's safe to rename:

```bash
wheel-rename inspect <wheel_path> [--json]
```

## How It Works

1. Extracts the wheel (which is a ZIP file)
2. Renames the package directory
3. Renames the `.dist-info` directory
4. Updates the `METADATA` file with the new package name
5. Updates import statements in Python files (optional)
6. Regenerates the `RECORD` file with new hashes
7. Repacks as a new wheel

## Compiled Extensions

For wheels with compiled extensions (`.so`/`.pyd` files), renaming works if the extension uses an underscore-prefix naming pattern (e.g., `_mypackage.cpython-311-darwin.so`). The internal extension filename is kept unchanged, only the parent package directory is renamed.

If the extension doesn't use this pattern, the tool will warn you and recommend rebuilding from source instead.

## License

MIT

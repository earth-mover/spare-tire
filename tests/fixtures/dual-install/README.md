# Dual Icechunk Version Installation Example

This directory demonstrates how to install two versions of icechunk side-by-side
using `wheel-rename` as a proxy server.

## Use Case

You want to test that icechunk v2 can read data written by icechunk v1, or
vice versa. This requires both versions to be importable in the same Python
environment.

## How It Works

1. **Start the wheel-rename proxy** that renames `icechunk` → `icechunk_v1` for
   versions less than 2.0:

   ```bash
   wheel-rename serve \
       -u https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \
       -r "icechunk=icechunk_v1:<2" \
       --port 8123
   ```

2. **Install with uv sync** using this project's configuration:

   ```bash
   cd tests/fixtures/dual-install
   uv sync
   ```

3. **Use both versions** in your code:

   ```python
   import icechunk      # v2.x
   import icechunk_v1   # v1.x (renamed)

   # Create a repository with v1
   repo_v1 = icechunk_v1.Repository.create(...)

   # Read it with v2
   repo_v2 = icechunk.Repository.open(...)
   ```

## Configuration Explained

The `pyproject.toml` configures:

- **Dependencies**: Both `icechunk>=2.0.0.dev0` and `icechunk_v1`
- **requires-python**: `>=3.12` (required by nightly numpy)
- **Extra indexes**:
  - Anaconda nightly wheels (for latest icechunk v2 and deps)
  - Local proxy at `http://127.0.0.1:8123` (serves renamed icechunk_v1)
- **prerelease**: `allow` - enables dev/alpha versions
- **index-strategy**: `unsafe-best-match` - considers all versions from all indexes
  (required when mixing nightly wheels with PyPI)
- **resolution**: `highest` - prefers newest available versions

## Running Locally

```bash
# Terminal 1: Start the proxy
cd /path/to/wheel-rename
uv run wheel-rename serve \
    -u https://pypi.anaconda.org/scientific-python-nightly-wheels/simple \
    -r "icechunk=icechunk_v1:<2" \
    --port 8123

# Terminal 2: Install and test
cd tests/fixtures/dual-install
uv sync
uv run python -c "import icechunk; import icechunk_v1; print('Both imported!')"
```

## CI Usage

This fixture is used in the `proxy-dual-install` CI job to verify that the
proxy server works correctly for real-world multi-version installation.

# Novelos Version Policy

## Single source of truth

`novel_factory/version.py` is the product runtime version source of truth. A release uses one product version across the Python runtime and package metadata, the React workspace, and the Electron desktop client.

The following values must be exactly equal:

| Surface | Version location |
|---|---|
| Runtime | `novel_factory/version.py` → `__version__` |
| Python package | `pyproject.toml` → `[project].version` |
| Python lock | editable `novel-factory` entry in `uv.lock` |
| Frontend package | `frontend/package.json` → `version` |
| Frontend lock | `frontend/package-lock.json` root and `packages[""]` versions |
| Desktop package | `desktop/package.json` → `version` |
| Desktop lock | `desktop/package-lock.json` root and `packages[""]` versions |

Generated application bundles and vendored sidecars are release artifacts, not editable version sources. They are rebuilt after the manifest contract passes.

## Version change procedure

1. Choose the target product version.
2. Update `novel_factory/version.py` first.
3. Copy the exact value to every package and lock location in the table.
4. Add the target version entry to `CHANGELOG.md`.
5. Run `python3 scripts/release_preflight.py` during development.
6. Before recording release evidence, run `python3 scripts/verify.py release`.

Do not hard-code a current release number in feature tests. Tests should compare their surface to the runtime source of truth.

## Release gates

The preflight is read-only. It reports the Git worktree state, validates required manifests and version equality, checks lock roots, and requires a matching changelog entry. It never updates versions, commits files, or calls a real LLM.

`python3 scripts/verify.py release` is the canonical release-evidence command. A completion report must not claim a release-ready baseline unless that command exits successfully.

# Releasing memoir

This document describes how to cut a release of the `memoir` Python package to [PyPI](https://pypi.org/project/memoir/).

## One-time setup (first release only)

The release workflow uses **PyPI Trusted Publishing** (OIDC) — no long-lived API tokens are stored in GitHub secrets. The following one-time configuration is required before the first successful release.

### 1. Configure Trusted Publisher on PyPI

1. Create the project on [pypi.org](https://pypi.org/) (if not already reserved) by running a first manual upload, or let the first trusted-publishing upload create it.
2. Go to `https://pypi.org/manage/project/memoir/settings/publishing/` and add a **pending publisher** (for the first release) or a regular publisher (after the project exists):
   - **Owner**: `zhangfengcdt`
   - **Repository name**: `memoir`
   - **Workflow name**: `release.yml`
   - **Environment name**: `pypi`

### 2. Configure Trusted Publisher on TestPyPI

Repeat the same at [test.pypi.org](https://test.pypi.org/manage/account/publishing/) with the same parameters. This is what the dry-run path uses.

### 3. Create the `pypi` GitHub Environment

1. In the GitHub repo: **Settings → Environments → New environment** → name it `pypi`.
2. No required reviewers are needed by default. Optionally add yourself as a required reviewer to add an extra approval gate before publishing.

## Cutting a release

1. **Create a release branch from `main`:**

   ```bash
   git checkout main
   git pull
   git checkout -b release/X.Y.Z
   ```

2. **Bump the version.** Edit `src/memoir/__init__.py` line 6 — this is the single source of truth. `pyproject.toml` reads it dynamically.

   ```python
   __version__ = "X.Y.Z"  # Single source of truth; read by hatch + release workflow (keep on one line)
   ```

3. **Update `CHANGELOG.md`** (if present) with the release entry.

4. **Push the release branch:**

   ```bash
   git add src/memoir/__init__.py CHANGELOG.md
   git commit -m "Release vX.Y.Z"
   git push -u origin release/X.Y.Z
   ```

5. **Open a PR** from `release/X.Y.Z` into `main` but do **not** merge yet. The workflow runs on the branch, not on main.

6. **Dry run to TestPyPI:**

   - Go to **Actions → Release → Run workflow**.
   - Select the `release/X.Y.Z` branch.
   - Set `dry_run` to `true` (default).
   - Click **Run workflow**.
   - When it completes, verify `https://test.pypi.org/project/memoir/X.Y.Z/` exists.
   - Smoke-test install:

     ```bash
     python -m venv /tmp/memoir-test
     /tmp/memoir-test/bin/pip install \
       -i https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple/ \
       memoir==X.Y.Z
     /tmp/memoir-test/bin/memoir --help
     /tmp/memoir-test/bin/python -c "import memoir; print(memoir.__version__)"
     ```

7. **Real release:** re-run the workflow on the same branch with `dry_run=false`.
   - The `publish` job uploads to PyPI.
   - The `create-release` job creates a GitHub Release tagged `vX.Y.Z` with the wheel and sdist attached.

8. **Merge the PR** into `main`.

## Rollback

If a bad release reaches PyPI:

- **Do not delete the version** (PyPI does not allow re-uploading a deleted version).
- Instead, **yank** it: `https://pypi.org/manage/project/memoir/release/X.Y.Z/` → Yank release. Yanked versions are still installable by exact pin but are skipped by default resolvers.
- Cut `X.Y.(Z+1)` with the fix.

## Troubleshooting

- **403 Forbidden on publish** — Trusted publisher config mismatch. Re-check owner / repo / workflow filename / environment name on PyPI.
- **Missing data files in installed package** (`ui.html`, `static/`, `taxonomy/data/`) — Check `[tool.hatch.build.targets.wheel.force-include]` in `pyproject.toml`. The workflow's `Inspect wheel contents` step also fails fast if these are missing.
- **Version extraction fails** — The workflow greps `^__version__` from `src/memoir/__init__.py`. Keep the assignment on a single line without leading whitespace.
- **`twine check` fails on long description** — Most often a README rendering issue. Fix locally with `make release-check`.

## Don't

- Don't force-push a `release/*` branch once the workflow has started.
- Don't edit the version in `pyproject.toml` directly — it's `dynamic`. Edit `src/memoir/__init__.py` only.
- Don't skip the dry-run step — TestPyPI is free and catches most issues.

# Releasing memoir

This document describes how to cut a release of the `memoir-ai` Python package to [PyPI](https://pypi.org/project/memoir-ai/). (The Python import name is `memoir`; the distribution name on PyPI is `memoir-ai` because `memoir` was already taken.)

The release workflow uses **PyPI Trusted Publishing** (OIDC) — no long-lived API tokens in GitHub secrets. Trusted publishers on [PyPI](https://pypi.org/manage/account/publishing/) and [TestPyPI](https://test.pypi.org/manage/account/publishing/) must be configured with project name `memoir-ai`, owner `zhangfengcdt`, repo `memoir`, workflow `release.yml`, environment `pypi`. A GitHub Environment named `pypi` must also exist.

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
   - When it completes, verify `https://test.pypi.org/project/memoir-ai/X.Y.Z/` exists.
   - Smoke-test install:

     ```bash
     python -m venv /tmp/memoir-test
     /tmp/memoir-test/bin/pip install \
       -i https://test.pypi.org/simple/ \
       --extra-index-url https://pypi.org/simple/ \
       memoir-ai==X.Y.Z
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
- Instead, **yank** it: `https://pypi.org/manage/project/memoir-ai/release/X.Y.Z/` → Yank release. Yanked versions are still installable by exact pin but are skipped by default resolvers.
- Cut `X.Y.(Z+1)` with the fix.

## Troubleshooting

- **403 Forbidden on publish** — Trusted publisher config mismatch. Most often the **PyPI project name** field doesn't match `[project] name` in `pyproject.toml` (currently `memoir-ai`). Also re-check owner / repo / workflow filename / environment name. Remember PyPI and TestPyPI have separate publisher configs.
- **Missing data files in installed package** (`ui.html`, `static/`, `taxonomy/data/`) — hatchling includes them by default via `[tool.hatch.build.targets.wheel] packages = ["src/memoir"]`. The workflow's `Inspect wheel contents` step fails fast if they're absent.
- **Version extraction fails** — The workflow greps `^__version__` from `src/memoir/__init__.py`. Keep the assignment on a single line without leading whitespace.
- **`twine check` fails on long description** — Most often a README rendering issue. Fix locally with `make release-check`.

## Don't

- Don't force-push a `release/*` branch once the workflow has started.
- Don't edit the version in `pyproject.toml` directly — it's `dynamic`. Edit `src/memoir/__init__.py` only.
- Don't skip the dry-run step — TestPyPI is free and catches most issues.

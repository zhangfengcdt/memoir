# Releasing memoir

Memoir ships as **three independently versioned products**:

| Product | Version source of truth | Distributed via |
| --- | --- | --- |
| Python package `memoir-ai` | `src/memoir/__init__.py` → `__version__` | [PyPI](https://pypi.org/project/memoir-ai/) |
| Claude Code plugin `memoir` | `plugins/claude-code/.claude-plugin/plugin.json` → `version` | Marketplace (`.claude-plugin/marketplace.json`) |
| Codex plugin `memoir-codex` | `plugins/memoir-codex/.codex-plugin/plugin.json` → `version` | Marketplace (`.agents/plugins/marketplace.json`) |

The three product versions may diverge (different release cadences). Within each product, every manifest that declares the version **must agree** — enforced in CI by `scripts/check_version_consistency.py` (see [Version consistency](#version-consistency) below).

(The Python import name is `memoir`; the distribution name on PyPI is `memoir-ai` because `memoir` was already taken.)

The PyPI release workflow uses **PyPI Trusted Publishing** (OIDC) — no long-lived API tokens in GitHub secrets. Trusted publishers on [PyPI](https://pypi.org/manage/account/publishing/) and [TestPyPI](https://test.pypi.org/manage/account/publishing/) must be configured with project name `memoir-ai`, owner `zhangfengcdt`, repo `memoir`, workflow `release.yml`, environment `pypi`. A GitHub Environment named `pypi` must also exist.

## Version consistency

Before pushing a release branch, run:

```bash
make check-versions
# or:
python3 scripts/check_version_consistency.py
```

This verifies that every version-bearing file inside each product agrees. CI runs the same check in the `lint` job.

**All files that declare a version:**

- **Python package (`memoir-ai`)**
  - `src/memoir/__init__.py` — `__version__ = "X.Y.Z"`  *(source of truth; `pyproject.toml` reads it via `[tool.hatch.version]`)*
- **Claude Code plugin (`memoir`)** — all three must match:
  - `plugins/claude-code/.claude-plugin/plugin.json` — `"version": "X.Y.Z"`
  - `.claude-plugin/marketplace.json` — `metadata.version`
  - `.claude-plugin/marketplace.json` — `plugins[<memoir>].version`
- **Codex plugin (`memoir-codex`)**
  - `plugins/memoir-codex/.codex-plugin/plugin.json` — `"version": "X.Y.Z"`

The first Codex plugin release starts at `0.1.0` even if the Python package and Claude Code plugin are on later versions, because it is a new independently versioned product surface.

Ancillary versions that are **intentionally independent** and not checked:

- `src/memoir/ui/__init__.py` — UI app version, decoupled from the package.
- `pyproject.toml` `target-version` / `python_version` / `minversion` — tool configs, not package versions.

## Cutting a Python package release (PyPI)

1. **Create a release branch from `main`:**

   ```bash
   git checkout main
   git pull
   git checkout -b release/X.Y.Z
   ```

2. **Bump the version.** Edit `src/memoir/__init__.py` line 6 — this is the single source of truth for the Python package. `pyproject.toml` reads it dynamically.

   ```python
   __version__ = "X.Y.Z"  # Single source of truth; read by hatch + release workflow (keep on one line)
   ```

   Run `make check-versions` to confirm the Python-package group stays consistent.

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

## Cutting a Claude Code plugin release

The plugin is distributed via the marketplace file in this repo — there is no external registry to publish to. A "release" is a coordinated version bump across three manifests plus a tag.

1. **Create a release branch from `main`:**

   ```bash
   git checkout -b release/plugin-X.Y.Z
   ```

2. **Bump the plugin version in all three locations** (they must stay in lockstep):

   - `plugins/claude-code/.claude-plugin/plugin.json` → `"version": "X.Y.Z"`
   - `.claude-plugin/marketplace.json` → `metadata.version`
   - `.claude-plugin/marketplace.json` → `plugins[0].version` (the entry where `name == "memoir"`)

3. **Verify consistency:**

   ```bash
   make check-versions
   ```

   This must pass before pushing.

4. **Commit and push:**

   ```bash
   git add plugins/claude-code/.claude-plugin/plugin.json .claude-plugin/marketplace.json
   git commit -m "Release plugin vX.Y.Z"
   git push -u origin release/plugin-X.Y.Z
   ```

5. **Open a PR, merge after review, then tag:**

   ```bash
   git checkout main && git pull
   git tag plugin-vX.Y.Z
   git push origin plugin-vX.Y.Z
   ```

Users pick up the new plugin version on their next `/plugin update memoir` (or whatever refresh command they use for marketplace-sourced plugins).

## Cutting a Codex plugin release

The Codex plugin is distributed by this repository's marketplace at `.agents/plugins/marketplace.json`. There is no separate Codex registry publish step today; after the release PR merges to `zhangfengcdt/memoir`, users install or refresh the marketplace from `/plugins` by adding the `memoir` marketplace from `zhangfengcdt/memoir`, or from the CLI with `codex plugin marketplace add zhangfengcdt/memoir` / `codex plugin marketplace upgrade memoir`.

1. **Create a release branch from `main`:**

   ```bash
   git checkout -b release/codex-plugin-X.Y.Z
   ```

2. **Bump the plugin manifest:**

   - `plugins/memoir-codex/.codex-plugin/plugin.json` → `"version": "X.Y.Z"`

3. **Verify consistency and tests:**

   ```bash
   make check-versions
   pytest plugins/memoir-codex/tests -v
   plugins/memoir-codex/tests/prompt-harness/runner.py gate --hook user-prompt-submit
   ```

4. **Run a real Codex smoke test with `gpt-5.4`** in `/tmp/memoir-codex-smoke`, export evidence to `/tmp/memoir-codex-smoke/evidence.md`, then clean the disposable project and store.

5. **Commit and push:**

   ```bash
   git add plugins/memoir-codex docs/codex.md .agents/plugins/marketplace.json
   git commit -m "Release Codex plugin vX.Y.Z"
   git push -u origin release/codex-plugin-X.Y.Z
   ```

6. **Open a PR, merge after review, then tag:**

   ```bash
   git checkout main && git pull
   git tag codex-plugin-vX.Y.Z
   git push origin codex-plugin-vX.Y.Z
   ```

## Rollback

If a bad release reaches PyPI:

- **Do not delete the version** (PyPI does not allow re-uploading a deleted version).
- Instead, **yank** it: `https://pypi.org/manage/project/memoir-ai/release/X.Y.Z/` → Yank release. Yanked versions are still installable by exact pin but are skipped by default resolvers.
- Cut `X.Y.(Z+1)` with the fix.

## Troubleshooting

- **403 Forbidden on publish** — Trusted publisher config mismatch. Most often the **PyPI project name** field doesn't match `[project] name` in `pyproject.toml` (currently `memoir-ai`). Also re-check owner / repo / workflow filename / environment name. Remember PyPI and TestPyPI have separate publisher configs.
- **Missing data files in installed package** (`webapp/dist/`, `taxonomy/data/`) — hatchling includes them by default via `[tool.hatch.build.targets.wheel] packages = ["src/memoir"]`; the webapp bundle is force-included via `artifacts` because `dist/` is git-ignored. The workflow's `Inspect wheel contents` step fails fast if they're absent.
- **Version extraction fails** — The workflow greps `^__version__` from `src/memoir/__init__.py`. Keep the assignment on a single line without leading whitespace.
- **`twine check` fails on long description** — Most often a README rendering issue. Fix locally with `make release-check`.

## Don't

- Don't force-push a `release/*` branch once the workflow has started.
- Don't edit the version in `pyproject.toml` directly — it's `dynamic`. Edit `src/memoir/__init__.py` only.
- Don't skip the dry-run step — TestPyPI is free and catches most issues.
- Don't bump only one of the three plugin manifests (`plugin.json`, `marketplace.json` metadata, `marketplace.json` plugin entry). `make check-versions` will fail in CI — run it locally first.

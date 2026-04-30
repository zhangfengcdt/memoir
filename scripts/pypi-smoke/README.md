# pypi-smoke

Smoke test that proves `pip install memoir-ai==<version>` works on a clean
machine (Python + git only — no Make, no node, no API keys) and that the
shipped CLI **and** the shipped UI both function end-to-end.

The harness is a Docker container, so the host stays clean and the test
behaves the same way regardless of who runs it. The same `smoke.sh`
also runs from a manual GitHub Actions workflow (see
`.github/workflows/pypi-smoke.yml`) — set `MEMOIR_SMOKE_HEADLESS=1` and
the script exits cleanly after the curl assertions instead of holding
the UI open for a human.

## Prerequisites

- Docker
- A version of `memoir-ai` already published to PyPI

## Usage

From the repo root:

```bash
scripts/pypi-smoke/run.sh 0.1.4
```

`run.sh` builds an image pinned to that PyPI version and runs the
container with port `9090` forwarded to the host.

## What gets checked

The harness runs ~18 small named test cases and reports per-case
pass/fail with timing. Cases are grouped into:

- **Install / version** — `memoir` on PATH, `--version` matches the
  requested release.
- **Store** — `memoir new` creates a git repo, `connect` persists, status
  + `--json` output is valid JSON.
- **Memory** — write three memories with explicit paths, read each back,
  `forget` removes a key, `get` on a missing key exits non-zero.
- **Branch** — create a branch, list it, switch to it, write a memory
  there, switch back to main, confirm the feature-branch memory does
  *not* leak.
- **UI** — server binds on :9090, `/` serves HTML with the React root,
  and four read-only API endpoints respond with sane JSON
  (`/api/branches`, `/api/current-branch`, `/api/statistics`,
  `/api/commits`).
- **LLM (gated)** — when `ANTHROPIC_API_KEY` is set, two extra cases run
  that exercise the LLM-backed code paths: `remember` without `-p`
  (auto-classification via `IntelligentClassifier`) and `recall` against
  the populated store. Without a key, both are reported as **SKIP** with
  a reason and the rest of the suite still passes. Model: memoir's
  default `claude-haiku-4-5`. Cost: a few cents per run.

  These cases require the `[litellm]` extra. The Docker image already
  installs `memoir-ai[litellm]==<version>` so this is wired up
  automatically. The `cli-remember-no-path-uses-llm` assertion now also
  rejects memoir's `memory.<unix-timestamp>` fallback path so the test
  fails (rather than spuriously passing) if the LLM round-trip didn't
  actually run.

Each case is independent: a failure prints its own diagnostic and the
runner keeps going so you see the full picture, then exits non-zero at
the end if anything failed.

The script also captures the test environment (memoir version, Python,
OS, arch, git) and prints it before the results.

**Manual (you, in your host browser) — once the script prints `OK`:**

1. Open `http://localhost:9090` in your browser.
2. Confirm the page loads — no white screen, no "failed to fetch" banners.
3. Click around: timeline view renders, click a branch, open a key detail panel.
4. Open DevTools → Console — confirm no red errors.
5. `Ctrl-C` in the terminal when satisfied.

The browser check catches things curl can't: a JS chunk that 404s, a
missing CSS asset, an API response shape the frontend doesn't know how
to render, etc.

## Running from CI

A manual GitHub Actions workflow (`PyPI Smoke Test`) does the same thing
without the human step. Trigger from the Actions tab or via CLI:

```bash
gh workflow run pypi-smoke.yml -f version=0.1.5
```

To enable the LLM cases locally:

```bash
export ANTHROPIC_API_KEY=sk-ant-…
scripts/pypi-smoke/run.sh 0.1.6
```

To enable in CI: configure `ANTHROPIC_API_KEY` in repo settings →
Settings → Secrets and variables → Actions. The workflow already wires
it through; absence of the secret silently falls back to SKIP.

The workflow builds the same image, runs the container with
`MEMOIR_SMOKE_HEADLESS=1` plus `MEMOIR_SMOKE_SUMMARY_FILE` pointed at a
bind-mounted host path, and appends the resulting markdown to
`GITHUB_STEP_SUMMARY` — so the run page shows a per-case results table
plus the test environment, regardless of pass or fail.

## Out of scope

- LLM-required commands (`memoir recall`, `memoir ui --usellm`) — no API
  key on the test machine by design.
- Multi-version Python matrix. We pin to `python:3.11-slim`; add 3.10 / 3.12
  only if a real bug surfaces.
- CI integration. Wire this into `release.yml` post-publish in a separate
  PR after the harness has been used by hand at least once.

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

**Automated (in-container):**

- `memoir --version` matches the requested version
- `memoir new` / `memoir connect` succeed
- `memoir remember "test fact" -p preferences.coding.style` writes
- `memoir get preferences.coding.style` reads back the same content
- `memoir branch` lists `main`
- `memoir status` exits cleanly
- `memoir ui --no-browser --port 9090 --idle-timeout 0` starts the server
- `GET /` returns HTML with the React root `<div id="root">`
- `GET /api/branches?store=/tmp/store` returns non-empty JSON
- `GET /api/current-branch?store=/tmp/store` returns 200

If any of these fail, the script exits non-zero and prints `FAIL: …`.

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
gh workflow run pypi-smoke.yml -f version=0.1.4
```

The workflow builds the same image, runs the container with
`MEMOIR_SMOKE_HEADLESS=1`, and the run goes red if any assertion fails.

## Out of scope

- LLM-required commands (`memoir recall`, `memoir ui --usellm`) — no API
  key on the test machine by design.
- Multi-version Python matrix. We pin to `python:3.11-slim`; add 3.10 / 3.12
  only if a real bug surfaces.
- CI integration. Wire this into `release.yml` post-publish in a separate
  PR after the harness has been used by hand at least once.

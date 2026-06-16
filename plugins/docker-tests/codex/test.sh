#!/usr/bin/env bash
# In-container smoke test for the memoir Codex plugin. Verifies the plugin's
# memoir integration headlessly (CLI resolution, store creation, capture).
# Pass ANTHROPIC_API_KEY for the capture step (the only LLM call).
#
# Note: the live Stop-hook capture runs inside a Codex session (needs Codex
# auth) — not exercised here; this checks the deterministic memoir plumbing.
set +e
ROOT="${MEMOIR_PLUGIN_ROOT:-/opt/memoir/plugins/codex}"

echo "===== 1. versions ====="
codex --version 2>&1 | head -1
memoir --version 2>&1 | head -1

echo
echo "===== 2. plugin files present ====="
ls "$ROOT" | tr '\n' ' '; echo

echo
echo "===== 3. plugin resolves the memoir CLI (resolve-memoir-cli.sh) ====="
# shellcheck disable=SC1091
source "$ROOT/scripts/resolve-memoir-cli.sh"
echo "MEMOIR_CMD=${MEMOIR_CMD:-<unresolved>}"

echo
echo "===== 4. plugin creates a store (ensure-store.sh) ====="
bash "$ROOT/scripts/ensure-store.sh" /tmp/codex-store >/dev/null 2>&1
memoir --json -s /tmp/codex-store status 2>/dev/null \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('branch:', d.get('branch'), '| memories:', d.get('memory_count'))"

echo
echo "===== 5. memoir capture works (needs ANTHROPIC_API_KEY) ====="
printf '[Human]\nWe use pytest and lint-before-commit; deploy is GitHub Actions.\n[Assistant]\nNoted.\n' \
  | memoir -s /tmp/codex-store capture --profile coding 2>&1 | tail -12

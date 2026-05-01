#!/usr/bin/env bash
# Host entry point for the Claude Code end-to-end smoke harness. Sanity-checks
# that the prerequisites are in place, then dispatches to smoke.sh.
#
# Usage: bash scripts/cc-smoke/run.sh
# Env:
#   CC_SMOKE_MODEL            override the model (default: claude-haiku-4-5)
#   CC_SMOKE_PLUGIN_DIR       override the plugin source dir under test
#                             (default: <repo>/plugins/claude-code)

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

if ! command -v claude >/dev/null 2>&1; then
  echo "ERROR: \`claude\` CLI not found on PATH."
  echo "Install Claude Code (https://docs.claude.com/claude-code) and run \`claude /login\`."
  exit 2
fi

if ! command -v memoir >/dev/null 2>&1; then
  echo "ERROR: \`memoir\` CLI not found on PATH."
  echo "Activate the venv (\`source venv/bin/activate\`) or install memoir-ai."
  exit 2
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "ERROR: \`jq\` not found on PATH (needed to parse stream-json hook events)."
  exit 2
fi

PLUGIN_DIR="${CC_SMOKE_PLUGIN_DIR:-$REPO/plugins/claude-code}"
if [ ! -d "$PLUGIN_DIR" ]; then
  echo "ERROR: plugin dir not found: $PLUGIN_DIR"
  exit 2
fi

export CC_SMOKE_PLUGIN_DIR="$PLUGIN_DIR"
export CC_SMOKE_MODEL="${CC_SMOKE_MODEL:-claude-haiku-4-5}"

echo "== cc-smoke =="
echo "  plugin-dir: $PLUGIN_DIR"
echo "  model:      $CC_SMOKE_MODEL"
echo "  claude:     $(claude --version 2>/dev/null | head -1 || echo unknown)"
echo "  memoir:     $(memoir --version 2>/dev/null | head -1 || echo unknown)"
echo

bash "$HERE/smoke.sh"

#!/usr/bin/env bash
# Idempotently create the memoir store at $1 with the builtin taxonomy.
#
# This is the single source of truth for store creation across the plugin —
# the SessionStart hook calls it, and command snippets (remember,
# status, ui) call it on every invocation so first-time users don't get
# trapped in the "CLI was missing at SessionStart, store never created,
# every helper now errors with 'Store not found'" failure mode.
#
# Usage:
#   bash ensure-store.sh <STORE_PATH>
#
# Exits:
#   0   — store exists (already, or just created). Prints "created" on
#         stdout iff this call is what materialized it, empty otherwise.
#         Callers gate one-time setup (custom-taxonomy load, store-mode
#         marker write) on that string.
#   1   — store creation failed.
#   2   — missing argument.
#   127 — no memoir CLI available (PATH + uv chain both empty).
#
# Thin wrapper: the actual creation (idempotency check, taxonomy install,
# the scratch-dir workaround for non-git callers) now lives in memoir-ai
# core as `memoir ensure-store`, shared by every host plugin instead of
# each carrying its own copy. See src/memoir/cli/commands/store.py in the
# memoir-ai package.

set -e

STORE="${1:-}"
if [ -z "$STORE" ]; then
  echo "ensure-store.sh: missing store path argument" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Standalone callers may run this from a minimal PATH (e.g. skill-driven
# helpers after SessionStart missed store creation). Mirror the same user bin
# bootstrap the other Codex helper entry points use before resolving the CLI.
for p in "$HOME/.local/bin" "$HOME/.cargo/bin" "$HOME/bin" "/usr/local/bin" "/opt/homebrew/bin"; do
  [[ -d "$p" ]] && [[ ":$PATH:" != *":$p:"* ]] && export PATH="$p:$PATH"
done

# shellcheck source=resolve-memoir-cli.sh
source "$SCRIPT_DIR/resolve-memoir-cli.sh"

if [ "${#MEMOIR_CMD_ARGV[@]}" -eq 0 ]; then
  echo "$MEMOIR_INSTALL_HINT" >&2
  exit 127
fi

result="$("${MEMOIR_CMD_ARGV[@]}" --json ensure-store "$STORE")" || {
  echo "ensure-store.sh: failed to create store at $STORE" >&2
  exit 1
}

created=$(printf '%s' "$result" | python3 -c 'import json, sys; print(json.load(sys.stdin).get("created", False))')
[ "$created" = "True" ] && echo "created"
exit 0

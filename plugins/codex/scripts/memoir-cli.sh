#!/usr/bin/env bash
# Drop-in wrapper for the memoir CLI that honours the plugin's fallback chain.
#
# Use this from contexts that need a single command token (e.g. skill prompts
# generating bash) instead of hardcoding `memoir`. With this wrapper:
#
#   bash "$PLUGIN_ROOT/scripts/memoir-cli.sh" --json -s "$STORE" status
#
# works on any machine where the chain in resolve-memoir-cli.sh resolves —
# i.e. memoir on PATH, or just `uv` installed (transparent uvx fallback).
#
# If no entry in the chain is available, prints the canonical install hint
# to stderr and exits 127 (the standard "command not found" code), so the
# caller can detect the missing-CLI state in the usual shell way.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Hooks pre-extend PATH with user bin dirs in common.sh; standalone callers
# don't, so do it here too — a `pip install --user memoir-ai` puts the
# binary in ~/.local/bin which isn't on PATH inside Codex's Bash tool
# subshells by default.
for p in "$HOME/.local/bin" "$HOME/.cargo/bin" "$HOME/bin" "/usr/local/bin" "/opt/homebrew/bin"; do
  [[ -d "$p" ]] && [[ ":$PATH:" != *":$p:"* ]] && export PATH="$p:$PATH"
done

# shellcheck source=resolve-memoir-cli.sh
source "$SCRIPT_DIR/resolve-memoir-cli.sh"

if [ "${#MEMOIR_CMD_ARGV[@]}" -eq 0 ]; then
  echo "$MEMOIR_INSTALL_HINT" >&2
  exit 127
fi

exec "${MEMOIR_CMD_ARGV[@]}" "$@"

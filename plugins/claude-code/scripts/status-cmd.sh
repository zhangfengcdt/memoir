#!/usr/bin/env bash
# Backing script for the /memoir:status slash command.
#
# Lives outside commands/status.md so it can `source resolve-memoir-cli.sh`
# and benefit from the same `memoir → uvx → uv tool run` fallback chain the
# hooks use. The previous inline `!`bash`` form in the markdown hard-coded
# `memoir`, which broke /memoir:status on machines that only had `uv`
# installed.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=resolve-memoir-cli.sh
source "$SCRIPT_DIR/resolve-memoir-cli.sh"

if [ "${#MEMOIR_CMD_ARGV[@]}" -eq 0 ]; then
  echo "ERROR: $MEMOIR_INSTALL_HINT" >&2
  exit 127
fi

STORE="${MEMOIR_STORE:-$(bash "$SCRIPT_DIR/derive-store-path.sh")}"

# First-time-user safety net: SessionStart is supposed to create the store,
# but if memoir wasn't installed when SessionStart fired (or the user
# installed memoir mid-session and then ran a slash command without
# restarting Claude Code) the store directory won't exist. Materialize it
# now so /memoir:status just works instead of erroring "Store not found".
bash "$SCRIPT_DIR/ensure-store.sh" "$STORE" >/dev/null || {
  echo "ERROR: failed to bootstrap memoir store at $STORE" >&2
  exit 1
}

exec "${MEMOIR_CMD_ARGV[@]}" --json -s "$STORE" status

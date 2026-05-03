#!/usr/bin/env bash
# Parse argv for /memoir:remember and invoke `memoir remember`.
#
# Lives in scripts/ (not in a commands/*.md inline bash block) because
# Claude Code's slash-command preprocessor substitutes $1, $2, $N inside
# the markdown body — even inside single-quoted bash strings — using the
# slash command's argument tokens. That rewriting silently breaks any
# bash positional dereference. Keeping the parse loop in a real shell
# script puts $1 etc. behind a script boundary that the preprocessor
# never crosses.
#
# Usage (from commands/remember.md):
#   bash "${CLAUDE_PLUGIN_ROOT}/scripts/remember-args.sh" $ARGUMENTS
#
# Each whitespace-split word of $ARGUMENTS arrives as a positional arg.
# -n / -p (and their long forms) consume their value; everything else is
# joined back into the content string with single spaces.
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
# now so /memoir:remember just works instead of erroring "Store not found".
bash "$SCRIPT_DIR/ensure-store.sh" "$STORE" >/dev/null || {
  echo "ERROR: failed to bootstrap memoir store at $STORE" >&2
  exit 1
}

content=""
flags=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    -n|-p|--namespace|--path)
      if [ "$#" -lt 2 ]; then
        echo "ERROR: $1 requires a value" >&2
        exit 2
      fi
      flags+=("$1" "$2")
      shift 2
      ;;
    *)
      if [ -z "$content" ]; then
        content="$1"
      else
        content="$content $1"
      fi
      shift
      ;;
  esac
done

if [ -z "$content" ]; then
  echo "ERROR: no content provided" >&2
  exit 2
fi

# Bash 3.2 / nounset safety: only expand the flags array when it has entries.
if [ "${#flags[@]}" -gt 0 ]; then
  exec env MEMOIR_LLM_BACKEND=claude-cli \
    "${MEMOIR_CMD_ARGV[@]}" --json -s "$STORE" remember "$content" "${flags[@]}"
else
  exec env MEMOIR_LLM_BACKEND=claude-cli \
    "${MEMOIR_CMD_ARGV[@]}" --json -s "$STORE" remember "$content"
fi

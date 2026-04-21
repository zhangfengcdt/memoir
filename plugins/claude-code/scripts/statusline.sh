#!/usr/bin/env bash
# memoir status-line widget: " | Memoir: <branch> · <N> memories"
#
# Designed for Claude Code's statusLine: reads branch from $STORE/.git/HEAD
# and memory count from a cache file written by the SessionStart + Stop hooks.
# No memoir CLI, no LLM, no subprocess beyond jq/python3 for one JSON parse —
# safe to run on every status-line refresh.
#
# Receives the statusLine JSON on stdin, emits a short suffix to stdout, and
# exits 0 with no output if there's no memoir store for the cwd (so the
# widget can be chained after any other statusLine command).
#
# Usage in ~/.claude/settings.json:
#   "statusLine": {
#     "type": "command",
#     "command": "input=$(cat); ... your existing line ...; printf '%s' \"$input\" | bash ~/.claude/plugins/cache/memoir/memoir/*/scripts/statusline.sh"
#   }

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

INPUT="$(cat 2>/dev/null || true)"

# cwd from statusLine JSON. Prefer workspace.current_dir (the project dir
# visible in the UI); fall back to cwd, then the shell's pwd.
CWD=""
if command -v jq &>/dev/null; then
  CWD=$(printf '%s' "$INPUT" | jq -r '.workspace.current_dir // .cwd // empty' 2>/dev/null || true)
elif command -v python3 &>/dev/null; then
  CWD=$(printf '%s' "$INPUT" | python3 -c "
import json, sys
try:
    obj = json.loads(sys.stdin.read() or '{}')
    print((obj.get('workspace') or {}).get('current_dir') or obj.get('cwd') or '')
except Exception:
    print('')
" 2>/dev/null || true)
fi
[ -z "$CWD" ] && CWD="$(pwd)"

STORE=$(bash "$SCRIPT_DIR/derive-store-path.sh" "$CWD" 2>/dev/null || true)
[ -z "$STORE" ] && exit 0
[ ! -d "$STORE/.git" ] && exit 0

# Branch: parse $STORE/.git/HEAD directly. On a named branch the file is
# "ref: refs/heads/<branch>"; in detached HEAD it's a raw sha — show the
# short hash so the widget still renders meaningfully.
BRANCH=""
if [ -f "$STORE/.git/HEAD" ]; then
  HEAD_REF=$(head -n1 "$STORE/.git/HEAD" 2>/dev/null || true)
  case "$HEAD_REF" in
    "ref: refs/heads/"*) BRANCH="${HEAD_REF#ref: refs/heads/}" ;;
    ?*)                  BRANCH="${HEAD_REF:0:8}" ;;
  esac
fi
[ -z "$BRANCH" ] && exit 0

# Memory count from cache (format: "<count>" on the first line). The hooks
# refresh this after every capture; on a fresh store it may not exist yet —
# fall back to showing just the branch.
CACHE="$STORE/.git/plugin-statusline-cache"
COUNT=""
if [ -f "$CACHE" ]; then
  COUNT=$(head -n1 "$CACHE" 2>/dev/null | tr -dc '0-9' || true)
fi

if [ -n "$COUNT" ]; then
  if [ "$COUNT" = "1" ]; then
    printf ' | Memoir: %s · %s memory' "$BRANCH" "$COUNT"
  else
    printf ' | Memoir: %s · %s memories' "$BRANCH" "$COUNT"
  fi
else
  printf ' | Memoir: %s' "$BRANCH"
fi

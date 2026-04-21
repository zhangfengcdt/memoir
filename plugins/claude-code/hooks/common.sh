#!/usr/bin/env bash
# Shared setup for memoir command hooks. Sourced by every hook.
#
# Conventions used throughout:
#   - memoir's global flags (--json, -s) must be passed BEFORE the subcommand.
#   - CLI resolution is PATH-only; if memoir is missing we surface a hint in
#     the status line and disable capture/recall. No uvx or git-URL fallbacks —
#     memoir is not on PyPI yet and silent installs would misconfigure users.

set -euo pipefail

# Read hook input JSON from stdin into $INPUT.
# timeout on Linux, perl alarm on macOS (which lacks timeout).
if command -v timeout &>/dev/null; then
  INPUT="$(timeout 2 cat 2>/dev/null || echo '{}')"
else
  INPUT="$(perl -e 'alarm 2; local $/; $_ = <STDIN>; print if defined' 2>/dev/null || echo '{}')"
fi

# Hooks may run in a minimal env; add common user bin paths so pip/uv installs are visible.
for p in "$HOME/.local/bin" "$HOME/.cargo/bin" "$HOME/bin" "/usr/local/bin"; do
  [[ -d "$p" ]] && [[ ":$PATH:" != *":$p:"* ]] && export PATH="$p:$PATH"
done

# Force memoir's LLM layer to the claude-cli backend so every memoir call the
# plugin makes (classification inside `memoir remember`, path selection inside
# `memoir recall`) rides Claude Code's auth — no OPENAI_API_KEY / ANTHROPIC_API_KEY
# needed. This is hard-set (not `${…:-claude-cli}`) because the plugin's whole
# value proposition under Claude Code is one-auth-for-everything; LiteLLM routing
# here would mean silent failures for users who don't have their own API key.
# If you need LiteLLM, use memoir outside the plugin.
export MEMOIR_LLM_BACKEND=claude-cli
# Model is still overridable — haiku is the sensible default, but a user who
# wants sonnet/opus for better classification can set MEMOIR_LLM_MODEL.
export MEMOIR_LLM_MODEL="${MEMOIR_LLM_MODEL:-claude-haiku-4-5}"

# Project directory: git root preferred (CLAUDE_PROJECT_DIR may point to a subdir
# inside forked `claude -p` sessions, which would otherwise create sibling stores).
_GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
if [ -n "$_GIT_ROOT" ]; then
  _PROJECT_DIR="$_GIT_ROOT"
else
  _PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
fi

# Resolve store path: MEMOIR_STORE env wins, else derive from project dir.
SCRIPT_PARENT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -n "${MEMOIR_STORE:-}" ]; then
  MEMOIR_STORE_PATH="$MEMOIR_STORE"
else
  MEMOIR_STORE_PATH="$(bash "$SCRIPT_PARENT/scripts/derive-store-path.sh" "$_PROJECT_DIR")"
fi

# Resolve the memoir CLI via PATH only. Empty MEMOIR_CMD => disabled.
if command -v memoir &>/dev/null; then
  MEMOIR_CMD="memoir"
else
  MEMOIR_CMD=""
fi

# Short prefix used in injected instructions / status lines even when CLI missing.
MEMOIR_CMD_PREFIX="${MEMOIR_CMD:-memoir}"

# --- JSON helpers (jq preferred, python3 fallback) ---

# _json_val <json_string> <dotted_key> [default]
_json_val() {
  local json="$1" key="$2" default="${3:-}"
  local result=""
  if command -v jq &>/dev/null; then
    result=$(printf '%s' "$json" | jq -r ".${key} // empty" 2>/dev/null) || true
  else
    result=$(python3 -c "
import json, sys
try:
    obj = json.loads(sys.argv[1])
    val = obj
    for k in sys.argv[2].split('.'):
        val = val[k]
    if val is None:
        print('')
    elif isinstance(val, bool):
        print(str(val).lower())
    else:
        print(val)
except Exception:
    print('')
" "$json" "$key" 2>/dev/null) || true
  fi
  if [ -z "$result" ]; then
    printf '%s' "$default"
  else
    printf '%s' "$result"
  fi
  return 0
}

# _json_encode_str <string>  -> JSON-encoded string (with surrounding quotes).
_json_encode_str() {
  local str="$1"
  if command -v jq &>/dev/null; then
    printf '%s' "$str" | jq -Rs . 2>/dev/null && return 0
  fi
  printf '%s' "$str" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read()))" 2>/dev/null && return 0
  printf '"%s"' "$str"
  return 0
}

# memoir_json <subcommand> [args...]
# Run memoir with --json and the resolved store path prepended. Silent on failure.
memoir_json() {
  if [ -z "$MEMOIR_CMD" ]; then
    return 1
  fi
  "$MEMOIR_CMD" --json -s "$MEMOIR_STORE_PATH" "$@" 2>/dev/null
}

# memoir_plain <subcommand> [args...]
# Same as memoir_json but without --json (for commands that don't support it or
# where human-readable output is desired).
memoir_plain() {
  if [ -z "$MEMOIR_CMD" ]; then
    return 1
  fi
  "$MEMOIR_CMD" -s "$MEMOIR_STORE_PATH" "$@" 2>/dev/null
}

# code_git_branch — current git branch of the user's project repo (not memoir's
# internal store). Used to disambiguate memoir's memory branch from the code
# branch in status lines: "memory:main · code:feature-x".
# Returns empty string if the project isn't a git repo or in detached HEAD.
code_git_branch() {
  if [ -z "$_GIT_ROOT" ]; then
    return 0
  fi
  git -C "$_GIT_ROOT" branch --show-current 2>/dev/null || true
}

# ensure_store — create the store directory with builtin taxonomy if missing.
# Safe to call on every SessionStart.
ensure_store() {
  if [ -z "$MEMOIR_CMD" ]; then
    return 1
  fi
  if [ ! -d "$MEMOIR_STORE_PATH/.git" ]; then
    mkdir -p "$(dirname "$MEMOIR_STORE_PATH")"
    # --no-connect because the plugin manages store selection via MEMOIR_STORE
    # env rather than memoir's global config file — we don't want to clobber
    # what a user may have set for CLI use outside the plugin.
    "$MEMOIR_CMD" new "$MEMOIR_STORE_PATH" --taxonomy-builtin --no-connect >/dev/null 2>&1 || return 1
  fi
  return 0
}

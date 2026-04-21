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

# --- branch auto-matching (memoir branch follows code branch) ---

# File locations inside the store's .git/ — these files are local-only state,
# not tracked because they live under .git.
_sticky_file() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-sticky-branch"; }
_ignored_branches_file() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-ignored-branches"; }
_synced_dir() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-synced-branches"; }

# record_branch_synced <branch> — called by /memoir-sync* after a successful
# merge. Records the Unix timestamp of the sync. The detector uses this to
# determine whether a branch's tip is newer than its last known promotion.
# Needed because memoir's merge rewrites patches on main, so git graph/diff
# checks (rev-list, merge-base, cherry, tree-diff) can't reliably detect
# "already merged".
record_branch_synced() {
  local name="$1"
  [ -z "$name" ] && return 1
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 1
  local dir f
  dir=$(_synced_dir)
  f="$dir/$name"
  # Branch names may contain `/` (feature/x); mkdir -p the parent of the
  # marker file so slash-paths are created as nested directories.
  mkdir -p "$(dirname "$f")"
  date +%s > "$f"
}

# branch_sync_timestamp <branch> — emit the recorded sync timestamp, or 0 if
# no marker exists.
branch_sync_timestamp() {
  local name="$1"
  local f
  f=$(_synced_dir)/"$name"
  if [ -f "$f" ]; then
    cat "$f" 2>/dev/null | head -n1
  else
    echo 0
  fi
}

# sticky_branch — return the name stored in .plugin-sticky-branch, or empty.
# Non-empty means the user explicitly picked a memoir branch that doesn't
# match the code branch; auto-matching stays off until cleared.
sticky_branch() {
  local f
  f=$(_sticky_file)
  [ -f "$f" ] && cat "$f" 2>/dev/null | head -n1 || true
}

set_sticky_branch() {
  local name="$1"
  local f
  f=$(_sticky_file)
  if [ -z "$name" ]; then
    rm -f "$f"
  else
    printf '%s\n' "$name" > "$f"
  fi
}

# is_branch_ignored <name> — user-maintained silence list.
is_branch_ignored() {
  local name="$1"
  local f
  f=$(_ignored_branches_file)
  [ -f "$f" ] || return 1
  grep -qxF "$name" "$f" 2>/dev/null
}

# branch_exists_in_memoir <name> — returns 0 if the memoir branch exists.
branch_exists_in_memoir() {
  local name="$1"
  [ -z "$MEMOIR_CMD" ] && return 1
  memoir_json branch 2>/dev/null | python3 -c "
import json, sys
try:
    obj = json.loads(sys.stdin.read() or '{}')
    branches = obj.get('branches', []) or []
    sys.exit(0 if sys.argv[1] in branches else 1)
except Exception:
    sys.exit(1)
" "$name"
}

# cleanup_store_worktree — reset the memoir store's working tree to match
# HEAD. Workaround for a prollytree behavior where `memoir checkout` updates
# .git/HEAD but doesn't sync the working tree + index, leaving `git status`
# showing `MM` on data files. Memoir itself reads from its internal data
# files (which ARE correct post-checkout), so this is primarily a `git status`
# cleanliness fix — but it also prevents the dirt from confusing subsequent
# git-based tooling or future memoir operations that might pay attention.
cleanup_store_worktree() {
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0
  git -C "$MEMOIR_STORE_PATH" reset --hard HEAD >/dev/null 2>&1 || true
}

# auto_match_memoir_branch — if auto-match isn't sticky-disabled and the
# current code branch differs from the checked-out memoir branch, create
# the memoir branch (forked from main) if needed and check it out.
# Emits nothing on stdout (all output routed to /dev/null); returns 0 on
# success, non-zero if memoir is missing or the operations failed.
auto_match_memoir_branch() {
  [ -z "$MEMOIR_CMD" ] && return 1
  local code_branch sticky current
  code_branch=$(code_git_branch)
  [ -z "$code_branch" ] && return 0          # no code branch (detached or non-git)
  sticky=$(sticky_branch)
  # If sticky is set, honor it: user picked a non-matching branch on purpose.
  # Only auto-match again when they return to a code-matching branch manually.
  if [ -n "$sticky" ]; then
    current=$(memoir_json status 2>/dev/null | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('branch',''))" 2>/dev/null)
    if [ "$current" = "$code_branch" ]; then
      # They navigated back to matching; clear the sticky.
      set_sticky_branch ""
    else
      return 0  # sticky still active; don't touch memoir branch
    fi
  fi

  current=$(memoir_json status 2>/dev/null | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('branch',''))" 2>/dev/null)
  # Already on the matching branch — nothing to do.
  [ "$current" = "$code_branch" ] && return 0

  # Need to switch. Create from main first if the branch doesn't exist.
  if ! branch_exists_in_memoir "$code_branch"; then
    "$MEMOIR_CMD" -s "$MEMOIR_STORE_PATH" branch "$code_branch" --from main >/dev/null 2>&1 || return 1
    # `memoir branch --from main` also leaves the working tree dirty.
    cleanup_store_worktree
  fi
  "$MEMOIR_CMD" -s "$MEMOIR_STORE_PATH" checkout "$code_branch" >/dev/null 2>&1 || return 1
  cleanup_store_worktree
  return 0
}

# list_unmerged_memoir_branches — emit one line per memoir branch (other than
# main and the currently-checked-out one) that is ahead of main by ≥1 commit
# AND whose last commit is within the last 30 days AND isn't in the ignore
# file. Each line is: "<branch-name>\t<ahead-count>".
list_unmerged_memoir_branches() {
  [ -z "$MEMOIR_CMD" ] && return 1
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 1

  local current all_branches thirty_days_ago
  current=$(memoir_json status 2>/dev/null | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('branch',''))" 2>/dev/null)
  all_branches=$(memoir_json branch 2>/dev/null | python3 -c "
import json, sys
try:
    obj = json.loads(sys.stdin.read() or '{}')
    for b in obj.get('branches', []) or []:
        print(b)
except Exception:
    pass
")
  # 30d cutoff as Unix seconds for POSIX-portable comparison via git.
  thirty_days_ago=$(( $(date +%s) - 30 * 86400 ))

  while IFS= read -r b; do
    [ -z "$b" ] && continue
    [ "$b" = "main" ] && continue
    [ "$b" = "$current" ] && continue
    is_branch_ignored "$b" && continue

    # Memoir's merge rewrites patches on main (not a normal two-parent merge
    # commit), so we can't use git graph, diff, or cherry to detect "already
    # merged". Instead, compare the branch's last-commit timestamp against a
    # sync-marker timestamp recorded by /memoir-sync / /memoir-sync-branch.
    #
    # Considered merged if: marker exists AND marker_ts >= last_commit_ts.
    # If the user captures more on the branch after syncing, the branch's
    # last-commit timestamp advances past the marker, and it resurfaces as
    # unmerged — which is the right behavior.
    local ahead last_ts marker_ts
    ahead=$(git -C "$MEMOIR_STORE_PATH" rev-list --count "main..$b" 2>/dev/null || echo 0)
    [ "$ahead" = "0" ] && continue
    last_ts=$(git -C "$MEMOIR_STORE_PATH" log -1 --format=%ct "$b" 2>/dev/null || echo 0)
    [ "$last_ts" -lt "$thirty_days_ago" ] && continue
    marker_ts=$(branch_sync_timestamp "$b")
    if [ "$marker_ts" != "0" ] && [ "$marker_ts" -ge "$last_ts" ]; then
      continue  # synced more recently than the last capture on this branch
    fi

    printf '%s\t%s\n' "$b" "$ahead"
  done <<< "$all_branches"
}

# (Concurrent-session heartbeats were removed — the common cases are already
# safe by construction [different cwds → different stores via path hash], and
# the only genuinely-racing case [explicit `MEMOIR_STORE` sharing across two
# sessions on different code branches] is self-evident to anyone who opts
# into it. The README documents the caveat. Real per-session isolation
# belongs in memoir's `WorktreeVersionedKvStore` integration, not in plugin
# bookkeeping.)

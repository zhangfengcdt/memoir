#!/usr/bin/env bash
# Shared setup for memoir command hooks. Sourced by every hook.
#
# Conventions used throughout:
#   - memoir's global flags (--json, -s) must be passed BEFORE the subcommand.
#   - CLI resolution: prefer `memoir` on PATH; if missing, fall back to
#     `uvx --from memoir-ai memoir` when `uv` is available (no global install,
#     no env pollution, one-time cache warmup). If neither is available we
#     surface an install hint in the status line and disable capture/recall.

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

# Resolve the memoir CLI. Preference order:
#   1. `memoir` on PATH (explicit install, fastest cold start).
#   2. `uvx --from memoir-ai memoir` (uv installed, no global CLI) — ephemeral,
#      no pollution of the user's Python envs, ~1s warmup on first use then
#      cached.
#   3. Nothing — capture/recall disabled, install hint shown.
#
# MEMOIR_CMD is the human-readable form used for `[ -z "$MEMOIR_CMD" ]`
# enable/disable checks throughout the hooks. MEMOIR_CMD_ARGV is the bash
# array used for actual invocation, since the uvx fallback is multi-token.
if command -v memoir &>/dev/null; then
  MEMOIR_CMD="memoir"
  MEMOIR_CMD_ARGV=(memoir)
elif command -v uvx &>/dev/null; then
  MEMOIR_CMD="uvx --from memoir-ai memoir"
  MEMOIR_CMD_ARGV=(uvx --from memoir-ai memoir)
elif command -v uv &>/dev/null; then
  MEMOIR_CMD="uv tool run --from memoir-ai memoir"
  MEMOIR_CMD_ARGV=(uv tool run --from memoir-ai memoir)
else
  MEMOIR_CMD=""
  MEMOIR_CMD_ARGV=()
fi

# Short prefix used in injected instructions / status lines. Always "memoir"
# so user-facing messages stay clean regardless of how the CLI is resolved.
MEMOIR_CMD_PREFIX="memoir"

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
  "${MEMOIR_CMD_ARGV[@]}" --json -s "$MEMOIR_STORE_PATH" "$@" 2>/dev/null
}

# memoir_plain <subcommand> [args...]
# Same as memoir_json but without --json (for commands that don't support it or
# where human-readable output is desired).
memoir_plain() {
  if [ -z "$MEMOIR_CMD" ]; then
    return 1
  fi
  "${MEMOIR_CMD_ARGV[@]}" -s "$MEMOIR_STORE_PATH" "$@" 2>/dev/null
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

# code_branch_exists <name> — returns 0 if the project git repo still has a
# local branch of that name. Memoir branches are named after code branches,
# so a missing local counterpart means the work unit is gone and its
# unmerged memories shouldn't nag the user. Remote-tracking refs are
# intentionally ignored: a branch the user has locally deleted is "done"
# from their perspective, even if a copy still lives on some remote.
#
# When there's no project git repo (_GIT_ROOT empty), return 0 — we can't
# tell whether the branch "exists", so preserve current behavior rather than
# suppressing all unmerged detection.
code_branch_exists() {
  local name="$1"
  [ -z "$name" ] && return 1
  [ -z "$_GIT_ROOT" ] && return 0
  git -C "$_GIT_ROOT" show-ref --verify --quiet "refs/heads/$name" 2>/dev/null
}

# ensure_store — create the store directory with builtin taxonomy if missing.
# Safe to call on every SessionStart. Sets MEMOIR_STORE_WAS_CREATED=1 as a
# side effect when this call actually created the store (vs. finding one
# already there) so callers can run one-time setup like custom-taxonomy
# loading without tracking that state themselves.
ensure_store() {
  MEMOIR_STORE_WAS_CREATED=0
  if [ -z "$MEMOIR_CMD" ]; then
    return 1
  fi
  if [ ! -d "$MEMOIR_STORE_PATH/.git" ]; then
    mkdir -p "$(dirname "$MEMOIR_STORE_PATH")"
    # --no-connect because the plugin manages store selection via MEMOIR_STORE
    # env rather than memoir's global config file — we don't want to clobber
    # what a user may have set for CLI use outside the plugin.
    "${MEMOIR_CMD_ARGV[@]}" new "$MEMOIR_STORE_PATH" --taxonomy-builtin --no-connect >/dev/null 2>&1 || return 1
    MEMOIR_STORE_WAS_CREATED=1
  fi
  return 0
}

# --- project-local custom taxonomy auto-discovery ---

# _project_root — resolve the project root the same way derive-store-path.sh
# does: prefer the git toplevel, fall back to CWD. Kept identical so that
# the taxonomy directory and the store lookup agree on what "this project"
# means.
_project_root() {
  local root
  root=$(git rev-parse --show-toplevel 2>/dev/null || true)
  if [ -n "$root" ]; then
    printf '%s' "$root"
  else
    printf '%s' "$PWD"
  fi
}

# load_project_custom_taxonomy — on first store creation, discover and load
# any markdown taxonomy files under <project-root>/.memoir/taxonomy/*.md into
# the freshly created store. Each file is loaded via `memoir taxonomy load`,
# which appends to (not replaces) the builtin taxonomy already installed by
# `memoir new --taxonomy-builtin`. Best-effort: per-file failures are
# silently swallowed so a broken custom file never blocks auto-capture.
#
# Intentionally one-shot — callers gate on MEMOIR_STORE_WAS_CREATED=1 so we
# do not re-run on every session. Users who edit their custom taxonomy
# after store creation must reload manually via `memoir taxonomy load` or
# by deleting the store.
load_project_custom_taxonomy() {
  [ -z "$MEMOIR_CMD" ] && return 0
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0
  local root dir
  root=$(_project_root)
  dir="$root/.memoir/taxonomy"
  [ -d "$dir" ] || return 0
  local loaded=0 failed=0 f
  # Bash globs return the literal pattern when nothing matches; guard with nullglob.
  shopt -s nullglob
  for f in "$dir"/*.md; do
    if "${MEMOIR_CMD_ARGV[@]}" -s "$MEMOIR_STORE_PATH" taxonomy load "$f" >/dev/null 2>&1; then
      loaded=$((loaded + 1))
    else
      failed=$((failed + 1))
    fi
  done
  shopt -u nullglob
  # Echo a compact summary for the caller to optionally surface; nothing
  # happens if the caller ignores stdout.
  if [ "$loaded" -gt 0 ] || [ "$failed" -gt 0 ]; then
    printf '%s' "loaded=${loaded} failed=${failed}"
  fi
}

# --- branch auto-matching (memoir branch follows code branch) ---

# File locations inside the store's .git/ — these files are local-only state,
# not tracked because they live under .git.
_sticky_file() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-sticky-branch"; }
_ignored_branches_file() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-ignored-branches"; }
_heartbeats_dir() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-active-sessions"; }
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
    "${MEMOIR_CMD_ARGV[@]}" -s "$MEMOIR_STORE_PATH" branch "$code_branch" --from main >/dev/null 2>&1 || return 1
  fi
  "${MEMOIR_CMD_ARGV[@]}" -s "$MEMOIR_STORE_PATH" checkout "$code_branch" >/dev/null 2>&1 || return 1
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
    # If the corresponding code branch is gone (deleted locally and absent
    # from every remote), the work unit no longer exists — suppress the
    # nag. Users who want to promote those memories can still do so via
    # /memoir-sync-branch explicitly.
    code_branch_exists "$b" || continue

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

# --- status-line cache ---

# write_statusline_cache <user_memory_count> — persist the current user-facing
# memory count so the statusline widget (scripts/statusline.sh) can render
# without spawning the memoir CLI on every refresh. Branch is read live from
# $STORE/.git/HEAD by the widget, so we only cache the count here.
write_statusline_cache() {
  local count="$1"
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0
  printf '%s\n' "$count" > "$MEMOIR_STORE_PATH/.git/plugin-statusline-cache" 2>/dev/null || true
}

# compute_user_memory_count — returns the user-facing memory count (total
# minus memoir's internal taxonomy:* namespaces). Shared between session-start
# and stop so both surface the same number in the statusline cache.
compute_user_memory_count() {
  [ -z "$MEMOIR_CMD" ] && return 1
  local status_json summary_json total
  status_json=$(memoir_json status 2>/dev/null || true)
  total=$(_json_val "$status_json" "memory_count" "0")
  summary_json=$(memoir_json summarize taxonomy 2>/dev/null || true)
  if [ -z "$summary_json" ]; then
    printf '%s' "$total"
    return 0
  fi
  python3 -c "
import json, sys
try:
    obj = json.loads(sys.argv[1])
    ns = obj.get('namespaces', {}) or {}
    print(sum(v for k, v in ns.items() if not k.startswith('taxonomy:')))
except Exception:
    print(sys.argv[2])
" "$summary_json" "$total" 2>/dev/null || printf '%s' "$total"
}

# --- stop-hook taxonomy-prompt cache ---

# Path to the cached taxonomy prompt snippet used by stop.sh's extractor.
# Populated by session-start.sh once per session so the Stop hook can inject
# the store's live taxonomy into its system prompt without another CLI hop
# on every turn.
_stop_prompt_cache_path() {
  printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-stop-taxonomy-prompt-cache"
}

# write_stop_prompt_cache — render the taxonomy:v1:* contents into a prompt
# snippet via `memoir taxonomy prompt-snippet` and cache it. Silent no-op if
# the store has no taxonomy, the CLI call fails, or output is empty.
write_stop_prompt_cache() {
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0
  [ -z "$MEMOIR_CMD" ] && return 0
  local snippet cache
  cache=$(_stop_prompt_cache_path)
  snippet=$($MEMOIR_CMD -s "$MEMOIR_STORE_PATH" taxonomy prompt-snippet 2>/dev/null || true)
  if [ -n "$snippet" ]; then
    printf '%s\n' "$snippet" > "$cache" 2>/dev/null || true
  else
    # No taxonomy loaded — clear any stale cache so the hook falls back cleanly.
    rm -f "$cache" 2>/dev/null || true
  fi
}

# read_stop_prompt_cache — emit the cached taxonomy prompt snippet, or nothing
# if unavailable. Callers treat empty output as "use hardcoded fallback".
read_stop_prompt_cache() {
  local cache
  cache=$(_stop_prompt_cache_path)
  [ -s "$cache" ] || return 0
  cat "$cache" 2>/dev/null || true
}

# --- concurrent-session heartbeats ---

# write_session_heartbeat — record that this session is active on the current
# memoir branch. Idempotent; overwrites any prior heartbeat for this session.
write_session_heartbeat() {
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0
  local session_id branch dir f
  # Claude Code puts the session id on the transcript path; fall back to PID.
  session_id="${CLAUDE_SESSION_ID:-${PPID:-$$}}"
  branch=$(memoir_json status 2>/dev/null | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('branch',''))" 2>/dev/null)
  dir=$(_heartbeats_dir)
  mkdir -p "$dir"
  f="$dir/$session_id"
  printf '%s\t%s\n' "$branch" "$(date +%s)" > "$f"
}

remove_session_heartbeat() {
  local session_id dir f
  session_id="${CLAUDE_SESSION_ID:-${PPID:-$$}}"
  dir=$(_heartbeats_dir)
  f="$dir/$session_id"
  rm -f "$f"
}

# concurrent_session_warning — returns non-empty on stdout if another live
# heartbeat (≤12h old) targets a memoir branch different from ours. Stale
# heartbeats are garbage-collected opportunistically.
concurrent_session_warning() {
  local dir my_session current twelve_hours_ago
  dir=$(_heartbeats_dir)
  [ ! -d "$dir" ] && return 0
  my_session="${CLAUDE_SESSION_ID:-${PPID:-$$}}"
  current=$(memoir_json status 2>/dev/null | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('branch',''))" 2>/dev/null)
  twelve_hours_ago=$(( $(date +%s) - 12 * 3600 ))

  local other_branch=""
  local -a stale=()
  for f in "$dir"/*; do
    [ -f "$f" ] || continue
    local fname
    fname=$(basename "$f")
    [ "$fname" = "$my_session" ] && continue
    # file format: "<branch>\t<epoch>"
    local rec branch ts
    rec=$(head -n1 "$f" 2>/dev/null || echo "")
    branch=$(printf '%s' "$rec" | cut -f1)
    ts=$(printf '%s' "$rec" | cut -f2)
    # numeric check; skip malformed
    case "$ts" in
      ''|*[!0-9]*) stale+=("$f"); continue ;;
    esac
    if [ "$ts" -lt "$twelve_hours_ago" ]; then
      stale+=("$f")
      continue
    fi
    if [ -n "$branch" ] && [ "$branch" != "$current" ]; then
      other_branch="$branch"
    fi
  done

  # GC stale heartbeats
  if [ "${#stale[@]}" -gt 0 ]; then
    rm -f "${stale[@]}"
  fi

  if [ -n "$other_branch" ]; then
    printf '⚠ concurrent session detected on branch %s. Captures may collide; set a distinct MEMOIR_STORE per session.' "$other_branch"
  fi
}

#!/usr/bin/env bash
# Shared setup for memoir command hooks. Sourced by every hook.
#
# Conventions used throughout:
#   - memoir's global flags (--json, -s) must be passed BEFORE the subcommand.
#   - CLI resolution: prefer `memoir` on PATH; if missing, fall back to
#     `uvx --from memoir-ai==<pin> memoir` when `uv` is available (no global
#     install, no env pollution, one-time cache warmup). The pin lives in
#     scripts/resolve-memoir-cli.sh (MEMOIR_AI_PIN). If neither is available
#     we surface an install hint in the status line and disable capture/recall.

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
# Empty `_GIT_ROOT` is intentional and load-bearing for non-git folders — see
# `in_git_repo` below; `code_git_branch`, `code_branch_exists`, and
# `auto_match_memoir_branch` all guard on it staying empty.
#
# Delegated to derive-store-path.sh so the worktree-aware logic (linked
# worktrees collapse onto the main worktree's path) lives in exactly one place.
SCRIPT_PARENT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
_GIT_ROOT="$(bash "$SCRIPT_PARENT/scripts/derive-store-path.sh" --print-git-root 2>/dev/null || echo "")"
if [ -n "$_GIT_ROOT" ]; then
  _PROJECT_DIR="$_GIT_ROOT"
else
  _PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
fi

# in_git_repo — 0 if the project root is inside a git working tree, else 1.
# Single-source check that callers (skill, hooks, commands) reuse instead of
# re-running `git rev-parse`. Non-git folders are a first-class case: only the
# `main` memoir branch is supported, /memoir:onboard switches to project:onboard.
in_git_repo() { [ -n "$_GIT_ROOT" ]; }

# Resolve store path: MEMOIR_STORE env wins, else derive from project dir.
if [ -n "${MEMOIR_STORE:-}" ]; then
  MEMOIR_STORE_PATH="$MEMOIR_STORE"
else
  MEMOIR_STORE_PATH="$(bash "$SCRIPT_PARENT/scripts/derive-store-path.sh" "$_PROJECT_DIR")"
fi

# Resolve the memoir CLI. The preference chain (memoir → uvx → uv tool run)
# and the rationale live in scripts/resolve-memoir-cli.sh so slash-command
# shims and skills can use the same logic without duplication. Sets
# MEMOIR_CMD (human-readable form, empty if no working invocation exists)
# and MEMOIR_CMD_ARGV (bash array for direct invocation).
# shellcheck source=../scripts/resolve-memoir-cli.sh
source "$SCRIPT_PARENT/scripts/resolve-memoir-cli.sh"

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

# Subshell cd to the store path before every memoir invocation. Memoir's
# write operations exercise the store's git backend, which requires the
# process cwd to be inside a git working tree. In a git-tracked project
# the user's cwd already satisfies that; in a non-git folder it does not,
# and writes silently fail with "Not in a git repository". The store
# directory itself IS a git repo, so cd-ing there before each call works
# uniformly for both modes. Subshell isolation prevents the caller's cwd
# from drifting.
memoir_json() {
  if [ -z "$MEMOIR_CMD" ]; then
    return 1
  fi
  ( cd "$MEMOIR_STORE_PATH" 2>/dev/null \
    && "${MEMOIR_CMD_ARGV[@]}" --json -s "$MEMOIR_STORE_PATH" "$@" ) 2>/dev/null
}

# memoir_plain <subcommand> [args...]
# Same as memoir_json but without --json (for commands that don't support it or
# where human-readable output is desired).
memoir_plain() {
  if [ -z "$MEMOIR_CMD" ]; then
    return 1
  fi
  ( cd "$MEMOIR_STORE_PATH" 2>/dev/null \
    && "${MEMOIR_CMD_ARGV[@]}" -s "$MEMOIR_STORE_PATH" "$@" ) 2>/dev/null
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

# --- store-mode drift guardrail (warning-only) ---
#
# A store keyed on `pwd` (non-git mode) and a store keyed on the same path that
# later acquires `.git/` resolve to the SAME `~/.memoir/<slug>/`. After a
# `git init` the auto-match logic starts running and (with default
# `init.defaultBranch=master` configs) silently forks a second memoir branch,
# splitting captures with no signal. The guardrail is warning-only: detect the
# transition via a side-car marker, surface a one-block message at SessionStart,
# never refuse writes.

_store_mode_file() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-store-mode"; }

# current_repo_mode — emit "git" or "non-git" based on the project dir.
current_repo_mode() {
  if in_git_repo; then
    printf 'git'
  else
    printf 'non-git'
  fi
}

# write_store_mode_marker — record the mode at first store creation. Idempotent:
# overwrites with the current mode (callers should only invoke right after a
# successful `memoir new`).
write_store_mode_marker() {
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0
  current_repo_mode > "$(_store_mode_file)" 2>/dev/null || true
}

# detect_store_mode_drift — sets MEMOIR_STORE_MODE_MISMATCH=1 plus
# MEMOIR_STORE_MODE_RECORDED / MEMOIR_STORE_MODE_CURRENT when the recorded marker
# disagrees with the current state. Backfills the marker on first observation
# against an old store (no warning fired in that case). Never blocks; callers
# decide what to do with the flag.
detect_store_mode_drift() {
  MEMOIR_STORE_MODE_MISMATCH=0
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0
  local f recorded current
  f=$(_store_mode_file)
  current=$(current_repo_mode)
  if [ ! -f "$f" ]; then
    printf '%s' "$current" > "$f" 2>/dev/null || true
    return 0
  fi
  recorded=$(head -n1 "$f" 2>/dev/null || echo "")
  if [ -n "$recorded" ] && [ "$recorded" != "$current" ]; then
    MEMOIR_STORE_MODE_MISMATCH=1
    MEMOIR_STORE_MODE_RECORDED="$recorded"
    MEMOIR_STORE_MODE_CURRENT="$current"
  fi
}

# render_store_mode_drift_warning — one compact block for SessionStart. Captures
# still proceed, so the message is informational, not an error.
render_store_mode_drift_warning() {
  cat <<EOF
[memoir] note: store mode drift
  This store was created in \`$MEMOIR_STORE_MODE_RECORDED\` mode; the project
  directory is now \`$MEMOIR_STORE_MODE_CURRENT\`. Captures continue, but
  branch auto-matching and the SessionStart onboard injection now use the
  new mode — earlier $MEMOIR_STORE_MODE_RECORDED-mode data may be on a
  different memoir branch (run \`memoir branch list\` to inspect).
  To suppress: \`memoir checkout main\` and update the marker with
  \`echo $MEMOIR_STORE_MODE_CURRENT > $MEMOIR_STORE_PATH/.git/plugin-store-mode\`.
EOF
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
  # Delegate the actual create-if-missing work to the shared helper so
  # slash-command shims and SessionStart use the same bootstrap path.
  # Helper prints "created" on stdout iff this call materialized the
  # store; empty stdout means it was already there.
  local _result
  _result=$(bash "$SCRIPT_PARENT/scripts/ensure-store.sh" "$MEMOIR_STORE_PATH" 2>/dev/null) || return 1
  if [ "$_result" = "created" ]; then
    MEMOIR_STORE_WAS_CREATED=1
    write_store_mode_marker
  else
    # Existing store: backfill the marker if missing, set mismatch flags otherwise.
    detect_store_mode_drift
  fi
  return 0
}

# --- custom taxonomy auto-discovery (global + project-local) ---

# _project_root — resolve the project root the same way derive-store-path.sh
# does: prefer the git toplevel, fall back to CWD. Kept identical so that
# the taxonomy directory and the store lookup agree on what "this project"
# means.
_project_root() {
  local root
  root=$(bash "$SCRIPT_PARENT/scripts/derive-store-path.sh" --print-git-root 2>/dev/null || true)
  if [ -n "$root" ]; then
    printf '%s' "$root"
  else
    printf '%s' "$PWD"
  fi
}

# _load_taxonomy_dir <dir> — scan <dir> for *.md files and load each via
# `memoir taxonomy load`. Best-effort: per-file failures don't abort.
# Writes two integers on stdout separated by a space: "<loaded> <failed>".
# Absent/empty directory is a silent no-op returning "0 0".
_load_taxonomy_dir() {
  local dir="$1"
  local loaded=0 failed=0 f
  if [ -d "$dir" ]; then
    shopt -s nullglob
    for f in "$dir"/*.md; do
      if "${MEMOIR_CMD_ARGV[@]}" -s "$MEMOIR_STORE_PATH" taxonomy load "$f" >/dev/null 2>&1; then
        loaded=$((loaded + 1))
      else
        failed=$((failed + 1))
      fi
    done
    shopt -u nullglob
  fi
  printf '%d %d' "$loaded" "$failed"
}

# load_custom_taxonomy_files — on first store creation, discover and load
# any markdown taxonomy files from two locations, in this order:
#
#   1. ~/.memoir/taxonomy/*.md                    — user-global taxonomies
#   2. <project-root>/.memoir/taxonomy/*.md       — project-specific
#
# Each file is appended to the store via `memoir taxonomy load`, on top of
# the builtin taxonomy already installed by `memoir new --taxonomy-builtin`.
# Project-local files load *after* global, so they can introduce narrower
# or overriding taxonomies for this particular repo.
#
# Intentionally one-shot — callers gate on MEMOIR_STORE_WAS_CREATED=1 so we
# do not re-run on every session. Users who edit their custom taxonomy
# after store creation must reload manually via `memoir taxonomy load` or
# by deleting the store.
load_custom_taxonomy_files() {
  [ -z "$MEMOIR_CMD" ] && return 0
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0

  local total_loaded=0 total_failed=0
  local global_dir="$HOME/.memoir/taxonomy"
  local project_dir
  project_dir="$(_project_root)/.memoir/taxonomy"

  local result loaded failed
  for dir in "$global_dir" "$project_dir"; do
    result=$(_load_taxonomy_dir "$dir")
    loaded=${result% *}
    failed=${result#* }
    total_loaded=$((total_loaded + loaded))
    total_failed=$((total_failed + failed))
  done

  if [ "$total_loaded" -gt 0 ] || [ "$total_failed" -gt 0 ]; then
    printf '%s' "loaded=${total_loaded} failed=${total_failed}"
  fi
}

# --- branch auto-matching (memoir branch follows code branch) ---

# File locations inside the store's .git/ — these files are local-only state,
# not tracked because they live under .git.
_sticky_file() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-sticky-branch"; }
_ignored_branches_file() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-ignored-branches"; }
_heartbeats_dir() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-active-sessions"; }
_synced_dir() { printf '%s' "$MEMOIR_STORE_PATH/.git/plugin-synced-branches"; }

# record_branch_synced <branch> — called by /memoir-sync-branch after a successful
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
    # sync-marker timestamp recorded by /memoir-sync-branch.
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
  local session_id branch dir f pid
  # Claude Code puts the session id on the transcript path; fall back to PID.
  session_id="${CLAUDE_SESSION_ID:-${PPID:-$$}}"
  # Record the owning PID so readers can reap the heartbeat the moment the
  # process is gone, instead of waiting for the 12h timestamp GC.
  pid="${PPID:-$$}"
  branch=$(memoir_json status 2>/dev/null | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('branch',''))" 2>/dev/null)
  dir=$(_heartbeats_dir)
  mkdir -p "$dir"
  f="$dir/$session_id"
  printf '%s\t%s\t%s\n' "$branch" "$(date +%s)" "$pid" > "$f"
}

remove_session_heartbeat() {
  local session_id dir f
  session_id="${CLAUDE_SESSION_ID:-${PPID:-$$}}"
  dir=$(_heartbeats_dir)
  f="$dir/$session_id"
  rm -f "$f"
}

# concurrent_session_warning — returns non-empty on stdout if another live
# heartbeat targets a memoir branch different from ours. Liveness is established
# by PID check when recorded; otherwise the 12h timestamp window applies. Stale
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
    # file format: "<branch>\t<epoch>[\t<pid>]"  (pid is optional for back-compat)
    local rec branch ts pid
    rec=$(head -n1 "$f" 2>/dev/null || echo "")
    branch=$(printf '%s' "$rec" | cut -f1)
    ts=$(printf '%s' "$rec" | cut -f2)
    pid=$(printf '%s' "$rec" | cut -f3)
    # numeric check; skip malformed
    case "$ts" in
      ''|*[!0-9]*) stale+=("$f"); continue ;;
    esac
    # If a PID was recorded and the process is gone, reap immediately — no
    # need to wait out the 12h window for a session that crashed or was killed.
    case "$pid" in
      ''|*[!0-9]*) ;;  # no/invalid pid — fall through to timestamp check
      *)
        if ! kill -0 "$pid" 2>/dev/null; then
          stale+=("$f")
          continue
        fi
        ;;
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

# --- default namespace key listing ---

# render_default_keys_compact — emit a compact list of keys in the `default`
# namespace, grouped by L1 prefix, capped at 200 keys. Prints nothing when the
# namespace is empty or the CLI is unavailable.
#
# This gives a fresh session a quick scan of "what does this user remember"
# without paying for a recall round-trip; the agent can spot relevant keys at
# a glance and only `memoir get` the ones that matter.
render_default_keys_compact() {
  [ -z "$MEMOIR_CMD" ] && return 0
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0

  local keys_json
  keys_json=$(memoir_json summarize --keys "*" -n default 2>/dev/null || true)
  [ -z "$keys_json" ] && return 0

  python3 -c "
import json, sys
from collections import defaultdict

LIMIT = 200

try:
    obj = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)

keys = obj.get('matching_keys', {}).get('default', []) or []
if not keys:
    sys.exit(0)

keys = sorted(keys)
total = len(keys)
shown = keys[:LIMIT]
truncated = total > LIMIT

groups = defaultdict(list)
for k in shown:
    l1 = k.split('.', 1)[0]
    groups[l1].append(k)

print('# default namespace keys')
if truncated:
    print(f'({total} keys total — showing first {LIMIT}, grouped by L1 prefix)')
else:
    print(f'({total} keys, grouped by L1 prefix)')

for l1 in sorted(groups.keys()):
    items = groups[l1]
    print('')
    print(f'{l1} ({len(items)}):')
    for k in items:
        print(f'  - {k}')
" "$keys_json" 2>/dev/null || true
}

# --- onboard rendering & meta update ---

# render_onboard_compact <namespace> — emit a compact block summarizing the
# given onboard namespace (`codebase:onboard` or `project:onboard`) for
# SessionStart injection. One line per non-_meta top-level root, joined from
# the first sentence of each child key, capped at ~140 chars per line. Empty
# output (nothing printed) when the namespace is empty or the CLI is
# unavailable — callers treat that as "no snapshot yet".
#
# If the last_onboard date is > 30 days old, the header is tagged stale="true"
# and a trailing refresh hint is appended.
#
# Per-namespace differences (header label, preferred-root ordering, identity
# field, suppressed roots) are encoded in the embedded Python; the bash side
# only forwards the namespace.
render_onboard_compact() {
  local namespace="$1"
  [ -z "$namespace" ] && return 0
  [ -z "$MEMOIR_CMD" ] && return 0
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0

  local keys_json all_keys
  keys_json=$(memoir_json summarize --keys "*" -n "$namespace" 2>/dev/null || true)
  [ -z "$keys_json" ] && return 0
  all_keys=$(python3 -c "
import json, sys
try:
    obj = json.loads(sys.argv[1])
    keys = obj.get('matching_keys', {}).get(sys.argv[2], []) or []
    print('\n'.join(keys))
except Exception:
    pass
" "$keys_json" "$namespace" 2>/dev/null || true)
  [ -z "$all_keys" ] && return 0

  # Batch-fetch every key in one `get` call. Keys are space-separated args.
  local keys_args values_json
  keys_args=$(printf '%s' "$all_keys" | tr '\n' ' ')
  # shellcheck disable=SC2086
  values_json=$("${MEMOIR_CMD_ARGV[@]}" --json -s "$MEMOIR_STORE_PATH" get $keys_args -n "$namespace" 2>/dev/null || true)
  [ -z "$values_json" ] && return 0

  python3 -c "
import json, re, sys
from datetime import datetime, timezone

namespace = sys.argv[2]

# Per-namespace render config. Keep this map small — the differences are
# header label, preferred-root ordering, the identity field rendered in the
# header, and which L1 roots to suppress (for project:onboard, files.* would
# explode the body).
CONFIG = {
    'codebase:onboard': {
        'title': '# codebase:onboard snapshot',
        'tag': 'codebase-onboard',
        'preferred_roots': ['goal', 'structure', 'test', 'debug', 'deploy', 'rules', 'lessons', 'references', 'document'],
        'suppressed_roots': set(),
        'identity_meta_key': '_meta.last_onboard.commit',
        'identity_attr': 'last_onboard',
        'identity_format': 'sha7',
    },
    'project:onboard': {
        'title': '# project:onboard snapshot',
        'tag': 'project-onboard',
        'preferred_roots': ['summary', 'structure'],
        # files.* is hundreds of per-file keys — surface the aggregate count
        # from _meta instead of dumping every leaf.
        'suppressed_roots': {'files'},
        'identity_meta_key': '_meta.last_onboard.snapshot_hash',
        'identity_attr': 'last_onboard',
        'identity_format': 'sha7',
    },
}
cfg = CONFIG.get(namespace)
if cfg is None:
    sys.exit(0)

try:
    obj = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)

items = obj.get('items', []) or []
if not items:
    sys.exit(0)

roots = {}
meta = {}
for it in items:
    if not it.get('found'):
        continue
    key = it.get('key', '')
    content = (it.get('value', {}) or {}).get('content', '')
    if not key or not content:
        continue
    if key.startswith('_meta.'):
        meta[key] = content
        continue
    root = key.split('.', 1)[0]
    if root in cfg['suppressed_roots']:
        continue
    roots.setdefault(root, []).append((key, content))

# project:onboard may have only suppressed roots populated; still render the
# header + trailing aggregate so the user sees the snapshot exists.
if not roots and not meta:
    sys.exit(0)

def first_sentence(s, maxlen=60):
    s = ' '.join(s.strip().split())
    m = re.match(r'^(.+?[.!?])(\s|$)', s)
    first = m.group(1) if m else s
    if len(first) > maxlen:
        first = first[:maxlen - 1].rstrip() + '…'
    return first

ident_raw = meta.get(cfg['identity_meta_key'], '') or ''
if cfg['identity_format'] == 'sha7':
    ident = ident_raw[:7] if ident_raw else '?'
else:
    ident = ident_raw or '?'
date_iso = meta.get('_meta.last_onboard.date', '')
mode = meta.get('_meta.last_onboard.mode', '') or '?'
age_str = '?'
stale = False
if date_iso:
    try:
        dt = datetime.fromisoformat(date_iso.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        delta = now - dt
        days = delta.days
        if days > 30:
            stale = True
        if days >= 1:
            age_str = f'{days}d ago'
        else:
            hours = delta.seconds // 3600
            age_str = f'{hours}h ago' if hours >= 1 else '<1h ago'
    except Exception:
        pass

header_attrs = [f'{cfg[\"identity_attr\"]}=\"{age_str} @ {ident}\"', f'mode=\"{mode}\"']
if stale:
    header_attrs.append('stale=\"true\"')

print(cfg['title'])
print(f'<{cfg[\"tag\"]} {\" \".join(header_attrs)}>')

preferred = cfg['preferred_roots']
seen = set()
ordered = [r for r in preferred if r in roots]
seen.update(ordered)
ordered.extend(sorted(r for r in roots.keys() if r not in seen))

for root in ordered:
    children = sorted(roots[root], key=lambda kv: kv[0])
    pieces = [first_sentence(v) for _, v in children]
    body = '; '.join(pieces)
    if len(body) > 140:
        body = body[:139].rstrip() + '…'
    print(f'{root}: {body}')

# project:onboard aggregate line: shows file_count when files.* was suppressed.
if 'files' in cfg['suppressed_roots']:
    file_count = meta.get('_meta.last_onboard.file_count', '')
    if file_count:
        print(f'files: {file_count} indexed (run /memoir:onboard for per-file detail)')

print(f'</{cfg[\"tag\"]}>')
if stale:
    print('(snapshot is stale — run /memoir:onboard to refresh)')
" "$values_json" "$namespace" 2>/dev/null || true
}

# render_codebase_onboard_compact — backward-compat wrapper. Existing callers
# that don't know about project:onboard keep working unchanged.
render_codebase_onboard_compact() {
  render_onboard_compact codebase:onboard
}

# render_project_onboard_compact — non-git folders' counterpart.
render_project_onboard_compact() {
  render_onboard_compact project:onboard
}

# update_onboard_meta_after_sync <code_sha> [memoir_sha]
# Deterministic post-sync bump of the _meta.last_onboard.* keys on the
# currently-checked-out memoir branch. No LLM work. Called by
# /memoir-sync-branch after the merge step so the metadata stays truthful
# even when the user hasn't re-run /memoir:onboard yet; the narrative keys
# (structure.*, goal.*, …) are left alone.
#
# A missing code_sha is a no-op; a missing memoir_sha skips just that key.
update_onboard_meta_after_sync() {
  local code_sha="$1" memoir_sha="${2:-}"
  [ -z "$MEMOIR_CMD" ] && return 0
  [ ! -d "$MEMOIR_STORE_PATH/.git" ] && return 0
  [ -z "$code_sha" ] && return 0
  local date_iso
  date_iso=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  # Scalar pointers (latest sha, date, memoir version) — overwrite, not append.
  "${MEMOIR_CMD_ARGV[@]}" -s "$MEMOIR_STORE_PATH" remember "$code_sha"  -p _meta.last_onboard.commit -n codebase:onboard --replace >/dev/null 2>&1 || true
  "${MEMOIR_CMD_ARGV[@]}" -s "$MEMOIR_STORE_PATH" remember "$date_iso"  -p _meta.last_onboard.date   -n codebase:onboard --replace >/dev/null 2>&1 || true
  if [ -n "$memoir_sha" ]; then
    "${MEMOIR_CMD_ARGV[@]}" -s "$MEMOIR_STORE_PATH" remember "$memoir_sha" -p _meta.last_onboard.memoir_commit -n codebase:onboard --replace >/dev/null 2>&1 || true
  fi
  return 0
}

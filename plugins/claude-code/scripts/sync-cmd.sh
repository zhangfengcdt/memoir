#!/usr/bin/env bash
# Backing script for the /memoir:sync slash command (and the SessionStart
# merge auto-offer recipe). Owns every state read/write so the agent never
# composes raw CLI plumbing or hand-edits plugin state files.
#
# Subcommands (each prints one-line JSON on stdout):
#   list             — unmerged + deletable/stale memoir branches + ignore/snooze state
#   dry-run <branch> — preview promoting <branch> into main (CLI passthrough)
#   merge <branch>   — promote <branch> into main (CLI passthrough; the CLI
#                      writes the sync marker itself on success)
#   ignore <branch>  — add <branch> to the silence list (idempotent)
#   snooze [days]    — suppress the SessionStart auto-offer (default 7 days;
#                      resets the decline counter)
#   decline          — auto-offer declined: escalating snooze (1d → 7d → 30d)
#   prune <branch>   — delete a memoir branch (refuses main/current) + its plugin state

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# common.sh reads hook input from stdin with a 2s timeout; slash-command
# invocations have no stdin payload, so discard it first (same guard as
# session-start.sh).
exec < /dev/null
# shellcheck source=../hooks/common.sh
source "$SCRIPT_DIR/../hooks/common.sh"

if [ -z "$MEMOIR_CMD" ]; then
  echo "ERROR: $MEMOIR_INSTALL_HINT" >&2
  exit 127
fi

# First-time-user safety net (mirrors status-cmd.sh): materialize the store
# if SessionStart didn't get the chance to.
ensure_store >/dev/null 2>&1 || {
  echo "ERROR: failed to bootstrap memoir store at $MEMOIR_STORE_PATH" >&2
  exit 1
}

cmd="${1:-list}"

case "$cmd" in
  list)
    unmerged=$(list_unmerged_memoir_branches 2>/dev/null || true)
    # Enrich each "<branch>\t<ahead>" line with the branch tip's commit
    # epoch so the command can rank pickers by recency.
    enriched=""
    while IFS=$'\t' read -r b n; do
      [ -z "$b" ] && continue
      ts=$(git -C "$MEMOIR_STORE_PATH" log -1 --format=%ct "$b" 2>/dev/null || echo 0)
      enriched+="${b}"$'\t'"${n}"$'\t'"${ts}"$'\n'
    done <<< "$unmerged"

    ignored=""
    [ -f "$(_ignored_branches_file)" ] && ignored=$(cat "$(_ignored_branches_file)" 2>/dev/null || true)
    snoozed_until=0
    if [ -f "$(_merge_prompt_cooldown_file)" ]; then
      snoozed_until=$(head -n1 "$(_merge_prompt_cooldown_file)" 2>/dev/null || echo 0)
      case "$snoozed_until" in ''|*[!0-9]*) snoozed_until=0 ;; esac
    fi
    warn=$(concurrent_session_warning 2>/dev/null || true)
    deletable=$(list_deletable_memoir_branches 2>/dev/null || true)

    python3 -c "
import json, sys, time
unmerged = []
total = 0
now = int(time.time())
for line in sys.argv[1].splitlines():
    parts = line.split('\t')
    if len(parts) != 3 or not parts[0]:
        continue
    branch, ahead, ts = parts[0], int(parts[1] or 0), int(parts[2] or 0)
    total += ahead
    unmerged.append({
        'branch': branch,
        'ahead': ahead,
        'last_commit_ts': ts,
        'age_days': max(0, (now - ts) // 86400) if ts else None,
    })
unmerged.sort(key=lambda e: -(e['last_commit_ts'] or 0))
deletable = []
for line in sys.argv[7].splitlines():
    parts = line.split('\t')
    if len(parts) != 6 or not parts[0]:
        continue
    deletable.append({
        'branch': parts[0],
        'age_days': int(parts[1] or 0),
        'synced': parts[2] == 'true',
        'code_branch_exists': parts[3] == 'true',
        'ahead': int(parts[4] or 0),
        'stale': parts[5] == 'true',
    })
# Stale first (safe deletions lead the picker), then oldest first.
deletable.sort(key=lambda e: (not e['stale'], -e['age_days']))
stale = [
    {k: e[k] for k in ('branch', 'age_days', 'synced', 'code_branch_exists')}
    for e in deletable if e['stale']
]
print(json.dumps({
    'store': sys.argv[2],
    'code_branch': sys.argv[3],
    'unmerged': unmerged,
    'total_ahead': total,
    'stale': stale,
    'deletable': deletable,
    'ignored': [l for l in sys.argv[4].splitlines() if l.strip()],
    'snoozed_until': int(sys.argv[5]),
    'concurrent_warning': sys.argv[6],
}))
" "$enriched" "$MEMOIR_STORE_PATH" "$(code_git_branch)" "$ignored" "$snoozed_until" "$warn" "$deletable"
    ;;

  dry-run|merge)
    branch="${2:-}"
    if [ -z "$branch" ]; then
      echo "ERROR: usage: sync-cmd.sh $cmd <branch>" >&2
      exit 2
    fi
    # Pass the CLI's JSON through verbatim, success or failure (on failure it
    # still emits {success: false, error: ...} on stdout). Keep its exit code.
    # No empty-array expansion here — macOS bash 3.2 trips on it under set -u.
    rc=0
    if [ "$cmd" = "dry-run" ]; then
      ( cd "$MEMOIR_STORE_PATH" 2>/dev/null \
        && "${MEMOIR_CMD_ARGV[@]}" --json -s "$MEMOIR_STORE_PATH" \
             sync-branch "$branch" --into main --yes --dry-run ) || rc=$?
    else
      ( cd "$MEMOIR_STORE_PATH" 2>/dev/null \
        && "${MEMOIR_CMD_ARGV[@]}" --json -s "$MEMOIR_STORE_PATH" \
             sync-branch "$branch" --into main --yes ) || rc=$?
    fi
    exit "$rc"
    ;;

  ignore)
    branch="${2:-}"
    if [ -z "$branch" ]; then
      echo "ERROR: usage: sync-cmd.sh ignore <branch>" >&2
      exit 2
    fi
    already=false
    is_branch_ignored "$branch" && already=true
    ignore_branch "$branch" || {
      echo "ERROR: failed to update ignore list (no store?)" >&2
      exit 1
    }
    printf '{"ignored": %s, "already": %s}\n' "$(_json_encode_str "$branch")" "$already"
    ;;

  snooze)
    days="${2:-7}"
    set_merge_prompt_cooldown "$days" || {
      echo "ERROR: usage: sync-cmd.sh snooze [days]  (days must be a positive integer)" >&2
      exit 2
    }
    printf '{"snoozed_until": %s, "days": %s}\n' "$(head -n1 "$(_merge_prompt_cooldown_file)")" "$days"
    ;;

  decline)
    out=$(escalate_merge_prompt_cooldown) || {
      echo "ERROR: failed to record decline (no store?)" >&2
      exit 1
    }
    days="${out%%$'\t'*}"
    declines="${out##*$'\t'}"
    printf '{"snoozed_until": %s, "days": %s, "declines": %s}\n' \
      "$(head -n1 "$(_merge_prompt_cooldown_file)")" "$days" "$declines"
    ;;

  prune)
    branch="${2:-}"
    if [ -z "$branch" ]; then
      echo "ERROR: usage: sync-cmd.sh prune <branch>" >&2
      exit 2
    fi
    if [ "$branch" = "main" ]; then
      echo "ERROR: refusing to delete main" >&2
      exit 2
    fi
    current=$(memoir_json status 2>/dev/null | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('branch',''))" 2>/dev/null)
    if [ "$branch" = "$current" ]; then
      echo "ERROR: cannot delete the currently checked-out memoir branch '$branch'" >&2
      exit 2
    fi
    rc=0
    ( cd "$MEMOIR_STORE_PATH" 2>/dev/null \
      && "${MEMOIR_CMD_ARGV[@]}" --json -s "$MEMOIR_STORE_PATH" \
           branch "$branch" -D ) >/dev/null 2>&1 || rc=$?
    if [ "$rc" -ne 0 ]; then
      echo "ERROR: failed to delete memoir branch '$branch'" >&2
      exit 1
    fi
    remove_branch_plugin_state "$branch"
    printf '{"pruned": %s}\n' "$(_json_encode_str "$branch")"
    ;;

  *)
    echo "ERROR: unknown subcommand '$cmd' (expected: list, dry-run, merge, ignore, snooze, decline, prune)" >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
# SessionStart hook: auto-init the memoir store, surface status + current branch.
#
# Discard stdin before sourcing common.sh — session-start never uses $INPUT and
# `claude --resume` can leave the pipe open indefinitely, which would block the
# `cat` inside common.sh on macOS.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec < /dev/null
source "$SCRIPT_DIR/common.sh"

# If neither `memoir` nor `uv`/`uvx` is available, surface an install hint.
# With uv present, the plugin transparently shells out via `uvx --from memoir-ai memoir`.
if [ -z "$MEMOIR_CMD" ]; then
  status="[memoir] CLI not found. Install one of: \`pip install memoir-ai\`, \`pipx install memoir-ai\`, \`uv tool install memoir-ai\`, or install \`uv\` for transparent uvx fallback. Capture/recall disabled."
  json_status=$(_json_encode_str "$status")
  echo "{\"systemMessage\": $json_status}"
  exit 0
fi

# Create the store on first run (idempotent).
if ! ensure_store; then
  status="[memoir] Failed to initialize store at $MEMOIR_STORE_PATH. Run: memoir new \"$MEMOIR_STORE_PATH\" --taxonomy-builtin"
  json_status=$(_json_encode_str "$status")
  echo "{\"systemMessage\": $json_status}"
  exit 0
fi

# Auto-match memoir branch to current code branch (creates from main if
# missing; honors sticky opt-out). Failures are non-fatal — we just end
# up on whatever memoir branch was already current.
auto_match_memoir_branch || true

# Pull status JSON — contains branch, commit_count, memory_count (total).
STATUS_JSON=$(memoir_json status || true)
BRANCH=$(_json_val "$STATUS_JSON" "branch" "main")
COMMITS=$(_json_val "$STATUS_JSON" "commit_count" "0")
TOTAL_MEMORIES=$(_json_val "$STATUS_JSON" "memory_count" "0")

# Compute *user-facing* memory count by subtracting entries in memoir's
# internal taxonomy:v1:* namespaces. A brand-new store created with
# `--taxonomy-builtin` has ~8 taxonomy entries that are classification
# hints, not user memories; showing them in the status line as "8 memories"
# confuses users who expect that number to reflect what they've captured.
# `summarize taxonomy --json` returns a per-namespace count map; we sum the
# non-taxonomy entries. Quick read, no LLM call, safe to run every session.
SUMMARY_JSON=$(memoir_json summarize taxonomy 2>/dev/null || true)
USER_MEMORIES="$TOTAL_MEMORIES"
if [ -n "$SUMMARY_JSON" ]; then
  USER_MEMORIES=$(python3 -c "
import json, sys
try:
    obj = json.loads(sys.argv[1])
    ns = obj.get('namespaces', {}) or {}
    print(sum(v for k, v in ns.items() if not k.startswith('taxonomy:')))
except Exception:
    print(sys.argv[2])
" "$SUMMARY_JSON" "$TOTAL_MEMORIES" 2>/dev/null || echo "$TOTAL_MEMORIES")
fi

# Status line:
# - Under the new auto-matching default, code and memoir branches should agree,
#   so we collapse to just `<branch>`. When they diverge (user chose a sticky
#   opt-out memoir branch), show `<code>+<memory>*` — the `*` signals "sticky".
# - Falls back to just `<memory-branch>` when there's no code git repo.
CODE_BRANCH=$(code_git_branch)
if [ -n "$CODE_BRANCH" ] && [ "$CODE_BRANCH" = "$BRANCH" ]; then
  DISPLAY_BRANCH="${BRANCH}"
elif [ -n "$CODE_BRANCH" ]; then
  DISPLAY_BRANCH="${CODE_BRANCH}+${BRANCH}*"
else
  DISPLAY_BRANCH="${BRANCH}"
fi

# Unmerged-branch detector: surface any memoir branches ahead of main so the
# user notices captured knowledge that hasn't been promoted. Stateless —
# scans all branches each SessionStart. Filters to ≤30d active + not ignored.
# Computed early so it can feed both the status line and additionalContext.
#
# Gated on code branch == main: while the user is mid-flight on a feature
# branch, other branches' unmerged work is noise. main is the natural sync
# point, so we only nag there. (An empty CODE_BRANCH — no code repo — also
# skips; users without a code repo can invoke /memoir-unmerged manually.)
unmerged=""
if [ "$CODE_BRANCH" = "main" ]; then
  unmerged=$(list_unmerged_memoir_branches 2>/dev/null || true)
fi

status="[memoir] ${DISPLAY_BRANCH} · ${USER_MEMORIES} memories · ${COMMITS} commits"
if [ "${MEMOIR_NO_CAPTURE:-}" = "1" ]; then
  status+=" · capture disabled"
fi

if [ -n "$unmerged" ]; then
  unmerged_branch_count=$(printf '%s\n' "$unmerged" | grep -c .)
  if [ "$unmerged_branch_count" = "1" ]; then
    status+=" · 1 branch unmerged"
  else
    status+=" · ${unmerged_branch_count} branches unmerged"
  fi
fi

# Concurrent-session warning: if another Claude Code session shares this
# MEMOIR_STORE on a different branch, surface it once in the status line.
# (Writes collide silently otherwise — memoir's git backend has one HEAD.)
CONCURRENT_WARN=$(concurrent_session_warning 2>/dev/null || true)
if [ -n "$CONCURRENT_WARN" ]; then
  status+=" · ${CONCURRENT_WARN}"
fi

# Inject a short taxonomy snapshot as additionalContext so Claude sees what
# kinds of memories exist without having to invoke the recall skill up front.
# Reuses SUMMARY_JSON fetched above; filters the same taxonomy:v1:* noise.
context=""
if [ "$USER_MEMORIES" != "0" ] && [ -n "$SUMMARY_JSON" ]; then
  ns_list=$(python3 -c "
import json, sys
try:
    obj = json.loads(sys.argv[1])
    ns = obj.get('namespaces', {}) or {}
    user_ns = {k: v for k, v in ns.items() if not k.startswith('taxonomy:')}
    if not user_ns:
        sys.exit(0)
    lines = [f'- {k}: {v} memor' + ('y' if v == 1 else 'ies') for k, v in sorted(user_ns.items())]
    print('# Memoir store — current state')
    print(f'branch: $DISPLAY_BRANCH  ·  user memories: $USER_MEMORIES')
    print('')
    print('namespaces:')
    print('\n'.join(lines))
except Exception:
    pass
" "$SUMMARY_JSON" 2>/dev/null || true)
  context="$ns_list"
fi

if [ -n "$unmerged" ]; then
  unmerged_block="# memoir — unmerged branches detected"$'\n'
  unmerged_block+="You have captured memories on these branches that aren't on main yet:"$'\n\n'
  while IFS=$'\t' read -r b n; do
    [ -z "$b" ] && continue
    unmerged_block+="- memoir/${b}: ${n} unmerged commits → memoir:memoir-sync-branch ${b}"$'\n'
  done <<< "$unmerged"
  unmerged_block+=$'\n'"Run the suggested command to promote them to main (keeps the source branch)."
  if [ -n "$context" ]; then
    context="${context}"$'\n\n'"${unmerged_block}"
  else
    context="$unmerged_block"
  fi
fi

# Record this session's heartbeat so any parallel session can detect the
# collision. Must happen after auto-match so we record the actual branch
# we're targeting.
write_session_heartbeat || true

json_status=$(_json_encode_str "$status")
if [ -n "$context" ]; then
  json_context=$(_json_encode_str "$context")
  echo "{\"systemMessage\": $json_status, \"hookSpecificOutput\": {\"hookEventName\": \"SessionStart\", \"additionalContext\": $json_context}}"
else
  echo "{\"systemMessage\": $json_status}"
fi

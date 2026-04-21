#!/usr/bin/env bash
# SessionStart hook: auto-init the memoir store, surface status + current branch.
#
# Discard stdin before sourcing common.sh — session-start never uses $INPUT and
# `claude --resume` can leave the pipe open indefinitely, which would block the
# `cat` inside common.sh on macOS.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec < /dev/null
source "$SCRIPT_DIR/common.sh"

# If the CLI isn't installed, surface a clear install hint and stop — no fallbacks.
if [ -z "$MEMOIR_CMD" ]; then
  status="[memoir] CLI not found on PATH — install with: pip install -e /path/to/memoir  (or pip install memoir once published). Capture/recall disabled."
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

# Status line mirrors memsearch's shape but surfaces memoir's differentiators:
# current branch (what CLI recalls/captures target) and commit_count (full history).
CODE_BRANCH=$(code_git_branch)
# Display memoir's memory branch as `<code-branch>+<memory-branch>` so the
# code repo context is always part of the memory-branch identifier in the UI,
# even though memoir's internal branch name is just `<memory-branch>`.
# The `+` signals "pair of branches" and makes the two coordinates impossible
# to conflate at a glance. Falls back to just `<memory-branch>` when the
# project isn't a git repo.
if [ -n "$CODE_BRANCH" ]; then
  DISPLAY_BRANCH="${CODE_BRANCH}+${BRANCH}"
else
  DISPLAY_BRANCH="${BRANCH}"
fi
status="[memoir] ${DISPLAY_BRANCH} · ${USER_MEMORIES} memories · ${COMMITS} commits"
if [ "${MEMOIR_NO_CAPTURE:-}" = "1" ]; then
  status+=" · capture disabled"
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
    print(f'branch (code+memory): $DISPLAY_BRANCH  ·  user memories: $USER_MEMORIES')
    print('')
    print('namespaces:')
    print('\n'.join(lines))
except Exception:
    pass
" "$SUMMARY_JSON" 2>/dev/null || true)
  context="$ns_list"
fi

json_status=$(_json_encode_str "$status")
if [ -n "$context" ]; then
  json_context=$(_json_encode_str "$context")
  echo "{\"systemMessage\": $json_status, \"hookSpecificOutput\": {\"hookEventName\": \"SessionStart\", \"additionalContext\": $json_context}}"
else
  echo "{\"systemMessage\": $json_status}"
fi

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

# Pull status JSON — contains branch, commit_count, memory_count.
STATUS_JSON=$(memoir_json status || true)
BRANCH=$(_json_val "$STATUS_JSON" "branch" "main")
COMMITS=$(_json_val "$STATUS_JSON" "commit_count" "0")
MEMORIES=$(_json_val "$STATUS_JSON" "memory_count" "0")

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
status="[memoir] ${DISPLAY_BRANCH} · ${MEMORIES} memories · ${COMMITS} commits"
if [ "${MEMOIR_NO_CAPTURE:-}" = "1" ]; then
  status+=" · capture disabled"
fi

# Inject a short taxonomy snapshot as additionalContext so Claude sees what
# kinds of memories exist without having to invoke the recall skill up front.
# `summarize taxonomy --json` returns a namespace->count mapping; we trim the
# taxonomy:v1:* internal namespaces and keep user-facing ones.
context=""
if [ "$MEMORIES" != "0" ]; then
  SUMMARY_JSON=$(memoir_json summarize taxonomy || true)
  if [ -n "$SUMMARY_JSON" ]; then
    ns_list=$(python3 -c "
import json, sys
try:
    obj = json.loads(sys.argv[1])
    ns = obj.get('namespaces', {}) or {}
    # Drop memoir's internal bookkeeping namespaces — they're noise for Claude.
    user_ns = {k: v for k, v in ns.items() if not k.startswith('taxonomy:')}
    if not user_ns:
        sys.exit(0)
    total = obj.get('total_memories', 0)
    lines = [f'- {k}: {v} memor' + ('y' if v == 1 else 'ies') for k, v in sorted(user_ns.items())]
    print('# Memoir store — current state')
    print(f'branch (code+memory): $DISPLAY_BRANCH  ·  total memories: {total}')
    print('')
    print('namespaces:')
    print('\n'.join(lines))
except Exception:
    pass
" "$SUMMARY_JSON" 2>/dev/null || true)
    context="$ns_list"
  fi
fi

json_status=$(_json_encode_str "$status")
if [ -n "$context" ]; then
  json_context=$(_json_encode_str "$context")
  echo "{\"systemMessage\": $json_status, \"hookSpecificOutput\": {\"hookEventName\": \"SessionStart\", \"additionalContext\": $json_context}}"
else
  echo "{\"systemMessage\": $json_status}"
fi

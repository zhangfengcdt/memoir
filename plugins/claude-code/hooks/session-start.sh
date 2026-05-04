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
# With uv present, the plugin transparently shells out via
# `uvx --from memoir-ai==<pin> memoir` (pin in scripts/resolve-memoir-cli.sh).
if [ -z "$MEMOIR_CMD" ]; then
  status="[memoir] $MEMOIR_INSTALL_HINT Capture/recall disabled."
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

# One-shot: on brand-new store creation, auto-discover and load any custom
# taxonomy markdown files from:
#   1. ~/.memoir/taxonomy/*.md                — user-global
#   2. <project-root>/.memoir/taxonomy/*.md   — project-specific (overrides)
# Both are appended to the builtin taxonomy already installed by `memoir
# new`. Skipped for existing stores so editing these files mid-project
# doesn't silently change what the user has already captured against.
if [ "${MEMOIR_STORE_WAS_CREATED:-0}" = "1" ]; then
  load_custom_taxonomy_files >/dev/null 2>&1 || true
fi

# Auto-match memoir branch to current code branch (creates from main if
# missing; honors sticky opt-out). Failures are non-fatal — we just end
# up on whatever memoir branch was already current.
auto_match_memoir_branch || true

# Pull status JSON — contains branch, memory_count (total).
STATUS_JSON=$(memoir_json status || true)
BRANCH=$(_json_val "$STATUS_JSON" "branch" "main")
TOTAL_MEMORIES=$(_json_val "$STATUS_JSON" "memory_count" "0")

# Compute *user-facing* memory count by subtracting entries in memoir's
# internal scaffolding namespaces — `taxonomy:v1:*` (classification hints
# installed by `memoir new --taxonomy-builtin`) and `codebase:onboard`
# (agent-generated repo snapshot written by /memoir:onboard). Both are
# machinery, not user captures; counting them inflates the status-line
# number away from what the user has actually remembered.
# `summarize taxonomy --json` returns a per-namespace count map; we sum the
# remaining entries. Quick read, no LLM call, safe to run every session.
SUMMARY_JSON=$(memoir_json summarize taxonomy 2>/dev/null || true)
USER_MEMORIES="$TOTAL_MEMORIES"
if [ -n "$SUMMARY_JSON" ]; then
  USER_MEMORIES=$(python3 -c "
import json, sys
SCAFFOLDING = {'codebase:onboard', 'project:onboard'}
try:
    obj = json.loads(sys.argv[1])
    ns = obj.get('namespaces', {}) or {}
    print(sum(v for k, v in ns.items() if not k.startswith('taxonomy:') and k not in SCAFFOLDING))
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

status="[memoir] ${DISPLAY_BRANCH} · ${USER_MEMORIES} memories"
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
# Reuses SUMMARY_JSON fetched above; filters the same scaffolding namespaces
# as the count above (taxonomy:v1:* + codebase:onboard) so the listed
# namespaces sum to the number rendered in the status line.
context=""
if [ "$USER_MEMORIES" != "0" ] && [ -n "$SUMMARY_JSON" ]; then
  ns_list=$(python3 -c "
import json, sys
SCAFFOLDING = {'codebase:onboard', 'project:onboard'}
try:
    obj = json.loads(sys.argv[1])
    ns = obj.get('namespaces', {}) or {}
    user_ns = {k: v for k, v in ns.items() if not k.startswith('taxonomy:') and k not in SCAFFOLDING}
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

# Inject a flat listing of `default`-namespace keys (grouped by L1 prefix,
# capped at 200) so the agent can see what the user remembers without paying
# for a recall round-trip.
default_keys_block=$(render_default_keys_compact 2>/dev/null || true)
if [ -n "$default_keys_block" ]; then
  if [ -n "$context" ]; then
    context="${context}"$'\n\n'"${default_keys_block}"
  else
    context="$default_keys_block"
  fi
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

# Inject the onboard snapshot so fresh sessions start with a high-level map of
# the project. Two flavors share the same injection slot:
#   - git folder      → codebase:onboard (code-shape: modules, goals, rules,
#                       lessons), populated by /memoir:onboard's cold/warm path
#                       on the code SHA.
#   - non-git folder  → project:onboard (file-shape: summary, structure tree,
#                       per-file blobs), populated by /memoir:onboard's
#                       project-onboard path on a filesystem snapshot hash.
# Gated on MEMOIR_ONBOARD_INJECT (default=1) so a user who finds the block
# noisy can opt out with MEMOIR_ONBOARD_INJECT=0. If the namespace is empty,
# emit a one-line hint nudging the user to populate it via /memoir:onboard.
if [ "${MEMOIR_ONBOARD_INJECT:-1}" = "1" ]; then
  if in_git_repo; then
    onboard_namespace="codebase:onboard"
    onboard_block=$(render_codebase_onboard_compact 2>/dev/null || true)
  else
    onboard_namespace="project:onboard"
    onboard_block=$(render_project_onboard_compact 2>/dev/null || true)
  fi
  if [ -z "$onboard_block" ]; then
    # No snapshot yet — only surface the hint if some user memories already
    # exist (brand-new store gets no extra noise on first launch).
    if [ "$USER_MEMORIES" != "0" ]; then
      onboard_block="# ${onboard_namespace} snapshot"$'\n'
      onboard_block+="(none yet — run /memoir:onboard to generate one; future sessions will auto-inject it here)"
    fi
  fi
  if [ -n "$onboard_block" ]; then
    if [ -n "$context" ]; then
      context="${context}"$'\n\n'"${onboard_block}"
    else
      context="$onboard_block"
    fi
  fi
fi

# Surface the store-mode drift warning (one block, informational only).
# Captures still proceed; the user decides whether to act. Detection runs in
# `ensure_store` for existing stores; brand-new stores set the marker without
# triggering the warning. The warning lives alongside the normal status line
# and onboard injection so the user sees it during routine SessionStart.
if [ "${MEMOIR_STORE_MODE_MISMATCH:-0}" = "1" ]; then
  drift_block=$(render_store_mode_drift_warning 2>/dev/null || true)
  if [ -n "$drift_block" ]; then
    if [ -n "$context" ]; then
      context="${context}"$'\n\n'"${drift_block}"
    else
      context="$drift_block"
    fi
  fi
fi

# Refresh the statusline cache so the plugin's statusline widget can render
# the current memory count without spawning the CLI on every tick.
write_statusline_cache "$USER_MEMORIES" || true

# Snapshot the store's taxonomy into a prompt snippet that the Stop hook's
# fact extractor will fold into its system prompt. Keeps auto-capture aligned
# with whatever taxonomy the user loaded at `memoir new` (builtin or custom).
# Refreshed once per session — mid-session taxonomy edits won't take effect
# until the next SessionStart, which is an acceptable staleness trade-off.
write_stop_prompt_cache || true

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

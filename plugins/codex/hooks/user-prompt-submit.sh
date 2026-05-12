#!/usr/bin/env bash
# UserPromptSubmit hook: light hint reminding Codex the memory-recall skill
# is available, and surfacing the current memoir branch name.
# The actual retrieval is pull-based (memory-recall skill, context: fork).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

PROMPT=$(_json_val "$INPUT" "prompt" "")
if [ -z "$PROMPT" ] || [ "${#PROMPT}" -lt 10 ]; then
  echo '{}'
  exit 0
fi

if [ -z "$MEMOIR_CMD" ]; then
  echo '{}'
  exit 0
fi

# Re-run auto-match here (not just SessionStart). If the user switched code
# branches mid-session (e.g. `git checkout feature/b` in a terminal), the
# memoir branch would otherwise remain on the old match and subsequent Stop
# captures would write to the wrong branch. Calling auto_match on every
# prompt makes "memoir branch == code branch (unless sticky)" an invariant
# across the entire session, not just at start. Fast no-op when branches
# already agree; flips the memoir branch when they don't.
auto_match_memoir_branch || true

# Read state AFTER the potential auto-switch so the status hint reflects reality.
STATUS_JSON=$(memoir_json status || true)
BRANCH=$(_json_val "$STATUS_JSON" "branch" "main")
CODE_BRANCH=$(code_git_branch)

# Display: collapse to `<branch>` when code and memoir agree (the default
# after auto-match); show `<code>+<memory>*` when they differ, which only
# happens when the user has a sticky opt-out active.
if [ -n "$CODE_BRANCH" ] && [ "$CODE_BRANCH" = "$BRANCH" ]; then
  DISPLAY_BRANCH="${BRANCH}"
elif [ -n "$CODE_BRANCH" ]; then
  DISPLAY_BRANCH="${CODE_BRANCH}+${BRANCH}*"
else
  DISPLAY_BRANCH="${BRANCH}"
fi

# Read the user-facing memory count from the memory-count cache — written by
# SessionStart and Stop hooks. Cheap read, no CLI spawn. Falls back to 0
# if the cache is missing (pre-first-session or writes-failed state).
USER_MEMORIES=0
CACHE="$MEMOIR_STORE_PATH/.git/plugin-memory-count-cache"
if [ -f "$CACHE" ]; then
  USER_MEMORIES=$(head -n 1 "$CACHE" 2>/dev/null | tr -dc '0-9' || true)
  [ -z "$USER_MEMORIES" ] && USER_MEMORIES=0
fi

# Base hook message: branch (+ sticky marker if needed).
msg="[memoir] ${DISPLAY_BRANCH}"

# When user memories exist, append the "memory available" signal the
# memory-recall skill keys off. This is the single canonical trigger that
# tells Codex "don't silently answer — check past context first".
if [ "$USER_MEMORIES" -gt 0 ]; then
  msg+=" · memory available (${USER_MEMORIES} facts)"
fi

# Classify the prompt. Short/trivial prompts don't warrant a strong recall
# nudge — we keep the status line quiet so Codex doesn't spin up the skill
# on every "ok" or "thanks". Non-trivial prompts (longer, or mentioning
# design/implementation/refactor verbs, or self-referential nouns about the
# memory system, or showing structural signals like questions / code blocks
# / file paths) get an additionalContext block that actively instructs a
# recall pass before answering.
#
# Operating principle: lean toward recall. False positives waste a ~500ms
# recall call. False negatives mean Codex gives advice that conflicts with
# stored prefs — expensive (wasted reasoning, user has to correct).
#
# The harness at tests/prompt-harness/cases/gate/user-prompt-submit/ pins
# this behavior with deterministic regression tests; tune triggers there
# before changing the regexes here.

# Pure-ack short-circuit: a one-liner like "ok thanks" should never invoke
# recall regardless of length. Catches the case where a 40+ char filler
# ("sounds good let me know when you're done") accidentally satisfies the
# gate. Anchored ^…$, case-insensitive, optional trailing dot.
ack_short_circuit=
if printf '%s' "$PROMPT" | grep -qiE '^[[:space:]]*(ok|okay|sure|yes|no|thanks|thank[[:space:]]+you|got[[:space:]]+it|sounds[[:space:]]+good|nice|cool|great|awesome|perfect)\.?[[:space:]]*$'; then
  ack_short_circuit=1
fi

prompt_len=${#PROMPT}
context=""
if [ -z "$ack_short_circuit" ] && [ "$USER_MEMORIES" -gt 0 ] && [ "$prompt_len" -ge 40 ]; then
  # Verbs and domain nouns combined into one alternation. Verbs cover the
  # "describe what to do" failure mode; nouns (memoir/recall/harness/hook/
  # prompt) catch self-referential prompts about the memory system itself
  # where prior context is almost certainly load-bearing.
  if printf '%s' "$PROMPT" | grep -qiE '\b(add|build|implement|refactor|redesign|design|create|write|set\s+up|wire\s+up|integrate|migrate|rewrite|extract|extend|plumb|hook\s+up|ship|scaffold|optimize|fix|debug|review|architect|model|schema|API|service|feature|module|system|pipeline|workflow|make|move|replace|convert|swap|remove|clean\s+up|transform|investigate|explore|figure\s+out|plan|decide|choose|pick|compare|walk\s+me\s+through|take\s+a\s+stab|help\s+me|memoir|recall|harness|hook|prompt)\b' \
     || printf '%s' "$PROMPT" | grep -qiE '^(how|why|what|where|when|should|can|could|would|is\s+it|are\s+we|do\s+I)\b.*\?' \
     || printf '%s' "$PROMPT" | grep -qF '```' \
     || printf '%s' "$PROMPT" | grep -qE '\b(def|function|class|import|export)\s+' \
     || printf '%s' "$PROMPT" | grep -qE '\.(py|js|ts|tsx|scala|java|go|rs|rb|md)(\b|$)' \
     || printf '%s' "$PROMPT" | grep -qE '[A-Za-z0-9_~.-]+/[A-Za-z0-9_.-]+'; then
    context="# memoir — recall before acting

The user's prompt describes work to do (implementation, design, refactor, or similar). Before starting, invoke the \`memoir:memory-recall\` skill to fetch any prior preferences, architectural decisions, coding conventions, or constraints that should shape the approach.

Silently executing without checking past context is a common failure mode: captured preferences (e.g. \"rebase not merge\", \"TypeScript not JavaScript\", \"two-approver PR policy\") only help if they're actually consulted. One recall call up front is cheap (~500-800ms) and typically answers whether any stored facts are relevant.

If recall returns nothing useful, proceed normally. If it returns relevant facts, incorporate them into your plan and mention the ones you applied."
  fi
fi

json_msg=$(_json_encode_str "$msg")
if [ -n "$context" ]; then
  json_context=$(_json_encode_str "$context")
  echo "{\"systemMessage\": $json_msg, \"hookSpecificOutput\": {\"hookEventName\": \"UserPromptSubmit\", \"additionalContext\": $json_context}}"
else
  echo "{\"systemMessage\": $json_msg}"
fi

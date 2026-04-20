#!/usr/bin/env bash
# Stop hook: summarize the last turn into discrete memory-worthy facts, then
# call `memoir remember` for each — memoir's classifier drops each fact into
# the correct taxonomy path and creates a git commit. Runs async so it never
# blocks the user's next turn.
#
# Escape hatch: MEMOIR_NO_CAPTURE=1 disables this hook per-session.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Infinite-loop guard: skip if this Stop was triggered by a nested Stop hook.
STOP_HOOK_ACTIVE=$(_json_val "$INPUT" "stop_hook_active" "false")
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  echo '{}'
  exit 0
fi

if [ -z "$MEMOIR_CMD" ] || [ "${MEMOIR_NO_CAPTURE:-}" = "1" ]; then
  echo '{}'
  exit 0
fi

# Store must already exist (SessionStart creates it). If not, bail silently.
if [ ! -d "$MEMOIR_STORE_PATH/.git" ]; then
  echo '{}'
  exit 0
fi

TRANSCRIPT_PATH=$(_json_val "$INPUT" "transcript_path" "")
if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  echo '{}'
  exit 0
fi

LINE_COUNT=$(wc -l < "$TRANSCRIPT_PATH" 2>/dev/null || echo "0")
if [ "$LINE_COUNT" -lt 3 ]; then
  echo '{}'
  exit 0
fi

PARSED=$("$SCRIPT_DIR/parse-transcript.sh" "$TRANSCRIPT_PATH" 2>/dev/null || true)
if [ -z "$PARSED" ] || [ "$PARSED" = "(empty transcript)" ] || [ "$PARSED" = "(no user message found)" ] || [ "$PARSED" = "(empty turn)" ]; then
  echo '{}'
  exit 0
fi

# Extract memory-worthy facts via haiku. Prompt is deliberately memoir-specific:
# memoir classifies *individual statements* into a taxonomy, so we want discrete
# facts (one per line), not a bullet-list summary of the conversation.
FACTS=""
if command -v claude &>/dev/null; then
  FACTS=$(printf '%s' "$PARSED" | MEMOIR_NO_CAPTURE=1 CLAUDECODE= claude -p \
    --model haiku \
    --no-session-persistence \
    --no-chrome \
    --system-prompt "You are an external observer extracting durable facts from a conversation turn between a human ([Human]) and Claude Code ([Claude Code]).

Output 0-6 facts, one per line. Each line must be a complete, self-contained statement that a memory classifier can categorize into one of: profile, preferences, workflow, context, relationships, goals, experience, knowledge, behavior, routine.

STRICT RULES:
- Each line is ONE fact. No bullet markers, no numbering, no prefixes.
- Write in third person when it's about the human: 'The user prefers X', 'The user works at Y'.
- Only include facts that are DURABLE (likely relevant across sessions): preferences, project/tool choices, roles, decisions, constraints.
- EXCLUDE: ephemeral task state, today-only TODOs, tool-call mechanics, what Claude did, things already likely stored elsewhere (git history, file contents).
- If the turn has no durable facts, output nothing (empty response). Do NOT fabricate.
- Do NOT output any preamble, explanation, or closing remark — only the fact lines.

Example good output:
The user prefers 2-space indentation in YAML files.
The project uses Python 3.12 and ruff for linting.
The user's team holds standups at 9:30am PT on weekdays.

Example bad output (do not do this):
- The user asked about indentation
Here are the facts I extracted: ..." \
    2>/dev/null || true)
fi

if [ -z "$FACTS" ]; then
  echo '{}'
  exit 0
fi

# Call `memoir remember` once per non-empty line. Each call is an LLM classify
# + commit; running in the foreground of the async Stop hook is fine.
printf '%s\n' "$FACTS" | while IFS= read -r line; do
  # Strip leading/trailing whitespace and common bullet markers haiku might still emit.
  trimmed=$(printf '%s' "$line" | sed -E 's/^[[:space:]]*[-*•]?[[:space:]]*//' | sed -E 's/[[:space:]]+$//')
  if [ -z "$trimmed" ] || [ "${#trimmed}" -lt 8 ]; then
    continue
  fi
  memoir_json remember "$trimmed" >/dev/null 2>&1 || true
done

echo '{}'

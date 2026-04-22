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

# Ensure memoir is on the branch matching the current code branch before we
# write. Covers the case where the user switched code branches mid-session
# (e.g. via `git checkout feature/b` in a terminal). Without this, captures
# from the post-switch turn would land on the previous code branch's memoir
# branch. Fast no-op when branches already agree.
auto_match_memoir_branch || true

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

# One-shot extract + classify via haiku. Output format: <taxonomy-path><TAB><fact>
# per line. We then call `memoir remember --path <path>` for each line, which
# bypasses memoir's internal LLM classifier entirely. Net result: ONE haiku call
# per turn instead of 1 (extract) + N×4-5 (memoir's classify+decide+metadata
# chain) — typically 25-30x faster end-to-end.
#
# System-prompt shape mirrors memoir's own IntelligentClassifier fast prompt
# (CATEGORIES / EXAMPLES / RULES). The CATEGORIES + EXAMPLES blocks come from
# the store's persisted taxonomy (`taxonomy:v1:*`), cached at SessionStart —
# so auto-capture classifies against the same taxonomy as explicit
# `/memoir-remember "fact"` (without -p). Falls back to a hardcoded hint
# sheet if the store has no taxonomy loaded.
TAXONOMY_BLOCK=$(read_stop_prompt_cache)
if [ -z "$TAXONOMY_BLOCK" ]; then
  TAXONOMY_BLOCK='CATEGORIES (top-level + common second levels — pick a sensible third level yourself):
  profile.{personal,professional}: identity, demographics, occupation, education, skills, location, etc.
  preferences.{coding,tools,work,food,hobbies,entertainment}: editors, languages, frameworks, AI models, work style, etc.
  workflow.{coding,devops}: testing, branching, review, deployment, versioning, etc.
  context.project.{stack,repository,infrastructure,database,cicd,standards}
  relationships.{family,friends,professional}: manager, mentees, colleagues, etc.
  goals.{career,education,projects,financial}
  experience: past work, milestones, decisions
  knowledge.technical: languages, tools the user knows
  behavior.work: schedule, habits
  routine.daily: standups, ceremonies'
fi

STOP_SYSTEM_PROMPT="You are an external observer extracting durable facts from a conversation turn between a human ([Human]) and Claude Code ([Claude Code]). For each fact, output ONE line in this exact format:

<taxonomy-path><TAB><fact>

${TAXONOMY_BLOCK}

RULES:
- Output 0-6 lines. Each line is exactly: path<TAB>fact (use a real tab character between path and fact).
- EXACTLY 3 levels required: category.subcategory.type (e.g., preferences.coding.style).
- Prefer paths shown in CATEGORIES/EXAMPLES; invent a new 3-level path under an existing top-level category only if nothing fits.
- Each fact is ONE complete, self-contained statement. Third-person when about the human.
- DURABLE only: preferences, project/tool choices, roles, decisions, constraints likely relevant across sessions.
- EXCLUDE: ephemeral task state, today-only TODOs, tool-call mechanics, what Claude did, things in git history or file contents.
- If no durable facts, output nothing.
- NO preamble, NO explanation, NO bullets/numbering — only the path<TAB>fact lines."

FACTS_TSV=""
if command -v claude &>/dev/null; then
  FACTS_TSV=$(printf '%s' "$PARSED" | MEMOIR_NO_CAPTURE=1 CLAUDECODE= claude -p \
    --model haiku \
    --no-session-persistence \
    --no-chrome \
    --system-prompt "$STOP_SYSTEM_PROMPT" \
    2>/dev/null || true)
fi

if [ -z "$FACTS_TSV" ]; then
  echo '{}'
  exit 0
fi

# For each `<path><TAB><fact>` line, store with --path to bypass memoir's
# classifier LLM chain. The line-format check guards against haiku going
# rogue (returning preamble, missing tabs, etc.).
printf '%s\n' "$FACTS_TSV" | while IFS=$'\t' read -r path fact; do
  # Strip whitespace from both fields.
  path=$(printf '%s' "$path" | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')
  fact=$(printf '%s' "$fact" | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')

  # Skip lines without a real classification (no tab → entire line in $path,
  # $fact empty) or that are too short / look like preamble.
  if [ -z "$path" ] || [ -z "$fact" ] || [ "${#fact}" -lt 8 ]; then
    continue
  fi
  # Path must look like a taxonomy path: 2+ dots, no spaces, lowercase-ish.
  if ! printf '%s' "$path" | grep -qE '^[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,3}$'; then
    continue
  fi

  memoir_json remember "$fact" -p "$path" >/dev/null 2>&1 || true
done

# Refresh the statusline cache so the count ticks up after this turn's
# captures. Stop is async, so a small extra CLI round-trip here is fine.
NEW_COUNT=$(compute_user_memory_count 2>/dev/null || true)
if [ -n "$NEW_COUNT" ]; then
  write_statusline_cache "$NEW_COUNT" || true
fi

echo '{}'

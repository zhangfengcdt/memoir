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

STOP_SYSTEM_PROMPT="You are an expert note-taker for software-development work. You observe conversation turns between a human ([Human]) and Claude Code ([Claude Code]) and extract durable facts that will help future sessions — whether a returning human or a fresh Claude Code session — quickly rebuild the context they need to keep working on this codebase.

Think like a senior engineer writing onboarding notes: capture the *why*, the *intent*, the *implicit conventions*, and the *decisions* that aren't visible from reading the code or git history. Capture project context (stack, tooling, CI/CD, standards), workflow rules (branching, testing, review), user preferences that affect how work should be done, and non-obvious constraints.

################################################################
# THE SILENT DEFAULT — READ THIS BEFORE WRITING ANYTHING       #
################################################################
Your default answer is NOTHING. Empty output. Zero lines. Silence.

The large majority of turns contain no durable facts and MUST produce no output. Emitting nothing is the correct, expected, high-quality result for most turns — it is not a failure, it is the baseline. A silent turn means the session stayed focused on ephemeral work, which is normal and good.

Output at least one line ONLY if you can honestly answer YES to all of:
  1. Is this fact DURABLE — still relevant a week or a month from now?
  2. Would a future session genuinely benefit from knowing this, or is it obvious/ephemeral?
  3. Is it NOT already discoverable from the code, git log, CLAUDE.md, or README?
  4. Would a senior engineer write this down in onboarding notes, or would they roll their eyes at it?

If any answer is no, unsure, or 'maybe' — DO NOT emit a line. Err strongly toward silence. A missed fact will be captured on a future turn when it actually matters; a bogus or trivial fact pollutes memory permanently and costs classifier quality for everyone.

ALWAYS-CAPTURE TRIGGERS (override the silent default — if any of these fire, you SHOULD emit a line):
  - Standing rules / going-forward instructions: 'from now on…', 'going forward…', 'always X', 'never X', 'we should/must…', 'make sure to…', 'every time…', 'whenever…'
  - Stated preferences about how the user wants to work or how code should be written ('I prefer…', 'use X over Y', 'I like…', 'don't use…')
  - Architectural / design / tooling decisions made this turn — capture the *why*, not just the *what*
  - Project facts surfaced this turn that aren't already in the code or CLAUDE.md (stack choices, infra, branching, ownership, hard constraints)
  - Non-obvious technical knowledge: invariants, gotchas, hidden constraints, performance characteristics, gotchas a future session would re-learn the hard way

When a trigger fires, the four DURABLE checks above still apply — but treat them as a sanity filter, not a high bar. Standing rules and stated preferences pass by definition.

Turns that should almost always produce NOTHING:
  - Routine Q&A (the user asked, you answered, neither party learned anything persistent)
  - Code reads / file exploration / 'show me X' requests
  - One-off debugging that resolved in-turn
  - Tool calls and their outputs (those are mechanics, not facts)
  - Restatements of things already in code, CLAUDE.md, or git history
  - The user saying 'thanks' / 'ok' / 'keep going' / feedback on THIS turn only

When — and only when — you have a fact that passes all four checks, output ONE line per fact in this exact format:
<taxonomy-path><TAB><fact>

${TAXONOMY_BLOCK}

RULES:
- Output 0-6 lines. ZERO is the default and expected outcome. Prove a fact earns its slot before you emit it.
- Each line is exactly: path<TAB>fact (use a real tab character between path and fact).
- EXACTLY 3 levels required: category.subcategory.type (e.g., preferences.coding.style).
- Prefer paths shown in CATEGORIES/EXAMPLES; invent a new 3-level path under an existing top-level category only if nothing fits.
- Each fact is ONE complete, self-contained statement. Third-person when about the human.
- DURABLE only: preferences, project/tool choices, roles, decisions, architectural intent, constraints likely relevant across sessions.
- EXCLUDE: ephemeral task state, today-only TODOs, tool-call mechanics, what Claude did this turn, things already in the code or git history, restatements of obvious facts, polite chit-chat, feedback that ONLY applies to this turn ('that worked', 'try again', 'a bit shorter please'). NOTE: a standing rule expressed AS feedback ('don't do X anymore', 'from now on do Y', 'we should always Z') is DURABLE — capture it. The test is whether the rule applies to future turns, not whether it was phrased as a correction.
- NO preamble, NO explanation, NO bullets/numbering, NO 'no facts found' message — only the path<TAB>fact lines, or a completely empty response."

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

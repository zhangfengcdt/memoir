#!/usr/bin/env bash
# Stop hook: summarize the last turn into discrete memory-worthy facts, then
# call `memoir remember` for each — memoir's classifier drops each fact into
# the correct taxonomy path and creates a git commit. Runs async so it never
# blocks the user's next turn.
#
# Escape hatches:
#   MEMOIR_NO_CAPTURE=1  disables auto-capture of memory-worthy facts.
#   MEMOIR_NO_METRICS=1  disables per-branch turn-statistics accumulation.
# Both are independent — either path can fail without affecting the other.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Infinite-loop guard: skip if this Stop was triggered by a nested Stop hook.
STOP_HOOK_ACTIVE=$(_json_val "$INPUT" "stop_hook_active" "false")
if [ "$STOP_HOOK_ACTIVE" = "true" ]; then
  echo '{}'
  exit 0
fi

if [ -z "$MEMOIR_CMD" ]; then
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

# Per-branch turn-statistics accumulator. Reads the existing
# `metrics.turn.<branch>` key (if any), folds in this turn's deltas, writes
# back. Independent of the capture path below — runs even when
# MEMOIR_NO_CAPTURE=1, fails silently on its own. Branches are part of the
# key, so promotions carry source-branch identity.
if [ "${MEMOIR_NO_METRICS:-}" != "1" ]; then
  DELTA=$("$SCRIPT_DIR/collect-metrics.sh" "$TRANSCRIPT_PATH" 2>/dev/null || true)
  if [ -n "$DELTA" ]; then
    BRANCH_RAW=$(memoir_json status 2>/dev/null \
      | python3 -c "import json,sys; d=json.loads(sys.stdin.read() or '{}'); print(d.get('branch','unknown'))" 2>/dev/null)
    if [ -z "$BRANCH_RAW" ]; then
      BRANCH_RAW="unknown"
    fi
    MKEY="metrics.turn.${BRANCH_RAW}"
    PREV=$(memoir_json get "$MKEY" 2>/dev/null \
      | python3 -c "import json,sys; d=json.loads(sys.stdin.read() or '{}'); items=d.get('items') or [{}]; v=items[0].get('value') or {}; c=v.get('content'); print(c if isinstance(c,str) else '')" 2>/dev/null)
    MERGED=$(python3 "$SCRIPT_DIR/merge-metrics.py" "$PREV" "$DELTA" 2>/dev/null || true)
    if [ -n "$MERGED" ]; then
      memoir_json remember "$MERGED" -p "$MKEY" >/dev/null 2>&1 || true
    fi
  fi
fi

if [ "${MEMOIR_NO_CAPTURE:-}" = "1" ]; then
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
# `/memoir:remember "fact"` (without -p). Falls back to a hardcoded hint
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

# System prompt template lives in hooks/prompts/ so it's a first-class artifact
# (testable in isolation by the prompt-harness under tests/prompt-harness/).
# We do the ${TAXONOMY_BLOCK} substitution here in bash rather than relying on
# the template being eval'd, to avoid any quoting surprises in the live prompt.
STOP_SYSTEM_PROMPT_TEMPLATE=$(cat "$SCRIPT_DIR/prompts/stop_capture.tmpl")
STOP_SYSTEM_PROMPT="${STOP_SYSTEM_PROMPT_TEMPLATE//\$\{TAXONOMY_BLOCK\}/$TAXONOMY_BLOCK}"

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

# For each `<path>[,<path>...]<TAB><fact>` line, store with --path to bypass
# memoir's classifier LLM chain. The line-format check guards against haiku
# going rogue (returning preamble, missing tabs, etc.). Comma-separated paths
# in column 1 mean: write the same fact to each path in one call; each blob's
# `related_keys` field records the siblings (handled by memoir-side, not here).
printf '%s\n' "$FACTS_TSV" | while IFS=$'\t' read -r paths fact; do
  # Strip whitespace from both fields.
  paths=$(printf '%s' "$paths" | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')
  fact=$(printf '%s' "$fact" | sed -E 's/^[[:space:]]+//;s/[[:space:]]+$//')

  # Skip lines without a real classification (no tab → entire line in $paths,
  # $fact empty) or that are too short / look like preamble.
  if [ -z "$paths" ] || [ -z "$fact" ] || [ "${#fact}" -lt 8 ]; then
    continue
  fi
  # Column 1 must be one or more comma-separated taxonomy paths.
  if ! printf '%s' "$paths" | grep -qE '^[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,3}(,[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,3})*$'; then
    continue
  fi

  # Build `-p p1 -p p2 ...` argv from the comma-separated path list.
  PATH_ARGS=()
  IFS=',' read -ra PATH_LIST <<< "$paths"
  for p in "${PATH_LIST[@]}"; do
    PATH_ARGS+=("-p" "$p")
  done
  memoir_json remember "$fact" "${PATH_ARGS[@]}" >/dev/null 2>&1 || true
done

# Refresh the statusline cache so the count ticks up after this turn's
# captures. Stop is async, so a small extra CLI round-trip here is fine.
NEW_COUNT=$(compute_user_memory_count 2>/dev/null || true)
if [ -n "$NEW_COUNT" ]; then
  write_statusline_cache "$NEW_COUNT" || true
fi

echo '{}'

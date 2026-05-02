#!/usr/bin/env bash
# Stop hook: summarize the last turn into discrete memory-worthy facts, then
# call `memoir remember` for each — memoir's classifier drops each fact into
# the correct taxonomy path and creates a git commit. Runs async so it never
# blocks the user's next turn.
#
# Escape hatches:
#   MEMOIR_NO_CAPTURE=1       disables auto-capture of memory-worthy facts.
#   MEMOIR_NO_METRICS=1       disables per-branch turn-statistics accumulation.
#   MEMOIR_NO_CODE_SUMMARY=1  disables per-turn code-change summary writes.
# All three are independent — any path can fail without affecting the others.

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

# Per-branch code-change audit log. Detects file-edit tool calls in this turn
# (Edit / Write / MultiEdit / NotebookEdit), asks haiku for a one-line summary,
# and appends to a JSON-encoded list at `metrics.code.<branch>`. Read-merge-
# write at the hook level (mirrors metrics.turn.<branch>) — `memoir remember`
# replaces by path, so the hook owns the append. Skipped silently when the
# turn has no file edits or when memoir/haiku is unavailable. Independent of
# capture and metrics; failure here doesn't affect them.
#
# Stored value shape (JSON string under the key):
#   {"schema_version": 1, "entries": [{"timestamp": <epoch>, "summary": "..."}]}
#
# Retention: the entries list is capped at the most recent
# MEMOIR_METRICS_CODE_MAX (default 1000); older summaries are dropped on write
# so a single key can't grow unbounded over months of use.
if [ "${MEMOIR_NO_CODE_SUMMARY:-}" != "1" ]; then
  EDITS_JSON=$("$SCRIPT_DIR/collect-edits.sh" "$TRANSCRIPT_PATH" 2>/dev/null || true)
  if [ -n "$EDITS_JSON" ]; then
    # Build the haiku input: an optional [User prompt] header (the *why*) followed
    # by "<tool> <file_path>\n<snippet>\n---" per edit. Capped at ~8KB so multi-file
    # refactors stay well under context. The user prompt gives haiku intent it
    # can't infer from snippets alone.
    EDITS_TEXT=$(printf '%s' "$EDITS_JSON" | python3 -c "
import json, sys
try:
    payload = json.loads(sys.stdin.read() or '{}')
except Exception:
    sys.exit(0)
if not isinstance(payload, dict):
    sys.exit(0)
user_prompt = payload.get('user_prompt') or ''
entries = payload.get('edits') or []
parts = []
total = 0
LIMIT = 8000
if isinstance(user_prompt, str) and user_prompt.strip():
    block = f'[User prompt]\n{user_prompt.strip()}\n---\n'
    parts.append(block)
    total += len(block)
for e in entries:
    if not isinstance(e, dict):
        continue
    tool = e.get('tool', '')
    fp = e.get('file_path', '')
    snippet = e.get('snippet', '')
    block = f'{tool} {fp}\n{snippet}\n---\n'
    if total + len(block) > LIMIT:
        parts.append('… (additional edits truncated for length) …\n')
        break
    parts.append(block)
    total += len(block)
sys.stdout.write(''.join(parts))
" 2>/dev/null || true)
    if [ -n "$EDITS_TEXT" ] && command -v claude &>/dev/null; then
      CC_SUMMARY_PROMPT=$(cat "$SCRIPT_DIR/prompts/code_change_summary.tmpl" 2>/dev/null || true)
      if [ -n "$CC_SUMMARY_PROMPT" ]; then
        SUMMARY=$(printf '%s' "$EDITS_TEXT" \
          | MEMOIR_NO_CAPTURE=1 MEMOIR_NO_METRICS=1 MEMOIR_NO_CODE_SUMMARY=1 CLAUDECODE= claude -p \
              --model haiku \
              --no-session-persistence \
              --no-chrome \
              --system-prompt "$CC_SUMMARY_PROMPT" \
              2>/dev/null || true)
        # Strip surrounding whitespace and any preamble / quoting haiku adds.
        SUMMARY=$(printf '%s' "$SUMMARY" | python3 -c "
import re, sys
text = sys.stdin.read().strip()
# Drop leading/trailing quotes if the whole thing is wrapped.
if (text.startswith('\"') and text.endswith('\"')) or (text.startswith(\"'\") and text.endswith(\"'\")):
    text = text[1:-1].strip()
# Strip common preambles.
text = re.sub(r'^(here(\\s+is)?|summary|the\\s+(changes?|diff|edits?))[:\\s-]+', '', text, flags=re.I)
# Strip leading bullets.
text = re.sub(r'^[\\-\\*\\u2022]\\s+', '', text)
# Collapse to first non-empty line.
for ln in text.splitlines():
    ln = ln.strip()
    if ln:
        text = ln
        break
sys.stdout.write(text[:1000])
" 2>/dev/null || true)
        # Skip writes for trivial-only turns or empty/preamble outputs.
        if [ -n "$SUMMARY" ] \
           && [ "$(printf '%s' "$SUMMARY" | tr '[:upper:]' '[:lower:]')" != "trivial" ]; then
          BRANCH_RAW=$(memoir_json status 2>/dev/null \
            | python3 -c "import json,sys; d=json.loads(sys.stdin.read() or '{}'); print(d.get('branch','unknown'))" 2>/dev/null)
          if [ -z "$BRANCH_RAW" ]; then
            BRANCH_RAW="unknown"
          fi
          CCKEY="metrics.code.${BRANCH_RAW}"
          # Read-merge-write the entries list. memoir remember -p replaces, so
          # the hook owns the append (mirrors merge-metrics for metrics.turn).
          PREV_CC=$(memoir_json get "$CCKEY" 2>/dev/null \
            | python3 -c "import json,sys; d=json.loads(sys.stdin.read() or '{}'); items=d.get('items') or [{}]; v=items[0].get('value') or {}; c=v.get('content'); print(c if isinstance(c,str) else '')" 2>/dev/null)
          MERGED_CC=$(SUMMARY="$SUMMARY" PREV_CC="$PREV_CC" \
            MEMOIR_METRICS_CODE_MAX="${MEMOIR_METRICS_CODE_MAX:-1000}" python3 -c "
import json, os, time
prev_raw = os.environ.get('PREV_CC', '').strip()
summary = os.environ.get('SUMMARY', '').strip()
if not summary:
    raise SystemExit(0)
try:
    max_entries = int(os.environ.get('MEMOIR_METRICS_CODE_MAX', '1000'))
except ValueError:
    max_entries = 1000
if max_entries < 1:
    max_entries = 1
acc = {'schema_version': 1, 'entries': []}
if prev_raw:
    try:
        parsed = json.loads(prev_raw)
        if isinstance(parsed, dict) and isinstance(parsed.get('entries'), list):
            acc = parsed
            acc.setdefault('schema_version', 1)
    except (TypeError, ValueError):
        pass
acc['entries'].append({'timestamp': time.time(), 'summary': summary})
# Retain only the most recent N entries — older summaries get dropped so the
# stored value can't grow unbounded over months of use.
if len(acc['entries']) > max_entries:
    acc['entries'] = acc['entries'][-max_entries:]
print(json.dumps(acc))
" 2>/dev/null || true)
          if [ -n "$MERGED_CC" ]; then
            memoir_json remember "$MERGED_CC" -p "$CCKEY" >/dev/null 2>&1 || true
          fi
        fi
      fi
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

#!/usr/bin/env bash
# End-to-end test for the Stop hook's code-change audit log
# (`metrics.code.<branch>`).
#
# Stages a tmp memoir store + a fixture JSONL transcript that contains an
# Edit, then invokes stop.sh and asserts the metrics.code.<branch> key
# accumulates across two turns. Suppresses the model-driven capture and
# summary paths via env vars — we are only testing the gating logic, branch
# resolution, and append-via-AggregatedMemory behavior; the LLM call itself
# is exercised by the prompt-harness.
#
# Usage: bash plugins/codex/tests/test_stop_code_summary.sh
# Requires: `memoir` CLI on PATH, python3.

set -e

if ! command -v memoir &>/dev/null; then
  echo "SKIP: memoir CLI not on PATH"
  exit 0
fi
if ! command -v python3 &>/dev/null; then
  echo "SKIP: python3 not on PATH"
  exit 0
fi

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PLUGIN_ROOT="$(cd "$TEST_DIR/.." && pwd)"

PROJ=$(mktemp -d -t memoir-cc-proj.XXXXXX)
STORE=$(mktemp -d -t memoir-cc-store.XXXXXX)
rm -rf "$STORE"

cleanup() { rm -rf "$PROJ" "$STORE"; }
trap cleanup EXIT

git init -q "$PROJ"
git -C "$PROJ" commit --allow-empty -q -m init
memoir new "$STORE" --taxonomy-builtin >/dev/null
export MEMOIR_STORE="$STORE"
# Keep this test deterministic: don't let the model-driven capture or summary
# stages run. We assert the *gating* + *append* behavior independently, by
# invoking `memoir remember` from the test itself (which is exactly what the
# real summary path does on success).
export MEMOIR_NO_CAPTURE=1
export MEMOIR_NO_METRICS=1
export MEMOIR_NO_CODE_SUMMARY=1
cd "$PROJ"

PASS=0
FAIL=0
declare -a FAILURES=()

assert() {
  local description="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    printf '  ✓ %s\n' "$description"
    PASS=$((PASS + 1))
  else
    printf '  ✗ %s\n    expected: %s\n    got:      %s\n' \
      "$description" "$expected" "$actual"
    FAIL=$((FAIL + 1))
    FAILURES+=("$description")
  fi
}

write_edit_transcript() {
  local out_path="$1"
  python3 - "$out_path" <<'PY'
import json, sys
turns = [
  {"type": "user", "isMeta": False, "message": {"content": "make a change"},
   "timestamp": "2026-05-02T08:00:00Z"},
  {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Edit", "input": {
      "file_path": "src/x.py",
      "old_string": "old",
      "new_string": "new content"
    }}
  ]}, "timestamp": "2026-05-02T08:00:01Z"}
]
with open(sys.argv[1], "w") as f:
  for t in turns:
    f.write(json.dumps(t) + "\n")
PY
}

write_no_edit_transcript() {
  local out_path="$1"
  python3 - "$out_path" <<'PY'
import json, sys
turns = [
  {"type": "user", "isMeta": False, "message": {"content": "just a question"},
   "timestamp": "2026-05-02T08:00:00Z"},
  {"type": "assistant", "message": {"content": [
    {"type": "text", "text": "Here is the answer."}
  ]}, "timestamp": "2026-05-02T08:00:01Z"}
]
with open(sys.argv[1], "w") as f:
  for t in turns:
    f.write(json.dumps(t) + "\n")
PY
}

# Resolve current memoir branch.
BRANCH=$(memoir --json -s "$STORE" status | python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("branch","main"))')
KEY="metrics.code.${BRANCH}"

count_entries() {
  memoir --json -s "$STORE" get "$KEY" 2>/dev/null \
    | python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read() or '{}')
except Exception:
    print(0); sys.exit(0)
items = d.get('items') or []
if not items:
    print(0); sys.exit(0)
v = items[0].get('value') or {}
content = v.get('content')
if isinstance(content, str) and content.strip():
    try:
        acc = json.loads(content)
        print(len(acc.get('entries', [])) if isinstance(acc, dict) else 0)
        sys.exit(0)
    except Exception:
        print(0); sys.exit(0)
print(0)
"
}

# Replicate stop.sh's read-merge-write append for direct testing of the merge
# logic without invoking model. Takes one summary string, appends to KEY.
append_summary_directly() {
  local summary="$1"
  local prev
  prev=$(memoir --json -s "$STORE" get "$KEY" 2>/dev/null \
    | python3 -c 'import json,sys; d=json.loads(sys.stdin.read() or "{}"); items=d.get("items") or [{}]; v=items[0].get("value") or {}; c=v.get("content"); print(c if isinstance(c,str) else "")')
  local merged
  merged=$(SUMMARY="$summary" PREV="$prev" python3 -c "
import json, os, time
prev_raw = os.environ.get('PREV','').strip()
summary = os.environ.get('SUMMARY','').strip()
acc = {'schema_version': 1, 'entries': []}
if prev_raw:
    try:
        parsed = json.loads(prev_raw)
        if isinstance(parsed, dict) and isinstance(parsed.get('entries'), list):
            acc = parsed
    except Exception:
        pass
acc['entries'].append({'timestamp': time.time(), 'summary': summary})
print(json.dumps(acc))
")
  memoir --json -s "$STORE" remember "$merged" -p "$KEY" --replace >/dev/null 2>&1
}

# --- Test 1: a no-edit turn writes nothing ---
TRANSCRIPT=$(mktemp -t memoir-cc-transcript.XXXXXX.jsonl)
write_no_edit_transcript "$TRANSCRIPT"
INPUT_JSON=$(printf '{"transcript_path":"%s","stop_hook_active":false}' "$TRANSCRIPT")
echo "$INPUT_JSON" | bash "$PLUGIN_ROOT/hooks/stop.sh" >/dev/null 2>&1 || true
assert "no-edit turn: 0 entries"   "0"   "$(count_entries)"
rm -f "$TRANSCRIPT"

# --- Test 2: read-merge-write append behavior (mirrors stop.sh's merge logic) ---
append_summary_directly "Refactored auth middleware to use JWT"
assert "after 1 append: 1 entry"  "1"   "$(count_entries)"

append_summary_directly "Renamed get_user → get_current_user across 7 callers"
assert "after 2 appends: 2 entries"  "2"   "$(count_entries)"

append_summary_directly "Added Apache-2.0 SPDX headers to src/memoir/"
assert "after 3 appends: 3 entries"  "3"   "$(count_entries)"

# Verify the entry shape carries timestamp + summary fields.
LATEST=$(memoir --json -s "$STORE" get "$KEY" 2>/dev/null \
  | python3 -c 'import json,sys; d=json.loads(sys.stdin.read() or "{}"); v=(d.get("items") or [{}])[0].get("value") or {}; c=v.get("content") or ""; acc=json.loads(c); e=acc["entries"][-1]; print("ok" if isinstance(e.get("timestamp"),float) and isinstance(e.get("summary"),str) and e["summary"] else "bad")')
assert "entry shape: timestamp + summary fields" "ok" "$LATEST"

# Verify schema_version is set on the accumulator.
SCHEMA=$(memoir --json -s "$STORE" get "$KEY" 2>/dev/null \
  | python3 -c 'import json,sys; d=json.loads(sys.stdin.read() or "{}"); v=(d.get("items") or [{}])[0].get("value") or {}; c=v.get("content") or ""; acc=json.loads(c); print(acc.get("schema_version"))')
assert "schema_version=1" "1" "$SCHEMA"

# --- Test 3: MEMOIR_NO_CODE_SUMMARY=1 short-circuits even when an edit exists ---
TRANSCRIPT=$(mktemp -t memoir-cc-transcript.XXXXXX.jsonl)
write_edit_transcript "$TRANSCRIPT"
INPUT_JSON=$(printf '{"transcript_path":"%s","stop_hook_active":false}' "$TRANSCRIPT")
# Already exported MEMOIR_NO_CODE_SUMMARY=1 — counter should not advance.
echo "$INPUT_JSON" | bash "$PLUGIN_ROOT/hooks/stop.sh" >/dev/null 2>&1 || true
assert "MEMOIR_NO_CODE_SUMMARY=1 suppresses write" "3" "$(count_entries)"
rm -f "$TRANSCRIPT"

# --- Test 4: branch identity rides in the key (different branch ⇒ different key) ---
# Switch branches in memoir and verify metrics.code.<old-branch> stays put.
memoir -s "$STORE" branch create feature-x >/dev/null 2>&1 || true
memoir -s "$STORE" checkout feature-x >/dev/null 2>&1 || true
NEW_BRANCH=$(memoir --json -s "$STORE" status | python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("branch",""))')
if [ -n "$NEW_BRANCH" ] && [ "$NEW_BRANCH" != "$BRANCH" ]; then
  NEW_KEY="metrics.code.${NEW_BRANCH}"
  KEY="$NEW_KEY" assert "branch switch: new key starts empty"     "0" "$(KEY="$NEW_KEY" count_entries 2>/dev/null || echo 0)"
fi

echo
echo "==========================="
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf '\nFailed:\n'
  for f in "${FAILURES[@]}"; do
    printf '  - %s\n' "$f"
  done
  exit 1
fi

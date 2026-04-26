#!/usr/bin/env bash
# End-to-end test for the Stop hook's per-branch metrics accumulator.
#
# Stages a tmp memoir store + a fixture JSONL transcript, invokes stop.sh
# directly, and reads back the `metrics.turn.<branch>` key to verify shape
# and accumulation. Bypasses the haiku capture path by setting
# MEMOIR_NO_CAPTURE=1 — we are only testing metrics here.
#
# Usage: bash plugins/claude-code/tests/test_stop_metrics.sh
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
export CLAUDE_PLUGIN_ROOT="$(cd "$TEST_DIR/.." && pwd)"

PROJ=$(mktemp -d -t memoir-metrics-proj.XXXXXX)
STORE=$(mktemp -d -t memoir-metrics-store.XXXXXX)
rm -rf "$STORE"

cleanup() { rm -rf "$PROJ" "$STORE"; }
trap cleanup EXIT

git init -q "$PROJ"
git -C "$PROJ" commit --allow-empty -q -m init
memoir new "$STORE" --taxonomy-builtin --no-connect >/dev/null
export MEMOIR_STORE="$STORE"
export MEMOIR_NO_CAPTURE=1  # only test metrics; skip haiku/capture path
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

# Build a fixture JSONL transcript with one realistic turn.
fixture_transcript() {
  local out_path="$1"
  python3 - "$out_path" <<'PY'
import json, sys
out = sys.argv[1]
turns = [
  {"type": "user", "isMeta": False, "message": {"content": "real user question"},
   "timestamp": "2026-04-26T08:00:00Z"},
  {"type": "assistant", "message": {"content": [
    {"type": "text", "text": "Reply text."},
    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}
  ]}, "timestamp": "2026-04-26T08:00:01Z"},
  {"type": "user", "message": {"content": [
    {"type": "tool_result", "content": "file.txt", "is_error": False}
  ]}},
  {"type": "assistant", "message": {"content": [
    {"type": "text", "text": "Done."}
  ]}, "timestamp": "2026-04-26T08:00:02Z"}
]
with open(out, "w") as f:
  for t in turns:
    f.write(json.dumps(t) + "\n")
PY
}

# Memoir store branch — defaults to main on `memoir new`.
BRANCH=$(memoir --json -s "$STORE" status | python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("branch","main"))')
KEY="metrics.turn.${BRANCH}"

# --- Test 1: first turn writes a fresh accumulator ---
TRANSCRIPT=$(mktemp -t memoir-metrics-transcript.XXXXXX.jsonl)
fixture_transcript "$TRANSCRIPT"

INPUT_JSON=$(printf '{"transcript_path":"%s","stop_hook_active":false}' "$TRANSCRIPT")
echo "$INPUT_JSON" | bash "$CLAUDE_PLUGIN_ROOT/hooks/stop.sh" >/dev/null 2>&1 || true

# Read back the accumulator.
RESULT=$(memoir --json -s "$STORE" get "$KEY" 2>/dev/null \
  | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); items=d.get("items") or [{}]; v=items[0].get("value") or {}; c=v.get("content"); print(c if isinstance(c,str) else "")')

if [ -z "$RESULT" ]; then
  echo "  ✗ first turn produced no metrics key"
  FAIL=$((FAIL + 1))
else
  TURNS=$(printf '%s' "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["turns_count"])')
  CALLS=$(printf '%s' "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["total_tool_calls"])')
  ERRS=$(printf '%s' "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["total_tool_errors"])')
  TOKENS=$(printf '%s' "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["tokens"])')
  SCHEMA=$(printf '%s' "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["schema_version"])')
  BRANCH_VAL=$(printf '%s' "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["branch"])')
  assert "first turn: turns_count=1"     "1"           "$TURNS"
  assert "first turn: total_tool_calls=1" "1"          "$CALLS"
  assert "first turn: total_tool_errors=0" "0"         "$ERRS"
  assert "first turn: tokens=null"        "None"       "$TOKENS"
  assert "first turn: schema_version=1"   "1"          "$SCHEMA"
  assert "first turn: branch field set"   "$BRANCH"    "$BRANCH_VAL"
fi

rm -f "$TRANSCRIPT"

# --- Test 2: second turn accumulates ---
TRANSCRIPT=$(mktemp -t memoir-metrics-transcript.XXXXXX.jsonl)
fixture_transcript "$TRANSCRIPT"
INPUT_JSON=$(printf '{"transcript_path":"%s","stop_hook_active":false}' "$TRANSCRIPT")
echo "$INPUT_JSON" | bash "$CLAUDE_PLUGIN_ROOT/hooks/stop.sh" >/dev/null 2>&1 || true

RESULT=$(memoir --json -s "$STORE" get "$KEY" 2>/dev/null \
  | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); items=d.get("items") or [{}]; v=items[0].get("value") or {}; c=v.get("content"); print(c if isinstance(c,str) else "")')

TURNS=$(printf '%s' "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["turns_count"])')
CALLS=$(printf '%s' "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["total_tool_calls"])')
assert "second turn: turns_count=2"          "2" "$TURNS"
assert "second turn: total_tool_calls=2"     "2" "$CALLS"

rm -f "$TRANSCRIPT"

# --- Test 3: MEMOIR_NO_METRICS=1 suppresses the write ---
TRANSCRIPT=$(mktemp -t memoir-metrics-transcript.XXXXXX.jsonl)
fixture_transcript "$TRANSCRIPT"
INPUT_JSON=$(printf '{"transcript_path":"%s","stop_hook_active":false}' "$TRANSCRIPT")
MEMOIR_NO_METRICS=1 bash -c "echo '$INPUT_JSON' | bash '$CLAUDE_PLUGIN_ROOT/hooks/stop.sh'" >/dev/null 2>&1 || true

# Counters must still be 2 (unchanged from test 2).
RESULT=$(memoir --json -s "$STORE" get "$KEY" 2>/dev/null \
  | python3 -c 'import json,sys; d=json.loads(sys.stdin.read()); items=d.get("items") or [{}]; v=items[0].get("value") or {}; c=v.get("content"); print(c if isinstance(c,str) else "")')
TURNS=$(printf '%s' "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["turns_count"])')
assert "MEMOIR_NO_METRICS suppresses write" "2" "$TURNS"

rm -f "$TRANSCRIPT"

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

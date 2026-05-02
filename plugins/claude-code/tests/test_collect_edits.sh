#!/usr/bin/env bash
# Unit tests for hooks/collect-edits.sh — the transcript scanner that detects
# file-edit tool calls in the most recent turn. No memoir, no haiku — purely
# tests the JSON shape and last-turn anchor logic.
#
# Usage: bash plugins/claude-code/tests/test_collect_edits.sh

set -e

if ! command -v python3 &>/dev/null; then
  echo "SKIP: python3 not on PATH"
  exit 0
fi

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLLECTOR="$(cd "$TEST_DIR/.." && pwd)/hooks/collect-edits.sh"

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

write_fixture() {
  local out_path="$1"
  local body="$2"
  python3 -c "
import json, sys
turns = $body
with open(sys.argv[1], 'w') as f:
    for t in turns:
        f.write(json.dumps(t) + '\n')
" "$out_path"
}

run_collector() {
  local fixture="$1"
  bash "$COLLECTOR" "$fixture" 2>/dev/null || true
}

count_entries() {
  local out="$1"
  if [ -z "$out" ]; then echo 0; return; fi
  printf '%s' "$out" | python3 -c "import json,sys; print(len(json.load(sys.stdin)['edits']))"
}

field() {
  local out="$1" idx="$2" key="$3"
  printf '%s' "$out" | python3 -c "import json,sys; print(json.load(sys.stdin)['edits'][$idx]['$key'])"
}

user_prompt() {
  local out="$1"
  printf '%s' "$out" | python3 -c "import json,sys; v=json.load(sys.stdin).get('user_prompt'); print('' if v is None else v)"
}

# --- Test 1: no edits in the turn ⇒ empty output ---
F=$(mktemp -t cc-edits-1.XXXXXX.jsonl)
write_fixture "$F" '[
  {"type": "user", "isMeta": False, "message": {"content": "do nothing"}},
  {"type": "assistant", "message": {"content": [
    {"type": "text", "text": "Sure"},
    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}
  ]}}
]'
OUT=$(run_collector "$F")
assert "no-edit turn produces empty output" "" "$OUT"
rm -f "$F"

# --- Test 2: single Edit + user prompt is captured ---
F=$(mktemp -t cc-edits-2.XXXXXX.jsonl)
write_fixture "$F" '[
  {"type": "user", "isMeta": False, "message": {"content": "fix the auth bug"}},
  {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Edit", "input": {
      "file_path": "src/x.py",
      "old_string": "old",
      "new_string": "new content here"
    }}
  ]}}
]'
OUT=$(run_collector "$F")
assert "single Edit: 1 entry"            "1"             "$(count_entries "$OUT")"
assert "single Edit: tool=Edit"          "Edit"          "$(field "$OUT" 0 tool)"
assert "single Edit: file_path"          "src/x.py"      "$(field "$OUT" 0 file_path)"
assert "single Edit: snippet=new_string" "new content here" "$(field "$OUT" 0 snippet)"
assert "single Edit: user_prompt"        "fix the auth bug" "$(user_prompt "$OUT")"
rm -f "$F"

# --- Test 3: Write ---
F=$(mktemp -t cc-edits-3.XXXXXX.jsonl)
write_fixture "$F" '[
  {"type": "user", "isMeta": False, "message": {"content": "create file"}},
  {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Write", "input": {
      "file_path": "docs/new.md",
      "content": "# New doc"
    }}
  ]}}
]'
OUT=$(run_collector "$F")
assert "Write: 1 entry"             "1"          "$(count_entries "$OUT")"
assert "Write: tool=Write"          "Write"      "$(field "$OUT" 0 tool)"
assert "Write: snippet=content"     "# New doc"  "$(field "$OUT" 0 snippet)"
rm -f "$F"

# --- Test 4: MultiEdit fans out to one entry per inner edit ---
F=$(mktemp -t cc-edits-4.XXXXXX.jsonl)
write_fixture "$F" '[
  {"type": "user", "isMeta": False, "message": {"content": "rename"}},
  {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "MultiEdit", "input": {
      "file_path": "src/api.py",
      "edits": [
        {"old_string": "foo", "new_string": "bar"},
        {"old_string": "baz", "new_string": "qux"}
      ]
    }}
  ]}}
]'
OUT=$(run_collector "$F")
assert "MultiEdit: 2 entries (one per inner edit)" "2"        "$(count_entries "$OUT")"
assert "MultiEdit: file_path"                       "src/api.py" "$(field "$OUT" 0 file_path)"
assert "MultiEdit: snippet[0]=bar"                  "bar"      "$(field "$OUT" 0 snippet)"
assert "MultiEdit: snippet[1]=qux"                  "qux"      "$(field "$OUT" 1 snippet)"
rm -f "$F"

# --- Test 5: NotebookEdit ---
F=$(mktemp -t cc-edits-5.XXXXXX.jsonl)
write_fixture "$F" '[
  {"type": "user", "isMeta": False, "message": {"content": "update cell"}},
  {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "NotebookEdit", "input": {
      "notebook_path": "notebooks/x.ipynb",
      "new_source": "import pandas"
    }}
  ]}}
]'
OUT=$(run_collector "$F")
assert "NotebookEdit: 1 entry"           "1"                  "$(count_entries "$OUT")"
assert "NotebookEdit: tool"              "NotebookEdit"       "$(field "$OUT" 0 tool)"
assert "NotebookEdit: file_path"         "notebooks/x.ipynb"  "$(field "$OUT" 0 file_path)"
assert "NotebookEdit: snippet=new_source" "import pandas"     "$(field "$OUT" 0 snippet)"
rm -f "$F"

# --- Test 6: mixed Bash + Edit (non-edit tools ignored) ---
F=$(mktemp -t cc-edits-6.XXXXXX.jsonl)
write_fixture "$F" '[
  {"type": "user", "isMeta": False, "message": {"content": "mixed"}},
  {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Bash",  "input": {"command": "ls"}},
    {"type": "tool_use", "name": "Read",  "input": {"file_path": "/etc/hosts"}},
    {"type": "tool_use", "name": "Edit",  "input": {"file_path": "f.py", "old_string": "a", "new_string": "b"}},
    {"type": "tool_use", "name": "Bash",  "input": {"command": "git status"}}
  ]}}
]'
OUT=$(run_collector "$F")
assert "mixed: only the Edit is captured" "1"     "$(count_entries "$OUT")"
assert "mixed: tool=Edit"                  "Edit" "$(field "$OUT" 0 tool)"
rm -f "$F"

# --- Test 7: snippet truncation at 300 chars ---
F=$(mktemp -t cc-edits-7.XXXXXX.jsonl)
LONG=$(python3 -c 'print("x" * 500)')
write_fixture "$F" "[
  {'type': 'user', 'isMeta': False, 'message': {'content': 'big edit'}},
  {'type': 'assistant', 'message': {'content': [
    {'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': 'big.txt', 'old_string': 'a', 'new_string': '$LONG'}}
  ]}}
]"
OUT=$(run_collector "$F")
SNIPPET_LEN=$(printf '%s' "$OUT" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["edits"][0]["snippet"]))')
# 300 chars + 1 ellipsis "…" character (3 bytes UTF-8 but 1 character)
assert "snippet truncated to 301 chars (300 + ellipsis)" "301" "$SNIPPET_LEN"
rm -f "$F"

# --- Test 8: only the LAST turn is scanned (anchor logic) ---
F=$(mktemp -t cc-edits-8.XXXXXX.jsonl)
write_fixture "$F" '[
  {"type": "user", "isMeta": False, "message": {"content": "first turn"}},
  {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Edit", "input": {"file_path": "old.py", "old_string": "x", "new_string": "old turn"}}
  ]}},
  {"type": "user", "isMeta": False, "message": {"content": "second turn"}},
  {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Edit", "input": {"file_path": "new.py", "old_string": "x", "new_string": "new turn"}}
  ]}}
]'
OUT=$(run_collector "$F")
assert "anchor: only last turn"        "1"           "$(count_entries "$OUT")"
assert "anchor: file from last turn"   "new.py"      "$(field "$OUT" 0 file_path)"
rm -f "$F"

# --- Test 9: user prompt as a list of text blocks (not a bare string) ---
F=$(mktemp -t cc-edits-9.XXXXXX.jsonl)
write_fixture "$F" '[
  {"type": "user", "isMeta": False, "message": {"content": [
    {"type": "text", "text": "let us switch to JWT"}
  ]}},
  {"type": "assistant", "message": {"content": [
    {"type": "tool_use", "name": "Edit", "input": {"file_path": "auth.py", "old_string": "a", "new_string": "b"}}
  ]}}
]'
OUT=$(run_collector "$F")
assert "list-content prompt: extracted as text" "let us switch to JWT" "$(user_prompt "$OUT")"
rm -f "$F"

# --- Test 10: user prompt truncation at 2000 chars ---
F=$(mktemp -t cc-edits-10.XXXXXX.jsonl)
LONG_PROMPT=$(python3 -c 'print("y" * 2500)')
write_fixture "$F" "[
  {'type': 'user', 'isMeta': False, 'message': {'content': '$LONG_PROMPT'}},
  {'type': 'assistant', 'message': {'content': [
    {'type': 'tool_use', 'name': 'Edit', 'input': {'file_path': 'f.py', 'old_string': 'a', 'new_string': 'b'}}
  ]}}
]"
OUT=$(run_collector "$F")
PROMPT_LEN=$(printf '%s' "$OUT" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["user_prompt"]))')
assert "user_prompt truncated to 2001 chars (2000 + ellipsis)" "2001" "$PROMPT_LEN"
rm -f "$F"

# --- Test 11: empty / nonexistent transcript path ---
OUT=$(run_collector "/tmp/this-does-not-exist-$$.jsonl")
assert "missing transcript ⇒ empty output" "" "$OUT"

EMPTY=$(mktemp -t cc-edits-empty.XXXXXX.jsonl)
OUT=$(run_collector "$EMPTY")
assert "empty transcript ⇒ empty output"   "" "$OUT"
rm -f "$EMPTY"

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

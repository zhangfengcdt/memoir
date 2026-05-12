#!/usr/bin/env bash
# Smoke test for hooks/collect-edits.sh against Codex transcript JSONL.

set -e

if ! command -v python3 >/dev/null 2>&1; then
  echo "SKIP: python3 not on PATH"
  exit 0
fi

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COLLECTOR="$(cd "$TEST_DIR/.." && pwd)/hooks/collect-edits.sh"
FIXTURE=$(mktemp -t codex-edits.XXXXXX.jsonl)
trap 'rm -f "$FIXTURE"' EXIT

python3 - "$FIXTURE" <<'PY'
import json
import sys

patch = "\n".join([
    "*** Begin Patch",
    "*** Update File: src/example.py",
    "@@",
    "-old",
    "+new",
    "*** End Patch",
])
records = [
    {"type": "response_item", "payload": {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": "fix example"}],
    }},
    {"type": "response_item", "payload": {
        "type": "function_call",
        "name": "apply_patch",
        "arguments": json.dumps({"cmd": patch}),
    }},
]
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    for record in records:
        handle.write(json.dumps(record) + "\n")
PY

OUT=$(bash "$COLLECTOR" "$FIXTURE")
COUNT=$(printf '%s' "$OUT" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)["edits"]))')
FILE=$(printf '%s' "$OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["edits"][0]["file_path"])')

[ "$COUNT" = "1" ]
[ "$FILE" = "src/example.py" ]
echo "PASS: collect-edits detected Codex apply_patch"

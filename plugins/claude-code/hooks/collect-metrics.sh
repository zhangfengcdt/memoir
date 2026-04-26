#!/usr/bin/env bash
# Extract per-turn metrics deltas from a Claude Code JSONL transcript.
#
# Mirrors the last-turn anchor logic of parse-transcript.sh, but emits a
# numeric-only JSON object on stdout instead of formatted text.
#
# Output is the *delta* for the most recent turn — merge-metrics.py folds it
# into a per-branch accumulator. Returns empty stdout if no turn is found.
#
# Usage: bash collect-metrics.sh <transcript_path>

set -euo pipefail

TRANSCRIPT_PATH="${1:-}"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

python3 - "$TRANSCRIPT_PATH" <<'PY'
import json, sys, time
from datetime import datetime, timezone

transcript_path = sys.argv[1]

try:
    with open(transcript_path) as f:
        lines = f.readlines()
except OSError:
    sys.exit(0)

if not lines:
    sys.exit(0)


def find_last_turn_start(lines):
    for i in range(len(lines) - 1, -1, -1):
        try:
            obj = json.loads(lines[i])
        except Exception:
            continue
        if obj.get("type") != "user" or obj.get("isMeta"):
            continue
        content = obj.get("message", {}).get("content")
        if isinstance(content, str) and content.strip():
            return i
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text", "").strip():
                    return i
    return None


def parse_ts(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


start_idx = find_last_turn_start(lines)
if start_idx is None:
    sys.exit(0)

turn = []
for raw in lines[start_idx:]:
    try:
        turn.append(json.loads(raw))
    except Exception:
        continue

if not turn:
    sys.exit(0)

output_chars = 0
tool_input_chars = 0
tool_result_chars = 0
tool_calls_count = 0
tool_errors_count = 0
assistant_messages_count = 0
text_blocks_count = 0
tool_call_signatures = []

for obj in turn:
    msg_type = obj.get("type", "")
    if msg_type == "assistant":
        assistant_messages_count += 1
        content = obj.get("message", {}).get("content", [])
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            btype = block.get("type", "")
            if btype == "text":
                text = block.get("text", "")
                if isinstance(text, str) and text.strip():
                    output_chars += len(text)
                    text_blocks_count += 1
            elif btype == "tool_use":
                tool_calls_count += 1
                name = block.get("name", "")
                inp = block.get("input", {})
                try:
                    inp_json = json.dumps(inp, sort_keys=True)
                except (TypeError, ValueError):
                    inp_json = str(inp)
                tool_input_chars += len(inp_json)
                tool_call_signatures.append((name, inp_json))
    elif msg_type == "user":
        content = obj.get("message", {}).get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    raw_result = block.get("content", "")
                    if isinstance(raw_result, list):
                        text_parts = []
                        for item in raw_result:
                            if isinstance(item, dict):
                                t = item.get("text", "")
                                if isinstance(t, str):
                                    text_parts.append(t)
                        result_str = "\n".join(text_parts)
                    else:
                        result_str = str(raw_result)
                    tool_result_chars += len(result_str)
                    if block.get("is_error"):
                        tool_errors_count += 1

repeated_tool_calls = len(tool_call_signatures) - len(set(tool_call_signatures))

started_at_ts = parse_ts(turn[0].get("timestamp"))
ended_at_ts = time.time()

if started_at_ts is not None:
    latency_ms = int(round((ended_at_ts - started_at_ts) * 1000))
    turn_started_at = datetime.fromtimestamp(started_at_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
else:
    latency_ms = None
    turn_started_at = None

turn_ended_at = datetime.fromtimestamp(ended_at_ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")

delta = {
    "turn_started_at": turn_started_at,
    "turn_ended_at": turn_ended_at,
    "latency_ms": latency_ms,
    "output_chars": output_chars,
    "tool_input_chars": tool_input_chars,
    "tool_result_chars": tool_result_chars,
    "tool_calls_count": tool_calls_count,
    "tool_errors_count": tool_errors_count,
    "repeated_tool_calls": repeated_tool_calls,
    "assistant_messages_count": assistant_messages_count,
    "text_blocks_count": text_blocks_count,
}

print(json.dumps(delta))
PY

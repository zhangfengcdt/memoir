#!/usr/bin/env bash
# Extract per-turn metrics deltas from a Codex JSONL transcript.
#
# Output is the delta for the most recent user turn. merge-metrics.py folds it
# into a per-branch accumulator.
#
# Usage: bash collect-metrics.sh <transcript_path>

set -euo pipefail

TRANSCRIPT_PATH="${1:-}"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

python3 - "$TRANSCRIPT_PATH" <<'PY'
import json
import sys
import time
from datetime import datetime

transcript_path = sys.argv[1]

try:
    lines = open(transcript_path, encoding="utf-8").readlines()
except OSError:
    raise SystemExit(0)

if not lines:
    raise SystemExit(0)


def payload_from(obj):
    if obj.get("type") == "response_item":
        payload = obj.get("payload")
        return payload if isinstance(payload, dict) else None
    payload = obj.get("payload")
    if isinstance(payload, dict):
        return payload
    if obj.get("type") in {"message", "function_call", "function_call_output"}:
        return obj
    return None


def content_text(content) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and item.get("type") in {"input_text", "output_text", "text"}:
            text = item.get("text", "")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts)


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


payloads = []
for raw in lines:
    try:
        obj = json.loads(raw)
    except Exception:
        continue
    payload = payload_from(obj)
    if payload:
        payloads.append(payload)

if not payloads:
    raise SystemExit(0)

start_idx = None
for idx in range(len(payloads) - 1, -1, -1):
    payload = payloads[idx]
    if payload.get("type") == "message" and payload.get("role") == "user" and content_text(payload.get("content")).strip():
        start_idx = idx
        break

if start_idx is None:
    raise SystemExit(0)

turn = payloads[start_idx:]
output_chars = 0
tool_input_chars = 0
tool_result_chars = 0
tool_calls_count = 0
tool_errors_count = 0
assistant_messages_count = 0
text_blocks_count = 0
tool_call_signatures = []

for payload in turn:
    payload_type = payload.get("type", "")
    if payload_type == "message" and payload.get("role") == "assistant":
        text = content_text(payload.get("content"))
        if text.strip():
            output_chars += len(text)
            text_blocks_count += 1
        assistant_messages_count += 1
    elif payload_type == "function_call":
        tool_calls_count += 1
        name = payload.get("name") or payload.get("tool_name") or ""
        args = payload.get("arguments", payload.get("input", {}))
        if isinstance(args, str):
            args_json = args
        else:
            try:
                args_json = json.dumps(args, sort_keys=True)
            except (TypeError, ValueError):
                args_json = str(args)
        tool_input_chars += len(args_json)
        tool_call_signatures.append((str(name), args_json))
    elif payload_type == "function_call_output":
        raw_output = payload.get("output", "")
        if isinstance(raw_output, (dict, list)):
            result = json.dumps(raw_output, sort_keys=True)
        else:
            result = str(raw_output)
        tool_result_chars += len(result)
        if payload.get("is_error"):
            tool_errors_count += 1
        elif isinstance(raw_output, str) and raw_output.lower().startswith("error"):
            tool_errors_count += 1

repeated_tool_calls = len(tool_call_signatures) - len(set(tool_call_signatures))
started_at_ts = parse_ts(turn[0].get("created_at") or turn[0].get("timestamp"))
latency_ms = int(round((time.time() - started_at_ts) * 1000)) if started_at_ts is not None else None

delta = {
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

#!/usr/bin/env bash
# Parse a Codex JSONL transcript and format the last user turn for capture.
#
# Codex records the durable transcript as JSONL event records. The useful
# conversation payloads live under response_item.payload:
#   - payload.type == "message" with role user|assistant
#   - payload.type == "function_call"
#   - payload.type == "function_call_output"
#
# Usage: bash parse-transcript.sh <transcript_path>

set -euo pipefail

TRANSCRIPT_PATH="${1:-}"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  echo "ERROR: transcript not found: $TRANSCRIPT_PATH" >&2
  exit 1
fi

LINE_COUNT=$(wc -l < "$TRANSCRIPT_PATH" 2>/dev/null || echo "0")
if [ "$LINE_COUNT" -eq 0 ]; then
  echo "(empty transcript)"
  exit 0
fi

MAX_RESULT_CHARS="${MEMOIR_MAX_RESULT_CHARS:-1000}"

python3 - "$TRANSCRIPT_PATH" "$MAX_RESULT_CHARS" <<'PY'
import json
import sys

transcript_path = sys.argv[1]
max_result_chars = int(sys.argv[2])


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...(truncated)"


def payload_from(obj):
    if obj.get("type") == "response_item":
        payload = obj.get("payload")
        return payload if isinstance(payload, dict) else None
    # Some tests and future transcript variants may contain the payload directly.
    payload = obj.get("payload")
    if isinstance(payload, dict):
        return payload
    if obj.get("type") in {"message", "function_call", "function_call_output"}:
        return obj
    return None


def content_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, str):
            if item.strip():
                parts.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type in {"input_text", "output_text", "text"}:
            text = item.get("text", "")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts).strip()


def load_payloads(path):
    payloads = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            payload = payload_from(obj)
            if payload:
                payloads.append(payload)
    return payloads


def find_last_user_message(payloads):
    for idx in range(len(payloads) - 1, -1, -1):
        payload = payloads[idx]
        if payload.get("type") != "message" or payload.get("role") != "user":
            continue
        if content_text(payload.get("content")):
            return idx
    return None


def parse_arguments(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except Exception:
            return value
        return parsed
    return value


payloads = load_payloads(transcript_path)
if not payloads:
    print("(empty transcript)")
    raise SystemExit(0)

start_idx = find_last_user_message(payloads)
if start_idx is None:
    print("(no user message found)")
    raise SystemExit(0)

output = ["=== Transcript of a conversation between a human and Codex ==="]
for payload in payloads[start_idx:]:
    payload_type = payload.get("type")
    if payload_type == "message":
        role = payload.get("role")
        text = content_text(payload.get("content"))
        if not text:
            continue
        if role == "user":
            output.append(f"[Human]: {text}")
        elif role == "assistant":
            output.append(f"[Codex]: {text}")
    elif payload_type == "function_call":
        name = payload.get("name") or payload.get("tool_name") or "unknown"
        args = parse_arguments(payload.get("arguments", payload.get("input", {})))
        if isinstance(args, dict):
            parts = []
            for key, value in args.items():
                value_str = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
                if len(value_str) > 120:
                    value_str = value_str[:120] + "..."
                parts.append(f"{key}={value_str}")
            input_summary = ", ".join(parts)
        else:
            input_summary = str(args)
            if len(input_summary) > 400:
                input_summary = input_summary[:400] + "..."
        output.append(f"[Codex calls tool]: {name}({input_summary})")
    elif payload_type == "function_call_output":
        raw_output = payload.get("output", "")
        if isinstance(raw_output, (dict, list)):
            result = json.dumps(raw_output, sort_keys=True)
        else:
            result = str(raw_output)
        label = "[Tool error]" if payload.get("is_error") else "[Tool output]"
        output.append(f"{label}: {truncate(result, max_result_chars)}")

formatted = "\n".join(output)
if not formatted.strip():
    print("(empty turn)")
else:
    print(formatted)
PY

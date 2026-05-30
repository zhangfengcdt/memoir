#!/usr/bin/env bash
# Extract per-turn file-edit deltas from a Codex JSONL transcript.
#
# Emits a compact JSON object:
#   {"user_prompt": "...", "edits": [{"tool": "apply_patch", "file_path": "...", "snippet": "..."}]}
#
# Usage: bash collect-edits.sh <transcript_path>

set -euo pipefail

TRANSCRIPT_PATH="${1:-}"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

python3 - "$TRANSCRIPT_PATH" <<'PY'
import json
import re
import sys

transcript_path = sys.argv[1]
MAX_SNIPPET_CHARS = 300
MAX_PROMPT_CHARS = 2000

try:
    lines = open(transcript_path, encoding="utf-8").readlines()
except OSError:
    raise SystemExit(0)

if not lines:
    raise SystemExit(0)


def truncate(text: str, limit: int = MAX_SNIPPET_CHARS) -> str:
    if not isinstance(text, str):
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


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
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for item in content:
        if isinstance(item, str):
            if item.strip():
                parts.append(item.strip())
        elif isinstance(item, dict) and item.get("type") in {"input_text", "output_text", "text"}:
            text = item.get("text", "")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts).strip()


def parse_arguments(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def patch_text_from_args(args) -> str:
    if isinstance(args, str):
        return args
    if not isinstance(args, dict):
        return ""
    for key in ("cmd", "command", "patch", "input"):
        value = args.get(key)
        if isinstance(value, str) and ("*** Begin Patch" in value or "*** Update File:" in value or "*** Add File:" in value):
            return value
    return ""


def entries_from_patch(patch):
    entries = []
    if not patch:
        return entries

    current_file = ""
    current_lines = []

    def flush() -> None:
        nonlocal current_file, current_lines
        if current_file:
            snippet = "\n".join(current_lines).strip()
            entries.append({
                "tool": "apply_patch",
                "file_path": current_file,
                "snippet": truncate(snippet),
            })
        current_file = ""
        current_lines = []

    for line in patch.splitlines():
        match = re.match(r"\*\*\* (?:Add|Update|Delete) File: (.+)$", line)
        if match:
            flush()
            current_file = match.group(1).strip()
            current_lines = [line]
            continue
        move_match = re.match(r"\*\*\* Move to: (.+)$", line)
        if move_match and current_file:
            current_lines.append(line)
            continue
        if current_file and (line.startswith("+") or line.startswith("-") or line.startswith("@@")):
            current_lines.append(line)
    flush()
    return entries


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
    if payload.get("type") == "message" and payload.get("role") == "user" and content_text(payload.get("content")):
        start_idx = idx
        break

if start_idx is None:
    raise SystemExit(0)

turn = payloads[start_idx:]
user_prompt = truncate(content_text(turn[0].get("content")), MAX_PROMPT_CHARS) if turn else ""
entries = []

for payload in turn:
    if payload.get("type") != "function_call":
        continue
    name = str(payload.get("name") or payload.get("tool_name") or "")
    args = parse_arguments(payload.get("arguments", payload.get("input", {})))

    if name in {"apply_patch", "Edit", "Write"}:
        if name == "apply_patch":
            entries.extend(entries_from_patch(patch_text_from_args(args)))
        elif isinstance(args, dict):
            file_path = args.get("file_path") or args.get("path")
            snippet = args.get("new_string") or args.get("content") or ""
            if file_path:
                entries.append({"tool": name, "file_path": str(file_path), "snippet": truncate(str(snippet))})
    elif name == "MultiEdit" and isinstance(args, dict):
        file_path = args.get("file_path") or args.get("path")
        edits = args.get("edits") or []
        if file_path and isinstance(edits, list):
            for edit in edits:
                if isinstance(edit, dict):
                    entries.append({
                        "tool": name,
                        "file_path": str(file_path),
                        "snippet": truncate(str(edit.get("new_string") or "")),
                    })
    elif name == "NotebookEdit" and isinstance(args, dict):
        file_path = args.get("notebook_path") or args.get("file_path")
        snippet = args.get("new_source") or ""
        if file_path:
            entries.append({"tool": name, "file_path": str(file_path), "snippet": truncate(str(snippet))})

if not entries:
    raise SystemExit(0)

# Extract unique file paths and estimate change size.
file_paths = sorted(set(e["file_path"] for e in entries if e.get("file_path")))
change_size = sum(len(e.get("snippet", "")) for e in entries)

print(json.dumps({
    "user_prompt": user_prompt or None,
    "edits": entries,
    "file_paths": file_paths,
    "change_size": change_size,
}))
PY

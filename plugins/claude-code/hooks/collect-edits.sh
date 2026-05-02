#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Extract per-turn file-edit deltas from a Claude Code JSONL transcript.
#
# Mirrors the last-turn anchor logic of collect-metrics.sh / parse-transcript.sh.
# Walks the most recent turn's tool_use blocks for the four file-mutating tools
# (Edit, Write, MultiEdit, NotebookEdit) and emits a compact JSON array on
# stdout, one entry per edit. Emits nothing (empty stdout, exit 0) when the
# turn made no file changes — caller uses that as the trigger gate.
#
# Output shape (one entry per tool_use block; MultiEdit is one entry per `edits[]` row):
#   [
#     {"tool": "Edit",     "file_path": "src/foo.py",            "snippet": "...300 chars..."},
#     {"tool": "Write",    "file_path": "src/bar.md",            "snippet": "..."},
#     {"tool": "MultiEdit","file_path": "src/baz.py",            "snippet": "..."},
#     {"tool": "NotebookEdit","file_path": "notebooks/x.ipynb",  "snippet": "..."}
#   ]
#
# Snippet is the most informative excerpt available: Edit's `new_string`,
# Write's `content`, MultiEdit's per-row `new_string`, NotebookEdit's
# `new_source`. Truncated to MAX_SNIPPET_CHARS to keep haiku context cheap.
#
# Usage: bash collect-edits.sh <transcript_path>

set -euo pipefail

TRANSCRIPT_PATH="${1:-}"

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
  exit 0
fi

python3 - "$TRANSCRIPT_PATH" <<'PY'
import json, sys

transcript_path = sys.argv[1]
MAX_SNIPPET_CHARS = 300

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


def truncate(text):
    if not isinstance(text, str):
        return ""
    if len(text) <= MAX_SNIPPET_CHARS:
        return text
    return text[:MAX_SNIPPET_CHARS] + "…"


start_idx = find_last_turn_start(lines)
if start_idx is None:
    sys.exit(0)

turn = []
for raw in lines[start_idx:]:
    try:
        turn.append(json.loads(raw))
    except Exception:
        continue

entries = []

for obj in turn:
    if obj.get("type") != "assistant":
        continue
    content = obj.get("message", {}).get("content", [])
    if not isinstance(content, list):
        continue
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        name = block.get("name", "")
        inp = block.get("input", {}) or {}
        if not isinstance(inp, dict):
            continue

        if name == "Edit":
            fp = inp.get("file_path", "")
            snippet = truncate(inp.get("new_string", ""))
            if fp:
                entries.append({"tool": "Edit", "file_path": fp, "snippet": snippet})
        elif name == "Write":
            fp = inp.get("file_path", "")
            snippet = truncate(inp.get("content", ""))
            if fp:
                entries.append({"tool": "Write", "file_path": fp, "snippet": snippet})
        elif name == "MultiEdit":
            fp = inp.get("file_path", "")
            edits = inp.get("edits", []) or []
            if not fp or not isinstance(edits, list):
                continue
            # One entry per inner edit so haiku sees each substitution.
            for e in edits:
                if not isinstance(e, dict):
                    continue
                snippet = truncate(e.get("new_string", ""))
                entries.append({"tool": "MultiEdit", "file_path": fp, "snippet": snippet})
        elif name == "NotebookEdit":
            fp = inp.get("notebook_path", "")
            snippet = truncate(inp.get("new_source", ""))
            if fp:
                entries.append({"tool": "NotebookEdit", "file_path": fp, "snippet": snippet})

if not entries:
    sys.exit(0)

print(json.dumps(entries))
PY

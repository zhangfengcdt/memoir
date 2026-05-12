"""Codex JSONL transcript parser tests."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
PARSE = HOOKS / "parse-transcript.sh"
COLLECT_EDITS = HOOKS / "collect-edits.sh"


def _response_item(payload: dict) -> dict:
    return {"type": "response_item", "payload": payload}


def _write_transcript(records: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="codex-transcript-test-")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


def _run(script: Path, transcript_path: str) -> str:
    proc = subprocess.run(
        ["bash", str(script), transcript_path],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip()


def test_parse_transcript_formats_last_codex_turn() -> None:
    path = _write_transcript(
        [
            _response_item(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "first turn"}],
                }
            ),
            _response_item(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "old reply"}],
                }
            ),
            _response_item(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "update the docs"}],
                }
            ),
            _response_item(
                {
                    "type": "function_call",
                    "name": "apply_patch",
                    "arguments": {"cmd": "*** Begin Patch\n*** Update File: docs/codex.md\n+hello\n*** End Patch"},
                }
            ),
            _response_item(
                {
                    "type": "function_call_output",
                    "call_id": "c1",
                    "output": "Success. Updated files.",
                }
            ),
            _response_item(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Done."}],
                }
            ),
        ]
    )
    try:
        out = _run(PARSE, path)
        assert "[Human]: update the docs" in out
        assert "[Codex calls tool]: apply_patch(" in out
        assert "[Tool output]: Success. Updated files." in out
        assert "[Codex]: Done." in out
        assert "first turn" not in out
    finally:
        os.unlink(path)


def test_collect_edits_detects_apply_patch_files() -> None:
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: docs/codex.md",
            "@@",
            "-old",
            "+new",
            "*** Add File: plugins/codex/README.md",
            "+# Memoir Plugin for Codex",
            "*** End Patch",
        ]
    )
    path = _write_transcript(
        [
            _response_item(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "port docs"}],
                }
            ),
            _response_item(
                {
                    "type": "function_call",
                    "name": "apply_patch",
                    "arguments": json.dumps({"cmd": patch}),
                }
            ),
        ]
    )
    try:
        out = _run(COLLECT_EDITS, path)
        payload = json.loads(out)
        assert payload["user_prompt"] == "port docs"
        assert [entry["file_path"] for entry in payload["edits"]] == [
            "docs/codex.md",
            "plugins/codex/README.md",
        ]
        assert all(entry["tool"] == "apply_patch" for entry in payload["edits"])
    finally:
        os.unlink(path)


def test_collect_edits_empty_for_non_edit_turn() -> None:
    path = _write_transcript(
        [
            _response_item(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "list files"}],
                }
            ),
            _response_item(
                {"type": "function_call", "name": "exec_command", "arguments": {"cmd": "ls"}}
            ),
        ]
    )
    try:
        assert _run(COLLECT_EDITS, path) == ""
    finally:
        os.unlink(path)

"""Unit tests for Codex transcript metrics and merge helpers."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
COLLECT = HOOKS / "collect-metrics.sh"
MERGE = HOOKS / "merge-metrics.py"


def _write_transcript(records: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="codex-metrics-test-")
    os.close(fd)
    with open(path, "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")
    return path


def _response_item(payload: dict) -> dict:
    return {"type": "response_item", "payload": payload}


def _run_collect(transcript_path: str) -> dict:
    proc = subprocess.run(
        ["bash", str(COLLECT), transcript_path],
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def _run_merge(prev: str, delta: str) -> dict:
    proc = subprocess.run(
        ["python3", str(MERGE), prev, delta],
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def test_empty_turn_yields_no_output() -> None:
    path = _write_transcript([{"type": "session_meta", "id": "s"}])
    try:
        proc = subprocess.run(["bash", str(COLLECT), path], capture_output=True, text=True)
        assert proc.stdout.strip() == ""
    finally:
        os.unlink(path)


def test_missing_transcript_yields_no_output() -> None:
    proc = subprocess.run(
        ["bash", str(COLLECT), "/tmp/does-not-exist-xyz"],
        capture_output=True,
        text=True,
    )
    assert proc.stdout.strip() == ""


def test_single_turn_basic_counters() -> None:
    path = _write_transcript(
        [
            _response_item(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                    "created_at": "2026-04-26T08:00:00Z",
                }
            ),
            _response_item(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hi there"}],
                }
            ),
        ]
    )
    try:
        delta = _run_collect(path)
        assert delta["output_chars"] == 8
        assert delta["tool_calls_count"] == 0
        assert delta["tool_errors_count"] == 0
        assert delta["assistant_messages_count"] == 1
        assert delta["text_blocks_count"] == 1
        assert delta["latency_ms"] is not None and delta["latency_ms"] >= 1000
    finally:
        os.unlink(path)


def test_tool_calls_and_errors_counted() -> None:
    path = _write_transcript(
        [
            _response_item(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "go"}],
                }
            ),
            _response_item(
                {"type": "function_call", "name": "exec_command", "arguments": {"cmd": "ls"}}
            ),
            _response_item(
                {"type": "function_call", "name": "exec_command", "arguments": {"cmd": "ls"}}
            ),
            _response_item(
                {"type": "function_call_output", "call_id": "1", "output": "ok"}
            ),
            _response_item(
                {
                    "type": "function_call_output",
                    "call_id": "2",
                    "output": "boom",
                    "is_error": True,
                }
            ),
        ]
    )
    try:
        delta = _run_collect(path)
        assert delta["tool_calls_count"] == 2
        assert delta["tool_errors_count"] == 1
        assert delta["repeated_tool_calls"] == 1
        assert delta["tool_result_chars"] == len("ok") + len("boom")
    finally:
        os.unlink(path)


def test_only_last_turn_is_counted() -> None:
    path = _write_transcript(
        [
            _response_item(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "first"}],
                }
            ),
            _response_item(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "first reply"}],
                }
            ),
            _response_item(
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "second"}],
                }
            ),
            _response_item(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "ok"}],
                }
            ),
        ]
    )
    try:
        delta = _run_collect(path)
        assert delta["output_chars"] == 2
        assert delta["assistant_messages_count"] == 1
    finally:
        os.unlink(path)


def test_merger_initializes_from_empty_prev() -> None:
    delta = json.dumps(
        {
            "output_chars": 100,
            "tool_calls_count": 2,
            "latency_ms": 1500,
        }
    )
    merged = _run_merge("", delta)
    assert merged["schema_version"] == 1
    assert merged["turns_count"] == 1
    assert merged["total_output_chars"] == 100
    assert merged["total_tool_calls"] == 2
    assert merged["total_latency_ms"] == 1500
    assert merged["latency_samples"] == 1
    assert merged["tokens"] is None
    assert merged["llms"] is None
    assert "first_turn_at" not in merged
    assert "last_turn_at" not in merged
    assert "branch" not in merged


def test_merger_accumulates() -> None:
    prev = json.dumps(
        {
            "schema_version": 1,
            "turns_count": 1,
            "total_output_chars": 100,
            "total_tool_calls": 2,
            "total_latency_ms": 1500,
            "latency_samples": 1,
        }
    )
    delta = json.dumps(
        {
            "output_chars": 50,
            "tool_calls_count": 1,
            "tool_errors_count": 1,
            "latency_ms": 800,
        }
    )
    merged = _run_merge(prev, delta)
    assert merged["turns_count"] == 2
    assert merged["total_output_chars"] == 150
    assert merged["total_tool_calls"] == 3
    assert merged["total_tool_errors"] == 1
    assert merged["total_latency_ms"] == 2300
    assert merged["latency_samples"] == 2


def test_merger_handles_garbage_prev_gracefully() -> None:
    merged = _run_merge("not json", json.dumps({"output_chars": 1}))
    assert merged["turns_count"] == 1
    assert merged["total_output_chars"] == 1

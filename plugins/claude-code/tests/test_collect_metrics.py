"""Unit tests for collect-metrics.sh and merge-metrics.py.

Run from the repo root:
    pytest plugins/claude-code/tests/test_collect_metrics.py -v

These tests do not depend on a memoir store or pytest fixtures from the main
suite. They shell out to the parser and merger scripts directly.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
COLLECT = HOOKS / "collect-metrics.sh"
MERGE = HOOKS / "merge-metrics.py"


def _write_transcript(turns: list[dict]) -> str:
    fd, path = tempfile.mkstemp(suffix=".jsonl", prefix="metrics-test-")
    os.close(fd)
    with open(path, "w") as f:
        for t in turns:
            f.write(json.dumps(t) + "\n")
    return path


def _run_collect(transcript_path: str) -> dict:
    proc = subprocess.run(
        ["bash", str(COLLECT), transcript_path],
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def _run_merge(prev: str, delta: str, branch: str = "test") -> dict:
    env = {**os.environ, "MEMOIR_BRANCH": branch}
    proc = subprocess.run(
        ["python3", str(MERGE), prev, delta],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def test_empty_turn_yields_no_output() -> None:
    """Transcript with no real user message produces empty stdout."""
    path = _write_transcript([
        {"type": "user", "isMeta": True, "message": {"content": "<meta>"}},
    ])
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
    path = _write_transcript([
        {
            "type": "user",
            "isMeta": False,
            "message": {"content": "hello"},
            "timestamp": "2026-04-26T08:00:00Z",
        },
        {
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "hi there"}]},
            "timestamp": "2026-04-26T08:00:01Z",
        },
    ])
    try:
        d = _run_collect(path)
        assert d["output_chars"] == 8
        assert d["tool_calls_count"] == 0
        assert d["tool_errors_count"] == 0
        assert d["assistant_messages_count"] == 1
        assert d["text_blocks_count"] == 1
        assert d["turn_started_at"] == "2026-04-26T08:00:00Z"
        assert d["latency_ms"] is not None and d["latency_ms"] >= 1000
    finally:
        os.unlink(path)


def test_tool_calls_and_errors_counted() -> None:
    path = _write_transcript([
        {"type": "user", "isMeta": False, "message": {"content": "go"}},
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}},
                    {"type": "tool_use", "name": "Bash", "input": {"cmd": "ls"}},
                    {"type": "tool_use", "name": "Read", "input": {"path": "/x"}},
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "content": "ok", "is_error": False},
                    {"type": "tool_result", "content": "boom", "is_error": True},
                ]
            },
        },
    ])
    try:
        d = _run_collect(path)
        assert d["tool_calls_count"] == 3
        assert d["tool_errors_count"] == 1
        assert d["repeated_tool_calls"] == 1
        assert d["tool_result_chars"] == len("ok") + len("boom")
    finally:
        os.unlink(path)


def test_missing_timestamp_yields_null_latency() -> None:
    path = _write_transcript([
        {"type": "user", "isMeta": False, "message": {"content": "ask"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "ok"}]}},
    ])
    try:
        d = _run_collect(path)
        assert d["turn_started_at"] is None
        assert d["latency_ms"] is None
    finally:
        os.unlink(path)


def test_isMeta_user_is_skipped_for_anchor() -> None:
    """The last-turn anchor must skip isMeta user messages."""
    path = _write_transcript([
        {
            "type": "user",
            "isMeta": False,
            "message": {"content": "real"},
            "timestamp": "2026-04-26T08:00:00Z",
        },
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "first reply"}]}},
        {"type": "user", "isMeta": True, "message": {"content": "<system-reminder>"}},
    ])
    try:
        d = _run_collect(path)
        assert d["turn_started_at"] == "2026-04-26T08:00:00Z"
        assert d["text_blocks_count"] == 1
    finally:
        os.unlink(path)


def test_merger_initializes_from_empty_prev() -> None:
    delta = json.dumps({
        "output_chars": 100,
        "tool_calls_count": 2,
        "latency_ms": 1500,
        "turn_started_at": "2026-04-26T08:00:00Z",
        "turn_ended_at": "2026-04-26T08:00:01Z",
    })
    merged = _run_merge("", delta, branch="main")
    assert merged["schema_version"] == 1
    assert merged["branch"] == "main"
    assert merged["turns_count"] == 1
    assert merged["total_output_chars"] == 100
    assert merged["total_tool_calls"] == 2
    assert merged["total_latency_ms"] == 1500
    assert merged["latency_samples"] == 1
    assert merged["first_turn_at"] == "2026-04-26T08:00:00Z"
    assert merged["tokens"] is None
    assert merged["model"] is None


def test_merger_accumulates() -> None:
    prev = json.dumps({
        "schema_version": 1,
        "branch": "main",
        "turns_count": 1,
        "total_output_chars": 100,
        "total_tool_calls": 2,
        "total_latency_ms": 1500,
        "latency_samples": 1,
        "first_turn_at": "2026-04-26T08:00:00Z",
        "last_turn_at": "2026-04-26T08:00:01Z",
    })
    delta = json.dumps({
        "output_chars": 50,
        "tool_calls_count": 1,
        "tool_errors_count": 1,
        "latency_ms": 800,
        "turn_started_at": "2026-04-26T08:01:00Z",
        "turn_ended_at": "2026-04-26T08:01:01Z",
    })
    merged = _run_merge(prev, delta, branch="main")
    assert merged["turns_count"] == 2
    assert merged["total_output_chars"] == 150
    assert merged["total_tool_calls"] == 3
    assert merged["total_tool_errors"] == 1
    assert merged["total_latency_ms"] == 2300
    assert merged["latency_samples"] == 2
    # first_turn_at preserved, last_turn_at updated
    assert merged["first_turn_at"] == "2026-04-26T08:00:00Z"
    assert merged["last_turn_at"] == "2026-04-26T08:01:01Z"


def test_merger_skips_latency_when_null() -> None:
    prev = json.dumps({
        "schema_version": 1,
        "branch": "main",
        "turns_count": 1,
        "total_latency_ms": 1000,
        "latency_samples": 1,
    })
    delta = json.dumps({"output_chars": 5, "latency_ms": None, "turn_ended_at": "2026-04-26T08:02Z"})
    merged = _run_merge(prev, delta, branch="main")
    assert merged["total_latency_ms"] == 1000
    assert merged["latency_samples"] == 1
    assert merged["turns_count"] == 2


def test_merger_handles_garbage_prev_gracefully() -> None:
    merged = _run_merge("not json", json.dumps({"output_chars": 1}), branch="x")
    assert merged["turns_count"] == 1
    assert merged["branch"] == "x"

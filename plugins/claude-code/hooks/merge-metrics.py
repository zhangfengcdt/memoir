#!/usr/bin/env python3
"""Merge a per-turn delta into a per-branch metrics accumulator.

Usage: merge-metrics.py <prev_json> <delta_json>

Reads `MEMOIR_BRANCH` from env to populate the `branch` field on first write.
Emits the merged accumulator JSON on stdout. Exits 0 with empty output if
inputs are unparseable — the Stop hook is fail-silent.
"""
from __future__ import annotations

import json
import os
import sys

SCHEMA_VERSION = 1

COUNTER_FIELDS = (
    "turns_count",
    "total_output_chars",
    "total_tool_input_chars",
    "total_tool_result_chars",
    "total_tool_calls",
    "total_tool_errors",
    "total_repeated_tool_calls",
    "total_latency_ms",
    "latency_samples",
)


def _empty_accumulator(branch: str) -> dict:
    acc = {
        "schema_version": SCHEMA_VERSION,
        "branch": branch,
        "first_turn_at": None,
        "last_turn_at": None,
        "tokens": None,
        "model": None,
    }
    for field in COUNTER_FIELDS:
        acc[field] = 0
    return acc


def _coerce_prev(raw: str, branch: str) -> dict:
    if not raw:
        return _empty_accumulator(branch)
    try:
        prev = json.loads(raw)
    except (TypeError, ValueError):
        return _empty_accumulator(branch)
    if not isinstance(prev, dict) or not prev:
        return _empty_accumulator(branch)
    base = _empty_accumulator(branch)
    for k, v in prev.items():
        base[k] = v
    return base


def _merge(prev: dict, delta: dict) -> dict:
    out = dict(prev)
    out["turns_count"] = int(prev.get("turns_count", 0)) + 1
    out["total_output_chars"] = int(prev.get("total_output_chars", 0)) + int(delta.get("output_chars", 0) or 0)
    out["total_tool_input_chars"] = int(prev.get("total_tool_input_chars", 0)) + int(delta.get("tool_input_chars", 0) or 0)
    out["total_tool_result_chars"] = int(prev.get("total_tool_result_chars", 0)) + int(delta.get("tool_result_chars", 0) or 0)
    out["total_tool_calls"] = int(prev.get("total_tool_calls", 0)) + int(delta.get("tool_calls_count", 0) or 0)
    out["total_tool_errors"] = int(prev.get("total_tool_errors", 0)) + int(delta.get("tool_errors_count", 0) or 0)
    out["total_repeated_tool_calls"] = int(prev.get("total_repeated_tool_calls", 0)) + int(delta.get("repeated_tool_calls", 0) or 0)

    latency = delta.get("latency_ms")
    if isinstance(latency, (int, float)):
        out["total_latency_ms"] = int(prev.get("total_latency_ms", 0)) + int(latency)
        out["latency_samples"] = int(prev.get("latency_samples", 0)) + 1

    started = delta.get("turn_started_at")
    ended = delta.get("turn_ended_at")
    if not out.get("first_turn_at"):
        out["first_turn_at"] = started or ended
    if ended:
        out["last_turn_at"] = ended

    return out


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0
    branch = os.environ.get("MEMOIR_BRANCH", "unknown")
    try:
        prev = _coerce_prev(argv[1], branch)
        delta = json.loads(argv[2]) if argv[2] else {}
    except (TypeError, ValueError):
        return 0
    if not isinstance(delta, dict):
        return 0
    merged = _merge(prev, delta)
    sys.stdout.write(json.dumps(merged))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

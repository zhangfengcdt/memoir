"""Recall A/B-mode runner: measure whether the model invokes the
``memoir:memory-recall`` skill across three configurations of system prompt
+ hook injection.

Used to answer the architectural question: **is the recall-trigger hook
earning its tokens, or can the model decide to recall on its own from the
skill's own description?**

Three arms per prompt:
  with_hook   — system prompt has the skill description AND the hook's
                additionalContext block is prepended (current production)
  prose_only  — system prompt has the skill description but NO hook block
  bare        — system prompt has neither (sanity baseline)

Per prompt, we look at the model's tool_use stream for a call to
``Skill`` with ``skill == "memoir:memory-recall"``. The runner is intended
to be invoked on demand (not on every commit) — full corpus is ~3 minutes
and costs LLM tokens.

NOTE: The stream-json event parser here is best-effort against
``claude -p --output-format stream-json``. Run one smoke case manually
before trusting the labeled-corpus output, and pin any schema drift
in this file's docstring + tests.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Read the canonical SKILL description directly from the plugin's
# memory-recall SKILL.md so the harness can never drift from production.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
SKILL_MD = PLUGIN_ROOT / "skills" / "memory-recall" / "SKILL.md"

# The hook's additionalContext block, kept in sync with user-prompt-submit.sh.
RECALL_HOOK_BLOCK = """\
# memoir — recall before acting

The user's prompt describes work to do (implementation, design, refactor, or similar). Before starting, invoke the `memoir:memory-recall` skill to fetch any prior preferences, architectural decisions, coding conventions, or constraints that should shape the approach.

Silently executing without checking past context is a common failure mode: captured preferences (e.g. "rebase not merge", "TypeScript not JavaScript", "two-approver PR policy") only help if they're actually consulted. One recall call up front is cheap (~500-800ms) and typically answers whether any stored facts are relevant.

If recall returns nothing useful, proceed normally. If it returns relevant facts, incorporate them into your plan and mention the ones you applied."""


Arm = Literal["with_hook", "prose_only", "bare"]


@dataclass
class RecallObservation:
    """Outcome of one (prompt, arm) pair."""

    prompt: str
    arm: Arm
    skill_invoked: bool  # did the model call memoir:memory-recall?
    tool_calls: list[dict]  # full tool_use events captured for debug
    raw_events_path: str | None  # path to the events.jsonl artifact
    duration_s: float
    error: str | None = None


def _read_skill_description() -> str:
    """Extract the description front-matter or first paragraph of SKILL.md.

    Used as the "prose_only" / "with_hook" arms' indication that
    memoir:memory-recall exists. Truncated for prompt budget; the real
    SKILL body is loaded by Claude Code at skill-invocation time anyway.
    """
    if not SKILL_MD.is_file():
        return "(memory-recall SKILL.md not found — this run is degenerate)"
    text = SKILL_MD.read_text()
    # Front matter is YAML between leading --- markers; description= line is
    # what we care about. Fall back to the first non-frontmatter paragraph.
    lines = text.splitlines()
    in_fm = False
    desc = None
    for ln in lines:
        s = ln.strip()
        if s == "---":
            in_fm = not in_fm
            continue
        if in_fm and s.lower().startswith("description:"):
            desc = s.split(":", 1)[1].strip().strip('"').strip("'")
            break
    if desc:
        return f"Available skill: memoir:memory-recall — {desc}"
    return "Available skill: memoir:memory-recall — recall facts from prior sessions."


def _system_prompt_for(arm: Arm) -> str:
    """Compose the system prompt sent to claude -p for one arm."""
    skill_line = _read_skill_description()
    if arm == "bare":
        return "You are a coding assistant."
    if arm == "prose_only":
        return f"You are a coding assistant. {skill_line}"
    if arm == "with_hook":
        return f"You are a coding assistant. {skill_line}\n\n{RECALL_HOOK_BLOCK}"
    raise ValueError(f"unknown arm: {arm!r}")


def _parse_skill_call(events: list[dict]) -> tuple[bool, list[dict]]:
    """Walk a list of stream-json events and detect Skill→memory-recall calls.

    The stream-json schema (as of this writing): each event has a "type"
    discriminator. Tool-use events surface as either:
      {"type": "tool_use", "name": "Skill", "input": {"skill": "...", ...}}
    or nested inside an assistant message's content array as
      {"type": "tool_use", "name": "...", "input": {...}}

    This parser handles both shapes — defensively scans every event and
    every nested content array for tool_use entries, then filters on
    name == "Skill" with input.skill matching memoir:memory-recall (or
    legacy "memoir-recall" name).
    """
    tool_calls: list[dict] = []

    def _harvest(node):
        if isinstance(node, dict):
            if node.get("type") == "tool_use" and "name" in node:
                tool_calls.append(node)
            for v in node.values():
                _harvest(v)
        elif isinstance(node, list):
            for v in node:
                _harvest(v)

    for ev in events:
        _harvest(ev)

    invoked = False
    for tc in tool_calls:
        if tc.get("name") != "Skill":
            continue
        inp = tc.get("input") or {}
        skill = inp.get("skill") if isinstance(inp, dict) else None
        if isinstance(skill, str) and "memory-recall" in skill:
            invoked = True
            break
    return invoked, tool_calls


def run_recall_ab_case(
    prompt: str,
    arm: Arm,
    model: str,
    artifact_dir: Path,
    timeout_s: float = 120.0,
) -> RecallObservation:
    """Run one (prompt, arm) pair against ``claude -p`` and observe whether
    the model invoked memoir:memory-recall.

    Persists the raw stream-json events to ``artifact_dir/events.jsonl``
    and the parsed tool-call list to ``artifact_dir/tool_calls.json``.
    """
    import datetime as dt
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if not shutil.which("claude"):
        return RecallObservation(
            prompt=prompt, arm=arm, skill_invoked=False,
            tool_calls=[], raw_events_path=None, duration_s=0.0,
            error="`claude` CLI not on PATH",
        )

    system_prompt = _system_prompt_for(arm)
    (artifact_dir / "system.txt").write_text(system_prompt)
    (artifact_dir / "input.txt").write_text(prompt)

    # Stream-json output, allow Skill tool so the model CAN invoke it.
    cmd = [
        "claude", "-p",
        "--model", model,
        "--no-session-persistence",
        "--no-chrome",
        "--output-format", "stream-json",
        "--input-format", "text",
        "--allowed-tools", "Skill",
        "--system-prompt", system_prompt,
    ]
    env = {**os.environ, "MEMOIR_NO_CAPTURE": "1", "CLAUDECODE": ""}

    start = dt.datetime.now()
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return RecallObservation(
            prompt=prompt, arm=arm, skill_invoked=False,
            tool_calls=[], raw_events_path=None,
            duration_s=(dt.datetime.now() - start).total_seconds(),
            error=f"claude -p timed out after {timeout_s}s",
        )
    duration_s = (dt.datetime.now() - start).total_seconds()

    raw_path = artifact_dir / "events.jsonl"
    raw_path.write_text(proc.stdout or "")

    events: list[dict] = []
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # tolerate non-json chatter lines

    invoked, tool_calls = _parse_skill_call(events)
    (artifact_dir / "tool_calls.json").write_text(
        json.dumps(tool_calls, indent=2)
    )

    return RecallObservation(
        prompt=prompt, arm=arm, skill_invoked=invoked,
        tool_calls=tool_calls, raw_events_path=str(raw_path),
        duration_s=duration_s,
        error=None if proc.returncode == 0 else f"claude exit code {proc.returncode}",
    )


def summarize_arms(observations: list[RecallObservation], labels: dict[str, bool]) -> dict:
    """Tally TP/FP/F1 per arm given ground-truth labels.

    ``labels`` maps prompt → should_fire. Returns a nested dict suitable
    for both summary.md rendering and machine consumption.
    """
    arms = sorted({obs.arm for obs in observations})
    out: dict = {"arms": {}}
    for arm in arms:
        tp = fp = fn = tn = 0
        for obs in observations:
            if obs.arm != arm:
                continue
            should = labels.get(obs.prompt)
            if should is None:
                continue
            if should and obs.skill_invoked:
                tp += 1
            elif should and not obs.skill_invoked:
                fn += 1
            elif (not should) and obs.skill_invoked:
                fp += 1
            else:
                tn += 1
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0.0
        )
        out["arms"][arm] = {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        }
    return out

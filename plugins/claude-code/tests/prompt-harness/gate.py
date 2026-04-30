"""Gate-mode runner: invoke a hook script with synthetic JSON stdin and
parse its JSON stdout.

Used to test deterministic shell-level decisions in the plugin's hooks
(today: ``user-prompt-submit.sh``'s recall-trigger gate). No LLM calls,
no network, no real memoir CLI mutations — runs in ~50 ms per case.

Usage from runner.py::

    from gate import run_gate, GateResult, gate_store_for
    res = run_gate(
        hook_script=PLUGIN_ROOT / "hooks" / "user-prompt-submit.sh",
        prompt="Please refactor the auth middleware.",
        env={"USER_MEMORIES": "5", "MEMOIR_CMD": "memoir"},
        store_dir=gate_store_for(case_label),
    )
    # res.recall_block_emitted, res.system_message, res.additional_context, ...

The hook reads its input from stdin as a JSON string (production: Claude
Code passes ``{"prompt": "...", ...}``). It reads ``USER_MEMORIES`` from
``<store>/.git/plugin-statusline-cache``. Both are simulated here.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Deterministic per-case stores live under here so each case starts from a
# clean slate (no leakage from a prior case's auto-match write).
GATE_STORE_ROOT = Path("/tmp/memoir-prompt-tests/_gate-store")


@dataclass
class GateResult:
    """Structured view of one hook invocation.

    ``raw_stdout``/``raw_stderr`` are kept so artifact dumps can show
    exactly what the hook printed when an assertion fails.
    """

    exit_code: int
    raw_stdout: str
    raw_stderr: str
    parsed_ok: bool  # True when stdout was valid JSON
    parse_error: str | None = None
    # Convenience accessors derived from the parsed JSON (None when missing).
    system_message: str | None = None
    additional_context: str | None = None
    hook_event_name: str | None = None
    # Derived booleans for the most common assertion shapes.
    recall_block_emitted: bool = False
    fields: dict = field(default_factory=dict)  # full parsed payload


def gate_store_for(case_label: str) -> Path:
    """Return a per-case store dir under ``GATE_STORE_ROOT``.

    The label is hashed so any string (incl. paths with slashes) is a safe
    directory name. The store is recreated fresh on each call so leftover
    state from prior runs can't influence the result.
    """
    digest = hashlib.sha1(case_label.encode("utf-8")).hexdigest()[:12]
    p = GATE_STORE_ROOT / digest
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
    (p / ".git").mkdir(parents=True, exist_ok=True)
    return p


def run_gate(
    hook_script: Path,
    prompt: str,
    env: dict[str, str] | None = None,
    store_dir: Path | None = None,
    timeout_s: float = 10.0,
) -> GateResult:
    """Invoke a hook script with ``{"prompt": prompt}`` on stdin.

    ``env`` overrides on top of the inherited environment. The harness
    always sets ``MEMOIR_NO_CAPTURE=1`` so a Stop-hook test wouldn't
    accidentally fire auto-capture against the temp store.

    ``store_dir`` is used for two things:
      * Exported as ``MEMOIR_STORE`` so ``common.sh`` resolves to it.
      * The harness writes ``USER_MEMORIES`` (when supplied via env) into
        ``<store>/.git/plugin-statusline-cache`` so the hook reads the
        intended value through its real cache-file code path.
    """
    if not hook_script.is_file():
        return GateResult(
            exit_code=-1,
            raw_stdout="",
            raw_stderr=f"hook script not found: {hook_script}",
            parsed_ok=False,
            parse_error="hook script missing",
        )

    e = dict(os.environ)
    e["MEMOIR_NO_CAPTURE"] = "1"
    if store_dir is not None:
        e["MEMOIR_STORE"] = str(store_dir)

    # USER_MEMORIES isn't a regular env var — the hook reads it from the
    # statusline cache file. If the case asked for a count, materialize it
    # there so the hook's real read path exercises.
    if env and "USER_MEMORIES" in env and store_dir is not None:
        cache = store_dir / ".git" / "plugin-statusline-cache"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(str(env["USER_MEMORIES"]) + "\n")

    if env:
        for k, v in env.items():
            # USER_MEMORIES already handled above — don't pollute the env
            # with it (production reads from the cache, not env).
            if k == "USER_MEMORIES":
                continue
            e[k] = v

    stdin_payload = json.dumps({"prompt": prompt})

    try:
        proc = subprocess.run(
            ["bash", str(hook_script)],
            input=stdin_payload,
            capture_output=True,
            text=True,
            env=e,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as ex:
        return GateResult(
            exit_code=-1,
            raw_stdout=ex.stdout.decode("utf-8", "replace") if ex.stdout else "",
            raw_stderr=(ex.stderr.decode("utf-8", "replace") if ex.stderr else "")
            + f"\n[harness] hook timed out after {timeout_s}s",
            parsed_ok=False,
            parse_error="timeout",
        )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    rc = proc.returncode

    # Parse the JSON. The hook always emits a single-line JSON object on
    # the last non-empty stdout line (debug output may precede it via stderr,
    # but stdout should be machine-parseable).
    parsed: dict | None = None
    parse_error: str | None = None
    candidate = stdout.strip()
    if candidate:
        try:
            parsed = json.loads(candidate)
            if not isinstance(parsed, dict):
                parsed = None
                parse_error = f"top-level JSON is {type(parsed).__name__}, not object"
        except json.JSONDecodeError as ex:
            parse_error = f"json decode failed: {ex.msg} (line {ex.lineno})"

    if parsed is None:
        return GateResult(
            exit_code=rc,
            raw_stdout=stdout,
            raw_stderr=stderr,
            parsed_ok=False,
            parse_error=parse_error or "stdout was empty",
        )

    sys_msg = parsed.get("systemMessage")
    hook_specific = parsed.get("hookSpecificOutput") or {}
    additional_ctx = (
        hook_specific.get("additionalContext")
        if isinstance(hook_specific, dict)
        else None
    )
    hook_event = (
        hook_specific.get("hookEventName")
        if isinstance(hook_specific, dict)
        else None
    )

    return GateResult(
        exit_code=rc,
        raw_stdout=stdout,
        raw_stderr=stderr,
        parsed_ok=True,
        parse_error=None,
        system_message=sys_msg if isinstance(sys_msg, str) else None,
        additional_context=additional_ctx if isinstance(additional_ctx, str) else None,
        hook_event_name=hook_event if isinstance(hook_event, str) else None,
        recall_block_emitted=isinstance(additional_ctx, str)
        and "memoir — recall before acting" in additional_ctx,
        fields=parsed,
    )

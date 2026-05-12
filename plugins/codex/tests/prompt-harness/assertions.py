"""Assertion DSL for prompt test cases.

Each assertion is a dict with at least a ``kind`` field (the assertion name)
and a ``value`` field (its argument). Evaluation returns an ``AssertionResult``
that's both human-readable (``message``) and machine-checkable (``passed``).

Kinds:
  empty:                 output must be empty / whitespace-only
  not_empty:             output must contain at least one non-whitespace char
  min_lines:             output has >= value non-empty lines
  max_lines:             output has <= value non-empty lines
  exact_lines:           output has exactly value non-empty lines
  regex_each_line:       every non-empty line matches value (regex)
  any_line_matches:      at least one line matches value (regex)
  no_line_contains:      no line contains value (substring)
  any_path_prefix:       at least one line's path field starts with one of the
                         given prefixes (value: list[str] of dotted prefixes,
                         line is split on first \\t)
  no_path_prefix:        no line's path field starts with any of the prefixes
  min_valid_capture_lines:
                         at least ``value`` lines match the production
                         capture-line regex (path<TAB>fact, path with 3 dotted
                         lowercase segments). Tolerates chatter lines that
                         don't match — production's stop.sh filter drops those.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Production's stop.sh regex for valid capture lines. Lines matching this
# get written to memoir; non-matching lines (preamble, "got it", etc.) are
# silently dropped. The harness uses the same shape so positive-case
# assertions reflect what production actually persists.
#
# Column 1 may now be a single taxonomy path *or* a comma-separated list of
# paths (no spaces) — multi-path lines write the same fact under each path
# with cross-references stored in `related_keys`.
_PRODUCTION_CAPTURE_RE = (
    r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,3}"
    r"(,[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,3})*\t.+$"
)


@dataclass
class AssertionResult:
    kind: str
    value: object
    passed: bool
    message: str


def _non_empty_lines(output: str) -> list[str]:
    return [ln for ln in output.splitlines() if ln.strip()]


def _path_of(line: str) -> str | None:
    """Return the path field of a path<TAB>fact line, or None if no tab."""
    if "\t" not in line:
        return None
    return line.split("\t", 1)[0].strip()


def _eval_one(output: str, spec: dict) -> AssertionResult:
    kind = spec.get("kind")
    value = spec.get("value")
    lines = _non_empty_lines(output)
    n = len(lines)

    if kind == "empty":
        ok = output.strip() == ""
        return AssertionResult(
            kind, value, ok,
            "output is empty" if ok else f"expected empty, got {n} non-empty line(s)",
        )

    if kind == "not_empty":
        ok = output.strip() != ""
        return AssertionResult(
            kind, value, ok,
            "output is non-empty" if ok else "expected non-empty output, got nothing",
        )

    if kind == "min_lines":
        ok = n >= int(value)
        return AssertionResult(
            kind, value, ok,
            f"got {n} non-empty line(s), need >= {value}",
        )

    if kind == "max_lines":
        ok = n <= int(value)
        return AssertionResult(
            kind, value, ok,
            f"got {n} non-empty line(s), need <= {value}",
        )

    if kind == "exact_lines":
        ok = n == int(value)
        return AssertionResult(
            kind, value, ok,
            f"got {n} non-empty line(s), need exactly {value}",
        )

    if kind == "regex_each_line":
        pattern = re.compile(str(value))
        bad = [ln for ln in lines if not pattern.match(ln)]
        ok = not bad
        msg = (
            f"all {n} line(s) match {value!r}"
            if ok
            else f"{len(bad)} of {n} line(s) failed to match {value!r}: {bad[:3]!r}"
        )
        return AssertionResult(kind, value, ok, msg)

    if kind == "any_line_matches":
        pattern = re.compile(str(value))
        ok = any(pattern.search(ln) for ln in lines)
        return AssertionResult(
            kind, value, ok,
            f"some line matched {value!r}" if ok else f"no line matched {value!r}",
        )

    if kind == "no_line_matches":
        pattern = re.compile(str(value))
        bad = [ln for ln in lines if pattern.search(ln)]
        ok = not bad
        return AssertionResult(
            kind, value, ok,
            f"no line matched {value!r}"
            if ok
            else f"{len(bad)} line(s) matched {value!r}: {bad[:3]!r}",
        )

    if kind == "min_valid_capture_lines":
        pattern = re.compile(_PRODUCTION_CAPTURE_RE)
        valid = [ln for ln in lines if pattern.match(ln)]
        ok = len(valid) >= int(value)
        return AssertionResult(
            kind, value, ok,
            f"got {len(valid)} valid capture line(s), need >= {value}"
            + (
                ""
                if ok
                else f"; saw {n} total lines (chatter dropped by prod filter)"
            ),
        )

    if kind == "no_line_contains":
        s = str(value)
        bad = [ln for ln in lines if s in ln]
        ok = not bad
        return AssertionResult(
            kind, value, ok,
            f"no line contained {s!r}" if ok else f"{len(bad)} line(s) contained {s!r}: {bad[:3]!r}",
        )

    if kind == "any_path_prefix":
        prefixes = value if isinstance(value, list) else [str(value)]
        path_lines = [(ln, _path_of(ln)) for ln in lines]
        hits = [
            ln for ln, p in path_lines
            if p and any(p == pre or p.startswith(pre + ".") for pre in prefixes)
        ]
        ok = bool(hits)
        return AssertionResult(
            kind, value, ok,
            f"path prefix matched: {hits[0]!r}"
            if ok
            else f"no line had path under {prefixes!r}; saw paths: {[p for _, p in path_lines]!r}",
        )

    if kind == "no_path_prefix":
        prefixes = value if isinstance(value, list) else [str(value)]
        bad = []
        for ln in lines:
            p = _path_of(ln)
            if p and any(p == pre or p.startswith(pre + ".") for pre in prefixes):
                bad.append(ln)
        ok = not bad
        return AssertionResult(
            kind, value, ok,
            f"no path under {prefixes!r}"
            if ok
            else f"{len(bad)} line(s) had a path under {prefixes!r}: {bad[:3]!r}",
        )

    return AssertionResult(
        kind or "<missing>", value, False,
        f"unknown assertion kind: {kind!r}",
    )


def evaluate(output: str, specs: list[dict]) -> list[AssertionResult]:
    """Run each assertion against ``output`` in order; return all results."""
    return [_eval_one(output, s) for s in specs]


# --- gate-mode assertions ---------------------------------------------------
#
# These run against a parsed ``GateResult`` from gate.py rather than raw
# stdout. Kept separate from ``_eval_one`` (which is string-output only)
# so the existing LLM-mode assertions stay unaffected and the two modes
# don't share an awkward dispatch.
#
# Kinds:
#   recall_block_emitted: hookSpecificOutput.additionalContext contains
#                         the production "memoir — recall before acting" header
#   recall_block_absent:  the additionalContext is absent or doesn't carry
#                         the recall block
#   additional_context_contains: substring check on additionalContext (case
#                                sensitive). value: str
#   system_message_contains:     substring check on systemMessage. value: str
#   exit_code_is:                hook exit code matches. value: int
#   parsed_ok:                   stdout was valid JSON object


def _eval_one_gate(result: object, spec: dict) -> AssertionResult:
    # Local import to avoid a hard dep cycle if gate.py grows imports later.
    from gate import GateResult  # noqa: WPS433
    if not isinstance(result, GateResult):
        return AssertionResult(
            spec.get("kind", "<missing>"),
            spec.get("value"),
            False,
            f"gate assertion needs a GateResult, got {type(result).__name__}",
        )

    kind = spec.get("kind")
    value = spec.get("value")

    if kind == "recall_block_emitted":
        ok = result.recall_block_emitted
        return AssertionResult(
            kind, value, ok,
            "recall block was emitted"
            if ok
            else "recall block NOT emitted (additionalContext missing or doesn't carry the header)",
        )

    if kind == "recall_block_absent":
        ok = not result.recall_block_emitted
        return AssertionResult(
            kind, value, ok,
            "no recall block emitted"
            if ok
            else "recall block was emitted but the case expected it absent",
        )

    if kind == "additional_context_contains":
        s = str(value)
        ctx = result.additional_context or ""
        ok = s in ctx
        return AssertionResult(
            kind, value, ok,
            f"additionalContext contained {s!r}"
            if ok
            else f"additionalContext did NOT contain {s!r} (got {ctx[:80]!r}…)",
        )

    if kind == "system_message_contains":
        s = str(value)
        msg = result.system_message or ""
        ok = s in msg
        return AssertionResult(
            kind, value, ok,
            f"systemMessage contained {s!r}"
            if ok
            else f"systemMessage did NOT contain {s!r} (got {msg!r})",
        )

    if kind == "exit_code_is":
        ok = result.exit_code == int(value)
        return AssertionResult(
            kind, value, ok,
            f"exit_code was {result.exit_code}",
        )

    if kind == "parsed_ok":
        ok = result.parsed_ok
        return AssertionResult(
            kind, value, ok,
            "stdout parsed as JSON object"
            if ok
            else f"stdout did NOT parse: {result.parse_error!r}",
        )

    return AssertionResult(
        kind or "<missing>", value, False,
        f"unknown gate assertion kind: {kind!r}",
    )


def evaluate_gate(result: object, specs: list[dict]) -> list[AssertionResult]:
    """Run each gate assertion against a ``GateResult`` in order."""
    return [_eval_one_gate(result, s) for s in specs]

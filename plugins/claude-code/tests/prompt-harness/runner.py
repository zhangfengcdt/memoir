#!/usr/bin/env python3
"""Prompt test harness for the Claude Code plugin.

Loads the same prompt templates the plugin uses in production
(``hooks/prompts/*.tmpl``), substitutes their dynamic placeholders, then runs
each test case against a real LLM via ``claude -p`` (Claude Code OAuth — no
API key needed).

Every invocation persists its full conversation to a fresh dir under
``/tmp/memoir-prompt-tests/<UTC-timestamp>/`` so you can read what happened
with your own eyes:

  <run>/summary.md
  <run>/summary.json
  <run>/<prompt>/<case>/system.txt   ← assembled system prompt
  <run>/<prompt>/<case>/input.txt    ← stdin sent to claude -p
  <run>/<prompt>/<case>/output.txt   ← raw model response
  <run>/<prompt>/<case>/result.json  ← per-assertion pass/fail
  <run>/<prompt>/<case>/command.sh   ← replayable invocation

Subcommands:
  run    --prompt NAME --model M [--store PATH]
                                  → run every case under cases/<NAME>/
  case   PATH --model M [--store PATH]
                                  → run a single case (path under cases/)
  adhoc  --prompt NAME --input FILE --model M [--store PATH]
                                  → no assertions; just record the response

Use ``--dry-run`` (with adhoc) to assemble the prompt and print, no LLM call.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

try:
    import yaml  # type: ignore[import-untyped]
except ModuleNotFoundError:
    sys.stderr.write(
        "PyYAML not installed in this Python. Install with one of:\n"
        "  python3 -m pip install pyyaml\n"
        "  pipx inject ... pyyaml\n"
        "  source <your-venv>/bin/activate  # if your project venv has it\n"
    )
    raise

# Local imports — the harness directory is on sys.path because we run from it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from assertions import evaluate, evaluate_gate  # noqa: E402
from gate import gate_store_for, run_gate  # noqa: E402
from prompts import PLUGIN_ROOT, assemble, list_prompts  # noqa: E402

HARNESS_ROOT = Path(__file__).resolve().parent
CASES_ROOT = HARNESS_ROOT / "cases"
TMP_ROOT = Path("/tmp/memoir-prompt-tests")


# --- data classes -----------------------------------------------------------


@dataclass
class CaseSpec:
    path: Path  # path to the YAML file, relative to CASES_ROOT
    description: str
    prompt: str
    input: str
    expect: list[dict]
    # Case mode. "llm" = run input through claude -p against the named
    # prompt template (existing behavior, default for back-compat with
    # cases that omit ``kind``). "gate" = invoke a hook script with synthetic
    # JSON stdin and assert on its parsed JSON output.
    kind: str = "llm"
    # Gate-mode fields. Ignored for kind=llm.
    hook: str = ""  # e.g. "user-prompt-submit" → hooks/user-prompt-submit.sh
    env: dict = field(default_factory=dict)


@dataclass
class CaseOutcome:
    case: str
    description: str
    prompt: str
    model: str
    skipped: bool
    passed: bool | None  # None for adhoc / dry-run
    duration_s: float
    artifacts_dir: str
    assertion_results: list[dict]
    notes: list[str]


# --- helpers ----------------------------------------------------------------


def _utc_stamp() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H-%M-%SZ")


def _new_run_dir() -> Path:
    p = TMP_ROOT / _utc_stamp()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _load_case(path: Path) -> CaseSpec:
    if not path.is_file():
        raise FileNotFoundError(f"case not found: {path}")
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"case YAML must be a mapping at {path}")
    expect = raw.get("expect") or []
    if not isinstance(expect, list):
        raise ValueError(f"'expect' must be a list at {path}")
    kind = str(raw.get("kind") or "llm")
    env = raw.get("env") or {}
    if not isinstance(env, dict):
        raise ValueError(f"'env' must be a mapping at {path}")
    return CaseSpec(
        path=path,
        description=str(raw.get("description") or ""),
        prompt=str(raw.get("prompt") or ""),
        input=str(raw.get("input") or ""),
        expect=expect,
        kind=kind,
        hook=str(raw.get("hook") or ""),
        env={str(k): str(v) for k, v in env.items()},
    )


def _discover_cases(prompt: str) -> list[Path]:
    d = CASES_ROOT / prompt
    if not d.is_dir():
        return []
    return sorted(d.glob("*.yaml")) + sorted(d.glob("*.yml"))


def _discover_gate_cases(hook: str | None = None) -> list[Path]:
    """Find all gate-mode case files under cases/gate/[<hook>/]*.yaml."""
    base = CASES_ROOT / "gate"
    if hook:
        base = base / hook
    if not base.is_dir():
        return []
    # Recursive — gate cases live under cases/gate/<hook>/
    return sorted(base.rglob("*.yaml")) + sorted(base.rglob("*.yml"))


def _render_command_sh(model: str, system_prompt_path: str, input_path: str) -> str:
    return f"""\
#!/usr/bin/env bash
# Replay this case against claude -p — same env vars and flags as the harness used.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
SYSTEM_PROMPT=$(cat "$SCRIPT_DIR/{system_prompt_path}")
INPUT=$(cat "$SCRIPT_DIR/{input_path}")
MEMOIR_NO_CAPTURE=1 CLAUDECODE= printf '%s' "$INPUT" | \\
  claude -p \\
    --model {shlex.quote(model)} \\
    --no-session-persistence \\
    --no-chrome \\
    --system-prompt "$SYSTEM_PROMPT"
"""


def _invoke_claude(model: str, system_prompt: str, case_input: str) -> tuple[str, str, int]:
    """Return (stdout, stderr, returncode). Raises RuntimeError if claude missing."""
    import shutil
    if not shutil.which("claude"):
        raise RuntimeError(
            "`claude` CLI not found on PATH. Install Claude Code "
            "(https://docs.claude.com/claude-code) and run `claude /login` first."
        )
    env = {**os.environ, "MEMOIR_NO_CAPTURE": "1", "CLAUDECODE": ""}
    res = subprocess.run(
        [
            "claude", "-p",
            "--model", model,
            "--no-session-persistence",
            "--no-chrome",
            "--system-prompt", system_prompt,
        ],
        input=case_input,
        capture_output=True,
        text=True,
        env=env,
        timeout=180,
    )
    return res.stdout or "", res.stderr or "", res.returncode


def _run_gate_case(
    case: CaseSpec,
    run_dir: Path,
) -> CaseOutcome:
    """Execute a kind=gate case: invoke a hook script, parse its JSON output,
    evaluate gate-mode assertions. No LLM call, deterministic.
    """
    case_label = (
        str(case.path.relative_to(CASES_ROOT))
        if case.path.is_relative_to(CASES_ROOT)
        else case.path.name
    )
    case_dir_name = case_label.replace("/", "__").removesuffix(".yaml").removesuffix(".yml")
    # Gate artifacts live under <run>/gate/<case>/ to keep them visually
    # separate from LLM-mode artifacts in the same run directory.
    case_dir = run_dir / "gate" / case_dir_name
    case_dir.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    start = dt.datetime.now()

    if not case.hook:
        notes.append("missing required field: 'hook' (e.g. 'user-prompt-submit')")
        (case_dir / "result.json").write_text(
            json.dumps({"error": "missing 'hook'"}, indent=2)
        )
        return CaseOutcome(
            case=case_label, description=case.description, prompt=case.prompt or "<gate>",
            model="gate", skipped=True, passed=None, duration_s=0.0,
            artifacts_dir=str(case_dir), assertion_results=[], notes=notes,
        )

    hook_script = PLUGIN_ROOT / "hooks" / f"{case.hook}.sh"
    store_dir = gate_store_for(case_label)
    notes.append(f"store: {store_dir}")
    notes.append(f"hook: {hook_script}")

    # Persist inputs for replay/debug.
    (case_dir / "input.json").write_text(
        json.dumps({"prompt": case.prompt}, indent=2)
    )
    (case_dir / "env.json").write_text(json.dumps(case.env, indent=2))

    result = run_gate(
        hook_script=hook_script,
        prompt=case.prompt,
        env=case.env,
        store_dir=store_dir,
    )

    (case_dir / "output.txt").write_text(result.raw_stdout)
    if result.raw_stderr.strip():
        (case_dir / "stderr.txt").write_text(result.raw_stderr)

    # Replay script — recreates the same invocation from artifacts.
    replay = f"""\
#!/usr/bin/env bash
# Replay this gate case — invokes the hook script with the recorded stdin.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
export MEMOIR_NO_CAPTURE=1
export MEMOIR_STORE={shlex.quote(str(store_dir))}
"""
    for k, v in case.env.items():
        if k == "USER_MEMORIES":
            # Statusline cache — rewrite per gate.py's contract.
            replay += (
                f'mkdir -p "$MEMOIR_STORE/.git" && '
                f"printf '%s\\n' {shlex.quote(str(v))} "
                f'> "$MEMOIR_STORE/.git/plugin-statusline-cache"\n'
            )
        else:
            replay += f"export {k}={shlex.quote(str(v))}\n"
    replay += (
        f'cat "$SCRIPT_DIR/input.json" | bash {shlex.quote(str(hook_script))}\n'
    )
    (case_dir / "command.sh").write_text(replay)
    (case_dir / "command.sh").chmod(0o755)

    # Evaluate.
    if not result.parsed_ok:
        notes.append(f"gate stdout did not parse: {result.parse_error}")
    assertion_results: list[dict] = []
    passed: bool | None = None
    if case.expect:
        results = evaluate_gate(result, case.expect)
        assertion_results = [asdict(r) for r in results]
        passed = all(r.passed for r in results)

    (case_dir / "result.json").write_text(json.dumps({
        "passed": passed,
        "kind": "gate",
        "exit_code": result.exit_code,
        "parsed_ok": result.parsed_ok,
        "parse_error": result.parse_error,
        "system_message": result.system_message,
        "additional_context_len": len(result.additional_context or ""),
        "recall_block_emitted": result.recall_block_emitted,
        "assertions": assertion_results,
    }, indent=2))

    dur = (dt.datetime.now() - start).total_seconds()
    return CaseOutcome(
        case=case_label, description=case.description, prompt=case.prompt or "<gate>",
        model="gate", skipped=False, passed=passed, duration_s=dur,
        artifacts_dir=str(case_dir),
        assertion_results=assertion_results, notes=notes,
    )


def _run_single(
    case: CaseSpec,
    model: str,
    store: str | None,
    run_dir: Path,
    *,
    dry_run: bool = False,
    skip_assertions: bool = False,
) -> CaseOutcome:
    case_label = str(case.path.relative_to(CASES_ROOT)) if case.path.is_relative_to(CASES_ROOT) else case.path.name
    case_dir_name = case_label.replace("/", "__").removesuffix(".yaml").removesuffix(".yml")
    case_dir = run_dir / case.prompt / case_dir_name
    case_dir.mkdir(parents=True, exist_ok=True)

    notes: list[str] = []
    start = dt.datetime.now()

    # Assemble system prompt (same code path as production).
    try:
        assembled = assemble(case.prompt, store=store)
    except Exception as e:
        notes.append(f"prompt assembly failed: {e}")
        (case_dir / "result.json").write_text(json.dumps({"error": str(e)}, indent=2))
        return CaseOutcome(
            case=case_label, description=case.description, prompt=case.prompt,
            model=model, skipped=True, passed=None, duration_s=0.0,
            artifacts_dir=str(case_dir), assertion_results=[], notes=notes,
        )

    system_path = case_dir / "system.txt"
    input_path = case_dir / "input.txt"
    system_path.write_text(assembled.system_prompt)
    input_path.write_text(case.input)
    notes.append(f"taxonomy: {assembled.taxonomy_source}")

    # Replay script always written, even on dry-run.
    (case_dir / "command.sh").write_text(
        _render_command_sh(model, "system.txt", "input.txt")
    )
    (case_dir / "command.sh").chmod(0o755)

    if dry_run:
        notes.append("dry-run: skipped LLM invocation")
        (case_dir / "result.json").write_text(json.dumps(
            {"dry_run": True, "system_prompt_chars": len(assembled.system_prompt),
             "input_chars": len(case.input)}, indent=2,
        ))
        dur = (dt.datetime.now() - start).total_seconds()
        return CaseOutcome(
            case=case_label, description=case.description, prompt=case.prompt,
            model=model, skipped=False, passed=None, duration_s=dur,
            artifacts_dir=str(case_dir), assertion_results=[], notes=notes,
        )

    # Real LLM call.
    try:
        stdout, stderr, rc = _invoke_claude(model, assembled.system_prompt, case.input)
    except subprocess.TimeoutExpired:
        notes.append("claude -p timed out (180s)")
        (case_dir / "result.json").write_text(json.dumps({"error": "timeout"}, indent=2))
        dur = (dt.datetime.now() - start).total_seconds()
        return CaseOutcome(
            case=case_label, description=case.description, prompt=case.prompt,
            model=model, skipped=True, passed=None, duration_s=dur,
            artifacts_dir=str(case_dir), assertion_results=[], notes=notes,
        )
    except RuntimeError as e:
        notes.append(str(e))
        (case_dir / "result.json").write_text(json.dumps({"error": str(e)}, indent=2))
        dur = (dt.datetime.now() - start).total_seconds()
        return CaseOutcome(
            case=case_label, description=case.description, prompt=case.prompt,
            model=model, skipped=True, passed=None, duration_s=dur,
            artifacts_dir=str(case_dir), assertion_results=[], notes=notes,
        )

    (case_dir / "output.txt").write_text(stdout)
    if stderr.strip():
        (case_dir / "stderr.txt").write_text(stderr)
    if rc != 0:
        notes.append(f"claude -p exited {rc}")

    # Evaluate assertions.
    assertion_results: list[dict] = []
    passed: bool | None = None
    if not skip_assertions and case.expect:
        results = evaluate(stdout, case.expect)
        assertion_results = [asdict(r) for r in results]
        passed = all(r.passed for r in results)
    elif skip_assertions:
        notes.append("adhoc: assertions not evaluated")

    (case_dir / "result.json").write_text(json.dumps({
        "passed": passed,
        "model": model,
        "exit_code": rc,
        "stdout_chars": len(stdout),
        "stderr_chars": len(stderr),
        "assertions": assertion_results,
    }, indent=2))

    dur = (dt.datetime.now() - start).total_seconds()
    return CaseOutcome(
        case=case_label, description=case.description, prompt=case.prompt,
        model=model, skipped=False, passed=passed, duration_s=dur,
        artifacts_dir=str(case_dir),
        assertion_results=assertion_results, notes=notes,
    )


def _write_summary(run_dir: Path, outcomes: list[CaseOutcome]) -> None:
    (run_dir / "summary.json").write_text(
        json.dumps([asdict(o) for o in outcomes], indent=2),
    )
    md_lines = [f"# Prompt harness run — {run_dir.name}", ""]
    md_lines.append(f"Cases: **{len(outcomes)}**")
    passed = sum(1 for o in outcomes if o.passed is True)
    failed = sum(1 for o in outcomes if o.passed is False)
    skipped = sum(1 for o in outcomes if o.skipped)
    adhoc = sum(1 for o in outcomes if o.passed is None and not o.skipped)
    md_lines.append(f"Passed: **{passed}** · Failed: **{failed}** · Skipped: **{skipped}** · Adhoc/dry-run: **{adhoc}**")
    md_lines.append("")
    md_lines.append("| Status | Case | Description | Model | Time | Artifacts |")
    md_lines.append("|---|---|---|---|---|---|")
    for o in outcomes:
        if o.skipped:
            status = "⏭ skipped"
        elif o.passed is True:
            status = "✅ pass"
        elif o.passed is False:
            status = "❌ FAIL"
        else:
            status = "📝 recorded"
        md_lines.append(
            f"| {status} | `{o.case}` | {o.description} | `{o.model}` | "
            f"{o.duration_s:.1f}s | `{o.artifacts_dir}` |"
        )
    md_lines.append("")
    for o in outcomes:
        if o.passed is False or o.skipped:
            md_lines.append(f"## `{o.case}`")
            md_lines.append(f"- **{o.description}**")
            for n in o.notes:
                md_lines.append(f"- note: {n}")
            for r in o.assertion_results:
                if not r["passed"]:
                    md_lines.append(f"- ❌ `{r['kind']}` {r['value']!r} — {r['message']}")
            md_lines.append("")
    (run_dir / "summary.md").write_text("\n".join(md_lines))


def _print_summary(run_dir: Path, outcomes: list[CaseOutcome]) -> int:
    print()
    print(f"Run directory: {run_dir}")
    for o in outcomes:
        if o.skipped:
            tag = "SKIP"
        elif o.passed is True:
            tag = "PASS"
        elif o.passed is False:
            tag = "FAIL"
        else:
            tag = "REC "
        print(f"  [{tag}] {o.case}  ({o.duration_s:.1f}s)  → {o.artifacts_dir}")
        if o.passed is False:
            for r in o.assertion_results:
                if not r["passed"]:
                    print(f"         ❌ {r['kind']} {r['value']!r} — {r['message']}")
        for n in o.notes:
            if "failed" in n.lower() or "error" in n.lower() or "timed out" in n.lower():
                print(f"         note: {n}")
    print()
    print(f"Summary: {run_dir / 'summary.md'}")
    failed = sum(1 for o in outcomes if o.passed is False)
    return 1 if failed else 0


# --- subcommands ------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    cases = _discover_cases(args.prompt)
    if not cases:
        avail = ", ".join(list_prompts()) or "(no prompts)"
        print(f"no cases under {CASES_ROOT / args.prompt}/", file=sys.stderr)
        print(f"available prompts: {avail}", file=sys.stderr)
        return 2
    run_dir = _new_run_dir()
    outcomes = []
    for case_path in cases:
        try:
            spec = _load_case(case_path)
        except Exception as e:
            print(f"skipping {case_path}: {e}", file=sys.stderr)
            continue
        if spec.prompt != args.prompt:
            print(
                f"skipping {case_path}: case prompt={spec.prompt!r} doesn't match --prompt={args.prompt!r}",
                file=sys.stderr,
            )
            continue
        outcomes.append(_run_single(spec, args.model, args.store, run_dir))
    _write_summary(run_dir, outcomes)
    return _print_summary(run_dir, outcomes)


def cmd_case(args: argparse.Namespace) -> int:
    case_path = (CASES_ROOT / args.path).resolve()
    if not case_path.is_file():
        # Allow absolute paths too.
        case_path = Path(args.path).resolve()
    spec = _load_case(case_path)
    run_dir = _new_run_dir()
    if spec.kind == "gate":
        outcome = _run_gate_case(spec, run_dir)
    else:
        outcome = _run_single(spec, args.model, args.store, run_dir)
    _write_summary(run_dir, [outcome])
    return _print_summary(run_dir, [outcome])


def cmd_recall_ab(args: argparse.Namespace) -> int:
    """Run all recall-ab cases under cases/recall_ab/, three arms each.

    Cases are YAML files with ``prompt:`` + ``should_fire: true|false``.
    No ``expect:`` block — assertions are aggregate (per-arm F1) rather
    than per-case. Output: <run>/recall_ab/{summary.md, comparison.json}
    and <run>/recall_ab/<case>/<arm>/{events.jsonl, tool_calls.json}.
    """
    from recall_ab import (  # noqa: WPS433
        run_recall_ab_case,
        summarize_arms,
    )

    cases_dir = CASES_ROOT / "recall_ab"
    if not cases_dir.is_dir():
        print(f"no cases under {cases_dir}/", file=sys.stderr)
        return 2
    case_files = sorted(cases_dir.glob("*.yaml")) + sorted(cases_dir.glob("*.yml"))
    if not case_files:
        print(f"no .yaml cases under {cases_dir}/", file=sys.stderr)
        return 2

    cases: list[tuple[str, str, bool]] = []  # (label, prompt, should_fire)
    for cp in case_files:
        try:
            raw = yaml.safe_load(cp.read_text())
        except Exception as e:
            print(f"skipping {cp}: {e}", file=sys.stderr)
            continue
        if not isinstance(raw, dict):
            print(f"skipping {cp}: top-level YAML must be a mapping", file=sys.stderr)
            continue
        prompt = str(raw.get("prompt") or "")
        should = bool(raw.get("should_fire"))
        if not prompt:
            print(f"skipping {cp}: missing 'prompt'", file=sys.stderr)
            continue
        cases.append((cp.stem, prompt, should))

    if not cases:
        print("no usable recall-ab cases", file=sys.stderr)
        return 2

    arms: list[str] = ["with_hook", "prose_only", "bare"]
    run_dir = _new_run_dir()
    ab_dir = run_dir / "recall_ab"
    ab_dir.mkdir(parents=True, exist_ok=True)

    observations = []
    labels: dict[str, bool] = {}
    for label, prompt, should in cases:
        labels[prompt] = should
        for arm in arms:
            artifact = ab_dir / label / arm
            obs = run_recall_ab_case(
                prompt=prompt,
                arm=arm,  # type: ignore[arg-type]
                model=args.model,
                artifact_dir=artifact,
            )
            observations.append(obs)
            tag = "FIRED" if obs.skill_invoked else "skip"
            err = f" (error: {obs.error})" if obs.error else ""
            print(f"  [{tag:5s}] {label:30s} arm={arm:11s} {obs.duration_s:.1f}s{err}")

    summary = summarize_arms(observations, labels)
    (ab_dir / "comparison.json").write_text(json.dumps(summary, indent=2))

    md = ["# Recall A/B comparison", ""]
    md.append(f"Cases: **{len(cases)}** · arms: {', '.join(arms)}")
    md.append("")
    md.append("| Arm | TP | FP | FN | TN | Precision | Recall | F1 |")
    md.append("|---|---|---|---|---|---|---|---|")
    for arm in arms:
        a = summary["arms"].get(arm, {})
        md.append(
            f"| `{arm}` | {a.get('tp', 0)} | {a.get('fp', 0)} | {a.get('fn', 0)} "
            f"| {a.get('tn', 0)} | {a.get('precision', 0):.3f} "
            f"| {a.get('recall', 0):.3f} | {a.get('f1', 0):.3f} |"
        )
    (ab_dir / "summary.md").write_text("\n".join(md))
    print(f"\nrecall-ab summary: {ab_dir / 'summary.md'}")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    """Run all gate-mode cases under cases/gate/[<hook>/]."""
    cases = _discover_gate_cases(args.hook)
    if not cases:
        target = (
            f"cases/gate/{args.hook}/" if args.hook else "cases/gate/"
        )
        print(f"no gate cases under {target}", file=sys.stderr)
        return 2
    run_dir = _new_run_dir()
    outcomes: list[CaseOutcome] = []
    for case_path in cases:
        try:
            spec = _load_case(case_path)
        except Exception as e:
            print(f"skipping {case_path}: {e}", file=sys.stderr)
            continue
        if spec.kind != "gate":
            print(
                f"skipping {case_path}: kind={spec.kind!r}, expected 'gate'",
                file=sys.stderr,
            )
            continue
        outcomes.append(_run_gate_case(spec, run_dir))
    _write_summary(run_dir, outcomes)
    return _print_summary(run_dir, outcomes)


def cmd_adhoc(args: argparse.Namespace) -> int:
    input_text = Path(args.input).read_text()
    spec = CaseSpec(
        path=Path(args.input),
        description=f"adhoc: {Path(args.input).name}",
        prompt=args.prompt,
        input=input_text,
        expect=[],
    )
    run_dir = _new_run_dir()
    # Re-key the artifact dir under "_adhoc/" so it doesn't collide with cases.
    spec.path = CASES_ROOT / "_adhoc" / Path(args.input).name
    outcome = _run_single(
        spec, args.model, args.store, run_dir,
        dry_run=args.dry_run, skip_assertions=True,
    )
    _write_summary(run_dir, [outcome])
    return _print_summary(run_dir, [outcome])


# --- entry point ------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(
        prog="runner.py",
        description="Prompt test harness for the Claude Code plugin.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    common_model = ("--model", {"required": True, "help": "Model name (haiku, sonnet, opus, ...)"})
    common_store = ("--store", {"default": None, "help": "Memoir store for taxonomy snippet (optional)"})

    run_p = sub.add_parser("run", help="Run all cases under cases/<prompt>/")
    run_p.add_argument("--prompt", required=True, help=f"Prompt name (one of: {', '.join(list_prompts()) or '(none)'})")
    run_p.add_argument(*([common_model[0]]), **common_model[1])
    run_p.add_argument(*([common_store[0]]), **common_store[1])
    run_p.set_defaults(func=cmd_run)

    case_p = sub.add_parser("case", help="Run a single case by relative or absolute path")
    case_p.add_argument("path", help="Path under cases/ (e.g. stop_capture/foo.yaml) or absolute path")
    # --model is only required for kind=llm cases; gate cases ignore it but
    # we keep it optional so a single ``case`` invocation works for both.
    case_p.add_argument("--model", default="", help="Model name (required for kind=llm cases)")
    case_p.add_argument(*([common_store[0]]), **common_store[1])
    case_p.set_defaults(func=cmd_case)

    gate_p = sub.add_parser(
        "gate",
        help="Run deterministic gate-mode cases (shell hooks, no LLM call)",
    )
    gate_p.add_argument(
        "--hook",
        default=None,
        help="Limit to one hook's cases (e.g. user-prompt-submit). Omit to run all.",
    )
    gate_p.set_defaults(func=cmd_gate)

    ab_p = sub.add_parser(
        "recall-ab",
        help="A/B test the recall trigger (LLM, costs tokens, run on demand)",
    )
    ab_p.add_argument(*([common_model[0]]), **common_model[1])
    ab_p.set_defaults(func=cmd_recall_ab)

    ad_p = sub.add_parser("adhoc", help="Diagnostic: run a prompt against an arbitrary input file")
    ad_p.add_argument("--prompt", required=True)
    ad_p.add_argument("--input", required=True, help="Path to a file containing the model's input text")
    ad_p.add_argument(*([common_model[0]]), **common_model[1])
    ad_p.add_argument(*([common_store[0]]), **common_store[1])
    ad_p.add_argument("--dry-run", action="store_true", help="Assemble prompt + record artifacts; skip LLM call")
    ad_p.set_defaults(func=cmd_adhoc)

    args = p.parse_args()
    _ = PLUGIN_ROOT  # silence unused import warning
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

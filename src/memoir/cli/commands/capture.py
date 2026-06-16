# SPDX-License-Identifier: Apache-2.0
"""
Capture command for memoir CLI.

`memoir capture` reads a single conversation turn from stdin, runs one LLM
extraction pass to pull out durable facts, and writes each fact via the same
pre-classified `remember` path the Claude Code Stop hook uses (`-p <path>`,
no per-fact classifier chain). It exists so that *non-coding* agent hosts —
personal assistants like Hermes and OpenClaw — get the same auto-capture
behavior without shelling out to the `claude` CLI (unavailable and
coding-specific for those hosts).

Extraction prompts live in `src/memoir/llm/prompts/capture_<profile>.tmpl`
and are the single source of truth (mirrors the plugin prompt-harness
convention). The taxonomy grounding (`${TAXONOMY_BLOCK}`) is rendered from
the store's persisted taxonomy via the same helper `taxonomy prompt-snippet`
uses, so capture classifies against the same paths as `memoir remember`.

Silence is the normal case: a turn with no durable facts exits 0 with
`{"captured": []}`.
"""

import asyncio
import os
import re
import sys
from pathlib import Path

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_NO_STORE,
    MemoirContext,
    pass_context,
)

# Column-1 validator. Mirrors the guard in the Claude Code Stop hook
# (hooks/stop.sh): one or more comma-separated taxonomy paths, each 2-4
# dotted segments of [a-z0-9_]. The prompt asks for exactly 3 levels, but we
# accept 2-4 here for resilience against the model emitting a slightly short
# or long path — the downstream store tolerates it and a near-miss path is
# more useful than a dropped fact.
_PATHS_RE = re.compile(
    r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,3}" r"(,[a-z][a-z0-9_]*(\.[a-z0-9_]+){1,3})*$"
)

# Minimum fact length — guards against the model emitting stray fragments or
# preamble that happened to contain a tab. Matches the Stop hook's threshold.
_MIN_FACT_LEN = 8

_PROFILES = ("assistant", "coding")

# Hardcoded taxonomy hints used only when the store has no taxonomy loaded.
# Kept profile-specific so the extractor still has sensible category
# grounding on a fresh store. Mirrors the fallback block in
# plugins/claude-code/hooks/stop.sh.
_FALLBACK_BLOCKS = {
    "assistant": (
        "CATEGORIES (top-level + common second levels — pick a sensible "
        "third level yourself):\n"
        "  profile.{personal,professional}: name, demographics, occupation, "
        "location, important dates, etc.\n"
        "  preferences.{food,communication,tools,travel,entertainment,"
        "shopping}: likes, dislikes, habits, brands, dietary needs, etc.\n"
        "  relationships.{family,friends,professional}: partner, children, "
        "colleagues, names and relationships, etc.\n"
        "  schedule.{recurring,appointments}: weekly classes, standing "
        "meetings, regular routines, etc.\n"
        "  goals.{personal,health,career,financial,travel}\n"
        "  instructions.assistant: standing rules the person has given the "
        "assistant ('always…', 'never…', 'from now on…')\n"
        "  routine.daily: habitual daily activities"
    ),
    "coding": (
        "CATEGORIES (top-level + common second levels — pick a sensible "
        "third level yourself):\n"
        "  profile.{personal,professional}: identity, occupation, skills, "
        "etc.\n"
        "  preferences.{coding,tools,work}: editors, languages, frameworks, "
        "AI models, work style, etc.\n"
        "  workflow.{coding,devops}: testing, branching, review, deployment, "
        "versioning, etc.\n"
        "  context.project.{stack,repository,infrastructure,database,cicd,"
        "standards}\n"
        "  knowledge.technical: languages, tools, invariants, gotchas\n"
        "  behavior.work: schedule, habits"
    ),
}


def _prompts_dir() -> Path:
    """Locate the packaged extraction-prompt templates.

    Resolved relative to the ``memoir.llm`` package so it works for both
    editable and wheel installs (hatchling ships non-Python assets under
    ``src/memoir`` by default).
    """
    import memoir.llm as _llm_pkg

    return Path(_llm_pkg.__file__).parent / "prompts"


def _load_template(profile: str) -> str:
    """Read the extraction prompt template for ``profile``."""
    tmpl = _prompts_dir() / f"capture_{profile}.tmpl"
    return tmpl.read_text(encoding="utf-8")


def _build_taxonomy_block(store_path: str, profile: str) -> str:
    """Render the store's taxonomy as a prompt block, or a fallback hint.

    Uses the same ``TaxonomyLoader.render_prompt_snippet`` helper as the
    ``taxonomy prompt-snippet`` CLI command so capture grounds against the
    same paths as ``memoir remember``. Falls back to a profile-specific
    hint sheet when the store has no taxonomy loaded.
    """
    try:
        from memoir.store.prolly_adapter import ProllyTreeStore
        from memoir.taxonomy.loader import TaxonomyLoader

        loader = TaxonomyLoader(ProllyTreeStore(store_path))
        snippet = loader.render_prompt_snippet()
        if snippet:
            return snippet
    except Exception:
        # A taxonomy-read failure must not abort capture — fall back.
        pass
    return _FALLBACK_BLOCKS.get(profile, _FALLBACK_BLOCKS["assistant"])


def _parse_facts(text: str) -> list[tuple[list[str], str]]:
    """Parse the model's ``<paths>\\t<fact>`` output into (paths, fact) pairs.

    Drops any line that doesn't carry a tab-separated column-1 path list
    matching ``_PATHS_RE`` or whose fact is too short — the same defensive
    filter the Stop hook applies to guard against the model emitting
    preamble or malformed lines.
    """
    results: list[tuple[list[str], str]] = []
    for line in text.splitlines():
        if "\t" not in line:
            continue
        raw_paths, _, fact = line.partition("\t")
        paths = raw_paths.strip()
        fact = fact.strip()
        if not paths or len(fact) < _MIN_FACT_LEN:
            continue
        if not _PATHS_RE.match(paths):
            continue
        results.append(([p for p in paths.split(",") if p], fact))
    return results


@click.command()
@click.option(
    "--profile",
    type=click.Choice(_PROFILES, case_sensitive=False),
    default="assistant",
    show_default=True,
    help=(
        "Extraction prompt to use. 'assistant' captures personal-assistant "
        "facts (people, schedules, preferences, standing instructions); "
        "'coding' captures software-development context (the Stop-hook "
        "prompt, host-agnostic)."
    ),
)
@click.option(
    "-n",
    "--namespace",
    default="default",
    show_default=True,
    help="Namespace to write captured facts into.",
)
@click.option(
    "--model",
    "model",
    default=None,
    help=(
        "LLM model for extraction. Resolution order: this flag → "
        "MEMOIR_LLM_MODEL env var → 'claude-haiku-4-5' default."
    ),
)
@click.option(
    "--branch",
    "branch",
    envvar="MEMOIR_BRANCH",
    default=None,
    help=(
        "Route captures to a specific branch without changing the store's "
        "checked-out branch (env: MEMOIR_BRANCH). Auto-created off HEAD if "
        "missing."
    ),
)
@click.option(
    "--input",
    "input_path",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Read the transcript from this file instead of stdin (for testing).",
)
@pass_context
def capture(
    ctx: MemoirContext,
    profile: str,
    namespace: str,
    model: str | None,
    branch: str | None,
    input_path: str | None,
):
    """Extract durable facts from a conversation turn and remember them.

    INPUT: A single turn transcript on stdin, in the form:

    \b
        [Human]
        <user message>
        [Assistant]
        <assistant response>

    OUTPUT: The facts captured (if any), each stored at a pre-classified
    taxonomy path. Silence is the expected outcome — most turns hold no
    durable facts and exit 0 with an empty list.

    One LLM call per turn extracts and classifies facts in a single pass
    (no per-fact classifier chain), then writes each via the pre-classified
    `remember` path. Built for non-coding agent hosts (personal assistants)
    that can't shell out to the `claude` CLI.

    \b
    Examples:
      memoir capture --profile assistant < turn.txt
      printf '[Human]\\nmy daughter has piano every Tuesday\\n[Assistant]\\nGot it.\\n' \\
          | memoir capture --profile assistant
      memoir capture --profile coding --model gpt-4o-mini < turn.txt

    \b
    JSON output includes: captured[{fact, paths, key, keys, commit_hash}],
    count, profile, model.
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd into a memoir store.",
            EXIT_NO_STORE,
        )

    profile = profile.lower()

    # Read the turn transcript.
    if input_path:
        transcript = Path(input_path).read_text(encoding="utf-8")
    else:
        transcript = sys.stdin.read()
    transcript = transcript.strip()

    # Empty input → silence. Not an error: an empty turn simply has nothing
    # to capture.
    if not transcript:
        _emit_empty(ctx, profile)
        return

    resolved_model = model or os.environ.get("MEMOIR_LLM_MODEL") or "claude-haiku-4-5"

    # Assemble the extraction prompt: template (with the store's taxonomy
    # substituted for ${TAXONOMY_BLOCK}) as the system message, the turn as
    # the user message. The message-list form is backend-portable: litellm
    # gets a proper system/user split; the claude-cli wrapper flattens it
    # without triggering its JSON-output discipline (which would corrupt our
    # TSV format).
    try:
        template = _load_template(profile)
    except Exception as e:
        ctx.error(f"Failed to load capture template for '{profile}': {e}", EXIT_ERROR)
        return

    taxonomy_block = _build_taxonomy_block(ctx.store_path, profile)
    system_prompt = template.replace("${TAXONOMY_BLOCK}", taxonomy_block)

    try:
        from memoir.llm import get_llm

        llm = get_llm(model=resolved_model, temperature=0, max_tokens=1024)
        response = asyncio.run(
            llm.ainvoke(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": transcript},
                ]
            )
        )
    except Exception as e:
        ctx.error(f"Extraction failed: {e}", EXIT_ERROR)
        return

    facts = _parse_facts(response.content or "")
    if not facts:
        _emit_empty(ctx, profile)
        return

    # Persist each fact via the pre-classified remember path (no per-fact
    # classifier LLM chain — paths come straight from the extractor).
    from memoir.services.branch_service import BranchService
    from memoir.services.memory_service import MemoryService

    service = MemoryService(ctx.store_path)
    branch_service = BranchService(ctx.store_path)

    captured: list[dict] = []
    try:
        with branch_service.routed_to(branch, auto_create=True):
            for paths, fact in facts:
                result = asyncio.run(service.remember(fact, namespace, paths=paths))
                if result.success:
                    captured.append(
                        {
                            "fact": fact,
                            "paths": paths,
                            "key": result.key,
                            "keys": result.keys,
                            "commit_hash": result.commit_hash,
                        }
                    )
    except Exception as e:
        ctx.error(f"Failed to store captured facts: {e}", EXIT_ERROR)
        return

    if ctx.json_output:
        ctx.output(
            {
                "captured": captured,
                "count": len(captured),
                "profile": profile,
                "model": resolved_model,
            }
        )
    elif not ctx.quiet:
        if not captured:
            click.echo("Nothing captured.")
        else:
            click.echo(
                click.style("✓ ", fg="green") + f"Captured {len(captured)} fact(s):"
            )
            for item in captured:
                click.echo(f"  [{', '.join(item['paths'])}] {item['fact']}")


def _emit_empty(ctx: MemoirContext, profile: str) -> None:
    """Emit the empty-capture result (the normal, silent case)."""
    if ctx.json_output:
        ctx.output({"captured": [], "count": 0, "profile": profile})
    elif not ctx.quiet:
        click.echo("Nothing captured.")

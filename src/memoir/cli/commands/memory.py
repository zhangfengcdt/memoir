# SPDX-License-Identifier: Apache-2.0
"""
Memory commands for memoir CLI.

Commands: remember, recall, forget
"""

import asyncio
import json
import sys

import click

from memoir.cli.main import (
    EXIT_CLASSIFICATION_FAILED,
    EXIT_ERROR,
    EXIT_NO_STORE,
    EXIT_NOT_FOUND,
    MemoirContext,
    pass_context,
)


@click.command()
@click.argument("content")
@click.option(
    "-n",
    "--namespace",
    default=None,
    help=(
        "Memory namespace. If omitted, inferred from a `<namespace>:<path>` "
        "prefix on -p (when present); otherwise falls back to 'default'."
    ),
)
@click.option(
    "-p",
    "--path",
    "paths",
    multiple=True,
    help=(
        "Pre-classified taxonomy path (e.g. 'preferences.coding.languages'). "
        "When given, skips memoir's LLM classifier entirely and stores at this "
        "path directly. May include a `<namespace>:` prefix "
        "(e.g. 'default:preferences.coding.languages') — the namespace is then "
        "inferred from the prefix when -n is omitted. Pass -p multiple times "
        "to write the same content to several paths in one call; each blob's "
        "`related_keys` field will list the other sibling paths (excluding "
        "self). All -p prefixes (and any explicit -n) must agree."
    ),
)
@click.option(
    "--model",
    "model",
    default=None,
    help=(
        "LLM model to use for classification (e.g. 'claude-haiku-4-5', "
        "'gpt-4o-mini'). Resolution order: this flag → MEMOIR_LLM_MODEL env "
        "var → 'claude-haiku-4-5' default. Ignored when -p is given (no LLM "
        "call)."
    ),
)
@click.option(
    "--replace",
    "replace",
    is_flag=True,
    default=False,
    help=(
        "Overwrite the existing value at each -p target instead of appending "
        "the new content as an '[update]' paragraph. Use for callers that own "
        "their own read-merge-write cycle (per-branch metrics, scalar pointers). "
        "No effect without -p — the LLM-classifier path always replaces."
    ),
)
@click.option(
    "--branch",
    "branch",
    envvar="MEMOIR_BRANCH",
    default=None,
    help=(
        "Route this write to a specific branch without changing the store's "
        "checked-out branch (per-call routing for multi-agent setups; env: "
        "MEMOIR_BRANCH). If the branch doesn't exist it's auto-created off "
        "current HEAD."
    ),
)
@pass_context
def remember(
    ctx: MemoirContext,
    content: str,
    namespace: str | None,
    paths: tuple,
    model: str | None,
    replace: bool,
    branch: str | None,
):
    """Store content in memory with intelligent classification.

    INPUT: Any text content (facts, preferences, events, notes).
    OUTPUT: Semantic path(s) where memory was stored (e.g., user.preferences.theme).

    Content is automatically classified into hierarchical paths using LLM
    and stored with git versioning. Each store creates a commit.

    Pass --path/-p to skip classification and store directly at a known path.
    Pass -p multiple times to store the same content under several paths in
    one write; each blob will carry a `related_keys` field listing the
    sibling paths.

    \b
    Examples:
      memoir remember "User prefers dark mode"
      memoir remember "Meeting at 3pm tomorrow" -n calendar
      memoir remember "API key is abc123" -n secrets
      memoir remember "Uses 4-space indentation" -p preferences.coding.style
      memoir remember "Feng prefers TDD and terminal CLIs" \\
          -p preferences.coding.methodology -p preferences.tooling.terminal
      memoir remember "..." --model claude-haiku-4-5

    \b
    JSON output includes: key, keys, confidence, reasoning, commit_hash
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd into a memoir store.",
            EXIT_NO_STORE,
        )

    from memoir.services.memory_service import MemoryService

    # Parse optional `<namespace>:<path>` prefix on each -p value. Taxonomy
    # paths are dot-segmented and never contain ':', so a leftmost ':' is an
    # unambiguous namespace separator. All prefixes must agree with each
    # other and with any explicit -n; conflicts hard-error rather than
    # silently picking one (a write to the wrong namespace is hard to find).
    paths_list: list[str] | None = None
    inferred_ns: str | None = None
    if paths:
        cleaned: list[str] = []
        for raw in paths:
            if ":" in raw:
                prefix, _, rest = raw.partition(":")
                if not prefix or not rest:
                    ctx.error(
                        f"Invalid -p value '{raw}': namespace prefix and path "
                        "must both be non-empty.",
                        EXIT_ERROR,
                    )
                if inferred_ns is None:
                    inferred_ns = prefix
                elif inferred_ns != prefix:
                    ctx.error(
                        f"Conflicting namespace prefixes on -p: "
                        f"'{inferred_ns}' vs '{prefix}'.",
                        EXIT_ERROR,
                    )
                cleaned.append(rest)
            else:
                cleaned.append(raw)
        paths_list = cleaned

    if namespace is not None and inferred_ns is not None and namespace != inferred_ns:
        ctx.error(
            f"-n '{namespace}' conflicts with namespace prefix on -p "
            f"'{inferred_ns}:...'.",
            EXIT_ERROR,
        )
    effective_namespace = namespace or inferred_ns or "default"

    from memoir.services.branch_service import BranchService

    service = MemoryService(ctx.store_path, llm_model=model)
    branch_service = BranchService(ctx.store_path)

    try:
        with branch_service.routed_to(branch, auto_create=True):
            result = asyncio.run(
                service.remember(
                    content, effective_namespace, paths=paths_list, replace=replace
                )
            )

        if ctx.json_output:
            ctx.output(result.to_dict())
        else:
            if result.success:
                click.echo(click.style("✓ ", fg="green") + f"Stored at: {result.key}")
                if len(result.keys) > 1:
                    siblings = ", ".join(result.keys[1:])
                    click.echo(f"  Also saved under: {siblings}")
                if result.reasoning and ctx.verbose:
                    click.echo(f"  Reasoning: {result.reasoning}")
                if result.confidence:
                    click.echo(f"  Confidence: {result.confidence:.2f}")
                if result.commit_hash:
                    click.echo(f"  Commit: {result.commit_hash[:8]}")
            else:
                ctx.error(
                    result.error or "Failed to store memory", EXIT_CLASSIFICATION_FAILED
                )
    except Exception as e:
        ctx.error(f"Failed to remember: {e}", EXIT_ERROR)


@click.command()
@click.argument("query")
@click.option("-n", "--namespace", help="Search in specific namespace (default: all)")
@click.option("-l", "--limit", default=10, help="Maximum results to return")
@click.option(
    "--threshold", default=0.0, type=float, help="Minimum relevance score (0.0-1.0)"
)
@click.option(
    "--mode",
    type=click.Choice(["single", "tiered"], case_sensitive=False),
    default="single",
    show_default=True,
    help="Search mode: 'single' (one LLM call) or 'tiered' (multi-stage drill-down).",
)
@click.option(
    "--model",
    "model",
    default=None,
    help=(
        "LLM model to use for semantic search (e.g. 'claude-haiku-4-5', "
        "'gpt-4o-mini'). Resolution order: this flag → MEMOIR_LLM_MODEL env "
        "var → 'claude-haiku-4-5' default."
    ),
)
@click.option(
    "--branch",
    "branch",
    envvar="MEMOIR_BRANCH",
    default=None,
    help=(
        "Recall from a specific branch without changing the store's checked-out "
        "branch (per-call routing for multi-agent setups; env: MEMOIR_BRANCH). "
        "Errors if the branch doesn't exist."
    ),
)
@pass_context
def recall(
    ctx: MemoirContext,
    query: str,
    namespace: str,
    limit: int,
    threshold: float,
    mode: str,
    model: str | None,
    branch: str | None,
):
    """Search memories using semantic query.

    INPUT: Natural language query describing what you're looking for.
    OUTPUT: List of matching memories with paths, content, and relevance scores.

    Uses semantic search to find relevant memories. Returns results sorted
    by relevance score (0.0-1.0). Searches all namespaces by default.

    \b
    Examples:
      memoir recall "user preferences"
      memoir recall "meeting notes" -n calendar -l 5
      memoir recall "programming languages" --threshold 0.5
      memoir recall "testing setup" --mode tiered
      memoir recall "..." --model gpt-4o-mini

    \b
    JSON output includes: memories[{path, content, score}], timing_ms
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd into a memoir store.",
            EXIT_NO_STORE,
        )

    from memoir.services.branch_service import BranchService
    from memoir.services.memory_service import MemoryService

    service = MemoryService(ctx.store_path, llm_model=model)
    branch_service = BranchService(ctx.store_path)

    try:
        with branch_service.routed_to(branch, auto_create=False):
            result = asyncio.run(
                service.recall(query, limit=limit, namespace=namespace, mode=mode)
            )

        if ctx.json_output:
            ctx.output(result.to_dict())
        else:
            if not result.memories:
                click.echo("No memories found.")
            else:
                for i, memory in enumerate(result.memories, 1):
                    # `result.memories` is a list[Memory] (dataclass at
                    # services/models.py:57) — fields are `relevance_score`,
                    # `path`, `content`. Use attribute access; the prior
                    # `memory.get(...)` form crashed with "'Memory' object has
                    # no attribute 'get'" and looked up wrong keys anyway.
                    score = memory.relevance_score
                    if score < threshold:
                        continue

                    path = memory.path or "unknown"
                    content = memory.content

                    # Truncate content for display
                    if isinstance(content, dict):
                        content = json.dumps(content)
                    if len(str(content)) > 100:
                        content = str(content)[:100] + "..."

                    click.echo(click.style(f"[{i}] ", fg="blue") + path)
                    click.echo(f"    {content}")
                    if ctx.verbose and score:
                        click.echo(f"    Score: {score:.3f}")

                click.echo(
                    f"\nFound {len(result.memories)} memories in {result.timing_ms:.1f}ms"
                )
    except Exception as e:
        ctx.error(f"Failed to recall: {e}", EXIT_ERROR)


@click.command("get")
@click.argument("keys", nargs=-1, required=True)
@click.option("-n", "--namespace", default="default", help="Memory namespace")
@click.option(
    "--branch",
    "branch",
    envvar="MEMOIR_BRANCH",
    default=None,
    help=(
        "Read from a specific branch without changing the store's checked-out "
        "branch (per-call routing for multi-agent setups; env: MEMOIR_BRANCH). "
        "Errors if the branch doesn't exist."
    ),
)
@pass_context
def get_memory(ctx: MemoirContext, keys: tuple, namespace: str, branch: str | None):
    """Fast direct lookup of memories by key. No LLM involved.

    INPUT: One or more exact taxonomy paths (space-separated).
    OUTPUT: Stored value for each key. Missing keys report found=false.

    This is the fast shortcut for reading memories when you already know the
    path — skips the LLM classifier and semantic search that `recall` uses.
    Typical latency is <10ms vs ~500-800ms for `recall`.

    \b
    Examples:
      memoir get preferences.coding.style
      memoir get preferences.coding.style profile.professional.skills
      memoir get "user.preferences.theme" -n default
      memoir --json get preferences.coding.style   # JSON output

    \b
    JSON output includes: items[{key, namespace, full_key, found, value}],
    count, found_count, timing_ms
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd into a memoir store.",
            EXIT_NO_STORE,
        )

    from memoir.services.branch_service import BranchService
    from memoir.services.memory_service import MemoryService

    service = MemoryService(ctx.store_path)
    branch_service = BranchService(ctx.store_path)

    try:
        with branch_service.routed_to(branch, auto_create=False):
            result = service.get(list(keys), namespace)

        if ctx.json_output:
            ctx.output(result.to_dict())
            return

        if not result.success:
            ctx.error(result.error or "Get failed", EXIT_ERROR)

        any_missing = False
        for item in result.items:
            full_key = item["full_key"]
            if item["found"]:
                value = item["value"]
                content = value.get("content") if isinstance(value, dict) else value
                click.echo(click.style("✓ ", fg="green") + full_key)
                if isinstance(content, (dict, list)):
                    click.echo(f"  {json.dumps(content)}")
                else:
                    click.echo(f"  {content}")
                if ctx.verbose and isinstance(value, dict):
                    for k in ("confidence", "timestamp"):
                        if k in value:
                            click.echo(f"  {k}: {value[k]}")
            else:
                any_missing = True
                click.echo(click.style("✗ ", fg="red") + f"{full_key} (not found)")

        click.echo(
            f"\n{sum(1 for i in result.items if i['found'])}/{len(result.items)} "
            f"found in {result.timing_ms:.1f}ms"
        )

        if any_missing and len(result.items) == 1:
            # Single-key miss: exit with not-found code so agents can branch on it.
            sys.exit(EXIT_NOT_FOUND)

    except Exception as e:
        ctx.error(f"Failed to get: {e}", EXIT_ERROR)


@click.command()
@click.argument("key")
@click.option("-n", "--namespace", default="default", help="Memory namespace")
@click.option("--force", is_flag=True, help="Skip confirmation (required for agents)")
@click.option(
    "--branch",
    "branch",
    envvar="MEMOIR_BRANCH",
    default=None,
    help=(
        "Delete from a specific branch without changing the store's checked-out "
        "branch (per-call routing for multi-agent setups; env: MEMOIR_BRANCH). "
        "Errors if the branch doesn't exist."
    ),
)
@pass_context
def forget(
    ctx: MemoirContext, key: str, namespace: str, force: bool, branch: str | None
):
    """Delete a memory by its key/path.

    INPUT: The exact key/path of the memory to delete (from recall results).
    OUTPUT: Confirmation of deletion with commit hash.

    Removes the memory and commits the change. Use --force to skip
    confirmation prompt (recommended for agents).

    \b
    Examples:
      memoir forget "user.preferences.theme" --force
      memoir forget "old-note" -n archive --force

    \b
    JSON output includes: success, key, commit_hash
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd into a memoir store.",
            EXIT_NO_STORE,
        )

    # Confirm unless --force is used
    if (
        not force
        and not ctx.json_output
        and not click.confirm(f"Delete memory '{key}' from namespace '{namespace}'?")
    ):
        ctx.info("Cancelled.")
        return

    from memoir.services.branch_service import BranchService
    from memoir.services.memory_service import MemoryService

    service = MemoryService(ctx.store_path)
    branch_service = BranchService(ctx.store_path)

    try:
        with branch_service.routed_to(branch, auto_create=False):
            result = asyncio.run(service.forget(key, namespace))

        if ctx.json_output:
            ctx.output(result.to_dict())
        else:
            if result.success:
                ctx.success(f"Deleted: {result.key}")
                if result.commit_hash:
                    click.echo(f"  Commit: {result.commit_hash[:8]}")
            else:
                if result.error and "not found" in result.error.lower():
                    ctx.error(f"Memory not found: {key}", EXIT_NOT_FOUND)
                else:
                    ctx.error(result.error or f"Failed to delete: {key}", EXIT_ERROR)
    except Exception as e:
        ctx.error(f"Failed to forget: {e}", EXIT_ERROR)

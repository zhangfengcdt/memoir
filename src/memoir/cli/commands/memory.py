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
@click.option("-n", "--namespace", default="default", help="Memory namespace")
@click.option(
    "-p",
    "--path",
    "paths",
    multiple=True,
    help=(
        "Pre-classified taxonomy path (e.g. 'preferences.coding.languages'). "
        "When given, skips memoir's LLM classifier entirely and stores at this "
        "path directly. Pass -p multiple times to write the same content to "
        "several paths in one call; each blob's `related_keys` field will list "
        "the other sibling paths (excluding self). Use for bulk imports or when "
        "the caller has already classified the content."
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
@pass_context
def remember(
    ctx: MemoirContext, content: str, namespace: str, paths: tuple, model: str | None
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
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.memory_service import MemoryService

    service = MemoryService(ctx.store_path, llm_model=model)
    paths_list = list(paths) if paths else None

    try:
        result = asyncio.run(service.remember(content, namespace, paths=paths_list))

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
@pass_context
def recall(
    ctx: MemoirContext,
    query: str,
    namespace: str,
    limit: int,
    threshold: float,
    mode: str,
    model: str | None,
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
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.memory_service import MemoryService

    service = MemoryService(ctx.store_path, llm_model=model)

    try:
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
                    score = memory.get("score", memory.get("relevance", 0))
                    if score < threshold:
                        continue

                    path = memory.get("path", memory.get("key", "unknown"))
                    content = memory.get("content", memory.get("value", ""))

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
@pass_context
def get_memory(ctx: MemoirContext, keys: tuple, namespace: str):
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
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.memory_service import MemoryService

    service = MemoryService(ctx.store_path)

    try:
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
@pass_context
def forget(ctx: MemoirContext, key: str, namespace: str, force: bool):
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
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    # Confirm unless --force is used
    if (
        not force
        and not ctx.json_output
        and not click.confirm(f"Delete memory '{key}' from namespace '{namespace}'?")
    ):
        ctx.info("Cancelled.")
        return

    from memoir.services.memory_service import MemoryService

    service = MemoryService(ctx.store_path)

    try:
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

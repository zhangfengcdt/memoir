# SPDX-License-Identifier: Apache-2.0
"""Memoir `search` CLI command — vector top-k semantic search.

Distinct from ``memoir recall``: recall is the LLM-driven semantic retrieval
that has shipped for a while; ``search`` is the new vector-index path written
on top of prollytree's text-index API, and is currently populated only by
``memoir watch``.
"""

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_NO_STORE,
    MemoirContext,
    pass_context,
)


@click.command("search")
@click.argument("query")
@click.option(
    "-n",
    "--namespace",
    default="watch",
    show_default=True,
    help="Search inside this namespace. Defaults to 'watch' since `memoir watch` writes there.",
)
@click.option(
    "-k",
    "--top-k",
    "top_k",
    default=5,
    show_default=True,
    type=int,
    help="Number of hits to return.",
)
@click.option(
    "--branch",
    "branch",
    envvar="MEMOIR_BRANCH",
    default=None,
    help=(
        "Search a specific branch without changing the store's checked-out "
        "branch (per-call routing for multi-agent setups; env: MEMOIR_BRANCH). "
        "Errors if the branch doesn't exist."
    ),
)
@pass_context
def search(
    ctx: MemoirContext, query: str, namespace: str, top_k: int, branch: str | None
):
    """Vector top-k semantic search over watch-indexed memories.

    Today the vector index is populated by `memoir watch`; entries written
    via `memoir remember` are not indexed for vector search and will not
    appear here. Scores are distances — lower means closer to the query.

    \b
    Examples:
      memoir search "async patterns in python"
      memoir search "transformer architecture" -k 10 -n research
      memoir search "..." --json
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd "
            "into a memoir store.",
            EXIT_NO_STORE,
        )

    from memoir.services.branch_service import BranchService
    from memoir.services.search_service import SearchService

    try:
        with BranchService(ctx.store_path).routed_to(branch, auto_create=False):
            result = SearchService(ctx.store_path).search(
                query, namespace=namespace, k=top_k
            )
    except Exception as e:
        ctx.error(f"search failed: {e}", EXIT_ERROR)
        return

    if ctx.json_output:
        ctx.output(result.to_dict())
        return

    if not result.success:
        ctx.error(result.error or "search failed", EXIT_ERROR)
        return

    if not result.hits:
        click.echo(f'No matches for "{query}" in namespace "{namespace}".')
        return

    for i, hit in enumerate(result.hits, start=1):
        click.echo(
            click.style(f"[{i}] ", fg="cyan")
            + f"{hit.key} "
            + click.style(f"(score: {hit.score:.4f})", fg="bright_black")
        )
        if hit.source and isinstance(hit.source, dict) and hit.source.get("abs_path"):
            click.echo(f"    {hit.source['abs_path']}")
        preview = (hit.content or "").strip().replace("\n", " ")
        if len(preview) > 200:
            preview = preview[:200] + "..."
        if preview:
            click.echo(f"    {preview}")
    click.echo()
    click.echo(
        f"Found {len(result.hits)} {'memory' if len(result.hits) == 1 else 'memories'} "
        f"in {result.timing_ms:.1f}ms"
    )

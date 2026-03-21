"""
Analysis commands for memoir CLI.

Commands: summarize
"""

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_NO_STORE,
    MemoirContext,
    pass_context,
)


@click.command()
@click.argument("summary_type", required=False, default="all")
@click.option("-n", "--namespace", help="Summarize specific namespace only")
@click.option("--keys", "key_pattern", help="Summarize keys matching pattern")
@pass_context
def summarize(ctx: MemoirContext, summary_type: str, namespace: str, key_pattern: str):
    """Summarize memories in the store.

    Summary types: all, taxonomy, timeline, places

    \b
    Examples:
      memoir summarize                    # Full summary
      memoir summarize taxonomy           # Taxonomy breakdown
      memoir summarize -n default         # Summarize 'default' namespace
      memoir summarize --keys profile.*   # Keys matching pattern
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.store_service import StoreService

    service = StoreService(ctx.store_path)

    try:
        data = service.read_store()
        all_namespaces = data.get("namespaces", {})

        # Filter by namespace if specified
        if namespace:
            if namespace in all_namespaces:
                namespaces = {namespace: all_namespaces[namespace]}
            else:
                available = ", ".join(all_namespaces.keys()) or "(none)"
                ctx.error(
                    f"Namespace '{namespace}' not found. Available: {available}",
                    EXIT_ERROR,
                )
        else:
            namespaces = all_namespaces

        total_memories = sum(len(keys) for keys in namespaces.values())

        if ctx.json_output:
            result = {
                "type": summary_type,
                "namespace_filter": namespace,
                "total_namespaces": len(namespaces),
                "total_memories": total_memories,
                "namespaces": {ns: len(keys) for ns, keys in namespaces.items()},
            }
            if key_pattern:
                # Filter keys by pattern
                import fnmatch

                matching = {}
                for ns, keys in namespaces.items():
                    matches = [k for k in keys if fnmatch.fnmatch(k, key_pattern)]
                    if matches:
                        matching[ns] = matches
                result["matching_keys"] = matching
            ctx.output(result)
        else:
            header = f"Memory Summary ({summary_type})"
            if namespace:
                header += f" - namespace: {namespace}"
            click.echo(f"\n{header}:")
            click.echo(f"  Total namespaces: {len(namespaces)}")
            click.echo(f"  Total memories: {total_memories}")

            if summary_type in ("all", "taxonomy"):
                click.echo("\n  By namespace:")
                for ns, keys in sorted(namespaces.items()):
                    click.echo(f"    {ns}: {len(keys)} memories")

            if key_pattern:
                import fnmatch

                click.echo(f"\n  Keys matching '{key_pattern}':")
                for ns, keys in namespaces.items():
                    matches = [k for k in keys if fnmatch.fnmatch(k, key_pattern)]
                    for key in matches[:10]:
                        click.echo(f"    {ns}/{key}")
                    if len(matches) > 10:
                        click.echo(f"    ... and {len(matches) - 10} more")

            click.echo()

    except Exception as e:
        ctx.error(f"Summarize failed: {e}", EXIT_ERROR)

# SPDX-License-Identifier: Apache-2.0
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
@click.option(
    "--depth",
    type=int,
    default=None,
    help="Group keys by first N taxonomy segments and return counts (N >= 1)",
)
@pass_context
def summarize(
    ctx: MemoirContext,
    summary_type: str,
    namespace: str,
    key_pattern: str,
    depth: int,
):
    """Summarize memories in the store.

    Summary types: all, taxonomy, timeline, places

    \b
    Examples:
      memoir summarize                       # Full summary
      memoir summarize taxonomy              # Taxonomy breakdown
      memoir summarize -n default            # Summarize 'default' namespace
      memoir summarize --keys profile.*      # Keys matching pattern
      memoir summarize --depth 1             # Group by top-level prefix
      memoir summarize --keys profile.* --depth 2   # Pattern filter, then group
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    if depth is not None and depth < 1:
        ctx.error("--depth must be >= 1", EXIT_ERROR)

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

        def _filter_keys(keys):
            if not key_pattern:
                return list(keys)
            import fnmatch

            return [k for k in keys if fnmatch.fnmatch(k, key_pattern)]

        def _group_by_depth(keys, n):
            counts: dict[str, int] = {}
            for key in keys:
                segments = key.split(".")
                prefix = ".".join(segments[:n]) if len(segments) >= n else key
                counts[prefix] = counts.get(prefix, 0) + 1
            return dict(sorted(counts.items()))

        if ctx.json_output:
            result = {
                "type": summary_type,
                "namespace_filter": namespace,
                "total_namespaces": len(namespaces),
                "total_memories": total_memories,
                "namespaces": {ns: len(keys) for ns, keys in namespaces.items()},
            }
            if key_pattern:
                matching = {}
                for ns, keys in namespaces.items():
                    matches = _filter_keys(keys)
                    if matches:
                        matching[ns] = matches
                result["matching_keys"] = matching
            if depth is not None:
                prefix_counts = {}
                for ns, keys in namespaces.items():
                    scoped = _filter_keys(keys)
                    if scoped:
                        prefix_counts[ns] = _group_by_depth(scoped, depth)
                result["depth"] = depth
                result["prefix_counts"] = prefix_counts
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

            if key_pattern and depth is None:
                click.echo(f"\n  Keys matching '{key_pattern}':")
                for ns, keys in namespaces.items():
                    matches = _filter_keys(keys)
                    for key in matches[:10]:
                        click.echo(f"    {ns}/{key}")
                    if len(matches) > 10:
                        click.echo(f"    ... and {len(matches) - 10} more")

            if depth is not None:
                scope = f" matching '{key_pattern}'" if key_pattern else ""
                click.echo(f"\n  Prefix counts (depth={depth}){scope}:")
                for ns, keys in sorted(namespaces.items()):
                    scoped = _filter_keys(keys)
                    if not scoped:
                        continue
                    click.echo(f"    {ns}:")
                    for prefix, count in _group_by_depth(scoped, depth).items():
                        click.echo(f"      {prefix}: {count}")

            click.echo()

    except Exception as e:
        ctx.error(f"Summarize failed: {e}", EXIT_ERROR)

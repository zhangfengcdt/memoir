"""
Analysis commands for memoir CLI.

Commands: summarize, timeline, location
"""

import asyncio

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_NO_STORE,
    MemoirContext,
    pass_context,
)


@click.command()
@click.argument("summary_type", required=False, default="all")
@click.option("--keys", "key_pattern", help="Summarize keys matching pattern")
@pass_context
def summarize(ctx: MemoirContext, summary_type: str, key_pattern: str):
    """Summarize memories in the store.

    Summary types: all, taxonomy, timeline, places

    \b
    Examples:
      memoir summarize                    # Full summary
      memoir summarize taxonomy           # Taxonomy breakdown
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
        namespaces = data.get("namespaces", {})
        total_memories = sum(len(keys) for keys in namespaces.values())

        if ctx.json_output:
            result = {
                "type": summary_type,
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
            click.echo(f"\nMemory Summary ({summary_type}):")
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


@click.command()
@click.argument("event", required=False)
@click.option("-d", "--date", help="Date for event (YYYY-MM-DD)")
@click.option("-n", "--limit", default=20, help="Maximum events to show")
@pass_context
def timeline(ctx: MemoirContext, event: str, date: str, limit: int):
    """Show or add timeline events.

    Without arguments, shows recent timeline events.
    With an event argument, adds a new timeline event.

    \b
    Examples:
      memoir timeline                        # Show timeline
      memoir timeline "Started new project"  # Add event
      memoir timeline "Meeting" -d 2024-01-15
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    try:
        if event:
            # Add timeline event
            from memoir.services.memory_service import MemoryService

            service = MemoryService(ctx.store_path)

            content = "Timeline event"
            if date:
                content += f" on {date}"
            content += f": {event}"

            result = asyncio.run(service.remember(content, "timeline"))

            if ctx.json_output:
                ctx.output(
                    {
                        "success": result.success,
                        "key": result.key,
                        "date": date,
                        "event": event,
                    }
                )
            else:
                if result.success:
                    ctx.success(f"Added timeline event: {event}")
                    if date:
                        click.echo(f"  Date: {date}")
                else:
                    ctx.error(f"Failed: {result.error}", EXIT_ERROR)
        else:
            # Show timeline
            from memoir.services.store_service import StoreService

            service = StoreService(ctx.store_path)
            data = service.read_store()

            timeline_ns = data.get("namespaces", {}).get("timeline", [])

            if ctx.json_output:
                ctx.output({"events": timeline_ns[:limit]})
            else:
                if not timeline_ns:
                    click.echo("No timeline events found.")
                else:
                    click.echo("\nTimeline:")
                    for evt in timeline_ns[:limit]:
                        click.echo(f"  - {evt}")
                    if len(timeline_ns) > limit:
                        click.echo(f"  ... and {len(timeline_ns) - limit} more")
                    click.echo()

    except Exception as e:
        ctx.error(f"Timeline operation failed: {e}", EXIT_ERROR)


@click.command()
@click.argument("place", required=False)
@click.option("-d", "--description", help="Description for the location")
@click.option("-n", "--limit", default=20, help="Maximum locations to show")
@pass_context
def location(ctx: MemoirContext, place: str, description: str, limit: int):
    """Show or add location events.

    Without arguments, shows recorded locations.
    With a place argument, adds a new location event.

    \b
    Examples:
      memoir location                           # Show locations
      memoir location "San Francisco"           # Add location
      memoir location "Office" -d "Main HQ"
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    try:
        if place:
            # Add location event
            from memoir.services.memory_service import MemoryService

            service = MemoryService(ctx.store_path)

            content = f"Location: {place}"
            if description:
                content += f" - {description}"

            result = asyncio.run(service.remember(content, "location"))

            if ctx.json_output:
                ctx.output(
                    {
                        "success": result.success,
                        "key": result.key,
                        "place": place,
                        "description": description,
                    }
                )
            else:
                if result.success:
                    ctx.success(f"Added location: {place}")
                    if description:
                        click.echo(f"  Description: {description}")
                else:
                    ctx.error(f"Failed: {result.error}", EXIT_ERROR)
        else:
            # Show locations
            from memoir.services.store_service import StoreService

            service = StoreService(ctx.store_path)
            data = service.read_store()

            location_ns = data.get("namespaces", {}).get("location", [])

            if ctx.json_output:
                ctx.output({"locations": location_ns[:limit]})
            else:
                if not location_ns:
                    click.echo("No location events found.")
                else:
                    click.echo("\nLocations:")
                    for loc in location_ns[:limit]:
                        click.echo(f"  - {loc}")
                    if len(location_ns) > limit:
                        click.echo(f"  ... and {len(location_ns) - limit} more")
                    click.echo()

    except Exception as e:
        ctx.error(f"Location operation failed: {e}", EXIT_ERROR)

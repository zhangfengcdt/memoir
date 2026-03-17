"""
Store commands for memoir CLI.

Commands: new, connect, status, refresh
"""

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_GIT_FAILED,
    EXIT_NO_STORE,
    MemoirContext,
    pass_context,
    save_default_store,
)


@click.command()
@click.argument("path")
@click.option(
    "--connect/--no-connect", default=True, help="Set as default store after creation"
)
@pass_context
def new(ctx: MemoirContext, path: str, connect: bool):
    """Create a new memory store.

    Creates a git-initialized memory store at PATH.

    \b
    Examples:
      memoir new /tmp/memories
      memoir new ~/ai-memories --no-connect
    """
    from memoir.services.store_service import StoreService

    service = StoreService()
    result = service.create_store(path)

    if result.success:
        if connect:
            save_default_store(result.path)
            ctx.success(
                f"Created and connected to {result.path}", {"path": result.path}
            )
        else:
            ctx.success(f"Created store at {result.path}", {"path": result.path})
    else:
        ctx.error(result.error or "Failed to create store", EXIT_GIT_FAILED)


@click.command()
@click.argument("path")
@pass_context
def connect(ctx: MemoirContext, path: str):
    """Connect to an existing memory store.

    Sets PATH as the default store for subsequent commands.

    \b
    Examples:
      memoir connect /tmp/memories
      memoir connect ~/ai-memories
    """
    from pathlib import Path

    from memoir.services.store_service import StoreService

    # Validate the path exists and is a valid store
    store_path = Path(path).expanduser().resolve()

    if not store_path.exists():
        ctx.error(f"Path does not exist: {store_path}", EXIT_NO_STORE)

    if not (store_path / ".git").exists():
        ctx.error(f"Not a valid memoir store (no .git): {store_path}", EXIT_NO_STORE)

    # Save as default
    save_default_store(str(store_path))

    # Get status info
    service = StoreService(str(store_path))
    info = service.get_status()

    if ctx.json_output:
        ctx.output(info.to_dict())
    else:
        ctx.success(f"Connected to {store_path}")
        if info.branch:
            ctx.info(f"Branch: {info.branch}")
        if info.memory_count is not None:
            ctx.info(f"Memories: {info.memory_count}")


@click.command()
@pass_context
def status(ctx: MemoirContext):
    """Show status of the connected memory store.

    Displays branch, memory count, and other store information.

    \b
    Examples:
      memoir status
      memoir --json status
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.store_service import StoreService

    service = StoreService(ctx.store_path)
    info = service.get_status()

    if ctx.json_output:
        ctx.output(info.to_dict())
    else:
        click.echo(f"Store: {info.path}")
        click.echo(
            f"Status: {'Initialized' if info.initialized else 'Not initialized'}"
        )
        if info.branch:
            click.echo(f"Branch: {info.branch}")
        if info.commit_count is not None:
            click.echo(f"Commits: {info.commit_count}")
        if info.memory_count is not None:
            click.echo(f"Memories: {info.memory_count}")
        if info.namespaces:
            click.echo(f"Namespaces: {', '.join(info.namespaces)}")


@click.command()
@pass_context
def refresh(ctx: MemoirContext):
    """Refresh the memory store.

    Re-reads store data and updates internal caches.

    \b
    Examples:
      memoir refresh
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.store_service import StoreService

    try:
        service = StoreService(ctx.store_path)
        data = service.read_store()

        if ctx.json_output:
            ctx.output({"success": True, "data": data})
        else:
            memory_count = data.get("statistics", {}).get("total_keys", 0)
            ns_count = data.get("statistics", {}).get("namespace_count", 0)
            ctx.success(f"Refreshed: {memory_count} memories in {ns_count} namespaces")
    except Exception as e:
        ctx.error(f"Failed to refresh: {e}", EXIT_ERROR)

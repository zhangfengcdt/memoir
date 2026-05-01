# SPDX-License-Identifier: Apache-2.0
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
@click.option(
    "--taxonomy-builtin",
    is_flag=True,
    default=False,
    help="Initialize with builtin taxonomy (classification examples, descriptions, presets)",
)
@click.option(
    "-t",
    "--taxonomy",
    "taxonomy_paths",
    multiple=True,
    type=click.Path(exists=True),
    help="External taxonomy markdown file(s) to load",
)
@pass_context
def new(
    ctx: MemoirContext,
    path: str,
    connect: bool,
    taxonomy_builtin: bool,
    taxonomy_paths: tuple,
):
    """Create a new memory store.

    INPUT: Path where the store should be created (will create directory).
    OUTPUT: Confirmation with store path.

    Creates a git-initialized memory store at PATH. By default, also
    sets it as the default store (use --no-connect to skip).

    Optionally initialize with taxonomy data for classification:
      --taxonomy-builtin loads the builtin taxonomy (~215 examples)
      -t/--taxonomy loads external markdown taxonomy files

    \b
    Examples:
      memoir new /tmp/my-agent-memory
      memoir new ~/memories --no-connect
      memoir new ~/memories --taxonomy-builtin
      memoir new ~/memories --taxonomy-builtin -t custom.md

    \b
    JSON output includes: path, success, taxonomy_loaded
    """
    from memoir.services.store_service import StoreService

    service = StoreService()
    result = service.create_store(path)

    if not result.success:
        ctx.error(result.error or "Failed to create store", EXIT_GIT_FAILED)
        return

    taxonomy_result = None

    # Initialize taxonomy if requested
    if taxonomy_builtin or taxonomy_paths:
        from memoir.taxonomy.loader import TaxonomyLoader

        try:
            # Re-open the store for taxonomy loading
            from memoir.store.prolly_adapter import ProllyTreeStore

            store = ProllyTreeStore(result.path)
            loader = TaxonomyLoader(store)
            taxonomy_result = loader.init_store(
                include_builtin=taxonomy_builtin,
                external_paths=list(taxonomy_paths),
            )
            ctx.info(f"Loaded taxonomy: {taxonomy_result}")
        except Exception as e:
            ctx.warn(f"Failed to initialize taxonomy: {e}")

    if connect:
        save_default_store(result.path)

    output_data = {"path": result.path}
    if taxonomy_result:
        output_data["taxonomy_loaded"] = taxonomy_result

    if connect:
        ctx.success(f"Created and connected to {result.path}", output_data)
    else:
        ctx.success(f"Created store at {result.path}", output_data)


@click.command()
@click.argument("path")
@pass_context
def connect(ctx: MemoirContext, path: str):
    """Connect to an existing memory store.

    INPUT: Path to an existing memoir store (must have .git directory).
    OUTPUT: Store status info (branch, memory count).

    Sets PATH as the default store for subsequent commands. This is
    saved to ~/.config/memoir/config.json. Alternative: set MEMOIR_STORE env var.

    \b
    Examples:
      memoir connect /tmp/memories
      memoir connect ~/ai-memories

    \b
    JSON output includes: path, branch, memory_count, namespaces
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

    INPUT: None (uses connected store).
    OUTPUT: Store info including path, branch, memory count, namespaces.

    Use this to verify connection and check store health before operations.

    \b
    Examples:
      memoir status
      memoir status --json

    \b
    JSON output includes: path, initialized, branch, commit_count, memory_count, namespaces
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

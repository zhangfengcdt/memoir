# SPDX-License-Identifier: Apache-2.0
"""Memoir `watch` CLI group: ingest files / folders into memoir.

Commands:
- ``memoir watch add <path>``        register + initial scan
- ``memoir watch list``              show registered paths
- ``memoir watch scan [path]``       re-scan one or all
- ``memoir watch remove <path>``     unregister (``--purge`` deletes indexed entries)
- ``memoir watch status <path>``     per-path status
- ``memoir watch formats``           list supported file extensions
"""

import asyncio

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_NO_STORE,
    EXIT_NOT_FOUND,
    MemoirContext,
    pass_context,
)


@click.group()
def watch():
    """Ingest single files into memoir.

    Watch parses each file (PDFs, markdown, docx, html, ...) with markitdown,
    classifies and stores the content via the existing memoir pipeline, and
    indexes it for semantic search. Only single files are supported — folders
    are rejected; add each file individually.

    \b
    Examples:
      memoir watch add paper.pdf -n research
      memoir watch list
      memoir watch scan paper.pdf
      memoir watch remove paper.pdf --purge
    """


@watch.command("add")
@click.argument("path", type=click.Path(exists=False))
@click.option(
    "-n",
    "--namespace",
    default="watch",
    show_default=True,
    help="Target namespace for the stored memories.",
)
@click.option(
    "--model",
    "model",
    default=None,
    help=(
        "LLM model used for classification. Resolution: this flag → "
        "MEMOIR_LLM_MODEL env var → 'claude-haiku-4-5' default."
    ),
)
@pass_context
def watch_add(ctx: MemoirContext, path: str, namespace: str, model: str | None):
    """Register PATH (a single file) and run the initial scan.

    Folders are rejected — add each file individually. Re-running on the
    same path is idempotent: only files whose content hashes have changed
    get re-classified and re-indexed.
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd "
            "into a memoir store.",
            EXIT_NO_STORE,
        )

    from memoir.services.watch_service import WatchService

    progress = None if ctx.json_output else (lambda msg: click.echo(msg))
    if not ctx.json_output:
        click.echo(
            click.style("⚠ ", fg="yellow")
            + "This may take a while — each new or changed file is parsed and "
            "classified by an LLM."
        )
    service = WatchService(
        ctx.store_path, llm_model=model, progress=progress, verbose=ctx.verbose
    )
    try:
        result = asyncio.run(service.add(path, namespace=namespace))
    except KeyboardInterrupt:
        click.echo(click.style("\n⚠ ", fg="yellow") + "Scan interrupted — partial progress saved.")
        return
    except Exception as e:
        ctx.error(f"Failed to add watch: {e}", EXIT_ERROR)
        return

    if ctx.json_output:
        ctx.output(result.to_dict())
        return

    if not result.success:
        ctx.error(result.error or "watch add failed", EXIT_ERROR)
        return

    scan = result.scan
    if scan is not None:
        click.echo(
            click.style("✓ ", fg="green")
            + f"Watching {result.path} (namespace: {namespace})"
        )
        click.echo(
            f"  Indexed {scan.files_indexed} of {scan.files_seen} files "
            f"({scan.slices_indexed} slices total; "
            f"{scan.files_unchanged} unchanged, "
            f"{scan.files_deleted} deleted, "
            f"{scan.files_skipped_unsupported} unsupported, "
            f"{scan.files_skipped_size} oversize, "
            f"{scan.files_skipped_parse_error} parse errors)"
        )
        if scan.index_failures:
            click.echo(
                click.style("⚠ ", fg="yellow")
                + f"{scan.index_failures} vector-index failures "
                f"(data still committed; see logs)"
            )
        if scan.commit_hash:
            click.echo(f"  Commit: {scan.commit_hash[:8]}")


@watch.command("list")
@pass_context
def watch_list(ctx: MemoirContext):
    """Show all registered watch paths and per-path file counts."""
    if not ctx.store_path:
        ctx.error("No store configured.", EXIT_NO_STORE)

    from memoir.services.watch_service import WatchService

    result = WatchService(ctx.store_path).list()
    if ctx.json_output:
        ctx.output(result.to_dict())
        return
    if not result.success:
        ctx.error(result.error or "watch list failed", EXIT_ERROR)
        return
    if not result.entries:
        click.echo("(no paths registered — `memoir watch add <path>`)")
        return
    for e in result.entries:
        last = e.last_scan or "(never)"
        click.echo(
            f"{e.path}  [{e.kind}]  ns={e.namespace}  files={e.indexed_count}  "
            f"last_scan={last}"
        )


@watch.command("scan")
@click.argument("path", required=False)
@click.option(
    "-n",
    "--namespace",
    default=None,
    help="Override the namespace recorded at watch-add time.",
)
@click.option(
    "--model",
    "model",
    default=None,
    help=(
        "LLM model used for classification. Resolution: this flag → "
        "MEMOIR_LLM_MODEL env var → 'claude-haiku-4-5' default."
    ),
)
@pass_context
def watch_scan(
    ctx: MemoirContext, path: str | None, namespace: str | None, model: str | None
):
    """Re-scan PATH (or all registered paths if omitted)."""
    if not ctx.store_path:
        ctx.error("No store configured.", EXIT_NO_STORE)

    from memoir.services.watch_service import WatchService

    progress = None if ctx.json_output else (lambda msg: click.echo(msg))
    if not ctx.json_output:
        click.echo(
            click.style("⚠ ", fg="yellow")
            + "This may take a while — each new or changed file is parsed and "
            "classified by an LLM."
        )
    service = WatchService(
        ctx.store_path, llm_model=model, progress=progress, verbose=ctx.verbose
    )
    try:
        results = asyncio.run(service.scan(path=path, namespace=namespace))
    except KeyboardInterrupt:
        click.echo(click.style("\n⚠ ", fg="yellow") + "Scan interrupted — partial progress saved.")
        return
    except Exception as e:
        ctx.error(f"watch scan failed: {e}", EXIT_ERROR)
        return

    if ctx.json_output:
        ctx.output({"scans": [r.to_dict() for r in results]})
        return

    if not results:
        click.echo("(no paths registered — `memoir watch add <path>` first)")
        return

    for r in results:
        marker = (
            click.style("✓ ", fg="green") if r.success else click.style("✗ ", fg="red")
        )
        click.echo(marker + f"{r.path}")
        if r.error:
            click.echo(f"  error: {r.error}")
            continue
        click.echo(
            f"  Indexed {r.files_indexed} of {r.files_seen} files "
            f"({r.slices_indexed} slices total; "
            f"{r.files_unchanged} unchanged, "
            f"{r.files_deleted} deleted, "
            f"{r.files_skipped_unsupported} unsupported, "
            f"{r.files_skipped_size} oversize, "
            f"{r.files_skipped_parse_error} parse errors)"
        )
        if r.index_failures:
            click.echo(
                click.style("  ⚠ ", fg="yellow")
                + f"{r.index_failures} vector-index failures"
            )


@watch.command("remove")
@click.argument("path")
@click.option(
    "--purge",
    is_flag=True,
    default=False,
    help=(
        "Also delete every memory + vector-index entry that came from this "
        "path. Without --purge the path is just unregistered; existing "
        "indexed entries stay in the store."
    ),
)
@pass_context
def watch_remove(ctx: MemoirContext, path: str, purge: bool):
    """Unregister PATH. Use --purge to also delete its indexed memories."""
    if not ctx.store_path:
        ctx.error("No store configured.", EXIT_NO_STORE)

    from memoir.services.watch_service import WatchService

    result = WatchService(ctx.store_path).remove(path, purge=purge)
    if ctx.json_output:
        ctx.output(result.to_dict())
        return
    if not result.success:
        ctx.error(result.error or "watch remove failed", EXIT_NOT_FOUND)
        return
    click.echo(click.style("✓ ", fg="green") + f"Unregistered: {result.path}")
    if purge:
        click.echo(f"  Purged {result.files_removed} indexed entries.")


@watch.command("status")
@click.argument("path")
@pass_context
def watch_status(ctx: MemoirContext, path: str):
    """Show per-path stats: namespace, last scan, indexed count, recent files."""
    if not ctx.store_path:
        ctx.error("No store configured.", EXIT_NO_STORE)

    from memoir.services.watch_service import WatchService

    result = WatchService(ctx.store_path).status(path)
    if ctx.json_output:
        ctx.output(result.to_dict())
        return
    if not result.success:
        ctx.error(result.error or "watch status failed", EXIT_NOT_FOUND)
        return
    click.echo(f"Path:        {result.path}")
    click.echo(f"Kind:        {result.kind}")
    click.echo(f"Namespace:   {result.namespace}")
    click.echo(f"Added:       {result.added_at}")
    click.echo(f"Last scan:   {result.last_scan or '(never)'}")
    click.echo(f"Files:       {result.files_indexed} indexed")
    if result.recently_changed:
        click.echo("Recently changed:")
        for f in result.recently_changed[:10]:
            click.echo(f"  {f}")


@watch.command("formats")
@pass_context
def watch_formats(ctx: MemoirContext):
    """List file extensions watch can ingest."""
    from memoir.services.watch_service import supported_extensions

    exts = sorted(supported_extensions())
    if ctx.json_output:
        ctx.output({"extensions": exts, "count": len(exts)})
        return
    click.echo(f"{len(exts)} supported extensions:")
    for e in exts:
        click.echo(f"  {e}")

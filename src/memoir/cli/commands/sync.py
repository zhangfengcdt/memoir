# SPDX-License-Identifier: Apache-2.0
"""
Cloud sync commands for memoir CLI.

Commands: remote (add/show/remove), push, pull, fetch, clone

All of them are gated on ``MEMORY_API_KEY``. Without it memoir behaves
exactly as before (COMMUNITY tier) and these commands exit 1 with a
"requires MEMORY_API_KEY (PRO)" message.
"""

from collections.abc import Callable
from typing import Any

import click

from memoir.cli.main import EXIT_NO_STORE, MemoirContext, pass_context


def _require_cloud(ctx: MemoirContext) -> None:
    from memoir.services.sync_service import PRO_REQUIRED_MESSAGE, cloud_enabled

    if not cloud_enabled():
        ctx.error(PRO_REQUIRED_MESSAGE, 1)


def _require_store(ctx: MemoirContext) -> None:
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd into a memoir store.",
            EXIT_NO_STORE,
        )


def _run(ctx: MemoirContext, op: Callable[[], Any]) -> Any:
    """Run a service call, mapping ServiceError → ctx.error(code)."""
    from memoir.services.base import ServiceError
    from memoir.services.sync_service import redact

    try:
        return op()
    except ServiceError as e:
        ctx.error(redact(e.message), e.code)


def _service(ctx: MemoirContext):
    from memoir.services.sync_service import SyncService

    return SyncService(ctx.store_path or "")


# --------------------------------------------------------------------------
# remote
# --------------------------------------------------------------------------


@click.group()
def remote():
    """Link this store to a memoir-cloud store.

    \b
    Subcommands:
      memoir remote add <store_id> [--url <gateway>]
      memoir remote add --create [--name <name>]
      memoir remote show
      memoir remote remove

    Requires MEMORY_API_KEY. The key is never written to disk.
    """


@remote.command("add")
@click.argument("store_id", required=False)
@click.option("--create", is_flag=True, help="Create the cloud store first, then link")
@click.option("--name", help="Name for --create (default: store directory name)")
@click.option("--url", help="Gateway URL (default: MEMOIR_CLOUD_URL or production)")
@click.option("--force", is_flag=True, help="Replace an existing memoir-cloud remote")
@pass_context
def remote_add(
    ctx: MemoirContext,
    store_id: str | None,
    create: bool,
    name: str | None,
    url: str | None,
    force: bool,
):
    """Link the local store to a cloud store.

    INPUT: A cloud store id (str_...), or --create to make one.
    OUTPUT: Gateway, store id, and the cloud store summary.

    Verifies MEMORY_API_KEY against the gateway, verifies the store exists
    and belongs to you, then adds an ordinary git remote named
    `memoir-cloud` with URL <gateway>/sync/<store_id>.

    \b
    Examples:
      memoir remote add str_abc123
      memoir remote add --create --name "laptop memories"
      memoir remote add str_abc123 --url https://my-gateway.example

    \b
    JSON output includes: gateway, store_id, branch, store
    """
    _require_store(ctx)
    _require_cloud(ctx)
    if create and store_id:
        ctx.error("pass either <store_id> or --create, not both", 1)
    if not create and not store_id:
        ctx.error("store id required (or pass --create)", 1)

    service = _service(ctx)
    if create:
        info = _run(ctx, lambda: service.remote_create(name, url, force))
    else:
        info = _run(ctx, lambda: service.remote_add(store_id, url, force))

    ctx.success(
        f"linked to cloud store {info.store_id} at {info.gateway}", info.to_dict()
    )


@remote.command("show")
@pass_context
def remote_show(ctx: MemoirContext):
    """Show the configured cloud remote.

    INPUT: None.
    OUTPUT: Gateway, store id, current branch, cloud store summary.

    \b
    JSON output includes: gateway, store_id, branch, store
    """
    _require_store(ctx)
    _require_cloud(ctx)
    info = _run(ctx, lambda: _service(ctx).remote_show())
    if ctx.json_output:
        ctx.output(info.to_dict())
    else:
        click.echo(f"Gateway:  {info.gateway}")
        click.echo(f"Store id: {info.store_id}")
        click.echo(f"Branch:   {info.branch}")
        if info.store.get("name"):
            click.echo(f"Name:     {info.store['name']}")
        if info.store.get("created_at"):
            click.echo(f"Created:  {info.store['created_at']}")


@remote.command("remove")
@pass_context
def remote_remove(ctx: MemoirContext):
    """Unlink the cloud remote (local data is untouched).

    INPUT: None.
    OUTPUT: Confirmation.
    """
    _require_store(ctx)
    _require_cloud(ctx)
    store_id = _run(ctx, lambda: _service(ctx).remote_remove())
    ctx.success(f"removed cloud remote (was {store_id})", {"store_id": store_id})


# --------------------------------------------------------------------------
# push / fetch / pull / clone
# --------------------------------------------------------------------------


@click.command()
@click.option("-b", "--branch", help="Branch to push (default: current)")
@pass_context
def push(ctx: MemoirContext, branch: str | None):
    """Push a branch and its memory chunks to memoir-cloud.

    INPUT: Optional branch name (default: current branch).
    OUTPUT: Branch pushed, chunks uploaded / already present.

    Uploads every node file the cloud is missing first, and only then runs
    the git push. A chunk failure never results in a git push. Branches are
    fast-forward only: if the cloud is ahead, exit code 6 and a hint to run
    `memoir pull`. `cloud/*` branches are cloud-owned and cannot be pushed.

    \b
    Examples:
      memoir push
      memoir push --branch experiments

    \b
    JSON output includes: branch, chunks_uploaded, chunks_present, pushed
    """
    _require_store(ctx)
    _require_cloud(ctx)
    result = _run(ctx, lambda: _service(ctx).push(branch))
    ctx.success(
        f"pushed {result.branch} ({result.chunks_uploaded} new chunks, "
        f"{result.chunks_present} already present)",
        result.to_dict(),
    )


@click.command()
@pass_context
def fetch(ctx: MemoirContext):
    """Fetch cloud branches, tags, and missing memory chunks.

    INPUT: None.
    OUTPUT: Chunks downloaded and the remote refs now visible.

    Fetches refs/heads/* and refs/cloud/* (cloud proposal branches appear as
    memoir-cloud/cloud/...), then downloads every chunk not present locally.
    Does not move any local branch — use `memoir pull` for that.

    \b
    JSON output includes: chunks_downloaded, remote_refs
    """
    _require_store(ctx)
    _require_cloud(ctx)
    result = _run(ctx, lambda: _service(ctx).fetch())
    ctx.success(
        f"fetched {len(result.remote_refs)} remote refs, "
        f"{result.chunks_downloaded} new chunks",
        result.to_dict(),
    )


@click.command()
@click.option("-b", "--branch", help="Branch to pull (default: current)")
@pass_context
def pull(ctx: MemoirContext, branch: str | None):
    """Fetch and fast-forward a branch to the cloud tip.

    INPUT: Optional branch name (default: current branch).
    OUTPUT: Branch, new tip, chunks downloaded.

    Runs `memoir fetch`, then fast-forwards the branch (creating it from the
    cloud if it does not exist locally). Diverged histories are rejected with
    exit code 6 — cloud merge is a later feature.

    \b
    Examples:
      memoir pull
      memoir pull --branch experiments

    \b
    JSON output includes: branch, chunks_downloaded, created, tip
    """
    _require_store(ctx)
    _require_cloud(ctx)
    result = _run(ctx, lambda: _service(ctx).pull(branch))
    verb = "created" if result.created else "fast-forwarded"
    ctx.success(
        f"{verb} {result.branch} to {result.tip} "
        f"({result.chunks_downloaded} new chunks)",
        result.to_dict(),
    )


@click.command()
@click.argument("store_id")
@click.argument("path")
@click.option("--url", help="Gateway URL (default: MEMOIR_CLOUD_URL or production)")
@pass_context
def clone(ctx: MemoirContext, store_id: str, path: str, url: str | None):
    """Clone a cloud store into a new local memoir store.

    INPUT: Cloud store id (str_...) and a destination path.
    OUTPUT: Path, branch, chunks downloaded.

    Runs git clone against the gateway, marks the store as file-backed,
    downloads every chunk, and verifies the root chunk is present. The
    remote is named `memoir-cloud` so push/pull/fetch work immediately.

    \b
    Examples:
      memoir clone str_abc123 ~/memories
      export MEMOIR_STORE=~/memories && memoir recall "preferences"

    \b
    JSON output includes: path, store_id, branch, chunks_downloaded
    """
    _require_cloud(ctx)
    from memoir.services import sync_service

    result = _run(ctx, lambda: sync_service.clone(store_id, path, url))
    ctx.success(
        f"cloned {result.store_id} into {result.path} "
        f"({result.chunks_downloaded} chunks)",
        result.to_dict(),
    )
    if not ctx.json_output:
        ctx.info(f"To use this store: export MEMOIR_STORE={result.path}")

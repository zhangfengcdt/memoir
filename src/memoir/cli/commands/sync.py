# SPDX-License-Identifier: Apache-2.0
"""
Cloud sync commands for memoir CLI.

Commands: remote (add/show/remove), push, pull, fetch, clone

Cloud stores are addressed GitHub-style as ``<owner>/<store>``. All of these
commands are gated on ``MEMOIR_API_KEY``; without it memoir behaves exactly
as before (COMMUNITY tier) and they exit 1 with a "requires MEMOIR_API_KEY
(PRO)" message.
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
      memoir remote add [<owner>/<store>] [--url <gateway>] [--force]
      memoir remote show
      memoir remote remove

    To create a new cloud store and link it in one step, use
    `memoir push --create <store>`. Requires MEMOIR_API_KEY; the key is
    never written to disk.
    """


@remote.command("add")
@click.argument("address", required=False)
@click.option("--url", help="Gateway URL (default: MEMOIR_CLOUD_URL or production)")
@click.option("--force", is_flag=True, help="Replace an existing origin remote")
@pass_context
def remote_add(
    ctx: MemoirContext,
    address: str | None,
    url: str | None,
    force: bool,
):
    """Link the local store to an existing cloud store.

    INPUT: A cloud store address <owner>/<store>, or nothing to default to
    <your handle>/<store directory name> (confirmed before use).
    OUTPUT: The address and the cloud store summary.

    Verifies MEMOIR_API_KEY, resolves the address, and only then sets the
    git remote `origin` to https://<gateway>/<owner>/<store>.

    \b
    Examples:
      memoir remote add feng-zhang/demo
      memoir remote add                         # proposes <handle>/<dirname>
      memoir remote add feng-zhang/demo --url https://my-gateway.example

    \b
    JSON output includes: origin, gateway, branch, store
    """
    _require_store(ctx)
    _require_cloud(ctx)
    service = _service(ctx)

    if address is None:
        if ctx.json_output:
            ctx.error("an address (<owner>/<store>) is required with --json", 1)
        address = _run(ctx, lambda: service.default_address(url))
        if not click.confirm(f"Link this store to {address}?", default=True):
            ctx.error("aborted", 1)

    info = _run(ctx, lambda: service.remote_add(address, url, force))
    ctx.success(f"origin: {info.address}", info.to_dict())


@remote.command("show")
@pass_context
def remote_show(ctx: MemoirContext):
    """Show the configured cloud remote.

    INPUT: None.
    OUTPUT: Address, gateway, current branch, cloud store summary.

    \b
    JSON output includes: origin, gateway, branch, store
    """
    _require_store(ctx)
    _require_cloud(ctx)
    info = _run(ctx, lambda: _service(ctx).remote_show())
    if ctx.json_output:
        ctx.output(info.to_dict())
    else:
        click.echo(f"origin:   {info.address}")
        click.echo(f"Gateway:  {info.gateway}")
        click.echo(f"Branch:   {info.branch}")
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
    address = _run(ctx, lambda: _service(ctx).remote_remove())
    ctx.success(f"removed cloud remote (was {address})", {"origin": address})


# --------------------------------------------------------------------------
# push / fetch / pull / clone
# --------------------------------------------------------------------------


@click.command()
@click.option("-b", "--branch", help="Branch to push (default: current)")
@click.option(
    "--create",
    "create_name",
    metavar="<store>",
    help="Create a cloud store with this name, link it as origin, then push",
)
@click.option("--url", help="Gateway URL for --create (default: MEMOIR_CLOUD_URL)")
@pass_context
def push(
    ctx: MemoirContext, branch: str | None, create_name: str | None, url: str | None
):
    """Push a branch and its memory chunks to memoir-cloud.

    INPUT: Optional branch name (default: current branch). With
    --create <store>, first create that cloud store under your handle and
    link it as origin.
    OUTPUT: Address, branch pushed, chunks uploaded / already present.

    Uploads every node file the cloud is missing first, and only then runs
    the git push. A chunk failure never results in a git push. Branches are
    fast-forward only: if the cloud is ahead, exit code 6 and a hint to run
    `memoir pull`. `cloud/*` branches are cloud-owned and cannot be pushed.

    \b
    Examples:
      memoir push --create demo       # first time: creates <handle>/demo
      memoir push
      memoir push --branch experiments

    \b
    JSON output includes: origin, branch, chunks_uploaded, chunks_present, pushed
    """
    _require_store(ctx)
    _require_cloud(ctx)
    result = _run(ctx, lambda: _service(ctx).push(branch, create_name, url))
    ctx.success(
        f"pushed {result.branch} to {result.address} ({result.chunks_uploaded} "
        f"new chunks, {result.chunks_present} already present)",
        result.to_dict(),
    )


@click.command()
@pass_context
def fetch(ctx: MemoirContext):
    """Fetch cloud branches, tags, and missing memory chunks.

    INPUT: None.
    OUTPUT: Chunks downloaded and the remote refs now visible.

    Fetches refs/heads/* and refs/cloud/* (cloud proposal branches appear as
    origin/cloud/...), then downloads every chunk not present locally. Does
    not move any local branch — use `memoir pull` for that.

    \b
    JSON output includes: origin, chunks_downloaded, remote_refs
    """
    _require_store(ctx)
    _require_cloud(ctx)
    result = _run(ctx, lambda: _service(ctx).fetch())
    ctx.success(
        f"fetched {len(result.remote_refs)} remote refs, "
        f"{result.chunks_downloaded} new chunks from {result.address}",
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
    JSON output includes: origin, branch, chunks_downloaded, created, tip
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
@click.argument("address")
@click.argument("path", required=False)
@click.option("--url", help="Gateway URL (default: MEMOIR_CLOUD_URL or production)")
@pass_context
def clone(ctx: MemoirContext, address: str, path: str | None, url: str | None):
    """Clone a cloud store into a new local memoir store.

    INPUT: Cloud store address <owner>/<store> (a https://<gateway>/<owner>/<store>
    URL is accepted too) and an optional destination (default: the store name).
    OUTPUT: Path, branch, chunks downloaded.

    Resolves the address first (nothing is written for an unknown store), then
    runs git clone, marks the store file-backed, downloads every chunk, and
    verifies the root chunk is present. The remote is `origin`, so push, pull,
    and fetch work immediately.

    \b
    Examples:
      memoir clone feng-zhang/demo
      memoir clone feng-zhang/demo ~/memories
      export MEMOIR_STORE=~/memories && memoir recall "preferences"

    \b
    JSON output includes: path, origin, branch, chunks_downloaded
    """
    _require_cloud(ctx)
    from memoir.services import sync_service

    result = _run(ctx, lambda: sync_service.clone(address, path, url))
    ctx.success(
        f"cloned {result.address} into {result.path} "
        f"({result.chunks_downloaded} chunks)",
        result.to_dict(),
    )
    if not ctx.json_output:
        ctx.info(f"origin: {result.address}")
        ctx.info(f"To use this store: export MEMOIR_STORE={result.path}")

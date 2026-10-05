# SPDX-License-Identifier: Apache-2.0
"""
Cloud sync commands for memoir CLI.

Commands: login, logout, remote (add/show/remove), push, pull, fetch

Cloud stores are addressed GitHub-style as ``<owner>/<store>``. The cloud
commands need a key: ``memoir login`` saves one (``MEMOIR_API_KEY`` still
overrides it); without either memoir behaves exactly as before (COMMUNITY
tier) and they exit 1 asking for ``memoir login``.

In a code repo (repo mode) the store is the repo's ``~/.memoir/<slug>`` —
the one Claude Code uses — and ``remote add`` / ``pull`` create it on first
use, so ``memoir login`` then ``memoir push --create`` (or ``memoir remote
add <owner>/<store> && memoir pull``) is the whole setup.
"""

from collections.abc import Callable
from typing import Any

import click

from memoir.cli.main import EXIT_NO_STORE, MemoirContext, pass_context


def _require_cloud(ctx: MemoirContext) -> None:
    from memoir.services.sync_service import PRO_REQUIRED_MESSAGE, cloud_enabled

    if not cloud_enabled():
        ctx.error(PRO_REQUIRED_MESSAGE, 1)


def _require_store(ctx: MemoirContext, *, create: bool = False) -> None:
    """Check there is a store to work on. In repo mode, say which one, and
    with ``create`` make it on first use (``memoir new`` semantics, no
    taxonomy, so a following ``pull`` sees a pristine store and adopts the
    cloud history)."""
    if not ctx.store_path:
        ctx.error(
            "No store configured. Pass -s <path>, set MEMOIR_STORE, or cd into a memoir store.",
            EXIT_NO_STORE,
        )
    repo = ctx.repo
    if repo is None:
        return
    from memoir.store import repo_mode

    if not ctx.json_output and not ctx.quiet:
        click.echo(f"store: {repo_mode.display(repo.store)} (repo {repo.name})")
    if repo.store.exists():
        return
    if not create:
        ctx.error(
            f"no memoir store for repo {repo.name} yet ({repo_mode.display(repo.store)}); "
            "link a cloud store with `memoir remote add <owner>/<store> && memoir pull`, "
            "or start a Claude Code session here",
            EXIT_NO_STORE,
        )
    from memoir.services.store_service import StoreService

    result = StoreService().create_store(str(repo.store))
    if not result.success:
        ctx.error(result.error or "failed to create the store", EXIT_NO_STORE)
    ctx.info(f"created {repo_mode.display(repo.store)}")


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
      memoir remote add                         # proposes <handle>/<repo or dir name>
      memoir remote add feng-zhang/demo --url https://my-gateway.example

    \b
    JSON output includes: origin, gateway, branch, store
    """
    _require_cloud(ctx)
    if address is None and ctx.json_output:
        ctx.error("an address (<owner>/<store>) is required with --json", 1)
    _require_store(ctx, create=True)
    service = _service(ctx)

    if address is None:
        repo_name = ctx.repo.name if ctx.repo else None
        address = _run(ctx, lambda: service.default_address(url, name=repo_name))
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
    _require_cloud(ctx)
    _require_store(ctx)
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
    _require_cloud(ctx)
    _require_store(ctx)
    address = _run(ctx, lambda: _service(ctx).remote_remove())
    ctx.success(f"removed cloud remote (was {address})", {"origin": address})


# --------------------------------------------------------------------------
# push / fetch / pull
# --------------------------------------------------------------------------


@click.command()
@click.option("-b", "--branch", help="Branch to push (default: current)")
@click.option(
    "--create",
    "create_name",
    is_flag=False,
    flag_value="",
    default=None,
    metavar="[<store>]",
    help="Create a cloud store (default name: the code repo's, else the store "
    "directory's), link it as origin, then push",
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

    Uploads the node files the cloud is missing first (multipart batches of
    up to 500 chunks, 4 in flight), and only then runs the git push. A chunk
    failure never results in a git push. After a successful push the server-
    confirmed hashes are recorded under .git/memoir-cloud/, so the next push
    skips negotiation entirely and sends only new chunks. Branches are
    fast-forward only: if the cloud is ahead, exit code 6 and a hint to run
    `memoir pull`. `cloud/*` branches are cloud-owned and cannot be pushed.

    \b
    Examples:
      memoir push --create            # in a code repo: creates <handle>/<repo name>
      memoir push --create demo       # or name it
      memoir push
      memoir push --branch experiments

    \b
    JSON output includes: origin, branch, chunks_uploaded, chunks_present, pushed,
    seconds, chunk_seconds, git_seconds, bytes_sent, compressed
    """
    _require_cloud(ctx)
    _require_store(ctx)
    if create_name == "":
        from pathlib import Path

        create_name = ctx.repo.name if ctx.repo else Path(ctx.store_path or ".").name
    result = _run(ctx, lambda: _service(ctx).push(branch, create_name, url))
    ctx.success(
        f"pushed {result.branch} to {result.address}: "
        f"{result.chunks_uploaded + result.chunks_present:,} chunks "
        f"({result.chunks_uploaded:,} new{_sent(result)}) in "
        f"{result.chunk_seconds:.1f} s, git in {result.git_seconds:.1f} s",
        result.to_dict(),
    )


def _sent(result) -> str:
    """``, 1.2 MB sent (gzip)`` when chunk bytes went out, else nothing."""
    if not result.bytes_sent:
        return ""
    size = result.bytes_sent
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            break
        size /= 1000
    shown = f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
    return f", {shown} sent" + (" (gzip)" if result.compressed else "")


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
    _require_cloud(ctx)
    _require_store(ctx)
    result = _run(ctx, lambda: _service(ctx).fetch())
    ctx.success(
        f"fetched {len(result.remote_refs)} remote refs, "
        f"{result.chunks_downloaded} new chunks from {result.address}",
        result.to_dict(),
    )


@click.command()
@click.option("-b", "--branch", help="Branch to pull (default: current)")
@click.option(
    "--force",
    is_flag=True,
    help="Replace the local branch with the cloud copy, discarding local memories",
)
@pass_context
def pull(ctx: MemoirContext, branch: str | None, force: bool):
    """Fetch and fast-forward a branch to the cloud tip.

    INPUT: Optional branch name (default: current branch).
    OUTPUT: Branch, new tip, chunks downloaded.

    Runs `memoir fetch`, then fast-forwards the branch. A branch missing
    locally is created from the cloud; a never-used local store adopts the
    cloud history. Anything else that is not a fast-forward (both sides have
    commits the other lacks) is rejected with exit code 6 — cloud merge is a
    later feature. Pass --force to discard the local memories on that branch
    and take the cloud copy instead; the previous tip is kept under
    refs/memoir/backup/<branch> and printed.

    \b
    Examples:
      memoir pull
      memoir pull --branch experiments
      memoir pull --force              # local main := cloud main

    \b
    JSON output includes: origin, branch, chunks_downloaded, created, tip,
    forced, previous_tip, backup_ref
    """
    _require_cloud(ctx)
    _require_store(ctx, create=True)
    result = _run(ctx, lambda: _service(ctx).pull(branch, force))
    if result.forced:
        message = (
            f"replaced {result.branch} (was {result.previous_tip}, kept at "
            f"{result.backup_ref}) with origin/{result.branch} at {result.tip} "
            f"({result.chunks_downloaded} new chunks)"
        )
    else:
        verb = "created" if result.created else "fast-forwarded"
        message = (
            f"{verb} {result.branch} to {result.tip} "
            f"({result.chunks_downloaded} new chunks)"
        )
    ctx.success(message, result.to_dict())


# --------------------------------------------------------------------------
# login / logout
# --------------------------------------------------------------------------


@click.command()
@click.option("--url", help="Gateway URL (default: MEMOIR_CLOUD_URL, else production)")
@click.option(
    "--with-key",
    is_flag=True,
    help="Read an API key from stdin instead of approving in a browser (headless machines)",
)
@click.option(
    "--no-browser", is_flag=True, help="Print the approval link without opening it"
)
@pass_context
def login(ctx: MemoirContext, url: str | None, with_key: bool, no_browser: bool):
    """Log in to memoir-cloud and save a key for this machine.

    INPUT: Optional gateway (--url); with --with-key, an API key on stdin.
    OUTPUT: The gateway and handle you're logged in as (never the key).

    Starts a device approval like `gh auth login`: memoir prints a link and
    a short code, opens the browser, and waits while you click Authorize on
    the cloud (signed in there). The cloud mints a key named
    "memoir CLI (<hostname>)", visible and revocable on its keys page.
    The key, gateway and handle are saved to ~/.config/memoir/cloud.json
    (mode 0600). MEMOIR_API_KEY, when set, still overrides it.

    \b
    Examples:
      memoir login
      memoir login --url https://api-gateway-staging-3ce9.up.railway.app
      echo "$KEY" | memoir login --with-key

    \b
    JSON output includes: gateway, handle, config
    """
    import os
    import sys

    from memoir.services import cloud_auth
    from memoir.services.sync_service import (
        GATEWAY_ENV,
        CloudClient,
        redact,
    )

    gateway = (url or os.environ.get(GATEWAY_ENV) or _default_gateway()).rstrip("/")

    if with_key:
        key = sys.stdin.read().strip()
        if not key:
            ctx.error("no key on stdin", 1)
        from memoir.services.base import ServiceError

        try:
            with CloudClient(gateway, key) as client:
                handle = client.whoami().get("handle")
        except ServiceError as e:
            ctx.error(redact(e.message, key), 1)
        path = cloud_auth.save(gateway, key, handle)
    else:

        def show(start: dict) -> None:
            link = start.get("verification_url_complete") or start.get(
                "verification_url"
            )
            click.echo(
                f"Open {start.get('verification_url')} and enter {start.get('user_code')}"
                f"\n  (or go straight to {link})",
                err=ctx.json_output,
            )
            if not no_browser and link:
                import contextlib
                import webbrowser

                with contextlib.suppress(Exception):  # a missing browser is fine
                    webbrowser.open(link)
            click.echo("Waiting for approval in the browser…", err=ctx.json_output)

        try:
            got = cloud_auth.device_login(gateway, on_code=show)
        except cloud_auth.LoginError as e:
            ctx.error(str(e), 1)
        key, handle, gateway = got["api_key"], got.get("handle"), got["gateway"]
        path = cloud_auth.save(gateway, key, handle)

    if os.environ.get(GATEWAY_ENV) and os.environ[GATEWAY_ENV].rstrip("/") != gateway:
        ctx.warn(
            f"{GATEWAY_ENV} is set to a different gateway and will take precedence"
        )
    if os.environ.get("MEMOIR_API_KEY"):
        ctx.warn("MEMOIR_API_KEY is set and still overrides the saved key")
    ctx.success(
        f"logged in to {gateway} as {handle or '(no handle yet)'}",
        {"gateway": gateway, "handle": handle, "config": str(path)},
    )


def _default_gateway() -> str:
    from memoir.services import cloud_auth
    from memoir.services.sync_service import DEFAULT_GATEWAY

    return cloud_auth.saved_gateway() or DEFAULT_GATEWAY


@click.command()
@pass_context
def logout(ctx: MemoirContext):
    """Log out: revoke this machine's key on the cloud and delete it locally.

    INPUT: None.
    OUTPUT: Whether the key was revoked and the saved login removed.

    Revocation is best-effort (offline is fine); the local file is always
    removed. MEMOIR_API_KEY, if set in your shell, is not affected.
    """
    from memoir.services import cloud_auth

    saved = cloud_auth.load()
    if not saved:
        ctx.success("not logged in", {"revoked": False, "removed": False})
        return
    gateway = saved.get("gateway") or _default_gateway()
    revoked = cloud_auth.revoke(gateway, saved["api_key"])
    removed = cloud_auth.delete()
    note = (
        "key revoked"
        if revoked
        else "could not reach the cloud to revoke the key; revoke it on the keys page"
    )
    ctx.success(
        f"logged out of {gateway} ({note})", {"revoked": revoked, "removed": removed}
    )

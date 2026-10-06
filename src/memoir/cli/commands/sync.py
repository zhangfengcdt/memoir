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
            "link a cloud store with `memoir pull <owner>/<store>`, "
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


def _service(ctx: MemoirContext, remote: str = "origin"):
    from memoir.services.base import ServiceError
    from memoir.services.sync_service import SyncService

    try:
        return SyncService(ctx.store_path or "", remote)
    except ServiceError as e:
        ctx.error(e.message, e.code)


REMOTE_OPTION_HELP = "Cloud remote to use (default: origin); see `memoir remote list`"


# --------------------------------------------------------------------------
# remote
# --------------------------------------------------------------------------


@click.group()
def remote():
    """Link this store to a memoir-cloud store.

    \b
    Subcommands:
      memoir remote add [<owner>/<store>] [--name <remote>] [--url <gateway>] [--force]
      memoir remote list
      memoir remote show [<remote>]
      memoir remote remove [<remote>]

    A store can link to several cloud stores, like `git remote`: the default
    remote is `origin`; add others with --name (e.g. a staging copy) and pick
    one with `push/pull/fetch --remote <name>`. Each remote's requests carry
    the key saved for its own gateway (`memoir login --url <gateway>`).

    To create a new cloud store and link it in one step, use
    `memoir push --create <store>`.
    """


@remote.command("add")
@click.argument("address", required=False)
@click.option(
    "--name",
    "remote_name",
    default="origin",
    show_default=True,
    help="Name for this remote",
)
@click.option(
    "--url", help="Gateway URL (default: MEMOIR_CLOUD_URL, else the saved default)"
)
@click.option(
    "--force", is_flag=True, help="Replace an existing remote of the same name"
)
@pass_context
def remote_add(
    ctx: MemoirContext,
    address: str | None,
    remote_name: str,
    url: str | None,
    force: bool,
):
    """Link the local store to an existing cloud store.

    INPUT: A cloud store address <owner>/<store>, or nothing to default to
    <your handle>/<store directory name> (confirmed before use).
    OUTPUT: The address and the cloud store summary.

    Verifies the key for the gateway, resolves the address, and only then
    sets the git remote (default name `origin`) to
    https://<gateway>/<owner>/<store>.

    \b
    Examples:
      memoir remote add feng-zhang/demo
      memoir remote add                         # proposes <handle>/<repo or dir name>
      memoir remote add feng-zhang/demo --name staging --url https://staging.example

    \b
    JSON output includes: origin, gateway, branch, store
    """
    _require_cloud(ctx)
    if address is None and ctx.json_output:
        ctx.error("an address (<owner>/<store>) is required with --json", 1)
    _require_store(ctx, create=True)
    service = _service(ctx, remote_name)

    if address is None:
        repo_name = ctx.repo.name if ctx.repo else None
        address = _run(ctx, lambda: service.default_address(url, name=repo_name))
        if not click.confirm(f"Link this store to {address}?", default=True):
            ctx.error("aborted", 1)

    info = _run(ctx, lambda: service.remote_add(address, url, force))
    ctx.success(
        f"{remote_name}: {info.address}", {**info.to_dict(), "remote": remote_name}
    )


@remote.command("list")
@pass_context
def remote_list(ctx: MemoirContext):
    """List this store's cloud remotes.

    INPUT: None.
    OUTPUT: Each remote's name, address, gateway, and whether a key applies
    to that gateway (a login for it, or MEMOIR_API_KEY).

    \b
    JSON output includes: remotes[{name, address, gateway, logged_in}]
    """
    _require_store(ctx)
    rows = _service(ctx).list_remotes()
    if ctx.json_output:
        ctx.output({"remotes": rows})
        return
    if not rows:
        click.echo("no cloud remotes; run `memoir remote add <owner>/<store>`")
    for r in rows:
        state = "logged in" if r["logged_in"] else "not logged in"
        click.echo(f"{r['name']:<10} {r['address']:<32} {r['gateway']}  ({state})")


@remote.command("show")
@click.argument("remote_name", required=False, default="origin")
@pass_context
def remote_show(ctx: MemoirContext, remote_name: str):
    """Show the configured cloud remote.

    INPUT: None.
    OUTPUT: Address, gateway, current branch, cloud store summary.

    \b
    JSON output includes: origin, gateway, branch, store
    """
    _require_cloud(ctx)
    _require_store(ctx)
    info = _run(ctx, lambda: _service(ctx, remote_name).remote_show())
    if ctx.json_output:
        ctx.output({**info.to_dict(), "remote": remote_name})
    else:
        click.echo(f"{remote_name + ':':<9} {info.address}")
        click.echo(f"Gateway:  {info.gateway}")
        click.echo(f"Branch:   {info.branch}")
        if info.store.get("created_at"):
            click.echo(f"Created:  {info.store['created_at']}")


@remote.command("remove")
@click.argument("remote_name", required=False, default="origin")
@pass_context
def remote_remove(ctx: MemoirContext, remote_name: str):
    """Unlink the cloud remote (local data is untouched).

    INPUT: None.
    OUTPUT: Confirmation.
    """
    _require_cloud(ctx)
    _require_store(ctx)
    address = _run(ctx, lambda: _service(ctx, remote_name).remote_remove())
    ctx.success(
        f"removed cloud remote {remote_name} (was {address})",
        {"origin": address, "remote": remote_name},
    )


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
    "directory's), link it under --remote (default origin), then push",
)
@click.option("--url", help="Gateway URL for --create (default: MEMOIR_CLOUD_URL)")
@click.option("--remote", "remote_name", default="origin", help=REMOTE_OPTION_HELP)
@pass_context
def push(
    ctx: MemoirContext,
    branch: str | None,
    create_name: str | None,
    url: str | None,
    remote_name: str,
):
    """Push a branch and its memory chunks to memoir-cloud.

    INPUT: Optional branch name (default: current branch). With
    --create <store>, first create that cloud store under your handle and
    link it under --remote (default `origin`).
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
    result = _run(
        ctx, lambda: _service(ctx, remote_name).push(branch, create_name, url)
    )
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
@click.option("--remote", "remote_name", default="origin", help=REMOTE_OPTION_HELP)
@pass_context
def fetch(ctx: MemoirContext, remote_name: str):
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
    result = _run(ctx, lambda: _service(ctx, remote_name).fetch())
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
@click.option("--remote", "remote_name", default="origin", help=REMOTE_OPTION_HELP)
@click.option(
    "--url",
    help="Gateway for a remote that `pull <address>` creates "
    "(default: MEMOIR_CLOUD_URL, else the saved default)",
)
@click.argument("address", required=False)
@pass_context
def pull(
    ctx: MemoirContext,
    branch: str | None,
    force: bool,
    remote_name: str,
    url: str | None,
    address: str | None,
):
    """Fetch and fast-forward a branch to the cloud tip.

    INPUT: Optional <owner>/<store> to pull from (links the remote first
    when it doesn't exist yet); optional branch name (default: current).
    OUTPUT: Branch, new tip, chunks downloaded, whether the remote was linked.

    With an address, `pull` is the one-command way to start from an existing
    cloud store: when the remote (default `origin`, or --remote) doesn't
    exist it is linked exactly as `memoir remote add` would (and in a code
    repo the repo's store is created), then pulled. If the remote already
    points at that address, it just pulls, so repeating the command is
    harmless. If it points at a different store or gateway, nothing changes
    and the command exits 1: pull never relinks silently.

    Runs `memoir fetch`, then fast-forwards the branch. A branch missing
    locally is created from the cloud; a never-used local store adopts the
    cloud history. Anything else that is not a fast-forward (both sides have
    commits the other lacks) is rejected with exit code 6 — cloud merge is a
    later feature. Pass --force to discard the local memories on that branch
    and take the cloud copy instead; the previous tip is kept under
    refs/memoir/backup/<branch> and printed.

    \b
    Examples:
      memoir pull zhangfengcdt/sedona   # link origin to that store and pull
      memoir pull zhangfengcdt/sedona --remote staging --url https://staging.example
      memoir pull
      memoir pull --branch experiments
      memoir pull --force              # local main := cloud main

    \b
    JSON output includes: origin, branch, chunks_downloaded, created, tip,
    forced, previous_tip, backup_ref, linked
    """
    if address is not None:
        from memoir.services.base import ServiceError
        from memoir.services.sync_service import parse_address

        try:  # validate locally before anything touches disk or the network
            parse_address(address)
        except ServiceError as e:
            ctx.error(e.message, e.code)
    _require_cloud(ctx)
    _require_store(ctx, create=True)
    service = _service(ctx, remote_name)
    linked = False
    if address is not None:
        linked = _run(ctx, lambda: service.ensure_linked(address, url))
        if linked:
            ctx.info(f"linked {remote_name} to {address}")
    result = _run(ctx, lambda: service.pull(branch, force))
    result.linked = linked
    if result.forced:
        message = (
            f"replaced {result.branch} (was {result.previous_tip}, kept at "
            f"{result.backup_ref}) with {remote_name}/{result.branch} at {result.tip} "
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
@click.option(
    "--url",
    help="Gateway URL (default: MEMOIR_CLOUD_URL, else the saved default, else production)",
)
@click.option(
    "--with-key",
    is_flag=True,
    help="Read an API key from stdin instead of approving in a browser (headless machines)",
)
@click.option(
    "--no-browser", is_flag=True, help="Print the approval link without opening it"
)
@click.option(
    "--default",
    "make_default",
    is_flag=True,
    help="Make this gateway the default for new links (the first login always is)",
)
@click.option(
    "--status", is_flag=True, help="List the saved logins (gateway, handle, default)"
)
@pass_context
def login(
    ctx: MemoirContext,
    url: str | None,
    with_key: bool,
    no_browser: bool,
    make_default: bool,
    status: bool,
):
    """Log in to a memoir-cloud gateway and save a key for it on this machine.

    INPUT: Optional gateway (--url); with --with-key, an API key on stdin.
    OUTPUT: The gateway and handle you're logged in as (never the key).

    Starts a device approval like `gh auth login`: memoir prints a link and
    a short code, opens the browser, and waits while you click Authorize on
    the cloud (signed in there). The cloud mints a key named
    "memoir CLI (<hostname>)", visible and revocable on its keys page.

    Logins are kept per gateway in ~/.config/memoir/cloud.json (mode 0600),
    like gh's hosts: log in to production and staging side by side, and each
    saved key is only ever sent to its own gateway. MEMOIR_API_KEY, when
    set, still wins for every gateway.

    \b
    Examples:
      memoir login
      memoir login --url https://api-gateway-staging-3ce9.up.railway.app
      memoir login --status
      echo "$KEY" | memoir login --with-key

    \b
    JSON output includes: gateway, handle, default, config
    (--status: default, gateways[{gateway, handle, default}])
    """
    import os
    import sys

    from memoir.services import cloud_auth
    from memoir.services.sync_service import (
        GATEWAY_ENV,
        CloudClient,
        redact,
    )

    if status:
        saved = cloud_auth.load_all()
        rows = [
            {
                "gateway": gw,
                "handle": e.get("handle"),
                "default": gw == saved["default"],
            }
            for gw, e in saved["gateways"].items()
        ]
        if ctx.json_output:
            ctx.output({"default": saved["default"], "gateways": rows})
            return
        if not rows:
            click.echo("not logged in to any gateway; run `memoir login`")
        for r in rows:
            mark = "* " if r["default"] else "  "
            click.echo(f"{mark}{r['gateway']}  as {r['handle'] or '(no handle yet)'}")
        if os.environ.get("MEMOIR_API_KEY"):
            click.echo("MEMOIR_API_KEY is set: it is used for every gateway instead")
        return

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

    path = cloud_auth.save(gateway, key, handle, make_default=make_default)
    gateway = cloud_auth.normalize_gateway(gateway)
    is_default = cloud_auth.default_gateway() == gateway

    if (
        os.environ.get(GATEWAY_ENV)
        and cloud_auth.normalize_gateway(os.environ[GATEWAY_ENV]) != gateway
    ):
        ctx.warn(
            f"{GATEWAY_ENV} is set to a different gateway and will be used for new links"
        )
    if os.environ.get("MEMOIR_API_KEY"):
        ctx.warn("MEMOIR_API_KEY is set and still overrides the saved key")
    ctx.success(
        f"logged in to {gateway} as {handle or '(no handle yet)'}"
        + (" (default)" if is_default else ""),
        {
            "gateway": gateway,
            "handle": handle,
            "default": is_default,
            "config": str(path),
        },
    )


def _default_gateway() -> str:
    from memoir.services import cloud_auth
    from memoir.services.sync_service import DEFAULT_GATEWAY

    return cloud_auth.default_gateway() or DEFAULT_GATEWAY


@click.command()
@click.option(
    "--url",
    help="Gateway to log out of (default: MEMOIR_CLOUD_URL, else the saved default)",
)
@click.option("--all", "all_", is_flag=True, help="Log out of every saved gateway")
@pass_context
def logout(ctx: MemoirContext, url: str | None, all_: bool):
    """Log out: revoke a saved key on its gateway and delete it locally.

    INPUT: Optional gateway (--url) or --all.
    OUTPUT: For each gateway, whether the key was revoked and removed.

    Only that gateway's login is touched; others stay. Revocation is
    best-effort (offline is fine); the local entry is always removed.
    MEMOIR_API_KEY, if set in your shell, is not affected.

    \b
    Examples:
      memoir logout
      memoir logout --url https://api-gateway-staging-3ce9.up.railway.app
      memoir logout --all

    \b
    JSON output includes: gateways[{gateway, revoked}]
    """
    import os

    from memoir.services import cloud_auth
    from memoir.services.sync_service import GATEWAY_ENV

    if all_ and url:
        ctx.error("pass either --url or --all, not both", 1)
    saved = cloud_auth.load_all()
    if all_:
        targets = list(saved["gateways"])
    else:
        target = url or os.environ.get(GATEWAY_ENV) or saved["default"]
        targets = [cloud_auth.normalize_gateway(target)] if target else []
    targets = [t for t in targets if t in saved["gateways"]]
    if not targets:
        where = f" to {cloud_auth.normalize_gateway(url)}" if url else ""
        ctx.success(f"not logged in{where}", {"gateways": []})
        return
    results = []
    for gw in targets:
        entry = cloud_auth.remove(gw) or {}
        revoked = cloud_auth.revoke(gw, entry.get("api_key", "")) if entry else False
        results.append({"gateway": gw, "revoked": revoked})
    lines = [
        f"logged out of {r['gateway']} ("
        + (
            "key revoked"
            if r["revoked"]
            else "could not reach the cloud to revoke the key; revoke it on the keys page"
        )
        + ")"
        for r in results
    ]
    ctx.success("; ".join(lines), {"gateways": results})

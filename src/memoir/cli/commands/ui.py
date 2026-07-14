# SPDX-License-Identifier: Apache-2.0
"""
UI commands for memoir CLI.

Commands: ui, ui-start, ui-status, ui-stop

`ui` launches the interactive web-based memory visualization UI in the
foreground. `ui-start` / `ui-status` / `ui-stop` manage it as a detached
background server instead — the daemon bookkeeping lives in
`memoir.ui.daemon`, shared by every host plugin.
"""

import json
from pathlib import Path
from urllib.parse import quote

import click

from memoir.cli.main import (
    EXIT_ERROR,
    EXIT_NO_STORE,
    MemoirContext,
    pass_context,
)


@click.command()
@click.argument("path", required=False)
@click.option(
    "-p",
    "--port",
    default=0,
    type=int,
    help="Port number (default: 0 = pick a random free port)",
)
@click.option("--no-browser", is_flag=True, help="Don't open the browser automatically")
@click.option(
    "--readonly/--no-readonly",
    default=False,
    help="Lock the connected store and disable mutating actions (default: False)",
)
@click.option(
    "--usellm/--no-usellm",
    default=False,
    help="Enable UI features that call an LLM (recall, summarize, classify) "
    "(default: False)",
)
@click.option(
    "--idle-timeout",
    default=300,
    type=int,
    show_default=True,
    help="Auto-stop the server after this many seconds of inactivity. "
    "Pass 0 to disable (run indefinitely).",
)
@pass_context
def ui(
    ctx: MemoirContext,
    path: str | None,
    port: int,
    no_browser: bool,
    readonly: bool,
    usellm: bool,
    idle_timeout: int,
):
    """Launch the web UI to explore a memoir repo.

    INPUT: Optional PATH to an existing memoir store. If omitted, the store
    is resolved via the standard chain — `-s` flag → `MEMOIR_STORE` env →
    current working directory. The UI always opens against a real store;
    pre-launch demo mode was removed.
    OUTPUT: Starts an HTTP server on a free port (random by default) and opens
    a browser tab.

    By default the UI opens with edits enabled (writable) and LLM features off.
    Pass --readonly to lock the store, or --usellm to enable LLM-driven
    features (recall / summarize / classify, plus the natural-language input).

    \b
    Examples:
      memoir ui                                   # Writable, no LLM (default)
      memoir ui /tmp/my-store                     # Open a store, writable
      memoir ui /tmp/my-store --readonly          # Lock the store
      memoir ui /tmp/my-store --usellm            # + LLM recall/summarize/rewrite
      memoir ui /tmp/my-store --usellm --readonly # Full LLM, no edits
      memoir ui ~/memories --port 9090            # Pin to port 9090
    """
    # Resolution: positional path arg → standard ctx.store_path chain
    # (-s → MEMOIR_STORE → cwd). One of these must point at a real memoir
    # store; there's no "open without a store" path.
    target = path or ctx.store_path
    store_path = Path(target).expanduser().resolve()
    if not store_path.exists():
        ctx.error(f"Path does not exist: {store_path}", EXIT_NO_STORE)
    if not (store_path / ".git").exists():
        ctx.error(f"Not a valid memoir store (no .git): {store_path}", EXIT_NO_STORE)
    resolved = str(store_path)

    flags = f"readonly={1 if readonly else 0}&usellm={1 if usellm else 0}"

    def _on_ready(bound_port: int):
        base = f"http://localhost:{bound_port}"
        url = f"{base}/?store={quote(resolved, safe='')}&{flags}"
        mode = []
        mode.append("readonly" if readonly else "writable")
        mode.append("llm on" if usellm else "llm off")
        ctx.info(f"Opening {resolved} in the UI at {url}  ({', '.join(mode)})")
        if not no_browser:
            import webbrowser

            webbrowser.open(url)

    try:
        from memoir.ui.server import run_server

        run_server(port=port, on_ready=_on_ready, idle_timeout=idle_timeout)
    except FileNotFoundError as e:
        ctx.error(str(e), EXIT_ERROR)
    except KeyboardInterrupt:
        ctx.info("UI server stopped.")
    except OSError as e:
        port_desc = f"port {port}" if port else "an ephemeral port"
        hint = ""
        if getattr(e, "errno", None) == 48 or "Address already in use" in str(e):
            hint = (
                f" (port {port} is already in use — pass a different port with "
                f"--port, or free it with: lsof -nP -iTCP:{port} -sTCP:LISTEN)"
            )
        ctx.error(f"Failed to start server on {port_desc}: {e}{hint}", EXIT_ERROR)


@click.command("ui-start")
@click.argument("path", required=False)
@pass_context
def ui_start(ctx: MemoirContext, path: str | None):
    """Start a background UI server for a store, or reuse one already running.

    INPUT: Optional PATH to a memoir store. Falls back to the standard
    resolution chain (-s flag / MEMOIR_STORE / cwd) when omitted. The store
    is bootstrapped automatically if it doesn't exist yet.
    OUTPUT: A JSON document describing the running server — pid, port, url,
    store, started, log, and whether an existing server was reused.

    Unlike `memoir ui`, which blocks in the foreground, this detaches the
    server and tracks it under ~/.memoir/ui-servers/ so a second call
    against the same store reuses it instead of binding a new port.

    \b
    Examples:
      memoir ui-start                  # background-launch the current store
      memoir ui-start /tmp/my-store
    """
    from memoir.cli.commands.store import _ensure_store
    from memoir.ui import daemon

    target = path or ctx.store_path
    if not target:
        ctx.error(
            "No store configured. Pass a PATH, set MEMOIR_STORE, or cd into a memoir store.",
            EXIT_NO_STORE,
        )
        return

    store_path = str(Path(target).expanduser().resolve())
    try:
        _ensure_store(store_path)
    except Exception as e:
        ctx.error(f"Failed to bootstrap memoir store at {store_path}: {e}", EXIT_ERROR)
        return

    try:
        record, reused = daemon.start(store_path)
    except daemon.ServerStartError as e:
        ctx.error(str(e), EXIT_ERROR)
        return

    if ctx.json_output:
        click.echo(json.dumps(record, indent=2, default=str))
        return

    verb = "Reusing" if reused else "Started"
    ctx.success(f"{verb} UI server for {record['store']} at {record['url']}")


@click.command("ui-status")
@click.argument("path", required=False)
@pass_context
def ui_status(ctx: MemoirContext, path: str | None):
    """Show background UI server status.

    INPUT: Optional PATH to a memoir store. Without it, reports on every
    server memoir is currently tracking.
    OUTPUT: running/stale state, pid, url, and store for each tracked server.

    \b
    Examples:
      memoir ui-status                 # every tracked server
      memoir ui-status /tmp/my-store   # one store
    """
    from memoir.ui import daemon

    if path:
        store_path = str(Path(path).expanduser().resolve())
        record = daemon.status_one(store_path)
        if ctx.json_output:
            click.echo(
                json.dumps(
                    record or {"store": store_path, "state": "not running"},
                    indent=2,
                    default=str,
                )
            )
            return
        if record is None:
            click.echo(f"not running: {store_path}")
        elif record["state"] == "running":
            click.echo(
                f"running: pid={record['pid']} url={record['url']} store={store_path}"
            )
        else:
            click.echo(
                f"stale  : pid={record['pid']} url={record['url']} "
                f"store={store_path} (cleanup with stop)"
            )
        return

    records = daemon.status_all()
    if ctx.json_output:
        click.echo(json.dumps(records, indent=2, default=str))
        return
    if not records:
        click.echo("no memoir-ui servers tracked")
        return
    for record in records:
        label = "running" if record["state"] == "running" else "stale"
        click.echo(
            f"{label:7}: pid={record['pid']} url={record['url']} store={record['store']}"
        )


def _print_stop_result(result: dict) -> None:
    if result["outcome"] == "stopped":
        click.echo(f"stopped pid={result.get('pid')} url={result.get('url')}")
    else:
        click.echo(f"already gone: pid={result.get('pid')} url={result.get('url')}")


@click.command("ui-stop")
@click.argument("path", required=False)
@pass_context
def ui_stop(ctx: MemoirContext, path: str | None):
    """Stop a background UI server.

    INPUT: Optional PATH to a memoir store. Without it, stops every server
    memoir is currently tracking.
    OUTPUT: One line per server stopped.

    \b
    Examples:
      memoir ui-stop                   # stop every tracked server
      memoir ui-stop /tmp/my-store
    """
    from memoir.ui import daemon

    if path:
        store_path = str(Path(path).expanduser().resolve())
        result = daemon.stop_one(store_path)
        if ctx.json_output:
            click.echo(json.dumps(result, indent=2, default=str))
            return
        if result is not None:
            _print_stop_result(result)
        return

    results = daemon.stop_all()
    if ctx.json_output:
        click.echo(json.dumps(results, indent=2, default=str))
        return
    if not results:
        click.echo("no memoir-ui servers tracked")
        return
    for result in results:
        _print_stop_result(result)

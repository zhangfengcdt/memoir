"""
UI command for memoir CLI.

Launches the interactive web-based memory visualization UI.
"""

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
    default=True,
    help="Lock the connected store and disable mutating actions (default: True)",
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

    INPUT: Optional PATH to an existing memoir store. If omitted, falls back
    to the connected store (MEMOIR_STORE or default config); otherwise launches
    the UI in disconnected/demo mode.
    OUTPUT: Starts an HTTP server on a free port (random by default) and opens
    a browser tab.

    By default the UI opens in readonly mode (store URL is locked, mutating
    actions are disabled) and with LLM features off (recall / summarize /
    classify buttons disabled). Use --no-readonly and/or --usellm to enable.

    \b
    Examples:
      memoir ui                                   # Readonly, no LLM (default)
      memoir ui /tmp/my-store                     # Open a store readonly
      memoir ui /tmp/my-store --no-readonly       # Allow mutations
      memoir ui /tmp/my-store --usellm            # Readonly + LLM recall/summarize
      memoir ui /tmp/my-store --no-readonly --usellm   # Full interactive mode
      memoir ui ~/memories --port 9090            # Pin to port 9090
    """
    target = path or ctx.store_path
    resolved: str | None = None

    if target:
        store_path = Path(target).expanduser().resolve()
        if not store_path.exists():
            ctx.error(f"Path does not exist: {store_path}", EXIT_NO_STORE)
        if not (store_path / ".git").exists():
            ctx.error(
                f"Not a valid memoir store (no .git): {store_path}", EXIT_NO_STORE
            )
        resolved = str(store_path)

    flags = f"readonly={1 if readonly else 0}&usellm={1 if usellm else 0}"

    def _on_ready(bound_port: int):
        base = f"http://localhost:{bound_port}"
        if resolved:
            url = f"{base}/?store={quote(resolved, safe='')}&{flags}"
            mode = []
            mode.append("readonly" if readonly else "writable")
            mode.append("llm on" if usellm else "llm off")
            ctx.info(f"Opening {resolved} in the UI at {url}  ({', '.join(mode)})")
        else:
            url = f"{base}/?{flags}"
            ctx.info(f"Starting UI at {url} (no store pre-loaded)")
        if not no_browser:
            import webbrowser

            webbrowser.open(url)

    try:
        from memoir.ui.server import run_server

        run_server(port=port, on_ready=_on_ready, idle_timeout=idle_timeout)
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

# SPDX-License-Identifier: Apache-2.0
"""
TUI command for memoir CLI.

Launches the interactive terminal UI for a memoir store.
"""

from pathlib import Path

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
    "-b",
    "--branch",
    default=None,
    help="Check out this branch before entering the TUI (optional).",
)
@pass_context
def tui(ctx: MemoirContext, path: str | None, branch: str | None):
    """Launch the read-only terminal UI to explore a memoir repo.

    INPUT: Optional PATH to an existing memoir store. If omitted, the store
    is resolved via the standard chain — `-s` flag → `MEMOIR_STORE` env →
    current working directory. The TUI always opens against a real store.
    OUTPUT: Starts a full-screen Textual app showing Commits, Timeline, and
    Places against the store. Read-only — no mutations, no LLM. Pass
    `-b/--branch` to switch branches before the UI launches.

    \b
    Examples:
      memoir tui                                # Resolve store from -s / env / cwd
      memoir tui /tmp/my-store                  # Open a specific store
      memoir tui /tmp/my-store -b feature/foo   # Open and switch to a branch
    """
    target = path or ctx.store_path
    store_path = Path(target).expanduser().resolve()
    if not store_path.exists():
        ctx.error(f"Path does not exist: {store_path}", EXIT_NO_STORE)
    if not (store_path / ".git").exists():
        ctx.error(f"Not a valid memoir store (no .git): {store_path}", EXIT_NO_STORE)

    try:
        from memoir.tui import run_tui
    except ImportError as e:
        ctx.error(
            "memoir tui requires the optional TUI extras (textual, rich). "
            "Install with: pip install 'memoir-ai[tui]'  "
            f"(original error: {e})",
            EXIT_ERROR,
        )
        return

    try:
        run_tui(store_path=str(store_path), branch=branch)
    except KeyboardInterrupt:
        ctx.info("TUI stopped.")
    except Exception as e:
        ctx.error(str(e), EXIT_ERROR)

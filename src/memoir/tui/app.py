# SPDX-License-Identifier: Apache-2.0
"""
Memoir TUI — full-screen, read-only Textual interface.

Replaces the prior scrolling slash-command REPL. Mirrors the read-only
features of the web UI: Commits log + diff, Timeline, Places. No
mutations; no LLM; no HTTP server.

CLI entrypoint: ``memoir tui [PATH] [-b BRANCH]`` (see
``src/memoir/cli/commands/tui.py``). Programmatic use:
``from memoir.tui import run_tui; run_tui("/path/to/store")``.
"""

from __future__ import annotations

import time
from typing import ClassVar

from textual.app import App
from textual.binding import Binding

from memoir.services.branch_service import BranchService
from memoir.tui.data import DataLoader
from memoir.tui.screens.main import MainScreen


class MemoirApp(App):
    """Top-level Textual application."""

    TITLE = "memoir"
    SUB_TITLE = "read-only TUI"

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("q", "quit", "Quit", show=True),
        Binding("ctrl+c", "quit", "Quit", show=False),
    ]

    def __init__(self, loader: DataLoader, **kwargs) -> None:
        super().__init__(**kwargs)
        self._loader = loader

    def on_mount(self) -> None:
        # Default to the gruvbox theme (warm retro-green palette).
        # Users can switch via the ctrl+p command palette → "Theme".
        # Suppressed in case an older Textual version doesn't know the
        # theme name — we just fall back to the runtime default.
        import contextlib

        with contextlib.suppress(Exception):
            self.theme = "gruvbox"
        self.push_screen(MainScreen(self._loader))


def run_tui(store_path: str | None = None, branch: str | None = None) -> None:
    """Launch the memoir TUI against ``store_path``.

    A non-existent ``store_path`` raises ``FileNotFoundError``; the CLI
    catches and reports this. If ``branch`` is set, a checkout is attempted
    first — failures are surfaced via the click context (the CLI catches
    them); on success the TUI launches on the new branch.

    Before handing the terminal to Textual we open the ProllyTreeStore
    and pre-fetch outline keys in the normal shell: on big stores the
    ``_populate_key_registry`` walk can take 10-30 seconds and would
    otherwise appear as a frozen Textual screen. Surfacing it as a shell
    message keeps the wait debuggable.
    """
    if not store_path:
        raise ValueError("store_path is required")
    if not DataLoader.store_exists(store_path):
        raise FileNotFoundError(f"Not a valid memoir store (no .git): {store_path}")
    if branch:
        result = BranchService(store_path).checkout(branch)
        if not result.success:
            raise RuntimeError(f"Failed to switch to '{branch}': {result.error}")

    loader = DataLoader(store_path)
    t0 = time.monotonic()
    print(f"Opening memoir store at {store_path}…", flush=True)
    loader.warmup()
    elapsed = time.monotonic() - t0
    print(f"Loaded {len(loader.get_memories())} keys in {elapsed:.2f}s.", flush=True)
    app = MemoirApp(loader)
    app.run()

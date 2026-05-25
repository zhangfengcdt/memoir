# SPDX-License-Identifier: Apache-2.0
"""WatchPane — table of registered watch paths.

Read-only view. Each row is one ``memoir watch add <path>`` registration
with namespace, kind (file/folder), indexed file count, and last scan
timestamp. Mirrors what ``memoir watch list`` prints to the CLI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.containers import Vertical
from textual.widgets import DataTable, Static
from textual.worker import Worker, WorkerState

if TYPE_CHECKING:
    from typing import ClassVar

    from textual.app import ComposeResult

    from memoir.tui.data import DataLoader


def _fmt_time(s: str | None) -> str:
    return s or "—"


class WatchPane(Vertical):
    """List of registered watch paths."""

    DEFAULT_CSS: ClassVar[str] = """
    WatchPane {
        padding: 1 2;
    }
    #watch-empty {
        color: $text-muted;
        padding-top: 1;
    }
    #watch-table {
        height: 1fr;
    }
    """

    def __init__(self, loader: DataLoader, **kwargs) -> None:
        super().__init__(**kwargs)
        self._loader = loader
        self._loaded = False
        self._load_worker: Worker | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="watch-empty")
        table: DataTable = DataTable(id="watch-table", zebra_stripes=True)
        table.cursor_type = "row"
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#watch-table", DataTable)
        table.add_columns("Path", "Kind", "NS", "Files", "Last scan", "Added")

    def ensure_loaded(self) -> None:
        if self._loaded or (
            self._load_worker is not None
            and self._load_worker.state
            not in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED)
        ):
            return
        self.query_one("#watch-empty", Static).update("Loading watched paths…")
        self._load_worker = self.run_worker(
            self._fetch,
            exclusive=True,
            thread=True,
            description="watch:load",
        )

    def refresh_data(self) -> None:
        self._loaded = False
        self.ensure_loaded()

    def _fetch(self) -> None:
        try:
            entries = self._loader.get_watch_entries()
        except Exception as e:  # surface errors instead of silently empty-rendering
            self.app.call_from_thread(self._render_error_msg, str(e))
            return
        self.app.call_from_thread(self._render_table, entries)

    # NOTE: do not rename these back to ``_render`` / ``_render_error``.
    # ``_render`` is reserved by ``textual.widget.Widget`` — its rendering
    # pipeline calls ``self._render()`` (no args) on every paint, so a
    # method of the same name with required args raises
    # ``TypeError: _render() missing 1 required positional argument`` on
    # the first frame and the widget crashes mid-render.
    def _render_table(self, entries: list) -> None:
        self._loaded = True
        table = self.query_one("#watch-table", DataTable)
        table.clear()
        sorted_entries = sorted(entries, key=lambda e: e.path)
        for e in sorted_entries:
            table.add_row(
                e.path,
                e.kind,
                e.namespace,
                str(e.indexed_count),
                _fmt_time(e.last_scan),
                _fmt_time(e.added_at),
            )
        msg = self.query_one("#watch-empty", Static)
        if not sorted_entries:
            msg.update(
                "No paths registered. Run `memoir watch add <path>` to start indexing."
            )
        else:
            msg.update(f"{len(sorted_entries)} registered")

    def _render_error_msg(self, message: str) -> None:
        self._loaded = True
        self.query_one("#watch-empty", Static).update(f"[red]Error:[/] {message}")

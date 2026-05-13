# SPDX-License-Identifier: Apache-2.0
"""CommitsPane — split layout: DataTable of commits | DiffView."""

from __future__ import annotations

import time
from datetime import datetime
from typing import TYPE_CHECKING

from textual.containers import Horizontal
from textual.widgets import DataTable
from textual.worker import Worker, WorkerState

from memoir.tui.widgets.diff_view import DiffView

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from memoir.tui.data import DataLoader

# Soft cap on the rendered subject column. Wider values just get ellipsis.
_SUBJECT_WIDTH = 60


class CommitsPane(Horizontal):
    DEFAULT_CSS = """
    CommitsPane DataTable {
        width: 60%;
    }
    CommitsPane DiffView {
        width: 40%;
        border-left: solid $accent;
    }
    """

    def __init__(self, loader: DataLoader, **kwargs) -> None:
        super().__init__(**kwargs)
        self._loader = loader
        self._diff_worker: Worker | None = None
        self._row_to_hash: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        table: DataTable = DataTable(cursor_type="row", zebra_stripes=True)
        table.add_columns("hash", "when", "author", "subject", "refs")
        yield table
        yield DiffView()

    def on_mount(self) -> None:
        self.populate()

    def populate(self) -> None:
        """Re-render the commit table from the loader cache."""
        table = self.query_one(DataTable)
        diff = self.query_one(DiffView)
        table.clear()
        self._row_to_hash.clear()
        commits = self._loader.get_commits()
        if not commits:
            diff.show_message("No commits on this branch.")
            return
        now = time.time()
        for commit in commits:
            row_key = commit.hash
            self._row_to_hash[row_key] = commit.hash
            refs = ", ".join(commit.refs) if commit.refs else ""
            subject = commit.message.splitlines()[0] if commit.message else ""
            if len(subject) > _SUBJECT_WIDTH:
                subject = subject[: _SUBJECT_WIDTH - 1] + "…"
            table.add_row(
                commit.short_hash,
                _relative_time(now - commit.timestamp),
                commit.author,
                subject,
                refs,
                key=row_key,
            )
        # Auto-highlight first row so users see a diff immediately.
        if table.row_count:
            table.move_cursor(row=0)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        commit_hash = self._row_to_hash.get(str(event.row_key.value))
        if commit_hash is None:
            return
        if self._diff_worker is not None and self._diff_worker.state not in (
            WorkerState.SUCCESS,
            WorkerState.ERROR,
            WorkerState.CANCELLED,
        ):
            self._diff_worker.cancel()
        diff = self.query_one(DiffView)
        diff.show_message(f"Loading diff for {commit_hash[:8]}…")
        self._diff_worker = self.run_worker(
            self._fetch_changes(commit_hash),
            exclusive=True,
            thread=True,
            description=f"diff:{commit_hash[:8]}",
        )

    def _fetch_changes(self, commit_hash: str):
        # Closure that runs on a worker thread. Calls back via call_from_thread.
        def work():
            changes = self._loader.get_commit_changes(commit_hash)
            self.app.call_from_thread(self.query_one(DiffView).show, changes)

        return work

    def refresh_data(self) -> None:
        """Called by the screen on global refresh — reload from cleared cache."""
        self.populate()


def _relative_time(seconds: float) -> str:
    """Human-friendly elapsed time. Always 2-4 chars wide."""
    if seconds < 0:
        return "now"
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    if seconds < 86400 * 30:
        return f"{int(seconds // 86400)}d"
    if seconds < 86400 * 365:
        return f"{int(seconds // (86400 * 30))}mo"
    # Fall back to YYYY-MM-DD for very old commits — clearer than "Ny".
    return datetime.fromtimestamp(time.time() - seconds).strftime("%Y-%m-%d")

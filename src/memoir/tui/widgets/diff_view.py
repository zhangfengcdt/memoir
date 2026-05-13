# SPDX-License-Identifier: Apache-2.0
"""DiffView — renders structured commit changes as colored +/~/- lines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import RichLog

if TYPE_CHECKING:
    from memoir.tui.data import CommitChange


class DiffView(RichLog):
    """Right-side detail pane for the Commits view.

    One line per change. ``+`` green for additions, ``~`` yellow for
    modifications, ``-`` red for deletions. Path is shown verbatim;
    no content body in v1 (read-only TUI scope).
    """

    DEFAULT_CSS = """
    DiffView {
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(markup=True, wrap=False, highlight=False, **kwargs)

    def show(self, changes: list[CommitChange]) -> None:
        self.clear()
        if not changes:
            self.write("[dim]No changes recorded for this commit.[/dim]")
            return
        added = sum(1 for c in changes if c.op == "added")
        modified = sum(1 for c in changes if c.op == "modified")
        deleted = sum(1 for c in changes if c.op == "deleted")
        self.write(
            f"[dim]"
            f"[green]+{added}[/green]  "
            f"[yellow]~{modified}[/yellow]  "
            f"[red]-{deleted}[/red]"
            f"[/dim]"
        )
        self.write("")
        for c in changes:
            ns = f"[dim]{c.namespace}:[/dim]" if c.namespace else ""
            if c.op == "added":
                self.write(f"[green]+ added[/green]      {ns}{c.path}")
            elif c.op == "modified":
                self.write(f"[yellow]~ modified[/yellow]   {ns}{c.path}")
            elif c.op == "deleted":
                self.write(f"[red]- deleted[/red]    {ns}{c.path}")

    def show_message(self, msg: str, *, severity: str = "dim") -> None:
        self.clear()
        self.write(f"[{severity}]{msg}[/{severity}]")

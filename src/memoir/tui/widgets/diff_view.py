# SPDX-License-Identifier: Apache-2.0
"""DiffView — renders commit changes with BEFORE / AFTER content blocks.

Mirrors the web UI's ``CommitDetail`` drawer
(``src/memoir/ui/webapp/src/drawers/CommitDetail.tsx``):

* Stat chips header (``+N additions  ~N modifications  -N deletions``).
* One card per change with operation glyph, namespaced path, tag, and
  the decoded ``old_content`` / ``new_content`` body (wrapped, scrollable
  inside the RichLog).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text
from textual.widgets import RichLog

if TYPE_CHECKING:
    from memoir.tui.data import CommitChange


# Cap on lines per content block so a single huge JSON blob can't
# dominate the pane. The full body is still visible in the OutlinePane
# for additions/modifications.
_MAX_CONTENT_LINES = 30


class DiffView(RichLog):
    """Right-side detail pane for the Commits view."""

    DEFAULT_CSS = """
    DiffView {
        padding: 0 1;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(markup=True, wrap=True, highlight=False, **kwargs)

    def show(self, changes: list[CommitChange]) -> None:
        self.clear()
        if not changes:
            self.write("[dim]No key-level changes for this commit.[/dim]")
            return

        added = sum(1 for c in changes if c.op == "added")
        modified = sum(1 for c in changes if c.op == "modified")
        deleted = sum(1 for c in changes if c.op == "deleted")
        self.write(
            f"[green]+{added} addition{_plural(added)}[/green]   "
            f"[yellow]~{modified} modification{_plural(modified)}[/yellow]   "
            f"[red]-{deleted} deletion{_plural(deleted)}[/red]"
        )
        self.write("")

        for change in changes:
            self._write_change(change)

    def show_message(self, msg: str, *, severity: str = "dim") -> None:
        self.clear()
        self.write(f"[{severity}]{msg}[/{severity}]")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _write_change(self, c: CommitChange) -> None:
        if c.op == "added":
            sym, color, tag = "+", "green", "ADDED"
        elif c.op == "deleted":
            sym, color, tag = "-", "red", "DELETED"
        else:
            sym, color, tag = "~", "yellow", "MODIFIED"
        ns = f"[dim]{c.namespace}:[/dim]" if c.namespace else ""
        self.write(f"[{color} b]{sym} {ns}{c.path}[/]   " f"[{color}]{tag}[/{color}]")
        # ``Text(...)`` (not markup) for content so user-provided "[..]"
        # sequences never get interpreted as Rich markup.
        if c.old_content is not None and c.old_content != "":
            self.write("  [dim]BEFORE:[/dim]")
            for line in _clip_lines(c.old_content):
                self.write(Text(f"    {line}", style="red"))
        if c.new_content is not None and c.new_content != "":
            self.write("  [dim]AFTER:[/dim]")
            for line in _clip_lines(c.new_content):
                self.write(Text(f"    {line}", style="green"))
        self.write("")


def _plural(n: int) -> str:
    return "" if n == 1 else "s"


def _clip_lines(text: str, *, limit: int = _MAX_CONTENT_LINES) -> list[str]:
    """Return up to ``limit`` lines plus a "…N more" marker when truncated."""
    lines = text.splitlines() or [text]
    if len(lines) <= limit:
        return lines
    return [*lines[:limit], f"… ({len(lines) - limit} more lines)"]

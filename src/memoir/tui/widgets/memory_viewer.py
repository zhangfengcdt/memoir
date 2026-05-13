# SPDX-License-Identifier: Apache-2.0
"""MemoryViewer — scrollable read-only display of a single memory's content."""

from __future__ import annotations

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Static


class MemoryViewer(VerticalScroll):
    """Right-side detail pane for Timeline / Places.

    Uses ``Text(...)`` (not markup) so user-supplied content with ``[...]``
    sequences never gets interpreted as Rich markup.
    """

    DEFAULT_CSS = """
    MemoryViewer {
        padding: 0 1;
    }
    MemoryViewer > Static {
        width: 100%;
    }
    """

    def compose(self):
        yield Static("", id="memory-viewer-body")

    def show(self, body: str, *, dim: bool = False) -> None:
        widget = self.query_one("#memory-viewer-body", Static)
        text = Text(body or "", style="dim" if dim else "")
        widget.update(text)
        self.scroll_home(animate=False)

    def clear(self) -> None:
        self.show("")

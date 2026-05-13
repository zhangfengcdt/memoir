# SPDX-License-Identifier: Apache-2.0
"""HelpScreen — modal that lists keybindings."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult

_HELP = """[b]memoir tui — keybindings[/b]

  [b]q[/b] / [b]ctrl+c[/b]   Quit
  [b]r[/b]              Force refresh
  [b]1[/b] / [b]2[/b]        Commits / Outline
  [b]/[/b]              Focus the outline filter
  [b]tab[/b] / [b]shift+tab[/b]  Move focus inside a pane
  [b]↑[/b] [b]↓[/b] [b]j[/b] [b]k[/b]      Navigate the active list / tree
  [b]g[/b] / [b]G[/b]        Top / bottom of list
  [b]enter[/b]          Open detail
  [b]esc[/b]            Close help / clear focus
  [b]?[/b]              Toggle this help

[dim]Auto-refresh runs every 3 seconds. Press esc or ? to close.[/dim]
"""


class HelpScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > Vertical {
        width: 60;
        height: auto;
        padding: 1 2;
        border: round $accent;
        background: $panel;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(_HELP)

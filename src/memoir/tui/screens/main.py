# SPDX-License-Identifier: Apache-2.0
"""MainScreen — header + TabbedContent (Commits/Outline) + footer + auto-refresh."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer, Static, TabbedContent, TabPane

from memoir.tui.widgets.commits_pane import CommitsPane
from memoir.tui.widgets.outline_pane import OutlinePane

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from memoir.tui.data import DataLoader

# How often the auto-refresh tick fires. 3s matches the web UI's poll cadence.
_AUTO_REFRESH_SEC = 3.0


class MainScreen(Screen):
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("1", "show_tab('commits')", "Commits", show=True),
        Binding("2", "show_tab('outline')", "Outline", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("question_mark", "help", "Help", show=True),
    ]

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }
    #header-bar {
        height: 5;
        padding: 1 2;
        background: $panel;
        color: $text;
        border-bottom: solid $accent;
        content-align: left top;
    }
    TabbedContent {
        height: 1fr;
    }
    """

    def __init__(self, loader: DataLoader, **kwargs) -> None:
        super().__init__(**kwargs)
        self._loader = loader
        self._last_head: str | None = None

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="header-bar", markup=True)
        with TabbedContent(initial="commits", id="tabs"):
            with TabPane("Commits", id="commits"):
                yield CommitsPane(self._loader, id="commits-pane")
            with TabPane("Outline", id="outline"):
                yield OutlinePane(self._loader, id="outline-pane")
        yield Footer()

    def on_mount(self) -> None:
        self._last_head = self._loader.get_store_info().head_hash
        self.set_interval(_AUTO_REFRESH_SEC, self._auto_refresh_tick)
        # No prefetch worker here — ``run_tui`` already calls
        # ``DataLoader.warmup()`` synchronously before Textual takes over,
        # so the outline cache is already populated by the time the user
        # can press a tab.

    def _header_text(self) -> str:
        info = self._loader.get_store_info()
        return (
            f"[dim]branch:[/dim] [b yellow]⎇ {info.current_branch}[/]   "
            f"[dim]commits:[/dim] [b]{info.commits_count}[/b]   "
            f"[dim](auto-refresh {int(_AUTO_REFRESH_SEC)}s)[/dim]\n"
            f"[dim]store:[/dim]  [b]{info.store_path}[/b]"
        )

    def _update_header(self) -> None:
        self.query_one("#header-bar", Static).update(self._header_text())

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_show_tab(self, tab_id: str) -> None:
        tabbed = self.query_one("#tabs", TabbedContent)
        tabbed.active = tab_id

    def action_refresh(self) -> None:
        self._do_refresh()
        self.notify("Refreshed.", timeout=2)

    def action_help(self) -> None:
        from memoir.tui.screens.help import HelpScreen

        self.app.push_screen(HelpScreen())

    # ------------------------------------------------------------------
    # Auto-refresh
    # ------------------------------------------------------------------

    def _auto_refresh_tick(self) -> None:
        """Cheap probe; only re-fetch when the HEAD short-hash has changed."""
        head = self._loader.get_head_hash()
        if head == self._last_head:
            return
        self._last_head = head
        self._do_refresh()

    def _do_refresh(self) -> None:
        self._loader.refresh()
        self._update_header()
        self.query_one("#commits-pane", CommitsPane).refresh_data()
        # Outline lazy-loads on activation; this kicks the data fetch but
        # the UI only changes when the user opens that tab.
        self.query_one("#outline-pane", OutlinePane).refresh_data()

    # ------------------------------------------------------------------
    # Lazy-load tabs on first activation
    # ------------------------------------------------------------------

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        # ``event.tab.id`` in recent Textual versions is the prefixed
        # tab widget id (e.g. ``--content-tab-outline``), not the pane
        # id we set in ``compose``. Read ``tabbed.active`` instead — by
        # contract that's always the pane id.
        del event
        active = self.query_one("#tabs", TabbedContent).active
        if active == "outline":
            self.query_one("#outline-pane", OutlinePane).ensure_loaded()

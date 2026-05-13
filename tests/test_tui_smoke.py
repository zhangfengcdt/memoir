# SPDX-License-Identifier: Apache-2.0
"""Smoke tests for the memoir TUI.

The Textual app talks to memoir services in-process, so these tests run
``App.run_test()`` against a freshly created store and exercise the
tab-switching keybindings to catch obvious mount-time / wiring breakage.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from memoir.services.store_service import StoreService
from memoir.tui.app import MemoirApp, run_tui
from memoir.tui.data import DataLoader


@pytest.fixture
def temp_store():
    path = tempfile.mkdtemp(prefix="memoir_tui_test_")
    try:
        StoreService(path).create_store(path)
        yield path
    finally:
        if os.path.exists(path):
            shutil.rmtree(path)


def test_run_tui_rejects_invalid_store(tmp_path):
    """A path that isn't a memoir store must surface as FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        run_tui(str(tmp_path / "no-such-store"))


def test_dataloader_handles_empty_store(temp_store):
    """Fresh store: no user memories — DataLoader must not raise."""
    loader = DataLoader(temp_store)
    info = loader.get_store_info()
    assert info.store_path == temp_store
    assert isinstance(info.current_branch, str)
    # A freshly created store may carry an "Initial commit" from
    # ``StoreService.create_store``; commits_count just has to match what
    # ``get_commits`` actually returned.
    assert info.commits_count == len(loader.get_commits())
    assert info.commits_count >= 0
    # No user memories on a fresh store.
    assert loader.get_memories() == []


@pytest.mark.asyncio
async def test_app_mounts_and_switches_tabs(temp_store):
    """End-to-end: app mounts on an empty store, tabs switch, quit cleans up."""
    loader = DataLoader(temp_store)
    app = MemoirApp(loader)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent

        tabbed = app.screen.query_one("#tabs", TabbedContent)
        assert tabbed.active == "commits"

        await pilot.press("2")
        await pilot.pause()
        assert tabbed.active == "outline"

        await pilot.press("1")
        await pilot.pause()
        assert tabbed.active == "commits"


@pytest.mark.asyncio
async def test_help_modal_opens_and_closes(temp_store):
    loader = DataLoader(temp_store)
    app = MemoirApp(loader)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Open help via "?".
        await pilot.press("question_mark")
        await pilot.pause()
        from memoir.tui.screens.help import HelpScreen

        assert isinstance(app.screen, HelpScreen)
        # Close via escape.
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, HelpScreen)

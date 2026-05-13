# SPDX-License-Identifier: Apache-2.0
"""
Memoir TUI — read-only full-screen Textual interface.

Usage:
    # From the command line
    memoir tui
    memoir tui /path/to/store
    memoir tui /path/to/store -b feature/foo

    # Programmatically
    from memoir.tui import run_tui

    run_tui("/path/to/store")
"""

from memoir.tui.app import MemoirApp, run_tui

__all__ = ["MemoirApp", "run_tui"]

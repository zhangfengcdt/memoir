# SPDX-License-Identifier: Apache-2.0
"""
Memoir TUI - Terminal User Interface.

A simple CLI-style interface for memoir, styled similar to Claude Code.

Usage:
    # From command line
    memoir tui
    memoir tui -c /path/to/store

    # Programmatically
    from memoir.tui import MemoirCLI, run_tui

    run_tui("/path/to/store")
"""

from memoir.tui.app import MemoirCLI, MemoirTUI, run_tui

__all__ = [
    "MemoirCLI",
    "MemoirTUI",
    "run_tui",
]

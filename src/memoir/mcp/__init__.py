# SPDX-License-Identifier: Apache-2.0
"""
Memoir MCP server.

Model Context Protocol server (built on the official ``mcp`` SDK / FastMCP) that
exposes memoir to Claude Desktop, Cursor, Cline, Windsurf, Zed, Continue,
LibreChat, and other MCP hosts.

Usage:
    # Run the server (stdio)
    MEMOIR_STORE=/path/to/store memoir-mcp

    # Or build it programmatically
    from memoir.mcp import build_server, ensure_store

    ensure_store("/path/to/store")
    server = build_server("/path/to/store")  # a FastMCP instance
"""

from memoir.mcp.server import build_server, ensure_store, main, resolve_store_path

__all__ = [
    "build_server",
    "ensure_store",
    "main",
    "resolve_store_path",
]

# SPDX-License-Identifier: Apache-2.0
"""
Memoir MCP Server.

Model Context Protocol server for exposing memoir functionality
to Claude Desktop and other MCP-compatible AI tools.

Usage:
    # Set the store path and run the server
    MEMOIR_STORE=/path/to/store memoir-mcp

    # Or use programmatically
    from memoir.mcp import create_server, run_stdio_server

    server = create_server("/path/to/store")
    tools = server.get_tools()
"""

from memoir.mcp.server import MemoirMCPServer, create_server, run_stdio_server

__all__ = [
    "MemoirMCPServer",
    "create_server",
    "run_stdio_server",
]

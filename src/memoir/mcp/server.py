"""
Memoir MCP Server.

Model Context Protocol server for exposing memoir functionality
to Claude Desktop and other MCP-compatible AI tools.
"""

import asyncio
import json
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)


def _get_version() -> str:
    """Return the installed package version, or fall back to memoir.__version__."""
    try:
        from importlib.metadata import version

        return version("memoir-ai")
    except Exception:
        from memoir import __version__

        return __version__


# Tool definitions for MCP
TOOLS = [
    {
        "name": "memoir_remember",
        "description": "Store content in memory with intelligent classification. The content is automatically classified into semantic paths and stored with git versioning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The content to store in memory",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace for the memory (default: 'default')",
                    "default": "default",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "memoir_recall",
        "description": "Search memories using semantic query. Returns matching memories with relevance scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default: 10)",
                    "default": 10,
                },
                "namespace": {
                    "type": "string",
                    "description": "Limit search to specific namespace (default: all)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "memoir_forget",
        "description": "Delete a memory by its key/path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Memory key/path to delete",
                },
                "namespace": {
                    "type": "string",
                    "description": "Namespace containing the memory (default: 'default')",
                    "default": "default",
                },
            },
            "required": ["key"],
        },
    },
    {
        "name": "memoir_status",
        "description": "Get status information about the connected memory store.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "memoir_branches",
        "description": "List all branches in the memory store.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "memoir_checkout",
        "description": "Switch to a branch or commit. Can optionally create the branch if it doesn't exist.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Branch name or commit hash to checkout",
                },
                "create": {
                    "type": "boolean",
                    "description": "Create the branch if it doesn't exist (default: false)",
                    "default": False,
                },
            },
            "required": ["target"],
        },
    },
    {
        "name": "memoir_commits",
        "description": "Get commit history for the memory store.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum commits to return (default: 10)",
                    "default": 10,
                },
            },
        },
    },
]


class MemoirMCPServer:
    """MCP Server for memoir memory operations."""

    def __init__(self, store_path: str):
        """
        Initialize the MCP server.

        Args:
            store_path: Path to the memory store
        """
        self.store_path = store_path
        self._memory_service = None
        self._branch_service = None
        self._store_service = None

    def _get_memory_service(self):
        """Lazy load memory service."""
        if self._memory_service is None:
            from memoir.services.memory_service import MemoryService

            self._memory_service = MemoryService(self.store_path)
        return self._memory_service

    def _get_branch_service(self):
        """Lazy load branch service."""
        if self._branch_service is None:
            from memoir.services.branch_service import BranchService

            self._branch_service = BranchService(self.store_path)
        return self._branch_service

    def _get_store_service(self):
        """Lazy load store service."""
        if self._store_service is None:
            from memoir.services.store_service import StoreService

            self._store_service = StoreService(self.store_path)
        return self._store_service

    async def handle_tool_call(self, name: str, arguments: dict[str, Any]) -> str:
        """
        Handle a tool call from the MCP client.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            JSON string with tool result
        """
        try:
            if name == "memoir_remember":
                content = arguments["content"]
                namespace = arguments.get("namespace", "default")
                service = self._get_memory_service()
                result = await service.remember(content, namespace)
                return json.dumps(
                    {
                        "success": result.success,
                        "key": result.key,
                        "confidence": result.confidence,
                        "reasoning": result.reasoning,
                        "commit": result.commit_hash,
                    }
                )

            elif name == "memoir_recall":
                query = arguments["query"]
                limit = arguments.get("limit", 10)
                namespace = arguments.get("namespace")
                service = self._get_memory_service()
                result = await service.recall(query, limit=limit, namespace=namespace)
                return json.dumps(
                    {
                        "success": result.success,
                        "memories": result.memories,
                        "timing_ms": result.timing_ms,
                    }
                )

            elif name == "memoir_forget":
                key = arguments["key"]
                namespace = arguments.get("namespace", "default")
                service = self._get_memory_service()
                result = await service.forget(key, namespace)
                return json.dumps(
                    {
                        "success": result.success,
                        "key": result.key,
                        "commit": result.commit_hash,
                    }
                )

            elif name == "memoir_status":
                service = self._get_store_service()
                info = service.get_status()
                return json.dumps(info.to_dict())

            elif name == "memoir_branches":
                service = self._get_branch_service()
                info = service.list_branches()
                return json.dumps(
                    {
                        "branches": info.branches,
                        "current": info.current,
                    }
                )

            elif name == "memoir_checkout":
                target = arguments["target"]
                create = arguments.get("create", False)
                service = self._get_branch_service()
                result = service.checkout(target, create=create)
                return json.dumps(
                    {
                        "success": result.success,
                        "branch": result.branch,
                        "commit": result.commit,
                        "created": result.created,
                    }
                )

            elif name == "memoir_commits":
                limit = arguments.get("limit", 10)
                service = self._get_branch_service()
                commits = service.get_commits("HEAD", limit=limit)
                return json.dumps(
                    {
                        "commits": [c.to_dict() for c in commits],
                    }
                )

            else:
                return json.dumps({"error": f"Unknown tool: {name}"})

        except Exception as e:
            logger.error(f"Tool call error: {e}")
            return json.dumps({"error": str(e)})

    def get_tools(self) -> list[dict]:
        """Get list of available tools."""
        return TOOLS


def create_server(store_path: str) -> MemoirMCPServer:
    """
    Create a memoir MCP server.

    Args:
        store_path: Path to the memory store

    Returns:
        MemoirMCPServer instance
    """
    return MemoirMCPServer(store_path)


async def run_stdio_server(store_path: str):
    """
    Run the MCP server using stdio transport.

    This is the main entry point for the MCP server.
    Reads JSON-RPC requests from stdin and writes responses to stdout.

    Args:
        store_path: Path to the memory store
    """
    server = create_server(store_path)

    # Read from stdin, write to stdout
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    (
        writer_transport,
        writer_protocol,
    ) = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(
        writer_transport, writer_protocol, reader, asyncio.get_event_loop()
    )

    while True:
        try:
            line = await reader.readline()
            if not line:
                break

            request = json.loads(line.decode())
            method = request.get("method")
            params = request.get("params", {})
            request_id = request.get("id")

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "memoir",
                            "version": _get_version(),
                        },
                    },
                }
            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {"tools": server.get_tools()},
                }
            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                result = await server.handle_tool_call(tool_name, tool_args)
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [{"type": "text", "text": result}],
                    },
                }
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
        except Exception as e:
            logger.error(f"Server error: {e}")


def main():
    """Main entry point for memoir-mcp command."""
    store_path = os.environ.get("MEMOIR_STORE")

    if not store_path:
        print("Error: MEMOIR_STORE environment variable not set", file=sys.stderr)
        print("Usage: MEMOIR_STORE=/path/to/store memoir-mcp", file=sys.stderr)
        sys.exit(1)

    asyncio.run(run_stdio_server(store_path))


if __name__ == "__main__":
    main()

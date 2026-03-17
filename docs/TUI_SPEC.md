# Memoir Terminal & Agent Integration Specification

Multiple interfaces for memoir: CLI, TUI, Python SDK, and MCP Server - all sharing the same commands and business logic.

## Goals

1. **Feature parity** with web UI (all slash commands)
2. **Maximum code reuse** - shared services layer for all interfaces
3. **Claude Code / OpenClaw style** - minimal, elegant terminal experience
4. **Four interfaces, one codebase**:
   - **CLI**: Scriptable, pipeable, single commands (`memoir remember "..."`)
   - **TUI**: Interactive, visual, session-based (`memoir tui`)
   - **SDK**: Direct Python API for agent integration
   - **MCP Server**: Model Context Protocol for AI agents (Claude, OpenClaw, etc.)
   - **Web UI**: Browser-based (existing)

---

## Architecture Overview

### Current UI Architecture (Web)

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web Browser                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  ui.html + static/js/*.js                                   ││
│  │  - Command parsing (handleCommand)                          ││
│  │  - UI rendering (D3.js tree, modals)                        ││
│  │  - HTTP API calls                                           ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       server.py (HTTP)                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  handlers/                                                   ││
│  │  ├── store_handler.py    (store ops)                        ││
│  │  ├── memory_handler.py   (remember/forget/recall)           ││
│  │  ├── branch_handler.py   (git ops)                          ││
│  │  ├── crypto_handler.py   (proof/verify/blame)               ││
│  │  └── utils.py            (data extraction)                  ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Core memoir library                           │
│  ProllyTreeStore, IntelligentClassifier, SearchEngine, etc.     │
└─────────────────────────────────────────────────────────────────┘
```

### Proposed Unified Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Interfaces                                 │
├───────────────┬───────────────┬───────────────┬─────────────────────────────┤
│    Web UI     │     TUI       │     CLI       │     SDK / MCP Server        │
│  (Browser)    │  (Textual)    │   (Click)     │    (Agent Integration)      │
│               │               │               │                             │
│  Human use    │  Human use    │  Human +      │    AI Agent use             │
│  Visual       │  Interactive  │  Shell Agents │    Python / MCP Agents      │
│               │               │  (OpenClaw)   │    (LangGraph, Claude)      │
└───────┬───────┴───────┬───────┴───────┬───────┴──────────────┬──────────────┘
        │               │               │                      │
        │ HTTP          │ Direct        │ Direct               │ Direct
        ▼               ▼               ▼                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        services/ (Shared Business Logic)                     │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  ├── store_service.py      (store operations)                         │  │
│  │  ├── memory_service.py     (remember/forget/recall)                   │  │
│  │  ├── branch_service.py     (git operations)                           │  │
│  │  ├── crypto_service.py     (proof/verify/blame)                       │  │
│  │  ├── timeline_service.py   (timeline/location events)                 │  │
│  │  └── output_formatter.py   (shared output formatting)                 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Core memoir library                                │
│         ProllyTreeStore, IntelligentClassifier, SearchEngine, etc.          │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Insight**: Extract business logic into `services/`, then Web UI, TUI, and CLI all share the same code.

---

## Directory Structure

```
src/memoir/
├── services/                      # NEW: Shared business logic layer
│   ├── __init__.py
│   ├── store_service.py           # Store operations
│   ├── memory_service.py          # Memory operations
│   ├── branch_service.py          # Git/branch operations
│   ├── crypto_service.py          # Cryptographic operations
│   ├── timeline_service.py        # Timeline/location operations
│   └── output_formatter.py        # Shared output formatting (Rich)
│
├── sdk/                           # NEW: Python SDK for agents
│   ├── __init__.py
│   ├── client.py                  # MemoryClient main class
│   ├── models.py                  # RememberResult, Memory, etc.
│   └── branch.py                  # BranchManager
│
├── mcp/                           # NEW: MCP Server for AI agents
│   ├── __init__.py
│   ├── server.py                  # MCP server implementation
│   └── tools.py                   # Tool definitions
│
├── cli/                           # NEW: Command-line interface
│   ├── __init__.py
│   ├── main.py                    # Click application entry point
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── store.py               # connect, new, refresh
│   │   ├── memory.py              # remember, forget, recall
│   │   ├── branch.py              # branch, checkout, merge, commits
│   │   ├── crypto.py              # proof, verify, blame
│   │   ├── timeline.py            # timeline, location, time-travel
│   │   └── utils.py               # diff, summarize, code
│   └── output.py                  # CLI-specific output helpers
│
├── tui/                           # NEW: Terminal UI (interactive)
│   ├── __init__.py
│   ├── app.py                     # Main Textual application
│   ├── screens/
│   │   ├── __init__.py
│   │   ├── main_screen.py         # Primary interface
│   │   ├── help_screen.py         # Help overlay
│   │   └── branch_screen.py       # Branch management modal
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── command_input.py       # Command line input
│   │   ├── output_panel.py        # Output display
│   │   ├── tree_view.py           # Memory tree visualization
│   │   ├── status_bar.py          # Connection/branch status
│   │   └── timeline_view.py       # Timeline visualization
│   ├── styles/
│   │   └── memoir.tcss            # Textual CSS styling
│   └── themes/
│       ├── claude.py              # Claude Code theme
│       └── default.py             # Default theme
│
├── ui/                            # EXISTING: Web UI (refactored)
│   ├── handlers/
│   │   ├── api_handler.py         # Thin HTTP adapter
│   │   ├── store_handler.py       # Delegates to store_service
│   │   ├── memory_handler.py      # Delegates to memory_service
│   │   ├── branch_handler.py      # Delegates to branch_service
│   │   └── crypto_handler.py      # Delegates to crypto_service
│   └── ...
```

---

---

## SDK Design (Agent Integration)

The Python SDK provides direct, async-native access for AI agents running continuously.

### SDK Usage

```python
from memoir import MemoryClient

# Initialize with persistent connection
memory = MemoryClient("/path/to/store")

# Or async context manager
async with MemoryClient("/path/to/store") as memory:
    # Store memories (async, fast)
    result = await memory.remember(
        "User mentioned they have a dog named Max",
        namespace="user_facts"
    )
    print(f"Stored at: {result.path}, confidence: {result.confidence}")

    # Recall memories
    memories = await memory.recall("pets", limit=5)
    for m in memories:
        print(f"  {m.path}: {m.content}")

    # Forget
    await memory.forget("outdated.information")

    # Git operations
    await memory.branch.create("conversation_123")
    await memory.branch.checkout("conversation_123")
    commits = await memory.branch.history(limit=10)

    # Cryptographic proofs
    proof = await memory.proof("user.preferences")
    is_valid = await memory.verify(proof)

    # Time travel
    state = await memory.at_commit("abc1234")
    old_prefs = await state.recall("preferences")
```

### SDK for OpenClaw / LangGraph Agents

```python
# Example: OpenClaw agent with memoir memory
from memoir import MemoryClient

class MemoirMemorySkill:
    """Memoir integration as an agent skill."""

    def __init__(self, store_path: str):
        self.memory = MemoryClient(store_path)

    async def remember(self, content: str) -> dict:
        """Store information in long-term memory."""
        result = await self.memory.remember(content)
        return {
            "stored": True,
            "path": result.path,
            "confidence": result.confidence,
        }

    async def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Retrieve relevant memories."""
        results = await self.memory.recall(query, limit=limit)
        return [{"path": r.path, "content": r.content} for r in results]

    async def forget(self, path: str) -> bool:
        """Remove a memory."""
        return await self.memory.forget(path)


# Usage in agent
skill = MemoirMemorySkill("/var/agents/memory")

# Agent stores learned information
await skill.remember("User's timezone is PST")
await skill.remember("User prefers concise responses")

# Agent retrieves context
context = await skill.recall("user preferences")
```

### SDK for LangChain/LangGraph

```python
from langchain_core.tools import tool
from memoir import MemoryClient

memory = MemoryClient("/path/to/store")

@tool
async def remember_tool(content: str) -> str:
    """Store information in long-term memory for future reference."""
    result = await memory.remember(content)
    return f"Stored at {result.path} (confidence: {result.confidence:.2f})"

@tool
async def recall_tool(query: str) -> str:
    """Search long-term memory for relevant information."""
    results = await memory.recall(query, limit=5)
    if not results:
        return "No relevant memories found."
    return "\n".join(f"- {r.path}: {r.content}" for r in results)

@tool
async def forget_tool(path: str) -> str:
    """Remove information from long-term memory."""
    success = await memory.forget(path)
    return f"Deleted {path}" if success else f"Failed to delete {path}"

# Use in LangGraph
tools = [remember_tool, recall_tool, forget_tool]
```

### SDK Implementation

```python
# memoir/sdk/client.py
"""
Memoir SDK - Python client for AI agent integration.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from memoir.services import (
    MemoryService,
    BranchService,
    CryptoService,
    StoreService,
)


@dataclass
class RememberResult:
    """Result of storing a memory."""
    success: bool
    path: str
    paths: list[str]
    confidence: float
    commit_hash: Optional[str]
    timings: dict[str, float]


@dataclass
class Memory:
    """A retrieved memory."""
    path: str
    content: str
    namespace: str
    created_at: str
    updated_at: str
    metadata: dict


class BranchManager:
    """Branch operations for the SDK."""

    def __init__(self, service: BranchService):
        self._service = service

    async def list(self) -> list[str]:
        return await self._service.list_branches()

    async def current(self) -> str:
        return await self._service.current_branch()

    async def create(self, name: str) -> bool:
        result = await self._service.create_branch(name)
        return result.success

    async def delete(self, name: str, force: bool = False) -> bool:
        result = await self._service.delete_branch(name, force=force)
        return result.success

    async def checkout(self, target: str) -> bool:
        result = await self._service.checkout(target)
        return result.success

    async def merge(self, source: str) -> dict:
        result = await self._service.merge(source)
        return {"success": result.success, "conflicts": result.conflicts}

    async def history(self, limit: int = 20) -> list[dict]:
        return await self._service.get_commits(limit=limit)


class MemoryClient:
    """
    Main SDK client for memoir.

    Usage:
        async with MemoryClient("/path/to/store") as memory:
            await memory.remember("Important fact")
            results = await memory.recall("facts")
    """

    def __init__(self, store_path: str | Path):
        self.store_path = Path(store_path)
        self._memory_service: Optional[MemoryService] = None
        self._branch_service: Optional[BranchService] = None
        self._crypto_service: Optional[CryptoService] = None
        self._initialized = False

    async def __aenter__(self) -> "MemoryClient":
        await self._initialize()
        return self

    async def __aexit__(self, *args):
        await self._cleanup()

    async def _initialize(self):
        """Initialize services (lazy, connection pooling)."""
        if self._initialized:
            return
        self._memory_service = MemoryService(str(self.store_path))
        self._branch_service = BranchService(str(self.store_path))
        self._crypto_service = CryptoService(str(self.store_path))
        self._initialized = True

    async def _cleanup(self):
        """Cleanup resources."""
        # Close any open connections, caches, etc.
        pass

    async def remember(
        self,
        content: str,
        namespace: str = "default",
    ) -> RememberResult:
        """
        Classify and store content in memory.

        Args:
            content: The information to store
            namespace: Optional namespace for organization

        Returns:
            RememberResult with path, confidence, and commit info
        """
        await self._initialize()
        return await self._memory_service.remember(content, namespace)

    async def recall(
        self,
        query: str,
        limit: int = 10,
        namespace: Optional[str] = None,
    ) -> list[Memory]:
        """
        Search memories by semantic query.

        Args:
            query: Natural language search query
            limit: Maximum results to return
            namespace: Filter by namespace

        Returns:
            List of matching Memory objects
        """
        await self._initialize()
        result = await self._memory_service.recall(query, limit=limit, namespace=namespace)
        return [Memory(**m) for m in result.memories]

    async def forget(
        self,
        path: str,
        namespace: str = "default",
    ) -> bool:
        """
        Delete a memory by path.

        Args:
            path: The memory path to delete
            namespace: The namespace containing the memory

        Returns:
            True if deleted successfully
        """
        await self._initialize()
        return await self._memory_service.forget(path, namespace)

    async def proof(self, path: str, namespace: str = "default") -> str:
        """Generate cryptographic proof for a memory."""
        await self._initialize()
        result = await self._crypto_service.generate_proof(path, namespace)
        return result.proof_b64

    async def verify(self, proof: str, path: str, namespace: str = "default") -> bool:
        """Verify a cryptographic proof."""
        await self._initialize()
        result = await self._crypto_service.verify_proof(proof, path, namespace)
        return result.valid

    async def at_commit(self, commit_hash: str) -> "MemoryClient":
        """
        Get a read-only view of memory at a specific commit.

        Usage:
            historical = await memory.at_commit("abc1234")
            old_prefs = await historical.recall("preferences")
        """
        # Return a time-locked view of the store
        view = MemoryClient(self.store_path)
        view._commit_view = commit_hash
        return view

    @property
    def branch(self) -> BranchManager:
        """Access branch operations."""
        if not self._branch_service:
            self._branch_service = BranchService(str(self.store_path))
        return BranchManager(self._branch_service)
```

---

## MCP Server Design

The MCP (Model Context Protocol) server exposes memoir as tools for AI agents like Claude, OpenClaw, etc.

### MCP Server Implementation

```python
# memoir/mcp/server.py
"""
Memoir MCP Server - Model Context Protocol integration.
"""

from mcp.server import Server
from mcp.server.models import Tool, TextContent
from mcp.types import CallToolResult

from memoir import MemoryClient


def create_memoir_mcp_server(store_path: str) -> Server:
    """Create an MCP server for memoir."""

    server = Server("memoir")
    memory = MemoryClient(store_path)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="memoir_remember",
                description="Store information in long-term memory. Use for facts, preferences, context that should persist across conversations.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The information to remember"
                        },
                        "namespace": {
                            "type": "string",
                            "description": "Optional category (default, user, work, etc.)",
                            "default": "default"
                        }
                    },
                    "required": ["content"]
                }
            ),
            Tool(
                name="memoir_recall",
                description="Search long-term memory for relevant information. Use before responding to check for relevant context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language search query"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Max results (default: 5)",
                            "default": 5
                        }
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="memoir_forget",
                description="Remove information from long-term memory. Use when information is outdated or incorrect.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The memory path to delete"
                        }
                    },
                    "required": ["path"]
                }
            ),
            Tool(
                name="memoir_branches",
                description="List memory branches. Each branch can represent a different conversation context.",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            Tool(
                name="memoir_checkout",
                description="Switch to a different memory branch/context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "branch": {
                            "type": "string",
                            "description": "Branch name to switch to"
                        }
                    },
                    "required": ["branch"]
                }
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> CallToolResult:
        if name == "memoir_remember":
            result = await memory.remember(
                arguments["content"],
                namespace=arguments.get("namespace", "default")
            )
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Stored at {result.path} (confidence: {result.confidence:.2f})"
                )]
            )

        elif name == "memoir_recall":
            results = await memory.recall(
                arguments["query"],
                limit=arguments.get("limit", 5)
            )
            if not results:
                text = "No relevant memories found."
            else:
                text = "\n".join(f"- {r.path}: {r.content}" for r in results)
            return CallToolResult(
                content=[TextContent(type="text", text=text)]
            )

        elif name == "memoir_forget":
            success = await memory.forget(arguments["path"])
            text = f"Deleted {arguments['path']}" if success else "Failed to delete"
            return CallToolResult(
                content=[TextContent(type="text", text=text)]
            )

        elif name == "memoir_branches":
            branches = await memory.branch.list()
            current = await memory.branch.current()
            text = "\n".join(
                f"{'* ' if b == current else '  '}{b}"
                for b in branches
            )
            return CallToolResult(
                content=[TextContent(type="text", text=text)]
            )

        elif name == "memoir_checkout":
            success = await memory.branch.checkout(arguments["branch"])
            text = f"Switched to {arguments['branch']}" if success else "Failed"
            return CallToolResult(
                content=[TextContent(type="text", text=text)]
            )

    return server


# Entry point
def main():
    import asyncio
    import sys

    store_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/memoir-mcp"
    server = create_memoir_mcp_server(store_path)
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
```

### MCP Configuration

```json
// Claude Desktop config: ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "memoir": {
      "command": "python",
      "args": ["-m", "memoir.mcp.server", "/path/to/memories"]
    }
  }
}
```

```yaml
# OpenClaw config
mcp_servers:
  - name: memoir
    command: memoir-mcp
    args: ["/path/to/memories"]
```

### Running the MCP Server

```bash
# Direct execution
python -m memoir.mcp.server /path/to/memories

# Or via CLI
memoir mcp-server --store /path/to/memories

# With uvx (recommended for Claude Desktop)
uvx memoir-mcp /path/to/memories
```

---

## CLI Design

The CLI provides scriptable, single-command access to all memoir operations. Built with **Click** for a clean, Unix-style interface.

### CLI Usage Examples

```bash
# Store Management
memoir new /tmp/my-memories              # Create new memory store
memoir connect /tmp/my-memories          # Set default store (saved in config)
memoir refresh                           # Refresh store state

# Memory Operations
memoir remember "I love hiking on weekends"
memoir remember "Meeting with John at 3pm tomorrow" --namespace work
memoir forget profile.personal.interests.hiking
memoir recall "outdoor activities"
memoir recall "what do I like" --limit 5 --json

# Git Operations
memoir branch                            # List branches
memoir branch create experiment          # Create branch
memoir branch delete old-branch          # Delete branch
memoir checkout experiment               # Switch to branch
memoir checkout abc1234                  # Switch to commit
memoir merge experiment                  # Merge into current
memoir commits                           # Show commit history
memoir commits --limit 10 --oneline      # Compact format

# Cryptographic Operations
memoir proof profile.personal.name       # Generate SHA-256 proof
memoir verify --proof "base64..." --key profile.personal.name
memoir blame profile.personal.name       # Show change history

# Timeline & Location
memoir timeline                          # Show timeline events
memoir timeline add "2024-03-15" "Started new job"
memoir location                          # Show location events
memoir location add "San Francisco" "Visited Golden Gate"
memoir time-travel 2024-01-01            # View state at date
memoir time-travel abc1234               # View state at commit

# Analysis
memoir diff                              # Show uncommitted changes
memoir diff abc1234 def5678              # Compare two commits
memoir summarize                         # Summarize all memories
memoir summarize --type keys --pattern "profile.*"

# Utilities
memoir status                            # Show connection status
memoir code                              # Print Python integration code
memoir config                            # Show/edit configuration

# Interactive Mode
memoir tui                               # Launch interactive TUI
memoir ui                                # Launch web UI (opens browser)
```

### CLI Command Structure

```bash
memoir [OPTIONS] COMMAND [ARGS]...

Global Options:
  -s, --store PATH    Memory store path (or MEMOIR_STORE env var)
  -v, --verbose       Enable verbose output
  -q, --quiet         Suppress non-essential output
  --json              Output as JSON (for agents/scripting)
  --no-color          Disable colored output
  --version           Show version
  --help              Show help

Commands:
  # Store Management
  new          Create a new memory store
  connect      Set default memory store
  refresh      Refresh store state
  status       Show connection status (fast, no LLM)

  # Memory Operations (Core - most used by agents)
  remember     Classify and store content
  forget       Delete a memory
  recall       Search memories

  # Git Operations
  branch       Manage branches
  checkout     Switch branch or commit (--create-if-missing for agents)
  merge        Merge branches
  commits      Show commit history

  # Cryptographic
  proof        Generate cryptographic proof
  verify       Verify proof integrity
  blame        Show change history

  # Timeline & Location
  timeline     Manage timeline events
  location     Manage location events
  time-travel  View historical state

  # Analysis
  diff         Compare commits or show changes
  summarize    Generate memory summary

  # Interactive (Human use)
  tui          Launch interactive TUI
  ui           Launch web UI

  # Agent Utilities
  warmup       Pre-load models for faster subsequent calls
  mcp-server   Start MCP server for MCP-compatible agents

  # Configuration
  code         Show Python integration code
  config       Manage configuration

Exit Codes (for agent error handling):
  0 - Success
  1 - General error
  2 - Not found (no results, key doesn't exist)
  3 - Store not connected/configured
  4 - Classification failed
  5 - Git operation failed
```

### CLI Implementation (Click)

```python
# memoir/cli/main.py
"""
Memoir CLI - Command-line interface for AI memory management.
"""

import click
from rich.console import Console

from memoir.services import MemoryService, BranchService, CryptoService

console = Console()


@click.group()
@click.option('-s', '--store', envvar='MEMOIR_STORE', help='Memory store path')
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
@click.option('--json', 'json_output', is_flag=True, help='JSON output')
@click.option('--no-color', is_flag=True, help='Disable colors')
@click.pass_context
def cli(ctx, store, verbose, json_output, no_color):
    """Memoir - Git for AI Memory.

    Manage AI memories with semantic organization and version control.
    """
    ctx.ensure_object(dict)
    ctx.obj['store'] = store or get_default_store()
    ctx.obj['verbose'] = verbose
    ctx.obj['json'] = json_output
    ctx.obj['console'] = Console(no_color=no_color)


# ============== Store Commands ==============

@cli.command()
@click.argument('path', type=click.Path())
@click.pass_context
def new(ctx, path):
    """Create a new memory store."""
    from memoir.services import StoreService

    service = StoreService()
    result = service.create_store(path)

    if ctx.obj['json']:
        click.echo(json.dumps(result.to_dict()))
    else:
        if result.success:
            console.print(f"[green]✓[/green] Created memory store at {path}")
        else:
            console.print(f"[red]✗[/red] {result.error}")


@cli.command()
@click.argument('path', type=click.Path(exists=True))
@click.pass_context
def connect(ctx, path):
    """Set default memory store."""
    save_default_store(path)
    console.print(f"[green]✓[/green] Default store set to {path}")


# ============== Memory Commands ==============

@cli.command()
@click.argument('content')
@click.option('-n', '--namespace', default='default', help='Namespace')
@click.pass_context
def remember(ctx, content, namespace):
    """Classify and store content in memory."""
    import asyncio

    store_path = ctx.obj['store']
    if not store_path:
        console.print("[red]✗[/red] No store connected. Use 'memoir connect <path>' first.")
        raise SystemExit(1)

    service = MemoryService(store_path)
    result = asyncio.run(service.remember(content, namespace))

    if ctx.obj['json']:
        click.echo(json.dumps(result.to_dict()))
    else:
        if result.success:
            console.print(f"[green]✓[/green] Classified: [cyan]{result.key}[/cyan]")
            console.print(f"  Confidence: {result.confidence:.2f}")
            console.print(f"  Commit: [dim]{result.commit_hash}[/dim]")
            if ctx.obj['verbose']:
                for step, time in result.timings.items():
                    console.print(f"  {step}: {time:.3f}s")
        else:
            console.print(f"[red]✗[/red] {result.error}")


@cli.command()
@click.argument('key')
@click.option('-n', '--namespace', default='default', help='Namespace')
@click.pass_context
def forget(ctx, key, namespace):
    """Delete a memory."""
    import asyncio

    service = MemoryService(ctx.obj['store'])
    result = asyncio.run(service.forget(key, namespace))

    if result:
        console.print(f"[green]✓[/green] Deleted: {key}")
    else:
        console.print(f"[red]✗[/red] Failed to delete: {key}")


@cli.command()
@click.argument('query')
@click.option('-l', '--limit', default=10, help='Max results')
@click.option('-n', '--namespace', default=None, help='Namespace filter')
@click.pass_context
def recall(ctx, query, limit, namespace):
    """Search memories."""
    import asyncio

    service = MemoryService(ctx.obj['store'])
    result = asyncio.run(service.recall(query, limit=limit, namespace=namespace))

    if ctx.obj['json']:
        click.echo(json.dumps(result.to_dict()))
    else:
        if result.memories:
            console.print(f"[green]Found {len(result.memories)} memories[/green] ({result.timing_ms:.1f}ms)\n")
            for mem in result.memories:
                console.print(f"  [cyan]{mem['key']}[/cyan]")
                console.print(f"    {mem['content'][:80]}...")
        else:
            console.print("[yellow]No memories found[/yellow]")


# ============== Git Commands ==============

@cli.group()
@click.pass_context
def branch(ctx):
    """Manage branches."""
    pass


@branch.command('list')
@click.pass_context
def branch_list(ctx):
    """List all branches."""
    service = BranchService(ctx.obj['store'])
    branches = service.list_branches()
    current = service.current_branch()

    for b in branches:
        if b == current:
            console.print(f"[green]* {b}[/green]")
        else:
            console.print(f"  {b}")


@branch.command('create')
@click.argument('name')
@click.pass_context
def branch_create(ctx, name):
    """Create a new branch."""
    service = BranchService(ctx.obj['store'])
    result = service.create_branch(name)

    if result.success:
        console.print(f"[green]✓[/green] Created branch: {name}")
    else:
        console.print(f"[red]✗[/red] {result.error}")


@branch.command('delete')
@click.argument('name')
@click.option('--force', '-f', is_flag=True, help='Force delete')
@click.pass_context
def branch_delete(ctx, name, force):
    """Delete a branch."""
    service = BranchService(ctx.obj['store'])
    result = service.delete_branch(name, force=force)

    if result.success:
        console.print(f"[green]✓[/green] Deleted branch: {name}")
    else:
        console.print(f"[red]✗[/red] {result.error}")


@cli.command()
@click.argument('target')
@click.pass_context
def checkout(ctx, target):
    """Switch to a branch or commit."""
    service = BranchService(ctx.obj['store'])
    result = service.checkout(target)

    if result.success:
        console.print(f"[green]✓[/green] Switched to: {target}")
    else:
        console.print(f"[red]✗[/red] {result.error}")


@cli.command()
@click.argument('source')
@click.pass_context
def merge(ctx, source):
    """Merge a branch into current."""
    service = BranchService(ctx.obj['store'])
    result = service.merge(source)

    if result.success:
        console.print(f"[green]✓[/green] Merged {source} into {result.target}")
    elif result.conflicts:
        console.print(f"[yellow]⚠[/yellow] Merge conflicts detected:")
        for conflict in result.conflicts:
            console.print(f"  - {conflict}")
    else:
        console.print(f"[red]✗[/red] {result.error}")


@cli.command()
@click.option('-l', '--limit', default=20, help='Max commits')
@click.option('--oneline', is_flag=True, help='Compact format')
@click.pass_context
def commits(ctx, limit, oneline):
    """Show commit history."""
    service = BranchService(ctx.obj['store'])
    history = service.get_commits(limit=limit)

    for commit in history:
        if oneline:
            console.print(f"[yellow]{commit.hash[:7]}[/yellow] {commit.message}")
        else:
            console.print(f"[yellow]commit {commit.hash}[/yellow]")
            console.print(f"Author: {commit.author}")
            console.print(f"Date:   {commit.date}")
            console.print(f"\n    {commit.message}\n")


# ============== Crypto Commands ==============

@cli.command()
@click.argument('key')
@click.option('-n', '--namespace', default='default', help='Namespace')
@click.pass_context
def proof(ctx, key, namespace):
    """Generate cryptographic proof for a memory."""
    service = CryptoService(ctx.obj['store'])
    result = service.generate_proof(key, namespace)

    if ctx.obj['json']:
        click.echo(json.dumps(result.to_dict()))
    else:
        console.print(f"[green]✓[/green] Proof generated for: {key}")
        console.print(f"\n[dim]Proof (base64):[/dim]")
        console.print(f"{result.proof_b64}")


@cli.command()
@click.option('--proof', 'proof_b64', required=True, help='Base64 proof')
@click.option('--key', required=True, help='Memory key')
@click.option('-n', '--namespace', default='default', help='Namespace')
@click.pass_context
def verify(ctx, proof_b64, key, namespace):
    """Verify cryptographic proof."""
    service = CryptoService(ctx.obj['store'])
    result = service.verify_proof(proof_b64, key, namespace)

    if result.valid:
        console.print(f"[green]✓[/green] Proof is valid")
    else:
        console.print(f"[red]✗[/red] Proof is invalid: {result.reason}")


@cli.command()
@click.argument('key')
@click.option('-n', '--namespace', default='default', help='Namespace')
@click.pass_context
def blame(ctx, key, namespace):
    """Show change history for a memory."""
    service = CryptoService(ctx.obj['store'])
    history = service.blame(key, namespace)

    for entry in history:
        console.print(f"[yellow]{entry.commit[:7]}[/yellow] {entry.date} {entry.author}")
        console.print(f"    {entry.message}")


# ============== Interactive Commands ==============

@cli.command()
@click.option('-c', '--connect', 'store_path', help='Store to connect')
@click.pass_context
def tui(ctx, store_path):
    """Launch interactive TUI."""
    from memoir.tui.app import MemoirTUI

    path = store_path or ctx.obj['store']
    app = MemoirTUI(store_path=path)
    app.run()


@cli.command()
@click.option('-p', '--port', default=8080, help='Port number')
@click.option('--no-browser', is_flag=True, help="Don't open browser")
@click.pass_context
def ui(ctx, port, no_browser):
    """Launch web UI."""
    import webbrowser
    from memoir.ui.server import start_server

    if not no_browser:
        webbrowser.open(f"http://localhost:{port}")

    start_server(port=port)


# ============== Entry Point ==============

def main():
    cli(obj={})


if __name__ == '__main__':
    main()
```

---

## CLI for Shell-Based Agents (OpenClaw, Aider, etc.)

Shell-based AI agents like OpenClaw execute commands via `sh` or `bash` tool calls. The CLI must be optimized for this use case.

### Agent Requirements

| Requirement | Why | Implementation |
|-------------|-----|----------------|
| **Fast startup** | Agents call frequently | Lazy imports, minimal deps |
| **JSON output** | Easy parsing | `--json` flag, structured output |
| **Predictable exit codes** | Error handling | 0=success, 1=error, 2=not found |
| **No interactivity** | Agents can't respond | Never prompt, use flags |
| **Stateless** | No session assumed | Each command is independent |
| **Idempotent** | Retry-safe | Same input → same result |

### Agent-Optimized Commands

```bash
# All commands support --json for structured output
memoir remember "User prefers dark mode" --json
# {"success": true, "path": "profile.preferences.ui", "confidence": 0.92, "commit": "abc1234"}

memoir recall "user preferences" --json --limit 5
# {"success": true, "memories": [{"path": "...", "content": "...", "score": 0.95}], "count": 3}

memoir forget "profile.preferences.old" --json
# {"success": true, "deleted": "profile.preferences.old"}

# Exit codes for scripting
memoir recall "nonexistent" --json || echo "Not found"
```

### OpenClaw Skill Definition

```yaml
# .openclaw/skills/memoir.yaml
name: memoir
description: |
  Long-term memory system with semantic organization.
  Use to remember facts, preferences, and context across conversations.

store_path: /var/agents/memory  # Configure per deployment

tools:
  - name: memoir_remember
    description: |
      Store information in long-term memory. The content is automatically
      classified into a semantic path (e.g., profile.preferences.theme).
      Use for facts, preferences, and context that should persist.
    command: memoir remember "{content}" --json
    parameters:
      content:
        type: string
        description: The information to remember
        required: true
    examples:
      - content: "User's name is Alice"
      - content: "User prefers dark mode in all applications"
      - content: "Meeting with Bob scheduled for Friday 3pm"

  - name: memoir_recall
    description: |
      Search long-term memory for relevant information.
      Returns semantically similar memories ranked by relevance.
      Call this before responding to check for relevant context.
    command: memoir recall "{query}" --json --limit {limit}
    parameters:
      query:
        type: string
        description: Natural language search query
        required: true
      limit:
        type: integer
        description: Maximum results to return
        default: 5
    examples:
      - query: "user preferences"
      - query: "scheduled meetings"
      - query: "what does the user like"

  - name: memoir_forget
    description: |
      Remove information from long-term memory.
      Use when information is outdated, incorrect, or user requests deletion.
    command: memoir forget "{path}" --json
    parameters:
      path:
        type: string
        description: The memory path to delete (from recall results)
        required: true
    examples:
      - path: "profile.preferences.old_theme"

  - name: memoir_context
    description: |
      Get current memory context - what branch, recent commits, stats.
      Useful for understanding the current memory state.
    command: memoir status --json

  - name: memoir_branch
    description: |
      Switch memory context/branch. Each conversation can have its own branch.
      Use to isolate memory contexts between different tasks or users.
    command: memoir checkout "{branch}" --json --create-if-missing
    parameters:
      branch:
        type: string
        description: Branch name (e.g., "conversation_123", "user_alice")
        required: true
```

### Aider Integration

```yaml
# .aider/tools/memoir.yaml
tools:
  - name: remember
    cmd: memoir remember "$CONTENT" --json
    desc: Store information for later recall

  - name: recall
    cmd: memoir recall "$QUERY" --json --limit 5
    desc: Search stored memories
```

### Claude Code Integration (Hooks)

```bash
# .claude/hooks/post-response.sh
#!/bin/bash
# Auto-remember important facts from conversation

if [[ "$RESPONSE" =~ "I'll remember" ]]; then
    # Extract what to remember and store it
    memoir remember "$EXTRACTED_FACT" --json
fi
```

### Performance Optimizations for Agents

```python
# memoir/cli/main.py - Agent-optimized startup

# 1. Lazy imports - don't load LLM until needed
def get_classifier():
    """Lazy load classifier only when classifying."""
    from memoir.classifier.intelligent import IntelligentClassifier
    return IntelligentClassifier(...)

# 2. Connection caching via environment
MEMOIR_STORE = os.environ.get('MEMOIR_STORE', '/tmp/memoir')

# 3. Skip expensive initialization for simple commands
@cli.command()
@click.option('--json', 'json_output', is_flag=True)
def status(json_output):
    """Fast status check - no LLM initialization."""
    # Only reads git status, no model loading
    ...

# 4. Warm-start option for frequent callers
@cli.command()
def warmup():
    """Pre-load models for faster subsequent calls."""
    get_classifier()  # Force model loading
    print("Ready")
```

### Environment Variables for Agents

```bash
# Agent environment configuration
export MEMOIR_STORE="/var/agents/memory"      # Default store path
export MEMOIR_BRANCH="agent_main"             # Default branch
export MEMOIR_JSON="1"                        # Always output JSON
export MEMOIR_QUIET="1"                       # Suppress non-essential output
export MEMOIR_LLM_MODEL="gpt-4o-mini"         # LLM for classification
export MEMOIR_CACHE_DIR="/var/cache/memoir"   # Model cache location
```

### Error Handling for Agents

```bash
# Exit codes
# 0 - Success
# 1 - General error
# 2 - Not found (recall with no results, forget non-existent)
# 3 - Store not connected/configured
# 4 - Classification failed
# 5 - Git operation failed

# JSON error format
memoir recall "xyz" --json
# {"success": false, "error": "No memories found", "code": 2}

# Agents can check exit code OR parse JSON
memoir recall "query" --json && echo "Found" || echo "Not found"
```

### Benchmarks: CLI Startup Time

Target: <100ms for simple commands, <500ms for classification

```
Command                          Time      Notes
─────────────────────────────────────────────────────────
memoir --version                 15ms      No imports
memoir status --json             45ms      Git status only
memoir recall "x" --json         80ms      Pattern matching
memoir recall "x" --json         150ms     With LLM ranking
memoir remember "x" --json       350ms     Full classification
memoir remember "x" --json       120ms     Cached classifier
```

---

### Piping and Scripting

The CLI supports Unix-style piping and scripting:

```bash
# Pipe content to remember
echo "Important meeting notes" | memoir remember -

# Export memories as JSON
memoir recall "work" --json > work_memories.json

# Batch import
cat memories.txt | while read line; do
    memoir remember "$line"
done

# Chain commands
memoir checkout experiment && memoir remember "Testing new feature" && memoir checkout main

# Use in scripts
#!/bin/bash
STORE="/tmp/project-memory"
memoir connect "$STORE"
memoir remember "Build started at $(date)"
# ... build steps ...
memoir remember "Build completed successfully"

# Combine with other tools
memoir recall "api endpoints" --json | jq '.memories[].key'

# Backup current branch
memoir commits --json | jq -r '.[].hash' | head -1 > .last_commit

# Monitor changes
watch -n 5 'memoir status'
```

### Configuration File

```yaml
# ~/.config/memoir/config.yaml
default_store: /home/user/memories
editor: vim
output:
  color: true
  format: rich  # rich, plain, json
llm:
  provider: openai
  model: gpt-4o-mini
  temperature: 0
aliases:
  r: remember
  f: forget
  s: recall
```

---

## TUI Design (Claude Code Style)

### Main Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ memoir ─ /tmp/my-memory-store                          main ● 3 commits    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ╭─ Memory Tree ─────────────────────────────────────────────────────────╮  │
│  │ ▼ profile                                                             │  │
│  │   ▼ personal                                                          │  │
│  │     ├── name: "John Doe"                                              │  │
│  │     └── preferences: {...}                                            │  │
│  │   ▶ professional                                                      │  │
│  │ ▼ context                                                             │  │
│  │   └── current: {...}                                                  │  │
│  │ ▶ timeline                                                            │  │
│  ╰───────────────────────────────────────────────────────────────────────╯  │
│                                                                             │
│  ╭─ Output ──────────────────────────────────────────────────────────────╮  │
│  │ ✓ Connected to /tmp/my-memory-store                                   │  │
│  │ ✓ Loaded 42 memories across 8 namespaces                              │  │
│  │                                                                       │  │
│  │ > /remember I love hiking in the mountains on weekends                │  │
│  │                                                                       │  │
│  │ ✓ Classified: profile.personal.interests.outdoor                     │  │
│  │   Confidence: 0.92                                                    │  │
│  │   Commit: abc1234                                                     │  │
│  │   Timing: 1.2s (classify: 0.8s, store: 0.3s, commit: 0.1s)            │  │
│  ╰───────────────────────────────────────────────────────────────────────╯  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ > /remember _                                                     [↑↓] [?] │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Color Scheme (Claude Code Inspired)

```python
# memoir/tui/themes/claude.py
CLAUDE_THEME = {
    "background": "#1a1a2e",          # Deep dark blue
    "foreground": "#e0e0e0",          # Soft white
    "accent": "#ff6b35",              # Orange accent (memoir brand)
    "success": "#4ade80",             # Green
    "error": "#ef4444",               # Red
    "warning": "#fbbf24",             # Yellow
    "info": "#60a5fa",                # Blue
    "muted": "#6b7280",               # Gray
    "border": "#374151",              # Dark gray
    "highlight": "#2d2d44",           # Slightly lighter background
    "command": "#a78bfa",             # Purple for commands
    "path": "#34d399",                # Teal for memory paths
}
```

### Key UI Elements

1. **Header Bar**: Store path, current branch, commit count
2. **Memory Tree Panel**: Collapsible tree view of memories
3. **Output Panel**: Command results, logs, notifications
4. **Command Input**: Slash command entry with history
5. **Status Bar**: Quick actions, keyboard shortcuts

---

## Commands (Same as Web UI)

### Connection & Store Management
| Command | Aliases | Description |
|---------|---------|-------------|
| `/connect <path>` | `/con`, `/conn` | Connect to memory store |
| `/new <path>` | `/create` | Create new memory store |
| `/demo` | - | Load demo data |
| `/refresh` | `/ref` | Refresh current connection |

### Memory Operations
| Command | Aliases | Description |
|---------|---------|-------------|
| `/remember <content>` | `/rem` | Classify and store content |
| `/forget <key>` | `/del` | Delete a memory |
| `/recall <query>` | `/search` | Search memories |

### Git & Version Control
| Command | Aliases | Description |
|---------|---------|-------------|
| `/branch [list\|create\|delete] [args]` | `/br` | Branch operations |
| `/checkout <target>` | `/co` | Switch branch/commit |
| `/merge <source>` | - | Merge branches |
| `/commits` | `/log` | Show commit history |
| `/branches` | - | List all branches |

### Cryptographic Operations
| Command | Aliases | Description |
|---------|---------|-------------|
| `/proof <path>` | - | Generate SHA-256 proof |
| `/verify [proof]` | - | Verify proof integrity |
| `/blame <key>` | - | Show blame history |

### Time & Timeline
| Command | Aliases | Description |
|---------|---------|-------------|
| `/time-travel <target>` | `/tt` | Travel to commit/date |
| `/timeline [event]` | `/tl` | Show/add timeline events |
| `/location [place]` | `/loc` | Show/add location events |

### UI & Navigation
| Command | Aliases | Description |
|---------|---------|-------------|
| `/help` | `/h`, `?` | Show help |
| `/clear` | `/cls`, `Ctrl+L` | Clear output |
| `/quit` | `/exit`, `q` | Exit TUI |
| `/code` | - | Show Python integration code |
| `/diff [c1] [c2]` | `/d` | Compare commits |
| `/summarize [type]` | - | Generate summary |

---

## Services Layer (Code Reuse)

### Example: memory_service.py

```python
"""
Memory service - shared business logic for memory operations.
Used by both HTTP handlers and TUI.
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from memoir.classifier.intelligent import IntelligentClassifier
from memoir.store.prolly_adapter import ProllyTreeStore


@dataclass
class RememberResult:
    """Result of a remember operation."""
    success: bool
    key: str
    keys: list[str]  # All paths for multi-label
    confidence: float
    reasoning: str
    commit_hash: Optional[str]
    timings: dict[str, float]
    timeline_events: Optional[list] = None
    location_events: Optional[list] = None
    error: Optional[str] = None


@dataclass
class RecallResult:
    """Result of a recall/search operation."""
    success: bool
    memories: list[dict]
    query: str
    timing_ms: float
    error: Optional[str] = None


class MemoryService:
    """Service for memory operations."""

    def __init__(self, store_path: str):
        self.store_path = store_path
        self._store: Optional[ProllyTreeStore] = None
        self._classifier: Optional[IntelligentClassifier] = None

    async def remember(
        self,
        content: str,
        namespace: str = "default"
    ) -> RememberResult:
        """Classify and store content in memory."""
        timings = {}
        start = time.time()

        try:
            # Step 1: Initialize store
            t1 = time.time()
            store = self._get_store()
            timings["store_init"] = time.time() - t1

            # Step 2: Classify content
            t2 = time.time()
            classifier = self._get_classifier()
            result = await classifier.classify_input(content)
            timings["classification"] = time.time() - t2

            # Step 3: Store memory
            t3 = time.time()
            # ... storage logic ...
            timings["storage"] = time.time() - t3

            timings["total"] = time.time() - start

            return RememberResult(
                success=True,
                key=result.path,
                keys=result.paths or [result.path],
                confidence=result.confidence,
                reasoning=f"Classified as {result.path}",
                commit_hash="abc123",  # actual commit
                timings=timings,
                timeline_events=result.timeline_events,
                location_events=result.location_events,
            )

        except Exception as e:
            return RememberResult(
                success=False,
                key="",
                keys=[],
                confidence=0.0,
                reasoning="",
                commit_hash=None,
                timings=timings,
                error=str(e),
            )

    async def recall(self, query: str) -> RecallResult:
        """Search memories."""
        start = time.time()
        # ... search logic ...
        return RecallResult(
            success=True,
            memories=[],
            query=query,
            timing_ms=(time.time() - start) * 1000,
        )

    async def forget(self, key: str, namespace: str = "default") -> bool:
        """Delete a memory."""
        # ... delete logic ...
        return True

    def _get_store(self) -> ProllyTreeStore:
        if self._store is None:
            self._store = ProllyTreeStore(
                path=self.store_path,
                enable_versioning=True,
                auto_commit=True,
            )
        return self._store

    def _get_classifier(self) -> IntelligentClassifier:
        if self._classifier is None:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            self._classifier = IntelligentClassifier(llm=llm)
        return self._classifier
```

### Command Processor

```python
"""
Command processor - parses and dispatches commands.
Shared between Web UI and TUI.
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class CommandResult:
    """Result of command execution."""
    success: bool
    output: str
    data: Optional[Any] = None
    error: Optional[str] = None


class CommandProcessor:
    """Parses and executes slash commands."""

    # Command aliases
    ALIASES = {
        "/con": "/connect",
        "/conn": "/connect",
        "/rem": "/remember",
        "/del": "/forget",
        "/create": "/new",
        "/ref": "/refresh",
        "/h": "/help",
        "/cls": "/clear",
        "/br": "/branch",
        "/co": "/checkout",
        "/log": "/commits",
        "/tt": "/time-travel",
        "/tl": "/timeline",
        "/loc": "/location",
        "/d": "/diff",
    }

    def __init__(self, services: "ServiceContainer"):
        self.services = services
        self._handlers: dict[str, Callable] = {}
        self._register_handlers()

    def _register_handlers(self):
        """Register command handlers."""
        self._handlers = {
            "/connect": self._handle_connect,
            "/new": self._handle_new,
            "/remember": self._handle_remember,
            "/forget": self._handle_forget,
            "/recall": self._handle_recall,
            "/refresh": self._handle_refresh,
            "/branch": self._handle_branch,
            "/checkout": self._handle_checkout,
            "/merge": self._handle_merge,
            "/commits": self._handle_commits,
            "/branches": self._handle_branches,
            "/proof": self._handle_proof,
            "/verify": self._handle_verify,
            "/blame": self._handle_blame,
            "/time-travel": self._handle_time_travel,
            "/timeline": self._handle_timeline,
            "/location": self._handle_location,
            "/diff": self._handle_diff,
            "/summarize": self._handle_summarize,
            "/help": self._handle_help,
            "/clear": self._handle_clear,
            "/demo": self._handle_demo,
            "/code": self._handle_code,
        }

    def parse(self, input_text: str) -> tuple[str, list[str]]:
        """Parse command and arguments."""
        parts = input_text.strip().split(maxsplit=1)
        if not parts:
            return "", []

        cmd = parts[0].lower()
        cmd = self.ALIASES.get(cmd, cmd)

        args = parts[1].split() if len(parts) > 1 else []
        return cmd, args

    async def execute(self, input_text: str) -> CommandResult:
        """Execute a command."""
        cmd, args = self.parse(input_text)

        if not cmd.startswith("/"):
            # Natural language query - treat as recall
            return await self._handle_recall(input_text)

        handler = self._handlers.get(cmd)
        if not handler:
            return CommandResult(
                success=False,
                output=f"Unknown command: {cmd}",
                error=f"Use /help to see available commands",
            )

        return await handler(args)

    async def _handle_remember(self, args: list[str]) -> CommandResult:
        content = " ".join(args)
        if not content:
            return CommandResult(False, "Usage: /remember <content>")

        result = await self.services.memory.remember(content)
        if result.success:
            output = f"✓ Classified: {result.key}\n"
            output += f"  Confidence: {result.confidence:.2f}\n"
            output += f"  Commit: {result.commit_hash}"
            return CommandResult(True, output, data=result)
        return CommandResult(False, result.error or "Failed")

    # ... other handlers ...
```

---

## Textual App Implementation

### Main Application

```python
"""
Memoir TUI - Terminal User Interface
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from memoir.tui.screens.main_screen import MainScreen
from memoir.tui.screens.help_screen import HelpScreen


class MemoirTUI(App):
    """Memoir Terminal User Interface."""

    TITLE = "memoir"
    SUB_TITLE = "Git for AI Memory"
    CSS_PATH = "styles/memoir.tcss"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("?", "help", "Help"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, store_path: str = None):
        super().__init__()
        self.store_path = store_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield MainScreen(store_path=self.store_path)
        yield Footer()

    def action_help(self):
        self.push_screen(HelpScreen())

    def action_clear(self):
        self.query_one(MainScreen).clear_output()


def main():
    """Entry point for TUI."""
    import argparse

    parser = argparse.ArgumentParser(description="Memoir TUI")
    parser.add_argument("--connect", "-c", help="Store path to connect to")
    args = parser.parse_args()

    app = MemoirTUI(store_path=args.connect)
    app.run()


if __name__ == "__main__":
    main()
```

### Textual CSS Styling

```css
/* memoir/tui/styles/memoir.tcss */

/* Claude Code inspired dark theme */
Screen {
    background: #1a1a2e;
}

Header {
    background: #16213e;
    color: #e0e0e0;
}

Footer {
    background: #16213e;
}

/* Memory tree panel */
#tree-panel {
    border: round #374151;
    background: #1a1a2e;
    padding: 1;
    height: 40%;
}

#tree-panel .tree--label {
    color: #34d399;  /* Teal for paths */
}

#tree-panel .tree--cursor {
    background: #2d2d44;
}

/* Output panel */
#output-panel {
    border: round #374151;
    background: #1a1a2e;
    padding: 1;
    height: 1fr;
}

.output--success {
    color: #4ade80;
}

.output--error {
    color: #ef4444;
}

.output--info {
    color: #60a5fa;
}

.output--command {
    color: #a78bfa;
}

.output--path {
    color: #34d399;
}

/* Command input */
#command-input {
    dock: bottom;
    height: 3;
    border: round #374151;
    background: #16213e;
}

#command-input Input {
    background: transparent;
    border: none;
}

#command-input .input--cursor {
    color: #ff6b35;  /* Orange accent */
}

/* Status bar */
#status-bar {
    dock: top;
    height: 1;
    background: #16213e;
    padding: 0 1;
}

.status--connected {
    color: #4ade80;
}

.status--disconnected {
    color: #6b7280;
}

.status--branch {
    color: #a78bfa;
}

/* Notifications */
.notification {
    layer: notification;
    width: 50;
    height: auto;
    padding: 1 2;
    border: round $accent;
}

.notification--success {
    border: round #4ade80;
}

.notification--error {
    border: round #ef4444;
}
```

---

## Implementation Phases

### Phase 1: Services Layer Extraction (Foundation)
1. Create `services/` directory structure
2. Extract `MemoryService` from `memory_handler.py`
3. Extract `BranchService` from `branch_handler.py`
4. Extract `CryptoService` from `crypto_handler.py`
5. Extract `StoreService` from `store_handler.py`
6. Extract `TimelineService` for timeline/location
7. Create `OutputFormatter` for shared Rich output
8. Update HTTP handlers to delegate to services
9. Add comprehensive unit tests for services

### Phase 2: Python SDK (Agent Integration)
1. Create `sdk/` directory structure
2. Implement `MemoryClient` with async context manager
3. Implement `BranchManager` for git operations
4. Add connection pooling and caching
5. Create data models (`RememberResult`, `Memory`, etc.)
6. Add `at_commit()` for time-travel views
7. Write SDK documentation and examples
8. Add unit tests for SDK

### Phase 3: MCP Server
1. Create `mcp/` directory structure
2. Implement MCP server with `mcp` library
3. Define tools: `memoir_remember`, `memoir_recall`, `memoir_forget`
4. Add branch tools: `memoir_branches`, `memoir_checkout`
5. Add `memoir-mcp` entry point
6. Write Claude Desktop / OpenClaw configuration examples
7. Test with Claude Desktop and other MCP clients

### Phase 4: CLI Foundation (Agent-Optimized)
1. Set up Click application structure with lazy imports
2. Implement store commands: `new`, `connect`, `status`, `refresh`
3. Implement memory commands: `remember`, `forget`, `recall`
4. Add `--json` output for all commands (agent-friendly)
5. Define exit codes (0=success, 1=error, 2=not found, etc.)
6. Add environment variable support (`MEMOIR_STORE`, `MEMOIR_JSON`)
7. Benchmark startup time (<100ms target for simple commands)

### Phase 5: CLI Git & Branch Operations
1. Implement `branch` command group (list, create, delete)
2. Implement `checkout` with `--create-if-missing` for agents
3. Implement `merge`, `commits`
4. Add `--oneline` and formatting options
5. Implement `time-travel` command

### Phase 6: CLI Advanced Features
1. Implement `proof`, `verify`, `blame`
2. Implement `timeline`, `location`
3. Implement `diff`, `summarize`
4. Add stdin support (`memoir remember -`)
5. Add shell completions (bash, zsh, fish)
6. Add `warmup` command for pre-loading models
7. Create OpenClaw/Aider skill definition examples

### Phase 7: Basic TUI
1. Set up Textual app structure
2. Implement command input widget with history
3. Implement output panel (Rich-based)
4. Implement status bar (store path, branch)
5. Wire up core commands via services
6. Add keyboard shortcuts

### Phase 8: TUI Tree Visualization
1. Implement memory tree widget
2. Add collapsible/expandable nodes
3. Add selection and keyboard navigation
4. Show memory details panel
5. Add search/filter in tree

### Phase 9: TUI Advanced Features
1. Implement commit history viewer
2. Implement branch management modal
3. Implement diff viewer
4. Implement timeline view
5. Add help overlay screen

### Phase 10: Polish & Integration
1. Unified help system across all interfaces
2. Consistent error messages
3. Themes for TUI (Claude, default, light)
4. Performance optimization
5. Integration tests for all interfaces
6. Documentation and examples
7. PyPI packaging with optional dependencies

---

## Dependencies

```toml
# pyproject.toml additions
[project.optional-dependencies]
cli = [
    "click>=8.0.0",
    "rich>=13.0.0",
]
tui = [
    "textual>=3.0.0",
    "rich>=13.0.0",
]
mcp = [
    "mcp>=1.0.0",
]
terminal = [  # CLI + TUI
    "click>=8.0.0",
    "textual>=3.0.0",
    "rich>=13.0.0",
]
agents = [  # SDK + MCP for agent integration
    "mcp>=1.0.0",
]
all = [  # Everything
    "click>=8.0.0",
    "textual>=3.0.0",
    "rich>=13.0.0",
    "mcp>=1.0.0",
]

[project.scripts]
memoir = "memoir.cli.main:main"              # Main CLI entry point
memoir-tui = "memoir.tui.app:main"           # Direct TUI launch
memoir-mcp = "memoir.mcp.server:main"        # MCP server for AI agents
```

---

## Usage Examples

```bash
# ============== CLI Usage (Human) ==============

# Basic workflow
memoir new /tmp/my-memories
memoir connect /tmp/my-memories
memoir remember "I prefer dark mode in all applications"
memoir recall "preferences"

# Scripting
memoir remember "Build started" && make build && memoir remember "Build passed"

# JSON output for automation
memoir recall "work" --json | jq '.memories[].key'

# ============== CLI Usage (Shell Agents) ==============

# OpenClaw / Aider style - JSON output, simple commands
export MEMOIR_STORE="/var/agents/memory"

# Remember with JSON response
memoir remember "User's timezone is PST" --json
# {"success": true, "path": "profile.location.timezone", "confidence": 0.94}

# Recall with structured output
memoir recall "user timezone" --json --limit 3
# {"success": true, "memories": [...], "count": 1}

# Check exit codes
memoir recall "nonexistent" --json
echo $?  # 2 = not found

# Branch per conversation
memoir checkout "conversation_abc123" --create-if-missing --json
memoir remember "Context for this conversation" --json

# ============== TUI Usage ==============

# Start TUI
memoir tui

# Start TUI with store
memoir tui --connect /tmp/my-memory-store

# Or direct module
python -m memoir.tui

# ============== Web UI ==============

# Launch web UI
memoir ui
memoir ui --port 9000 --no-browser

# Direct module
python -m memoir.ui.server

# ============== Make Targets ==============

make cli                    # Install CLI
make tui                    # Start TUI
make tui-dev                # TUI with auto-reload
make ui                     # Start web UI
```

---

## Comparison: All Interfaces

| Feature | CLI | SDK | MCP | TUI | Web UI |
|---------|-----|-----|-----|-----|--------|
| **Primary Use** | Shell agents + humans | Python agents | MCP agents | Human interactive | Visual exploration |
| **Target** | OpenClaw, Aider, scripts | LangGraph, CrewAI | Claude Desktop | Power users | All users |
| **Session Type** | Single command | Persistent conn | Per-request | Persistent | Browser |
| **Latency** | ~80-350ms | ~2-5ms | ~15-30ms | ~2-5ms | ~30-50ms |
| **Async Native** | ❌ | ✅ | ✅ | ✅ | ✅ |
| **JSON Support** | `--json` flag | Native Python | Native | N/A | API |
| **Shell Friendly** | ✅ Native | ❌ | ❌ | ❌ | ❌ |
| **Visualization** | ❌ | ❌ | ❌ | ✅ Tree | ✅ D3.js |
| **No Dependencies** | ✅ Single binary | Python env | Python env | Python env | Browser |

### When to Use Each

| Agent/User Type | Best Interface | Why |
|-----------------|----------------|-----|
| **OpenClaw** | CLI | Shell tool calls, `--json` output |
| **Aider** | CLI | Shell integration |
| **Claude Code** | CLI | Bash tool, hooks |
| **LangGraph** | SDK | Python-native, async |
| **CrewAI** | SDK | Python tools |
| **Claude Desktop** | MCP Server | Native MCP support |
| **Human (interactive)** | TUI | Visual, session-based |
| **Human (quick)** | CLI | Fast one-off commands |
| **Human (visual)** | Web UI | Tree visualization |
| **CI/CD** | CLI | Scriptable, `--json` |

### Performance by Agent Type

```
Shell Agents (OpenClaw, Aider):
  CLI:     ████████████████████  ~80-350ms per call

Python Agents (LangGraph, CrewAI):
  SDK:     ██                    ~2-5ms per call (40x faster)

MCP Agents (Claude Desktop):
  MCP:     ████                  ~15-30ms per call
```

**Note**: For shell-based agents like OpenClaw, CLI latency is acceptable because:
1. Agent "thinking" time dominates (seconds, not milliseconds)
2. Memory operations are infrequent (a few per conversation)
3. JSON output enables clean parsing
4. No Python environment needed on agent host

---

## Future Enhancements

### SDK & MCP Enhancements
1. **Streaming recall** - Stream results as they're found
2. **Batch operations** - `remember_many()`, `recall_many()`
3. **Webhooks** - Notify on memory changes
4. **Memory subscriptions** - Watch for changes to specific paths
5. **Cross-store queries** - Search across multiple stores
6. **Embeddings cache** - Pre-computed embeddings for faster recall

### CLI Enhancements
1. **Shell completions** - Tab completion for commands, paths, and branches
2. **Watch mode** - `memoir watch` to monitor changes in real-time
3. **Import/Export** - `memoir export`, `memoir import` for backups
4. **Remote stores** - `memoir connect ssh://host/path`
5. **Aliases** - User-defined command aliases in config
6. **Hooks** - Pre/post command hooks for automation

### TUI Enhancements
1. **Split pane layout** - Tree on left, output on right
2. **Multiple tabs** - Multiple store connections
3. **Vim keybindings** - Optional vim-style navigation
4. **Mouse support** - Click to select, scroll
5. **Search overlay** - Fuzzy search across all memories
6. **Themes** - More color schemes, custom themes

### Shared Enhancements
1. **Plugin system** - Custom commands for all interfaces
2. **Sync** - Multi-device memory synchronization
3. **Encryption** - Encrypted stores at rest
4. **Metrics** - Usage analytics and performance tracking
5. **Multi-tenant** - Shared stores with access control

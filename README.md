# Memoir

<div align="center">
  <img src="static/memoir.png" alt="Memoir Logo" width="200" height="200">

  **Git for AI Memory**

  *Making AI memory as reliable and versioned as Git made code*
</div>

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Alpha-orange.svg)]()

Memoir brings Git-like version control to AI memory systems. Just as Git revolutionized software development by making code history transparent and reliable, Memoir transforms AI memory from a black box into a versioned, auditable, and cryptographically secure system.

## Features

- **Version Control**: Complete memory history with branching, merging, and rollback
- **Cryptographic Integrity**: SHA-256 hashing ensures memory state authenticity
- **Semantic Organization**: Hierarchical paths like `profile.skills.python` instead of UUIDs
- **Intelligent Classification**: LLM-powered automatic memory categorization
- **Time-travel Queries**: View AI memory as it existed at any point in time
- **Multiple Interfaces**: CLI, interactive TUI, Web UI, Python SDK, and MCP server

## Installation

### From Source

```bash
git clone https://github.com/yourusername/memoir.git
cd memoir
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

### From PyPI

```bash
pip install memoir
```

## Usage

Memoir provides multiple interfaces for different use cases.

### Command Line Interface (CLI)

Direct commands for scripting and automation:

```bash
# Create a new memory store
memoir new /path/to/store

# Connect and check status
memoir status -s /path/to/store

# Store a memory
memoir remember "I prefer dark mode" -s /path/to/store

# Search memories
memoir recall "preferences" -s /path/to/store

# Branch operations
memoir branch                     # List branches
memoir branch experiment          # Create branch
memoir checkout experiment        # Switch branch
memoir commits                    # View history
```

Set `MEMOIR_STORE` environment variable to avoid passing `-s` each time:

```bash
export MEMOIR_STORE=/path/to/store
memoir status
memoir remember "User prefers Python over JavaScript"
memoir recall "programming"
```

Use `--json` flag for machine-readable output:

```bash
memoir status --json
memoir recall "preferences" --json
```

### Interactive TUI

A scrolling command-line interface for interactive sessions:

```bash
memoir tui
memoir tui -c /path/to/store
```

Commands within the TUI:

```
/connect <path>   Connect to a memory store
/new <path>       Create a new memory store
/status           Show store status
/remember <text>  Store a memory
/recall <query>   Search memories
/forget <key>     Delete a memory
/branch [name]    List or create branches
/checkout <ref>   Switch branch or commit
/commits          Show commit history
/help             Show available commands
/quit             Exit
```

Aliases: `/con`, `/rem`, `/del`, `/br`, `/co`, `/log`, `/h`

### Web UI

Browser-based interface with visualization:

```bash
python -m memoir.ui.server
```

Open http://localhost:8080 in your browser. Use `/demo` command to explore with sample data.

### Python SDK

For integration into Python applications:

```python
from memoir.sdk import MemoryClient

async def main():
    client = MemoryClient("/path/to/store")

    # Store memory
    result = await client.remember("User prefers dark mode")
    print(f"Stored at: {result.key}")

    # Search memories
    results = await client.recall("preferences", limit=10)
    for mem in results.memories:
        print(f"{mem['path']}: {mem['content']}")

    # Branch operations
    client.branch.create("experiment")
    client.branch.checkout("experiment")
    branches = client.branch.list()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

Synchronous API is also available:

```python
client = MemoryClient("/path/to/store")
result = client.remember_sync("User prefers dark mode")
results = client.recall_sync("preferences")
```

### MCP Server

For integration with Claude Desktop and other MCP-compatible tools:

```bash
export MEMOIR_STORE=/path/to/store
memoir-mcp
```

Configure in Claude Desktop's MCP settings to enable memoir tools.

## Development

```bash
# Setup
make setup

# Run tests
make test

# Lint and format
make lint
make format

# Run all checks
make ci
```

## Architecture

| Component | Description |
|-----------|-------------|
| ProllyTreeStore | Git-like versioned storage with cryptographic integrity |
| IntelligentClassifier | LLM-powered classification with dynamic taxonomy |
| IntelligentSearchEngine | Multi-strategy search with relevance scoring |
| Services Layer | Shared business logic for all interfaces |

## License

Apache License 2.0 - see [LICENSE](LICENSE) file.

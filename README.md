# Memoir

<div align="center">
  <img src="https://raw.githubusercontent.com/zhangfengcdt/memoir/main/static/memoir.png" alt="Memoir Logo" width="200" height="200">

  **Git for AI Memory**

  *Making AI memory as reliable and versioned as Git made code*
</div>

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://github.com/zhangfengcdt/memoir/blob/main/LICENSE)
[![Status](https://img.shields.io/badge/Status-Alpha-orange.svg)]()

Memoir brings Git-like version control to AI memory systems. Just as Git revolutionized software development by making code history transparent and reliable, Memoir transforms AI memory from unversioned, mutable storage into a versioned, auditable, and cryptographically secure system.

## Why Memoir

Long-running AI agents like Claude Code, OpenClaw, and LangGraph-based systems need persistent memory. Current approaches rely on flat files (Memory.md, CLAUDE.md), rolling logs, or ad-hoc storage - fine for simple cases, but inadequate for production multi-agent systems where memory conflicts, state corruption, and debugging complexity become real problems.

Memoir brings engineering rigor to agent memory:

- **Version Control for Agent Memory**: Branch experimental strategies, rollback bad states, merge successful approaches - the same workflow that made collaborative software development reliable
- **Semantic Paths over Flat Files**: Replace unstructured Memory.md files with hierarchical paths like `user.preferences.coding_style` that agents can query precisely
- **Automatic Organization**: LLM-powered classification so agents store memories without manual path management
- **Debuggable History**: Time-travel queries let you understand why an agent behaved a certain way by viewing its memory at any point
- **Agent-Native Interfaces**: CLI and SDK for agent integration, TUI and Web UI for human inspection, MCP server for any MCP-compatible client
- **KV-Cache Friendly**: Structured, consistent memory format enables KV-cache aware prompting to reduce inference costs and latency
- **Multi-Agent Coordination**: Shared memory with cryptographic integrity enables multiple agents to collaborate on the same knowledge base safely

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
pip install memoir-ai
```

> The distribution name on PyPI is `memoir-ai` (the `memoir` name was already taken). After install, the Python import is still `import memoir` and the CLI is still `memoir`.

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

### Agent Integration

Memoir is designed for AI agent integration. Use `--machine-readable` (or `--json-schema`) to get the full CLI schema as JSON:

```bash
memoir --machine-readable
```

This outputs structured JSON with all commands, arguments, options, and exit codes - enabling agents to programmatically understand the CLI without parsing help text:

```json
{
  "name": "memoir",
  "version": "0.1.0",
  "exit_codes": {"0": "success", "1": "error", "2": "not_found", "3": "no_store", "5": "git_failed"},
  "env_vars": {"MEMOIR_STORE": "Default store path", "MEMOIR_JSON": "Always output JSON"},
  "commands": {
    "memory": [{"name": "remember", "arguments": [...], "options": [...]}],
    "branch": [{"name": "checkout", "options": [{"flags": ["--create-if-missing"]}]}]
  }
}
```

Recommended agent setup:

```bash
# Set environment for JSON output
export MEMOIR_STORE=/path/to/store
export MEMOIR_JSON=1

# Quick workflow
memoir remember "learned fact"       # Returns JSON with key, confidence
memoir recall "query" --limit 5      # Returns JSON with memories array
memoir checkout context-branch --create-if-missing  # Auto-create context branches
```

Exit codes enable reliable error handling: `0` success, `1` error, `2` not found, `3` no store configured, `5` git operation failed.

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

For integration with MCP-compatible clients:

```bash
export MEMOIR_STORE=/path/to/store
memoir-mcp
```

Add to your MCP client configuration to enable memoir tools.

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

## Benchmarks

Benchmark the classifier and search performance with different LLM providers:

```bash
# Using OpenAI (default)
export OPENAI_API_KEY=your-key
python benchmarks/classifier.py

# Using Anthropic Claude
export ANTHROPIC_API_KEY=your-key
python benchmarks/classifier.py --model claude-haiku-4-5

# Using Google Gemini
export GEMINI_API_KEY=your-key
python benchmarks/classifier.py --model gemini/gemini-1.5-flash

# Using Ollama (local, free)
python benchmarks/classifier.py --model ollama/llama3.2

# Run specific tests
python benchmarks/classifier.py --skip-recall        # Only remember benchmarks
python benchmarks/classifier.py --num-cases 10      # Limit test cases
python benchmarks/classifier.py --verbose           # Detailed output
```

See all options with `python benchmarks/classifier.py --help` or `make benchmark`.

## Architecture

| Component | Description |
|-----------|-------------|
| ProllyTreeStore | Git-like versioned storage with cryptographic integrity |
| IntelligentClassifier | LLM-powered classification with 3-level taxonomy paths |
| IntelligentSearchEngine | Single-stage LLM search with prompt caching support |
| Services Layer | Shared business logic for all interfaces |

## License

Apache License 2.0 - see [LICENSE](https://github.com/zhangfengcdt/memoir/blob/main/LICENSE) file.

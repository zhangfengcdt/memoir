# Welcome to Memoir's Documentation

**Memoir** is a high-performance semantic memory system for AI agents that brings Git-like version control to AI memory management. It replaces opaque vector databases with transparent, versioned, cryptographically secure memory storage using hierarchical semantic paths.

## Key Features

* **Git-like Versioning**: Branch, commit, merge, and rollback memories with cryptographic integrity
* **Semantic Paths**: Replace UUID keys with meaningful paths like `profile.professional.skills.python`
* **O(log n) Lookups**: Fast hierarchical search instead of expensive vector operations
* **Memory Aggregation**: Automatic consolidation of related memories at semantic locations
* **Clean Architecture**: Proper separation of storage, classification, and search layers
* **Multiple Search Engines**: Choose between fast keyword-based or intelligent LLM-powered search

## Integrations

Memoir ships first-class plugins that give agents versioned memory natively:

* **[Claude Code](claude_code.md)** — slash commands, auto-capture hooks, and codebase onboarding for coding sessions.
* **[Codex](codex.md)** — the same memory workflows for OpenAI Codex.
* **[Hermes](hermes.md)** — a memory provider for the Nous Research personal-assistant agent: auto-capture, recall/remember/forget/sync tools, and session-fork branching.
* **[OpenClaw](openclaw.md)** — a memory plugin for the OpenClaw personal-assistant gateway: auto-capture, recall/remember/forget tools, cross-session memory (per-agent scope), and an in-chat `/memoir` command.

Any other MCP host: the **[MCP server](mcp.md)** (`memoir-mcp`) plugs memoir into Claude Desktop, Cursor, Cline, Windsurf, VS Code, Zed, Continue, LibreChat, and more — one store across every tool.

Community: **[opencode-memoir](https://github.com/disafronov/opencode-memoir)** brings memoir to OpenCode.

## Quick Example

```python
from memoir import ProllyTreeMemoryStoreManager
from memoir.classifier.intelligent import IntelligentClassifier
from memoir.search.intelligent import IntelligentSearchEngine

# Initialize components with dependency injection
store = ProllyTreeStore(path="./memory_store")
classifier = IntelligentClassifier(llm=llm)
search_engine = IntelligentSearchEngine(llm=llm, store=store)

# Create memory manager
memory_manager = ProllyTreeMemoryStoreManager(
    prolly_store=store,
    classifier=classifier,
    search_engine=search_engine
)

# Store memories with automatic classification
await memory_manager.store_memory(
    content="I work as a senior software engineer at TechCorp",
    namespace="user123",
    auto_classify=True
)

# Search with intelligent path selection
results = await memory_manager.search_memories(
    query="What is the user's job?",
    namespace="user123"
)
```

## Performance

* **Search latency**: 0.1-1ms (vs 150-750ms for vector databases)
* **Storage latency**: 20-30ms (vs 200-600ms traditional)
* **Classification**: 1-5ms pattern matching (vs 2-5s LLM-only)
* **Overall improvement**: 10-20x faster end-to-end

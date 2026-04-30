# Quick Start Guide

This guide will help you get started with Memoir in just a few minutes.

## Installation

```bash
pip install memoir-ai
```

That's it. As of v0.1.7, `litellm` is a default dependency, so both
direct-path and LLM-backed commands work out of the box. (Prior to
v0.1.7 you had to add the `[litellm]` extra explicitly.)

For development:

```bash
pip install -e ".[dev]"
```

## CLI quick start

The CLI is the fastest path. Memoir's CLI defaults to Anthropic
**`claude-haiku-4-5`** as of v0.1.6 — set your key first:

```bash
export ANTHROPIC_API_KEY="sk-ant-…"
```

Then create a store and round-trip a memory:

```bash
# 1. Create + connect
memoir new ~/.memoir/notes
memoir connect ~/.memoir/notes

# 2. Store with an explicit path (offline, no LLM call)
memoir remember "Feng prefers tabs and 2-space indents" \
    -p preferences.coding.style

# 3. Store with auto-classification (LLM picks the path; needs API key)
memoir remember "I work in Pacific time"

# 4. Read back by path (offline)
memoir get preferences.coding.style

# 5. Semantic search (LLM-backed)
memoir recall "what does Feng prefer?"
```

### Picking a different model

The default is Haiku. Override per call:

```bash
memoir recall "..."   --model gpt-4o-mini   # needs OPENAI_API_KEY
memoir remember "..." --model claude-sonnet-4-5
```

…or set globally for the shell:

```bash
export MEMOIR_LLM_MODEL=gpt-4o-mini
export OPENAI_API_KEY=sk-…
```

Resolution order: `--model` flag → `MEMOIR_LLM_MODEL` → `claude-haiku-4-5`.

## Python API

For programmatic use, set up the LLM directly via memoir's helpers:

```python
import os
from memoir.llm import get_llm

os.environ["ANTHROPIC_API_KEY"] = "your-api-key-here"

# memoir.llm.get_llm() routes through litellm (a default dep as of v0.1.7).
llm = get_llm(model="claude-haiku-4-5", temperature=0)
```

If you prefer a langchain wrapper directly (or any other client), you
can pass it in too — memoir's classifier and search engine accept any
LLM with a `.invoke()` method.

### Initialize the memory system components

```python
from memoir.store.prolly_adapter import ProllyTreeStore
from memoir.classifier.intelligent import IntelligentClassifier
from memoir.search.intelligent import IntelligentSearchEngine
from memoir import ProllyTreeMemoryStoreManager

# Create storage layer
store = ProllyTreeStore(
    path="./memory_store",
    enable_versioning=True
)

# Create intelligent classifier
classifier = IntelligentClassifier(
    llm=llm,
    confidence_thresholds={
        "high": 0.8,
        "medium": 0.5,
        "low": 0.0
    }
)

# Create search engine
search_engine = IntelligentSearchEngine(
    llm=llm,
    store=store
)

# Assemble memory manager
memory_manager = ProllyTreeMemoryStoreManager(
    prolly_store=store,
    classifier=classifier,
    search_engine=search_engine
)
```

## Storing Memories

Store memories with automatic semantic classification:

```python
# Store a simple memory
await memory_manager.store_memory(
    content="My name is Sarah and I'm 32 years old",
    namespace="user123",
    auto_classify=True
)

# Store with metadata
await memory_manager.store_memory(
    content="I work as a senior software engineer at TechCorp",
    namespace="user123",
    metadata={"source": "conversation", "confidence": 0.95},
    auto_classify=True
)
```

The memories will be automatically classified to semantic paths like:

- `profile.identity.name.first`
- `profile.demographics.age`
- `profile.professional.occupation.role`

## Searching Memories

Search for memories using natural language queries:

```python
# Simple search
results = await memory_manager.search_memories(
    query="What is the user's name?",
    namespace="user123"
)

for result in results:
    print(f"Found: {result.content}")
    print(f"Path: {result.id}")

# Search with limit
results = await memory_manager.search_memories(
    query="Tell me about the user's work",
    namespace="user123",
    limit=5
)
```

## Version Control

Memoir provides Git-like version control for memories with fine-grained commit control:

**Traditional Auto-Commit (Default)**:

```python
# Every operation commits automatically (backward compatible)
store = ProllyTreeStore(path="./store", auto_commit=True)  # Default
await store.store_memory_async(namespace, content, key)  # Commits immediately
```

**Batch Commit Control**:

```python
# Batch multiple operations before committing
store = ProllyTreeStore(path="./store", auto_commit=False)

# Store multiple memories without committing (auto_commit=False)
await store.store_memory_async(namespace, content1, key1)
await store.store_memory_async(namespace, content2, key2)
await store.store_memory_async(namespace, content3, key3)

# Commit all changes as a single logical unit
commit_hash = store.commit("Batch of related memories")
```

**Memory Manager Level Control**:

```python
# Enable batch control by setting auto_commit=False on the store
store.auto_commit = False
memory_manager = ProllyTreeMemoryStoreManager(
    prolly_store=store,
    classifier=classifier,
    search_engine=search_engine
)

# Store memories without committing (auto_commit=False)
await memory_manager.store_memory(content1, namespace)
await memory_manager.store_memory(content2, namespace)

# Commit the batch
commit_hash = memory_manager.store_commit("User onboarding session")
```

**Mixed Workflow**:

```python
# Mix auto-commit and batch operations
store.auto_commit = True
await store.store_memory_async(critical_memory, key)  # Immediate commit

store.auto_commit = False  # Switch to batch mode
await store.store_memory_async(routine1, key1)
await store.store_memory_async(routine2, key2)
store.commit("Batch of routine updates")

store.auto_commit = True  # Re-enable for future critical operations
```

## Search Engine

Memoir uses an intelligent LLM-powered search engine:

```python
from memoir.search.intelligent import IntelligentSearchEngine

search_engine = IntelligentSearchEngine(llm=llm, store=store)
```

## Next Steps

- Explore the [architecture](architecture.md) to understand the system design
- Check out [basic_usage](basic_usage.md) for a complete working example
- See the [examples](examples.md) for advanced patterns and use cases
- Visit the [api/memoir](api/memoir.md) for complete API reference

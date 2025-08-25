# Memoir

<div align="center">
  <img src="static/memoir.png" alt="Memoir Logo" width="200" height="200">

  **Git for AI Memory**

  *Making AI memory as reliable and versioned as Git made code*
</div>

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Alpha-orange.svg)]()

## Overview

Memoir brings Git-like version control to AI memory systems. Just as Git revolutionized software development by making code history transparent and reliable, Memoir transforms AI memory from a "black box" into a versioned, auditable, and cryptographically secure system.

**The Problem**: Current AI systems have no memory version history, lack integrity checks, and provide no audit trails for critical decisions.

**The Solution**: Memoir provides cryptographically hashed memory states, complete version history, and the ability to branch, merge, and rollback AI memory - making AI systems as reliable and transparent as modern software development.

## Key Features

### Git-like Version Control
- **Complete memory history**: Every change is tracked and versioned
- **Cryptographic integrity**: SHA-256 hashing ensures memory state authenticity
- **Time-travel queries**: View AI memory as it existed at any point in time
- **Branching & merging**: Experiment safely with different AI strategies
- **Audit trails**: Full transparency for regulatory compliance and debugging

### Semantic Memory Organization
- **Hierarchical paths**: `profile.professional.skills.technical.programming.python`
- **Intelligent classification**: LLM-powered automatic memory categorization
- **Deterministic keys**: Replace random UUIDs with meaningful semantic paths
- **~800 predefined categories**: Comprehensive taxonomy for real-world use cases

### Git for AI Memory: The Paradigm Shift

Just as Git transformed software development from fragile, unversioned code to reliable, collaborative development, Memoir transforms AI memory from opaque, unreliable storage to transparent, versioned, and auditable systems.

| Git Concept | Memoir Equivalent | Benefit |
|-------------|-------------------|---------|
| `git commit` | Memory state snapshot | Immutable history of AI decisions |
| `git branch` | Memory state branching | Safe AI experimentation |
| `git merge` | Memory state merging | Combine successful AI strategies |
| `git log` | Memory history | Full audit trail for compliance |
| `git diff` | Memory state comparison | See exactly what changed in AI memory |
| `SHA-1 hash` | SHA-256 memory hash | Cryptographic integrity verification |

### Core Components

1. **ProllyTreeStore**: Git-like versioned storage with cryptographic integrity
2. **IntelligentClassifier**: LLM-powered classification with dynamic taxonomy expansion
3. **IntelligentSearchEngine**: Multi-strategy search with relevance scoring
4. **ProllyTreeMemoryStoreManager**: Complete audit trails and branching capabilities
5. **TaxonomyPresets**: Hierarchical organization of ~800 meaningful memory paths

## Quick Start

### Installation

#### Option 1: Docker (Recommended for Testing)

```bash
# Quick start with startup script
git clone https://github.com/yourusername/memoir.git
cd memoir
./docker.sh start

# Or run directly from docker/ folder
cd docker
./start-docker.sh start

# Open browser to http://localhost:8080
```

#### Option 2: Python Package

```bash
pip install memoir
```

#### Option 3: From Source

```bash
git clone https://github.com/yourusername/memoir.git
cd memoir
pip install -e ".[dev]"
```

> 📋 **See [docker/README.md](./docker/README.md) for comprehensive Docker setup and usage guide**
> 
> **Quick Docker Test**: After starting with `./docker.sh start`, open http://localhost:8080 and try `/demo` to explore the interface with demo data.

### Basic Usage with Version Control

```python
import asyncio
from langchain_openai import ChatOpenAI
from memoir import ProllyTreeMemoryStoreManager
from memoir.classifier.intelligent import IntelligentClassifier
from memoir.search.intelligent import IntelligentSearchEngine
from memoir.store.prolly_adapter import ProllyTreeStore
from memoir.taxonomy.taxonomy_presets import TaxonomyVersion

async def main():
    # Initialize LLM
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=500)

    # Create components with dependency injection
    store = ProllyTreeStore(
        path="./memory_store",
        enable_versioning=True
    )

    classifier = IntelligentClassifier(
        llm=llm,
        taxonomy_version=TaxonomyVersion.GENERAL,
        confidence_thresholds={
            "high": 0.8,
            "medium": 0.5,
            "low": 0.0
        }
    )

    search_engine = IntelligentSearchEngine(llm=llm, store=store)

    # Initialize memory manager with Git-like versioning
    memory = ProllyTreeMemoryStoreManager(
        prolly_store=store,
        classifier=classifier,
        search_engine=search_engine,
        enable_versioning=True  # Git-like version control enabled
    )

    user_id = "user123"

    # Store memories with automatic classification and versioning
    semantic_key = await memory.store_memory(
        content="I have 5 years of Python experience",
        namespace=user_id,
        auto_classify=True
    )
    # → Creates cryptographically verifiable memory commit
    # → Automatically classified to: profile.professional.skills.technical.programming

    # Store experimental memory on branch
    branch_id = await memory.branch_memories(user_id, "experiment")

    await memory.store_memory(
        content="I'm learning Rust programming",
        namespace=user_id,
        auto_classify=True
    )

    # Search memories semantically
    results = await memory.search_memories(
        query="What programming skills do I have?",
        namespace=user_id,
        limit=5
    )

    # Time-travel: View memory versions
    memory_versions = await memory.get_memory_versions(
        semantic_key="profile.professional.skills",
        namespace=user_id
    )

    print(f"Found {len(results)} current results")
    for result in results:
        print(f"Memory: {result.content}")
        print(f"Path: {result.id}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Advanced Version Control Operations

```python
# Branch and merge operations (like Git)
feature_branch_id = await memory.branch_memories(user_id, "feature_branch")

# Store memories on feature branch
await memory.store_memory(
    content="New feature memory",
    namespace=user_id,
    auto_classify=True
)

# Merge back to main branch
merge_result = await memory.merge_memories(
    namespace=user_id,
    source_branch="feature_branch",
    target_branch="main",
    strategy="union"
)

# Search with filters
results = await memory.search_memories(
    query="programming skills",
    namespace=user_id,
    limit=10,
    filter={"confidence": {"$gte": 0.7}}
)

# Get performance metrics
metrics = memory.get_performance_metrics()
print(f"Average search time: {metrics.get('avg_search_time_ms', 0):.1f}ms")
```

### Alternative LLM Providers

```python
# OpenAI
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4", temperature=0)

# Anthropic Claude
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-3-sonnet-20240229", temperature=0)

# Then use with any classifier
classifier = IntelligentClassifier(
    llm=llm,
    taxonomy_version=TaxonomyVersion.GENERAL
)
```

### Key API Methods with Version Control
```python
# Store memories with automatic classification and versioning
semantic_key = await memory.store_memory(
    content="Your memory content here",
    namespace="user_id",
    auto_classify=True,
    metadata={"source": "conversation"}
)

# Search memories semantically
results = await memory.search_memories(
    query="Your search query",
    namespace="user_id",
    limit=10
)

# Version control operations
branch_id = await memory.branch_memories("user_id", "experiment")
merge_result = await memory.merge_memories(
    namespace="user_id",
    source_branch="experiment",
    target_branch="main"
)

# Time-travel: View memory versions
versions = await memory.get_memory_versions(
    semantic_key="profile.professional.skills",
    namespace="user_id"
)

# Compare memory states
comparison = await memory.compare_memory_states(
    namespace="user_id",
    timestamp_1=1234567890,
    timestamp_2=1234567900
)
```

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) file.

---

<div align="center">

**🔄 Bring Git-like reliability to your AI memory systems!** 🔄

*Make AI memory as transparent and trustworthy as your code*

</div>

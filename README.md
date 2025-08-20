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
2. **SemanticTaxonomy**: Hierarchical organization of ~800 meaningful memory paths
3. **SemanticClassifier**: LLM-powered classification with intelligent fallbacks
4. **HierarchicalSearchEngine**: Multi-strategy search with relevance scoring
5. **VersionedMemoryManager**: Complete audit trails and branching capabilities

## Quick Start

### Installation

```bash
pip install memoir
```

### Basic Usage with Version Control

```python
import asyncio
from langchain_openai import ChatOpenAI
from memoir import ProllyTreeMemoryStoreManager
from memoir.taxonomy.semantic_classifier import SemanticClassifier
from memoir.taxonomy.iterative_taxonomy import LLMIterativeTaxonomy

async def main():
    # Initialize LLM
    llm = ChatOpenAI(model="gpt-4", temperature=0)

    # Create LLM-driven iterative taxonomy
    taxonomy = LLMIterativeTaxonomy(llm=llm)
    classifier = SemanticClassifier(llm=llm, taxonomy=taxonomy)

    # Initialize memory manager with Git-like versioning
    memory_manager = ProllyTreeMemoryStoreManager(
        prolly_path="./memory_db",
        classifier=classifier,
        enable_versioning=True  # Git-like version control enabled
    )

    user_id = "user123"

    # Store memories with automatic classification and versioning
    commit_1 = await memory_manager.store_memory(
        content="I have 5 years of Python experience",
        namespace=user_id
    )
    # → Creates cryptographically verifiable memory commit
    # → Automatically classified to: profile.professional.skills.technical.programming

    # Create experimental branch for testing new memories
    experiment_branch = await memory_manager.create_branch("experiment_branch")

    # Store experimental memory on branch
    await memory_manager.store_memory(
        content="I'm learning Rust programming",
        namespace=user_id,
        branch="experiment_branch"
    )

    # Search memories semantically with version control
    results = await memory_manager.search_memories(
        query="What programming skills do I have?",
        namespace=user_id,
        limit=5
    )

    # Time-travel: View memory as it existed at commit_1
    historical_results = await memory_manager.search_memories(
        query="What programming skills do I have?",
        namespace=user_id,
        at_commit=commit_1  # Time-travel query
    )

    # Verify memory integrity (like git fsck)
    integrity_check = await memory_manager.verify_integrity()
    print(f"Memory integrity: {'✅ Valid' if integrity_check else '❌ Corrupted'}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Advanced Version Control Operations

```python
# Branch and merge operations (like Git)
await memory_manager.create_branch("feature_branch")
await memory_manager.checkout("feature_branch")

# Store memories on feature branch
await memory_manager.store_memory("New feature memory", namespace=user_id)

# Merge back to main branch
await memory_manager.checkout("main")
await memory_manager.merge("feature_branch")

# View commit history (like git log)
history = await memory_manager.get_commit_history(namespace=user_id)
for commit in history:
    print(f"Commit: {commit.hash[:8]} - {commit.message} - {commit.timestamp}")

# Compare memory states (like git diff)
diff = await memory_manager.diff_commits(commit_1, commit_2)
print(f"Added: {len(diff.added)} memories")
print(f"Modified: {len(diff.modified)} memories")
print(f"Deleted: {len(diff.deleted)} memories")
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
classifier = SemanticClassifier(llm=llm, taxonomy=LLMIterativeTaxonomy(llm=llm))
```

### Key API Methods with Version Control
```python
# Store memories with automatic classification and versioning
commit_hash = await memory_manager.store_memory(
    content="Your memory content here",
    namespace="user_id",
    message="Added new user preference"  # Git-style commit message
)

# Search memories semantically
results = await memory_manager.search_memories(
    query="Your search query",
    namespace="user_id",
    limit=10
)

# Time-travel queries
historical_results = await memory_manager.search_memories(
    query="Your search query",
    namespace="user_id",
    at_commit="a7f3b2c1..."  # View memory at specific commit
)

# Branch operations
await memory_manager.create_branch("experiment")
await memory_manager.checkout("experiment")
await memory_manager.merge("experiment", into="main")

# Integrity verification
is_valid = await memory_manager.verify_integrity()
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

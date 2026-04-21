# Architecture Overview

Memoir implements a **clean layered architecture** with proper separation of concerns and dependency injection patterns. This design enables high performance, maintainability, and flexibility.

## Core Principles

1. **Git-like Versioning**: Every memory change is tracked with cryptographic integrity
2. **Semantic Paths**: Replace UUID keys with meaningful hierarchical paths
3. **Memory Aggregation**: Group related memories at semantic locations
4. **Dependency Injection**: Clean separation between storage, classification, and search
5. **Performance First**: O(log n) lookups instead of expensive vector operations

## System Architecture

```text
┌─────────────────────────────────────────────────┐
│               Memory Manager                    │
│           (Orchestration Layer)                 │
└─────────────────┬───────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
┌───▼────┐   ┌────▼────┐   ┌────▼────┐
│Storage │   │Classify │   │ Search  │
│ Layer  │   │  Layer  │   │ Engine  │
└────────┘   └─────────┘   └─────────┘
    │             │             │
┌───▼────┐   ┌────▼────┐   ┌────▼────┐
│Prolly  │   │Taxonomy │   │Path     │
│ Tree   │   │ System  │   │Selection│
└────────┘   └─────────┘   └─────────┘
```

## Layer Details

### 1. Storage Layer (`memoir.store`)

The storage layer provides pure data persistence without business logic:

- **ProllyTreeStore**: Git-like versioned key-value storage
- **Memory Aggregation**: Groups memories at semantic paths
- **Cryptographic Integrity**: SHA-256 hashing for all operations
- **Efficient Queries**: O(log n) prefix searches

```python
from memoir.store.prolly_adapter import ProllyTreeStore

store = ProllyTreeStore(
    path="./memory_store",
    enable_versioning=True,
    cache_size=10000
)
```

### 2. Classification Layer (`memoir.classifier`)

Handles semantic classification of memories into hierarchical paths:

- **SemanticClassifier**: Fast pattern-based classification (1-5ms)
- **IntelligentClassifier**: LLM-powered with dynamic taxonomy expansion
- **Confidence Thresholds**: Configurable acceptance criteria
- **Multi-stage Pipeline**: Pattern matching → LLM → Expansion

```python
from memoir.classifier.intelligent import IntelligentClassifier

classifier = IntelligentClassifier(
    llm=llm,
    confidence_thresholds={
        "high": 0.8,    # Auto-store
        "medium": 0.5,  # Review
        "low": 0.0      # Reject threshold
    }
)
```

### 3. Search Engine Layer (`memoir.search`)

Provides intelligent memory retrieval capabilities:

- **IntelligentSearchEngine**: LLM-powered path selection
- **Multi-strategy**: Breadth-first, depth-first, best-match
- **Relevance Scoring**: Combined semantic and structural scoring

```python
# Intelligent LLM-powered search
from memoir.search.intelligent import IntelligentSearchEngine
search_engine = IntelligentSearchEngine(llm=llm, store=store)
```

### 4. Memory Manager (`memoir.core`)

Orchestrates all components with proper dependency injection:

- **Dependency Injection**: Clean separation of concerns
- **Transaction Management**: Atomic operations
- **Version Control**: Branching, merging, rollback
- **Performance Monitoring**: Built-in metrics

```python
from memoir.core.memory import ProllyTreeMemoryStoreManager

memory_manager = ProllyTreeMemoryStoreManager(
    prolly_store=store,        # Injected dependency
    classifier=classifier,      # Injected dependency
    search_engine=search_engine # Injected dependency
)
```

## Data Flow

**Storage Flow**:

```text
Memory Input → Classification → Path Selection → Aggregation → Storage
     ↓              ↓              ↓              ↓            ↓
"I work at X"  →  Classifier  →  "profile.   →  Aggregate  → ProllyTree
                   Analysis      professional.   with        Storage
                                occupation"     similar
```

**Retrieval Flow**:

```text
Query → Path Selection → Storage Lookup → Aggregation → Results
  ↓          ↓               ↓             ↓            ↓
"user job" → "profile.*" → Tree Search → Collect → Ranked Results
             paths                        memories
```

## Memory Aggregation

Memories are aggregated at semantic paths rather than stored individually:

**Traditional Approach**:

```text
uuid-1234-5678 → "I work at TechCorp"
uuid-9876-5432 → "I'm a software engineer"
uuid-1111-2222 → "I've been coding for 5 years"
```

**Memoir Approach**:

```text
profile.professional.occupation → {
  "memories": [
    {"content": "I work at TechCorp", "confidence": 0.95},
    {"content": "I'm a software engineer", "confidence": 0.87},
    {"content": "I've been coding for 5 years", "confidence": 0.82}
  ],
  "count": 3,
  "last_updated": "2024-01-15"
}
```

## Taxonomy System

The taxonomy system provides hierarchical organization:

**Fixed Taxonomy** (`memoir.taxonomy.semantic`):
- ~800 predefined paths
- Fast pattern matching
- Consistent organization

**Dynamic Taxonomy** (`memoir.taxonomy.iterative`):
- LLM-driven expansion
- Automatic growth
- Context-aware paths

**Example Paths**:

```text
profile.
├── identity.
│   ├── name.{first,last,full}
│   └── demographics.{age,location}
├── professional.
│   ├── occupation.{role,company}
│   └── skills.{technical,soft}
└── personal.
    ├── interests.{hobbies,sports}
    └── relationships.{family,friends}
```

## Performance Characteristics

**Search Performance**:

- Semantic Search: 0.1-1ms average latency
- Intelligent Search: 100-500ms (includes LLM calls)
- Traditional Vector Search: 150-750ms

**Storage Performance**:

- Memory Classification: 1-5ms (pattern) / 100-500ms (LLM)
- Storage Operations: 20-30ms
- Version Control Ops: 50-100ms

**Scalability**:

- Memory Count: Tested up to 1M memories
- Path Depth: Up to 8 levels deep
- Concurrent Users: Horizontal scaling ready

## Version Control

Git-like operations for memory management:

```text
main branch
│
├─ commit: "Initial user profile"
│  └─ memories: profile.identity.*
│
├─ commit: "Added work info"
│  └─ memories: profile.professional.*
│
└─ branch: experiment
   ├─ commit: "Testing new classifier"
   └─ merge → main
```

## Extensions and Plugins

**Memento Collections** (`memoir.memento`):
- LocationMemento: Spatial/geographic memories
- TimelineMemento: Temporal/chronological memories
- ProfileMemento: Identity/personal memories

**Custom Extensions**:
- Custom classifiers
- Custom search engines
- Custom taxonomy systems
- Custom storage backends

This architecture enables Memoir to provide fast, reliable, and scalable semantic memory management while maintaining clean code organization and extensibility.

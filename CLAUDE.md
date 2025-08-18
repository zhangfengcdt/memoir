# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Core Development Workflow
```bash
# Setup development environment
make setup                    # Install deps + pre-commit hooks

# Code quality checks
make lint                     # Run ruff, black, and isort checks
make format                   # Auto-format with black, isort, ruff --fix
make type-check               # Run mypy type checking

# Testing
make test                     # Run pytest with verbose output
make test-cov                 # Run tests with coverage report
pytest tests/test_classifier.py -v  # Run single test file

# Examples and benchmarks
make examples                 # Run all example scripts
make benchmark               # Run performance benchmarks
python examples/basic_usage.py      # Run specific example

# Full CI pipeline
make ci                      # Run complete CI: lint, test, security, examples
```

### Performance Testing
```bash
make perf                    # Run benchmarks + show performance summary
python examples/performance_benchmark.py  # Detailed performance analysis
```

## Architecture Overview

### Core Innovation: Semantic Hierarchical Keys
This project fundamentally reimagines AI memory storage by replacing random UUIDs + vector search with deterministic semantic paths:

**Traditional Approach**: `uuid-1234` → expensive vector similarity search
**Our Approach**: `profile.professional.skills.technical.programming.python` → O(log n) prefix queries

### Component Architecture

#### 1. **Semantic Taxonomy** (`src/memoir/taxonomy/`)
- **Fixed hierarchy of ~800 paths** across 8 main categories
- **TaxonomyCategory enum**: profile, preferences, experience, context, knowledge, relationships, goals, behavior
- **SemanticTaxonomy class**: Manages the complete taxonomy tree with path validation and hierarchical operations

#### 2. **Classification System** (`semantic_classifier.py`)
- **OptimizedClassifier**: 1-5ms classification using keyword patterns (vs 2-5s LLM calls)
- **Pattern-based matching**: Uses taxonomy structure to avoid expensive model calls
- **ClassificationResult**: Returns semantic path + confidence score

#### 3. **Storage Layer** (`core/prolly_adapter.py`)
- **ProllyTreeStore**: Implements LangGraph BaseStore interface with ProllyTree backend
- **Automatic git repository initialization** for versioning support
- **VersionedKvStore integration**: Git-like branching, commits, time-travel queries
- **Encoding/decoding**: JSON serialization with proper byte handling

#### 4. **Search Engine** (`search/hierarchical_search.py`)
- **HierarchicalSearchEngine**: Multiple search strategies with relevance scoring
- **SearchStrategy enum**: SPECIFIC_TO_GENERAL, BREADTH_FIRST, BEST_MATCH
- **O(log n) complexity**: Uses ProllyTree prefix queries instead of vector similarity

#### 5. **Memory Manager** (`core/memory_manager.py`)
- **ProllyTreeMemoryStoreManager**: Drop-in replacement for LangMem's MemoryStoreManager
- **Integrates all components**: Classification → Storage → Search pipeline
- **Performance metrics tracking**: Built-in monitoring of operation latencies

### Key Performance Characteristics
- **Memory Search**: 0.1-1ms (was 150-750ms)
- **Memory Storage**: 20-30ms (was 200-600ms)
- **Classification**: 1-5ms (was 2-5 seconds)
- **Total improvement**: 10-20x faster overall

## Important Implementation Details

### Git Repository Handling
The ProllyTreeStore automatically initializes git repositories for versioning:
- Creates `.git` directory if not present
- Sets up initial commit with README.md
- VersionedKvStore requires data subdirectory (not git root)

### BaseStore Interface Compliance
The ProllyTreeStore implements LangGraph's BaseStore with these key methods:
- `get(namespace: tuple, key: str)` → retrieve value
- `put(namespace: tuple, key: str, value: dict)` → store value
- `search(namespace: tuple, *, filter: dict, limit: int)` → search with filters
- `batch(ops: list[tuple])` → batch operations

### Async vs Sync Patterns
- **MemoryStoreManager methods**: Mostly async (inherited from LangMem)
- **ProllyTreeStore methods**: Synchronous (BaseStore interface)
- **Classification**: Both sync (`fast_classify`) and async (`classify_async`) variants

### Testing Requirements
- Always run `make lint` before commits - includes ruff, black, isort
- Use `make test-cov` for coverage reports
- Examples must run without errors (tested via `make examples`)
- Performance benchmarks validate the 10-20x improvement claims

## Code Quality Standards

### Formatting and Linting
- **Black**: Line length 88, Python 3.9+ target
- **Ruff**: Comprehensive linting with pyflakes, pycodestyle, isort integration
- **isort**: Black-compatible import sorting with memoir as known first-party

### Type Checking
- **mypy**: Configured for Python 3.9+ with strict equality checks
- Import errors ignored (external dependencies)
- Gradual typing approach (not fully strict)

### Project Structure Patterns
- **Source layout**: `src/memoir/` with proper namespace packaging
- **Example scripts**: Self-contained in `examples/` directory
- **Test organization**: Mirrors source structure with clear test naming
- **Configuration**: Single pyproject.toml with all tool configs centralized

### Please also Follow These Instructions
- make sure black formats the code correctly
- make sure ruff passes without errors
- Verify that everything still works after the black formatting
- Run all tests to ensure no regressions before warming up
- When run tests or examples, DO NOt print debugging information to console, you can save it to a file under /tmp if needed

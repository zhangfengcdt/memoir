# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Core Development Workflow
```bash
# Setup development environment
make setup                    # Install deps + pre-commit hooks
make install-dev              # Install with all dev dependencies

# Code quality checks (ALWAYS run before commits)
make lint                     # Run ruff, black, and isort checks
make format                   # Auto-format with black, isort, ruff --fix
make type-check               # Run mypy type checking

# Testing
make test                     # Run pytest with verbose output
make test-cov                 # Run tests with coverage report
pytest tests/test_classifier.py -v        # Run single test file
pytest tests/ -k "test_function_name"     # Run specific test by name
pytest tests/ --tb=short                  # Compact traceback format
pytest tests/test_versioning_control.py   # Test version control features

# Examples and benchmarks
make examples                 # Run all example scripts
make benchmark               # Run performance benchmarks
python examples/basic_usage.py            # Basic memory system usage
python examples/intelligent_taxonomy.py   # Test intelligent classification
python examples/locomo_evaluation.py      # Evaluate with LOCOMO dataset
python examples/langgraph_with_memoir.py  # LangGraph integration demo
python examples/langmem_style_with_memoir.py # LangMem-pattern agent example
python examples/context_branching.py      # Demonstrate context branching
python examples/production_debugging.py   # Production debugging patterns
python examples/reproducible_testing.py   # Reproducible test scenarios
python examples/state_debugging.py        # State debugging techniques
python examples/versioning_control.py     # Git-like version control demo

# Jupyter Notebooks
jupyter notebook examples/notebooks/memoir_basic_usage.ipynb  # Interactive tutorial

# Full CI pipeline
make ci                      # Run complete CI: lint, test, security, examples
make perf                    # Run benchmarks + show performance summary

# Docker Support
./docker.sh --help           # Show Docker environment help
./docker.sh dev              # Start development environment
./docker.sh prod             # Start production environment
./docker.sh test             # Run tests in Docker
./docker.sh build            # Build Docker images
docker-compose -f docker/docker-compose.yml up     # Start with docker-compose
docker-compose -f docker/docker-compose.dev.yml up # Start dev environment

# Utility scripts
python scripts/check_status.py            # Check repository and system status

# UI Visualization Server
python -m src.memoir.ui.serve_ui          # Start interactive memory visualization UI (port 8080)
python -m src.memoir.ui.initialize_sample_store  # Create sample memory store for UI testing
```

## Architecture Overview

### Core Innovation: Git for AI Memory
This project brings Git-like version control to AI memory systems, replacing opaque storage with transparent, versioned, cryptographically secure memory management.

**Key Paradigm Shift**:
- **Traditional**: `uuid-1234` → expensive vector search → no history
- **Memoir**: `profile.professional.skills.python` → O(log n) lookup → full Git-like versioning

### Component Architecture

#### 1. **Taxonomy System** (`src/memoir/taxonomy/`)
- **SemanticTaxonomy** (`semantic.py`): Fixed ~800-path hierarchy
- **LLMIterativeTaxonomy** (`iterative.py`): Dynamic LLM-driven expansion
- **TaxonomyPresets** (`taxonomy_presets.py`): Version management for taxonomy configurations
- **DataSources** (`data_sources.py`): Integration with LOCOMO conversation dataset

#### 2. **Classification System** (`src/memoir/classifier/`)
- **IntelligentClassifier** (`intelligent.py`): Multi-stage classification with LLM
- **SemanticClassifier** (`semantic.py`): Fast pattern-based classification
- Three-tier pipeline: Pattern matching (1-5ms) → LLM classification → Dynamic expansion

#### 3. **Storage Layer** (`src/memoir/store/`)
- **ProllyTreeStore** (`prolly_adapter.py`): LangGraph BaseStore implementation
- **Git-like versioning**: Branches, commits, merges, time-travel
- **Cryptographic integrity**: SHA-256 hashing for all states
- **Structural sharing**: Efficient storage with deduplication

#### 4. **Search Engine** (`src/memoir/search/`)
- **IntelligentSearchEngine** (`intelligent.py`): LLM-powered path selection
- **SemanticSearchEngine** (`semantic.py`): Pattern-based semantic search
- **Relevance scoring**: Combined semantic and structural scoring
- **Prefix queries**: O(log n) complexity vs O(n) vector search

#### 5. **Memory Manager** (`src/memoir/core/`)
- **ProllyTreeMemoryStoreManager** (`memory.py`): Drop-in LangMem replacement
- **ProfileMemento** (`memory.py`): Profile management with versioning
- **TimelineMemento** (`memory.py`): Timeline-based memory organization
- **Async/sync support**: Compatible with both patterns

#### 6. **Framework Integrations** (`src/memoir/integration/`)
- **LangGraphMemoryStore** (`langgraph/memory_store.py`): LangGraph-compatible adapter
- **BaseIntegration** (`base.py`): Abstract base for framework integrations
- **MemoryConfig** (`langgraph/types.py`): Configuration management
- **Utilities** (`langgraph/utils.py`): Helper functions for LangGraph workflows

#### 7. **Interactive UI** (`src/memoir/ui/`)
- **Web-based Visualization** (`visualization.html`): D3.js memory tree explorer
- **Python code highlighting**: Syntax-highlighted code examples using highlight.js
- **Git-like interface**: Branch switching, commit history, time-travel
- **Command system**: `/connect`, `/code`, `/refresh`, `/proof`, `/verify` and more commands
- **Real-time updates**: Connect to live memory stores and explore data
- **Cryptographic proofs**: Generate and verify SHA-256 proofs for memory integrity
- **Memory store reader** (`memory_store_reader.py`): API for reading store data
- **Sample store initializer** (`initialize_sample_store.py`): Create demo data

### Key Performance Metrics
- **Search latency**: 0.1-1ms (vs 150-750ms traditional)
- **Storage latency**: 20-30ms (vs 200-600ms traditional)
- **Classification**: 1-5ms pattern matching (vs 2-5s LLM-only)
- **Overall improvement**: 10-20x faster end-to-end

## Important Implementation Details

### LLM Integration
The system requires an LLM for intelligent features. Supported providers:
- **OpenAI**: GPT-4, GPT-3.5-turbo via `langchain_openai.ChatOpenAI`
- **Anthropic**: Claude-3 via `langchain_anthropic.ChatAnthropic`
- **Local models**: Via LangChain-compatible interfaces

### Taxonomy Configuration
Multiple taxonomy strategies available:
- **Fixed taxonomy**: Use `SemanticTaxonomy` for stable, predefined paths
- **Dynamic expansion**: Use `LLMIterativeTaxonomy` for automatic growth
- **Custom presets**: Load from `TaxonomyPresets` for domain-specific taxonomies

### Version Control Features
Git-like operations for AI memory:
```python
# Branching
await memory_manager.create_branch("experiment")
await memory_manager.checkout("experiment")

# Committing
commit_hash = await memory_manager.store_memory(content, message="Added user preference")

# Time-travel
historical_results = await memory_manager.search_memories(query, at_commit=commit_hash)

# Merging
await memory_manager.merge("experiment", into="main")

# Cryptographic verification
proof = await memory_manager.generate_proof(path="user.preferences")
is_valid = await memory_manager.verify_proof(proof)
```

### Testing Strategy
- **Unit tests**: Test individual components in isolation
- **Integration tests**: Test component interactions
- **Performance benchmarks**: Validate latency claims
- **LOCOMO evaluation**: Test with real conversation data
- **Version control tests**: Test branching, merging, and time-travel features
- **Docker tests**: Run full test suite in containerized environment

### Code Quality Requirements
Before any commit or PR:
1. Run `make format` to auto-format code
2. Run `make lint` to check for issues
3. Run `make test` to ensure no regressions
4. Verify examples still work with `make examples`

### Common Pitfalls to Avoid
- **Don't skip linting**: Always run `make lint` before commits
- **Don't ignore type hints**: Use proper type annotations
- **Don't bypass the taxonomy**: Always use semantic paths, not raw UUIDs
- **Don't print debug info**: Use logging or write to `/tmp/` for debugging
- **Don't commit without testing**: Run at least `make test` before pushing
- **Don't create test data directories in project**: Use `/tmp/` for test data, never create data directories under the project folder

## Recent Features & Capabilities

### Docker Support
Full containerization for development and production:
- **Development environment**: Hot-reload, mounted volumes, debugging enabled
- **Production environment**: Optimized builds, health checks, auto-restart
- **Test environment**: Isolated testing with full CI pipeline
- **Multi-stage builds**: Minimal production images with security hardening

### LangGraph Integration 
Native integration with LangGraph's BaseStore interface:
```python
from memoir.integration.langgraph import LangGraphMemoryStore
store = LangGraphMemoryStore(namespace=("memories",))
await store.put(namespace, key, value)
```

### Enhanced UI Features
- **Cryptographic proof generation**: Generate SHA-256 proofs for any memory path
- **Proof verification**: Verify integrity of memory states
- **Enhanced visualization**: Improved D3.js tree rendering with collapsible nodes
- **Command palette**: Extended commands for debugging and exploration
- **Code examples**: Interactive Python snippets with syntax highlighting

### Advanced Examples
New comprehensive examples demonstrating:
- **Context branching**: Managing parallel conversation contexts
- **Production debugging**: Real-world debugging patterns
- **Reproducible testing**: Deterministic test scenarios
- **State debugging**: Inspecting and manipulating memory states
- **Version control**: Full Git-like workflow demonstrations

### Documentation Improvements
- **ReadTheDocs integration**: Full API documentation
- **Jupyter notebooks**: Interactive tutorials
- **FAQ section**: Common questions and troubleshooting
- **Architecture diagrams**: Visual system overview

## Project-Specific Patterns

### Async/Sync Dual Support
Many components offer both async and sync interfaces:
```python
# Async (preferred for web services)
result = await classifier.classify_async(content)

# Sync (for scripts and notebooks)
result = classifier.fast_classify(content)
```

### Error Handling
Use structured error handling with proper logging:
```python
try:
    result = await memory_manager.store_memory(content)
except ClassificationError as e:
    logger.warning(f"Classification failed, using fallback: {e}")
    # Handle gracefully with fallback
```

### Performance Monitoring
Built-in metrics tracking:
```python
metrics = memory_manager.get_performance_metrics()
print(f"Avg search time: {metrics['avg_search_ms']}ms")
```

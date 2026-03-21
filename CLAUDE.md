# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Core Development Workflow
```bash
# Create and activate virtual environment (recommended)
python -m venv venv
source venv/bin/activate      # On Windows: venv\Scripts\activate

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
pytest tests/test_versioning.py   # Test version control features

# Benchmarks
python benchmarks/classifier.py --help  # View benchmark options
python benchmarks/classifier.py --model gpt-4o-mini --num-cases 3  # Quick test
python benchmarks/classifier.py --model anthropic/claude-haiku-4-5 --num-cases 10 --verbose  # Test with Claude

# Full CI pipeline
make ci                      # Run complete CI: lint, test, security, docs
make perf                    # Run benchmarks + show performance summary

# Docker Support
./docker.sh --help           # Show Docker environment help
./docker.sh dev              # Start development environment
./docker.sh prod             # Start production environment
./docker.sh test             # Run tests in Docker
./docker.sh build            # Build Docker images
docker-compose -f docker/docker-compose.yml up     # Start with docker-compose
docker-compose -f docker/docker-compose.dev.yml up # Start dev environment

# UI Visualization Server
python -m src.memoir.ui.server          # Start interactive memory visualization UI (port 8080)
python -m src.memoir.ui.initializer  # Create sample memory store for UI testing
```

### Important Notes
Please do not auto commit or push code without running the above checks, especially `make lint` and `make test`. Always ensure code quality and functionality before pushing changes.

## Architecture Overview

### Core Innovation: Git for AI Memory
This project brings Git-like version control to AI memory systems, replacing opaque storage with transparent, versioned, cryptographically secure memory management.

**Key Paradigm Shift**:
- **Traditional**: `uuid-1234` → expensive vector search → no history
- **Memoir**: `profile.professional.skills` → O(log n) lookup → full Git-like versioning

### Component Architecture

#### 1. **Taxonomy System** (`src/memoir/taxonomy/`)
- **SemanticTaxonomy** (`semantic.py`): Fixed ~200-path hierarchy (3 levels max)
- **LLMIterativeTaxonomy** (`iterative.py`): Dynamic LLM-driven expansion
- **TaxonomyPresets** (`taxonomy.py`): Hardcoded taxonomy paths and classification examples
- **TaxonomyLoader** (`loader.py`): High-level API for loading taxonomy into store
- **TaxonomyRegistry** (`registry.py`): File registry for builtin and external taxonomy files
- **MarkdownTaxonomyDataSource** (`markdown_source.py`): Parser for markdown taxonomy files

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
- **IntelligentSearchEngine** (`intelligent.py`): Single-stage LLM-powered path selection
- **Prompt caching**: Static taxonomy cached for efficiency
- **Dynamic limit**: Configurable number of paths/results to retrieve

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
- **Main UI** (`ui.html`): Clean, modular web-based D3.js memory tree explorer (714 lines, 93% reduction from original)
- **HTTP Server** (`server.py`): Modular web server with API endpoints (2,842 lines, 36% reduction from original 4,420 lines)
- **Modular Python Backend Architecture** (`handlers/`): Clean separation of concerns with specialized handler modules:
  - **Base Handler** (`api_handler.py`): Common utilities and delegation pattern for all handlers
  - **Store Handler** (`store_handler.py`): Store operations (/api/store, /api/new) - 140 lines
  - **Memory Handler** (`memory_handler.py`): Memory operations (/api/remember, /api/forget, /api/recall) - 607 lines
  - **Branch Handler** (`branch_handler.py`): Git operations (/api/branches, /api/checkout, etc.) - 471 lines
  - **Crypto Handler** (`crypto_handler.py`): Cryptographic operations (/api/proof, /api/verify, /api/blame) - 219 lines
  - **Utility Handler** (`utils.py`): Data processing utilities and content extraction helpers - 289 lines
- **External Styles** (`static/styles.css`): Modular CSS for better maintainability
- **Modular JavaScript Architecture** (`static/js/`): Clean separation of concerns with focused modules:
  - **Core UI** (`core-ui.js`): Main UI functionality and business logic (9,440 lines)
  - **Demo Mode** (`demo-mode.js`): Demo/mock interactions and sample data (105 lines)
  - **DOM Events** (`dom-events.js`): Event handlers and user interactions (97 lines)
  - **Notifications** (`notifications.js`): Toast notification system (87 lines)
  - **Mock Data** (`mock-data.js`): Data generation functions (71 lines)
  - **View Switcher** (`view-switcher.js`): View switching logic (43 lines)
  - **Statistics Modal** (`stats-modal.js`): Statistics and analytics modal
- **Git-like interface**: Branch switching, commit history, time-travel
- **Command system**: `/connect`, `/code`, `/refresh`, `/proof`, `/verify` and more commands
- **Real-time updates**: Connect to live memory stores and explore data
- **Cryptographic proofs**: Generate and verify SHA-256 proofs for memory integrity
- **Memory store reader** (`reader.py`): API for reading store data
- **Sample store initializer** (`initializer.py`): Create demo data

### Key Performance Metrics
- **Search latency**: 500-800ms (single LLM call for path selection)
- **Storage latency**: 1000-2000ms (includes LLM classification)
- **Classification**: Single LLM call with prompt caching support
- **Prompt caching**: Up to 90% token savings on Anthropic models

## Important Implementation Details

### LLM Integration
The system requires an LLM for intelligent features. Supported providers:
- **OpenAI**: GPT-4, GPT-3.5-turbo via `langchain_openai.ChatOpenAI`
- **Anthropic**: Claude-3 via `langchain_anthropic.ChatAnthropic`
- **Local models**: Via LangChain-compatible interfaces

### Taxonomy Configuration
Multiple taxonomy strategies available:
- **Fixed taxonomy**: Use `SemanticTaxonomy` for stable, predefined paths (~200 paths, 3 levels)
- **Dynamic expansion**: Use `LLMIterativeTaxonomy` for automatic growth
- **Store-based loading**: Use `TaxonomyLoader` to load taxonomy from markdown files into the store
- **Custom taxonomies**: Create markdown files in `src/memoir/taxonomy/data/` or load external files

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
4. Run `make benchmark` to verify the benchmark works

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

### Benchmark Tool
The `benchmarks/classifier.py` provides comprehensive performance testing:
- **Multi-provider support**: OpenAI, Anthropic, Ollama, vLLM via LiteLLM
- **Prompt caching**: Automatic Anthropic cache optimization for reduced costs
- **Detailed metrics**: Classification and retrieval timing with step breakdown
- **External test data**: 100+ memories and queries in `benchmarks/data/`
- **LLM evaluation**: Recall quality verified by LLM (answers query or not)

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

### UI Refactoring (Recent)
The UI has been comprehensively refactored for better maintainability across both frontend and backend:

#### Full Stack Modular Architecture:
```
src/memoir/ui/
├── server.py                    # Main HTTP server (2,842 lines, 36% reduction from 4,420)
├── handlers/                    # Modular Python Backend Architecture
│   ├── api_handler.py          # Base handler with common utilities
│   ├── store_handler.py        # Store operations (/api/store, /api/new) - 140 lines
│   ├── memory_handler.py       # Memory operations (/api/remember, /api/forget, /api/recall) - 607 lines
│   ├── branch_handler.py       # Git operations (/api/branches, /api/checkout, etc.) - 471 lines
│   ├── crypto_handler.py       # Cryptographic operations (/api/proof, /api/verify, /api/blame) - 219 lines
│   └── utils.py                # Data processing utilities and helpers - 289 lines
├── ui.html                      # Main UI file (714 lines, 93% reduction from 10,495)
├── reader.py                    # Memory store reader (renamed)
├── initializer.py              # Sample store initializer (renamed)
└── static/
    ├── styles.css              # External CSS (extracted from HTML)
    └── js/                     # Modular JavaScript Architecture
        ├── core-ui.js          # Core UI functionality (9,440 lines)
        ├── demo-mode.js        # Demo/mock interactions (105 lines)
        ├── dom-events.js       # DOM event handlers (97 lines)
        ├── notifications.js    # Notification system (87 lines)
        ├── mock-data.js        # Data generation (71 lines)
        ├── view-switcher.js    # View switching logic (43 lines)
        └── stats-modal.js      # Statistics modal (existing)
```

#### Backend Architecture Benefits:
- **Modular Handler Pattern**: Each handler specializes in specific API functionality
- **Base Handler Design**: Common utilities and delegation pattern (`self.handler.*`)
- **Lazy Initialization**: Handlers loaded only when needed via `_ensure_handlers_initialized()`
- **Preserved Business Logic**: Core functionality maintained exactly, only infrastructure adapted
- **Eliminated Duplication**: Removed 1,000+ lines of duplicate methods
- **Clean Separation**: Store, memory, git, crypto, and utility operations isolated

#### Frontend Architecture Benefits:
- **Dramatic Size Reduction**: ui.html reduced from 10,495 → 714 lines (93% reduction)
- **Modular Architecture**: Clean separation of concerns across focused JavaScript modules
- **Maintainability**: Easy to locate, debug, and modify specific functionality
- **Performance**: External scripts can be cached by browsers, reduced HTML parsing overhead
- **Developer Experience**: Clear module boundaries and consistent naming conventions
- **Testing**: Individual modules can be tested in isolation
- **Scalability**: Easy to add new modules or extend existing functionality

#### Overall Impact:
- **Total Backend Reduction**: server.py from 4,420 → 2,842 lines (36% reduction)
- **Enhanced Maintainability**: Both Python and JavaScript follow modular patterns
- **Improved Debugging**: Issues isolated to specific handler/module boundaries
- **Future-Proof**: Clean architecture supports easy extension and modification

### Services Layer (`src/memoir/services/`)
Extracted business logic from HTTP handlers into reusable services:
- **StoreService** (`store_service.py`): Store creation, reading, status
- **MemoryService** (`memory_service.py`): Remember, recall, forget operations
- **BranchService** (`branch_service.py`): Git branch operations
- **CryptoService** (`crypto_service.py`): Proof generation, verification, blame

**Important API Notes:**
```python
# StoreService.create_store() requires path argument
store_service = StoreService()
result = store_service.create_store("/path/to/store")  # NOT create_store()

# BranchService.checkout() uses create_if_missing, not create
branch_service.checkout("branch-name", create_if_missing=True)  # NOT create=True
```

### CLI Tool (`src/memoir/cli/`)
Click-based CLI optimized for AI agents:
- Entry point: `memoir` command (via pyproject.toml scripts)
- Commands: `new`, `connect`, `status`, `remember`, `recall`, `forget`, `branch`, `checkout`, `merge`, `commits`, `proof`, `verify`, `blame`
- Supports `--json` flag for machine-readable output
- Environment variables: `MEMOIR_STORE`, `MEMOIR_JSON`

### TUI Interface (`src/memoir/tui/`)
Textual-based terminal UI:
- Entry point: `memoir tui` or `memoir-tui`
- Commands: `/connect`, `/remember`, `/recall`, `/branch`, `/checkout`, `/theme`
- 5 color themes: default, ocean, forest, mono, sunset

### Test Structure
```
tests/
├── test_cli.py                    # 53 CLI command tests
├── test_services/                 # Service unit tests
│   ├── test_store_service.py
│   ├── test_branch_service.py
│   ├── test_crypto_service.py
│   └── test_memory_service.py
├── test_integration/              # Integration tests
│   ├── test_memory_workflow.py
│   ├── test_branch_workflow.py
│   └── test_crypto_workflow.py
├── test_versioning.py             # Git-like versioning tests
├── test_classifier.py             # Classification tests
└── test_taxonomy.py               # Taxonomy tests
```

### CI/CD Configuration Notes

**GitHub Actions (`.github/workflows/ci.yml`):**
- Requires git user configuration for versioning tests
- Added step: `git config --global user.email/name`

**Makefile:**
- `type-check`: Non-blocking (237 pre-existing type errors)
- `security`: Uses `-c pyproject.toml` for bandit config
- `safety check`: Made non-blocking with `|| true`

**pyproject.toml - Bandit Skips:**
```toml
skips = ["B101", "B110", "B404", "B601", "B603", "B607", "B608"]
```
- B101: assert_used (needed for tests)
- B110: try_except_pass (intentional error suppression)
- B404: import_subprocess (required for git operations)
- B603/B607: subprocess calls (safe with hardcoded commands)
- B608: hardcoded_sql (false positive on commit messages)

**Known Technical Debt:**
- 237 mypy type errors (pre-existing, non-blocking in CI)
- Type annotations needed in CLI commands, services, SDK
- Some service methods have `Optional[str]` vs `str` mismatches

### Development Workflow
```bash
# Always use venv
source venv/bin/activate

# Before committing
make format && make lint && make test

# Full CI check
make ci
```

# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.


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

### Development Workflow
```bash
# Always use venv
source venv/bin/activate

# Before committing
make format && make lint && make test

# Full CI check
make ci
```

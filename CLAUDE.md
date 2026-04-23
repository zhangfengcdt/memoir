# CLAUDE.md

Guidance for Claude Code working in this repository. Keep it terse — the full reference lives at https://zhangfengcdt.github.io/memoir/.

## Project

Memoir is Git-like version control for AI memory, aimed at coding agents. A store is a Prolly-tree with semantic paths (`workflow.coding.style`, `preferences.tools.memory`), branch/commit/merge, and cryptographic proofs. Primary consumers: the `memoir` CLI, the MCP server, and the Claude Code plugin under `plugins/claude-code/`.

## Development

Use the venv for everything:

```bash
source venv/bin/activate    # or `python -m venv venv && source venv/bin/activate`
make install-dev            # first time only
```

Before any commit, in order:

```bash
make format                 # black + isort + ruff --fix
make lint                   # must pass
make test                   # must pass
```

`make ci` runs the full pipeline (lint, test, security, docs). Use it before opening a PR.

Test a single file or case:

```bash
pytest tests/test_cli.py -v
pytest tests/ -k "test_function_name"
```

## Critical rules

- **Never commit or push without explicit user permission.** This includes auto-mode. Ask.
- **Never create test data directories inside the project.** Use `/tmp/` for anything transient.
- **Never `print()` for debugging.** Use `logging`, or write to `/tmp/`.
- **Don't skip `make lint` / `make test`** — CI will block the PR anyway, fix it locally.
- **Don't bypass the taxonomy.** All memories go through semantic paths, never raw UUIDs.
- **`type-check` is non-blocking** (237 pre-existing mypy errors, tracked as tech debt) — do not add new ones, but don't gate work on them.

## Architecture at a glance

- `src/memoir/store/` — ProllyTree store, LangGraph `BaseStore` adapter, git-like versioning.
- `src/memoir/taxonomy/` — fixed (`SemanticTaxonomy`) and iterative (`LLMIterativeTaxonomy`) path systems, ~200 paths, 3 levels.
- `src/memoir/classifier/` — `IntelligentClassifier` (LLM + prompt caching) and `SemanticClassifier` (pattern, 1–5ms).
- `src/memoir/search/` — single-stage `IntelligentSearchEngine`, taxonomy cached into the system prompt.
- `src/memoir/core/` — `ProllyTreeMemoryStoreManager` (drop-in LangMem replacement), `ProfileMemento`, `TimelineMemento`.
- `src/memoir/services/` — `StoreService`, `MemoryService`, `BranchService`, `CryptoService` (reusable business logic).
- `src/memoir/cli/` — Click CLI (`memoir` entry point). Supports `--json` and the agent env vars `MEMOIR_STORE`, `MEMOIR_JSON`.
- `src/memoir/ui/` — web UI (server + D3.js explorer). Modular handlers under `ui/handlers/`, JS modules under `ui/static/js/`.
- `plugins/claude-code/` — Claude Code plugin: slash commands, skills, hooks.
- `tests/` — unit + integration + versioning + CLI tests. Run with `pytest`.

Deep structural details (layouts, refactor history, per-file line counts) intentionally omitted — use `rg` / `git log` when you need them.

## Patterns

- **Async-first.** Most APIs have `*_async` + sync wrappers. Prefer async in new code; sync is for scripts and notebooks.
- **Logging, not prints.** Use the module logger.
- **Errors at boundaries only.** Trust internal code and framework guarantees; validate at system boundaries (user input, external APIs).
- **`StoreService.create_store()` takes a `path`.** `BranchService.checkout()` uses `create_if_missing`, not `create`.

## Reference

- **Docs (primary):** https://zhangfengcdt.github.io/memoir/ — quickstart, CLI, UI, Claude Code plugin, architecture, API, examples.
- **Build the docs locally:** `make docs` (mkdocs) → `site/index.html`, or `make docs-live` for auto-reload.
- **Issues:** https://github.com/zhangfengcdt/memoir/issues

When in doubt, read the docs before extending CLAUDE.md. This file is for Claude's *working rules*, not a second copy of the reference.

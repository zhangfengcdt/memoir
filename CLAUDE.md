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
- `src/memoir/ui/` — web UI (Python HTTP server + React/Vite SPA). Handlers under `ui/handlers/`, frontend source under `ui/webapp/src/`, built bundle at `ui/webapp/dist/`.
- `plugins/claude-code/` — Claude Code plugin: slash commands, skills, hooks.
- `tests/` — unit + integration + versioning + CLI tests. Run with `pytest`.

Deep structural details (layouts, refactor history, per-file line counts) intentionally omitted — use `rg` / `git log` when you need them.

## Patterns

- **Async-first.** Most APIs have `*_async` + sync wrappers. Prefer async in new code; sync is for scripts and notebooks.
- **Logging, not prints.** Use the module logger.
- **Errors at boundaries only.** Trust internal code and framework guarantees; validate at system boundaries (user input, external APIs).
- **`StoreService.create_store()` takes a `path`.** `BranchService.checkout()` uses `create_if_missing`, not `create`.
- **Plugin works in non-git folders.** Single `main` memoir branch only; the Stop hook captures to `main`. `/memoir:onboard` switches to `project:onboard` (file-shape index built by deterministic stdlib extractors under `plugins/claude-code/skills/memoir-onboard/extractors.py`) instead of `codebase:onboard` (code map). Store keyed on absolute `pwd`. Mode at first store creation is recorded in `<store>/.git/plugin-store-mode`; flipping it later (`git init`, or `rm -rf .git`) surfaces a warning at SessionStart but does not block writes. Memoir helpers (`memoir_json` / `memoir_plain`) cd into the store path before invocation so writes work regardless of project-side git state.

## Prompt harness (debugging plugin skills + hooks)

The Claude Code plugin's LLM-driven hooks (today: `hooks/stop.sh` for auto-capture; more later) load their system prompts from `plugins/claude-code/hooks/prompts/*.tmpl` — those `.tmpl` files are the **single source of truth**, used by both production and the test harness. When changing a prompt, **run the harness against haiku before merging**.

The harness has two modes: **gate** (deterministic shell-hook tests, no LLM, sub-second per case — pins the recall-trigger gate in `hooks/user-prompt-submit.sh`) and **LLM mode** (`run` / `case` / `adhoc` against `claude -p` for prompt templates).

```bash
# Gate mode — no LLM cost, run on every commit.
plugins/claude-code/tests/prompt-harness/runner.py gate --hook user-prompt-submit

# Full LLM suite (5 cases for the Stop hook auto-capture prompt; ~60s, costs LLM tokens)
plugins/claude-code/tests/prompt-harness/runner.py run --prompt stop_capture --model haiku

# One case
plugins/claude-code/tests/prompt-harness/runner.py case stop_capture/capture-going-forward-rule.yaml --model haiku

# Diagnostic — paste a real "this should have captured but didn't" turn
echo "=== Transcript ===
[Human]
<paste the user message>
[Claude Code]
<paste the response>" > /tmp/turn.txt
plugins/claude-code/tests/prompt-harness/runner.py adhoc --prompt stop_capture --input /tmp/turn.txt --model haiku

# Try a different model on the same cases
plugins/claude-code/tests/prompt-harness/runner.py run --prompt stop_capture --model sonnet
```

`--model` is mandatory. Auth piggybacks on your existing `claude /login` (no API key). PyYAML required — easiest is `source venv/bin/activate` first.

Every run drops `system.txt` (the assembled prompt actually sent), `input.txt`, `output.txt`, `command.sh` (replayable), and `result.json` per case under `/tmp/memoir-prompt-tests/<UTC-timestamp>/`. Read `summary.md` for pass/fail; open `output.txt` to see what the model actually emitted when something fails. Skill prompts (`skills/<name>/SKILL.md`) are evaluated by the orchestrating Claude rather than dispatched as system prompts to a model, so they are *not* covered by this harness — to test those, run the slash command in a real session and inspect behavior. The harness is plugin-prompt-only.

When you add a new LLM-invoking hook: extract its system prompt to `plugins/claude-code/hooks/prompts/<name>.tmpl`, point the hook at it (mirror `stop.sh`'s `STOP_SYSTEM_PROMPT_TEMPLATE=$(cat …)` pattern), then add `cases/<name>/*.yaml` test cases. See `plugins/claude-code/tests/prompt-harness/README.md` for the assertion DSL.

## Reference

- **Docs (primary):** https://zhangfengcdt.github.io/memoir/ — quickstart, CLI, UI, Claude Code plugin, architecture, API, examples.
- **Build the docs locally:** `make docs` (mkdocs) → `site/index.html`, or `make docs-live` for auto-reload.
- **Issues:** https://github.com/zhangfengcdt/memoir/issues

When in doubt, read the docs before extending CLAUDE.md. This file is for Claude's *working rules*, not a second copy of the reference.

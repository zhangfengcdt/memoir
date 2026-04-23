# Memoir

<div align="center">
  <img src="https://memoir-ai-dev.vercel.app/images/memoir.png" alt="Memoir Logo" width="200" height="200">

  **Git for AI Memory**

  *Hierarchical Memory with Git-Like Version Control*
</div>

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://github.com/zhangfengcdt/memoir/blob/main/LICENSE)
[![Status](https://img.shields.io/badge/Status-Alpha-orange.svg)]()
[![Docs](https://img.shields.io/badge/Docs-zhangfengcdt.github.io%2Fmemoir-blue.svg)](https://zhangfengcdt.github.io/memoir/)

<p align="center">
  <img src="https://raw.githubusercontent.com/zhangfengcdt/memoir/main/docs/_static/memoir-demo.gif" alt="Memoir demo" width="900">
</p>

Memoir is a **hierarchical memory system for AI agents**, with Git-like version control built in. Instead of storing facts as opaque embeddings and guessing at relevance through vector similarity, Memoir classifies every fact into a semantic taxonomy path like `preferences.coding.style` or `workflow.coding.testing`. Retrieval becomes **explainable** (you see which path was chosen and why) and **efficient** (O(log n) tree lookup — no vector index, no embedding model to host, no re-rank stage). Memoir is framework-agnostic — usable from any agent runtime via its CLI, Python SDK, or MCP server — and sits alongside any static prompt or instruction file your agent already uses, carrying the evolving layer (decisions, debugging trails, accumulated preferences, branch-specific context) that a static file can't version or query.

## Why Memoir for Coding Agents

- **Hierarchical paths, not embeddings.** Every fact lands at a named path in a 3-level taxonomy (~200 paths in v1.1.0). No vector DB to operate, no similarity threshold to tune — lookup is a tree walk and results trace directly back to the path that matched.
- **Explainable retrieval.** Unlike semantic/vector search, you can always answer *why* a memory was surfaced: the agent picked path `preferences.coding.style` and read the value there. Good for debugging, auditability, and reproducibility.
- **Efficient at scale.** Taxonomy classification is O(log n), not O(n). No embedding inference on the hot path, no vector index to warm, no re-ranker. The CLI returns typical recalls in hundreds of milliseconds.
- **Complements static prompts.** System prompts and instruction files are great for invariants. Memoir handles the evolving layer — per-session decisions, debugging history, branch-specific context — so the prompt stays lean and the history stays queryable.
- **Branches for experiments.** Try a refactor direction or a new coding style on `experiment/*`, keep it if it works, discard it if it doesn't — same workflow you already trust from git.
- **Taxonomy designed for coding workflows.** v1.1.0 maps to how coding agents actually think — `workflow.coding`, `debugging`, `knowledge`, `preferences.tools` — not generic prose buckets.
- **Framework-agnostic, agent-native ergonomics.** Works with Claude Code, LangGraph, custom runtimes, or anything that can shell out. `--json` on every CLI command, stable exit codes, KV-cache-friendly output shapes, and an MCP server for any MCP-compatible client.

## Install from PyPI

```bash
pip install memoir-ai
```

> The distribution name on PyPI is `memoir-ai`. The Python import is `import memoir` and the CLI is `memoir`.

## Install for Claude Code

Inside a Claude Code session, run:

```
/plugin marketplace add zhangfengcdt/memoir
/plugin install memoir@memoir
```

The plugin registers hooks for session start, user-prompt-submit, and stop, so your project gets automatic context injection and auto-captured memories. Each project gets its own store under `~/.memoir/memoir_<hash>/` (override with `MEMOIR_STORE`). See the [Claude Code plugin guide](https://zhangfengcdt.github.io/memoir/claude_code/) for the full slash-command and hook reference.

## Quick look

```bash
export MEMOIR_STORE=/tmp/my_store
memoir new "$MEMOIR_STORE"
memoir remember "prefer pytest over unittest, parametrize aggressively"
memoir recall "what's my testing setup?"
```

That's the core loop — auto-classified on the way in, semantically retrieved on the way out.

## Documentation

Full docs live at **[zhangfengcdt.github.io/memoir](https://zhangfengcdt.github.io/memoir/)**:

- [Quickstart](https://zhangfengcdt.github.io/memoir/quickstart/) — five-minute tour of the core loop.
- [CLI Reference](https://zhangfengcdt.github.io/memoir/cli/) — every command, flag, and exit code.
- [UI](https://zhangfengcdt.github.io/memoir/ui/) — the visual explorer (Tree / Graph / Timeline / Places + `/stats`).
- [Claude Code](https://zhangfengcdt.github.io/memoir/claude_code/) — plugin install, slash commands, hooks, lifecycle.
- [Architecture](https://zhangfengcdt.github.io/memoir/architecture/) — taxonomy, classifier, store, search.
- [API Reference](https://zhangfengcdt.github.io/memoir/api/memoir/) — Python SDK.
- [Examples](https://zhangfengcdt.github.io/memoir/examples/) — context branching, memory debugging, reproducible testing.

## Contributing

Memoir is alpha and contributions are very welcome — especially from people building coding agents, since that's the audience we're optimizing for. Good first paths in:

- Pick an issue from the [issue tracker](https://github.com/zhangfengcdt/memoir/issues) or open one describing a gap.
- Fork the repo, branch off `main`, and run `make ci` before opening a PR (lint, tests, docs build must be green).
- Bug reports with a minimal reproducer and benchmark / taxonomy proposals for coding-agent use cases are particularly appreciated.

## License

Apache License 2.0 — see [LICENSE](https://github.com/zhangfengcdt/memoir/blob/main/LICENSE).

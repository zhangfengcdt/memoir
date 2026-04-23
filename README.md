# Memoir

<div align="center">
  <img src="https://memoir-ai-dev.vercel.app/images/memoir.png" alt="Memoir Logo" width="200" height="200">

  **Git for AI Memory**

  *The best memory system for coding agents.*
</div>

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](https://github.com/zhangfengcdt/memoir/blob/main/LICENSE)
[![Status](https://img.shields.io/badge/Status-Alpha-orange.svg)]()
[![Docs](https://img.shields.io/badge/Docs-zhangfengcdt.github.io%2Fmemoir-blue.svg)](https://zhangfengcdt.github.io/memoir/)

Memoir brings Git-like version control to AI memory. Long-running coding agents — Claude Code, LangGraph pipelines, multi-agent systems — lose state, overwrite context, and silently corrupt their own knowledge. Memoir replaces ad-hoc `CLAUDE.md` dumps with a versioned, queryable, cryptographically-verified memory store designed around how coding agents actually work.

## Why Memoir for Coding Agents

- **Persistent, queryable memory across sessions.** `CLAUDE.md` grows unboundedly and context windows don't. Memoir stores each durable fact at a hierarchical semantic path (e.g. `preferences.coding.style`, `workflow.coding.testing`) so agents recall only what's relevant to the current task.
- **Branches for experiments.** Try a refactor direction or a new coding style on `experiment/*`, keep it if it works, discard it if it doesn't — same workflow you already trust from git.
- **Cryptographic provenance.** Every memory is hashed and committed. An agent running for hours or days can prove what it remembered, when, and that nothing corrupted in between.
- **Taxonomy designed for coding workflows.** The v1.1.0 taxonomy maps to how coding agents actually think — `workflow.coding`, `debugging`, `knowledge`, `preferences.tools` — not generic prose buckets.
- **Agent-native ergonomics.** `--json` on every CLI command, stable exit codes, KV-cache-friendly output shapes, and an MCP server for any MCP-compatible client.

## Install for Claude Code

Inside a Claude Code session, run:

```
/plugin marketplace add zhangfengcdt/memoir
/plugin install memoir@memoir
```

The plugin registers hooks for session start, user-prompt-submit, and stop, so your project gets automatic context injection and auto-captured memories. Each project gets its own store under `~/.memoir/memoir_<hash>/` (override with `MEMOIR_STORE`). See the [Claude Code plugin guide](https://zhangfengcdt.github.io/memoir/claude_code/) for the full slash-command and hook reference.

## Install from PyPI

```bash
pip install memoir-ai
```

> The distribution name on PyPI is `memoir-ai` (the `memoir` name was taken). The Python import is still `import memoir` and the CLI is still `memoir`.

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

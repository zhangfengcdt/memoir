# Contributing to Memoir

Thanks for your interest. Memoir is alpha — bug reports, taxonomy proposals, and PRs from people building coding agents are especially welcome.

Full architecture and developer reference live at **[zhangfengcdt.github.io/memoir](https://zhangfengcdt.github.io/memoir/)**. This file covers only what you need to set up locally and ship a PR.

## Setup

```bash
git clone https://github.com/zhangfengcdt/memoir.git
cd memoir
python -m venv venv && source venv/bin/activate
make install-dev
```

Python 3.10+ and Make are required. `make install-dev` also wires up the pre-commit hooks.

## Before you commit

Run these in order. CI will run them again — it's faster to fix them locally.

```bash
make format    # black + isort + ruff --fix
make lint      # must pass
make test      # must pass
make ci        # full pipeline (lint, test, security, docs build)
```

`make type-check` is non-blocking (pre-existing mypy errors are tracked as tech debt) — don't add new errors, but don't gate work on existing ones.

Run a single test:

```bash
pytest tests/test_cli.py -v
pytest tests/ -k "test_function_name"
```

## Testing the Claude Code plugin from local source

The plugin lives under `plugins/claude-code/`, with the marketplace manifest at `.claude-plugin/marketplace.json`. To install your local working copy into Claude Code:

```text
/plugin marketplace add /absolute/path/to/memoir
/plugin install memoir@memoir
```

Pass the **repository root** (the directory containing `.claude-plugin/marketplace.json`), not the plugin subdirectory. The marketplace name is `memoir` and the plugin name is `memoir`, hence `memoir@memoir`.

After editing plugin files (`commands/`, `skills/`, `hooks/`):

```text
/plugin marketplace update memoir   # re-read the local marketplace
```

Then restart the Claude Code session to pick up hook changes. Slash commands and skills reload without a restart.

To remove your local install:

```text
/plugin uninstall memoir@memoir
/plugin marketplace remove memoir
```

For prompt-template debugging (Stop hook auto-capture, etc.), see the prompt-harness section in [`CLAUDE.md`](./CLAUDE.md).

## Testing the Codex plugin from local source

The Codex plugin lives under `plugins/memoir-codex/`, with the marketplace manifest at `.agents/plugins/marketplace.json`.

```bash
codex plugin marketplace add /absolute/path/to/memoir
```

That local command is for source testing. User-facing installs should use the repo marketplace:

```bash
codex plugin marketplace add zhangfengcdt/memoir
```

Install `memoir-codex` from Codex, then enable hooks with `[features].hooks = true` or a one-off `--enable hooks` run. The plugin resolves the Memoir CLI through `memoir` on `PATH`, `uvx --from memoir-ai==<pinned> memoir`, or `uv tool run --from memoir-ai==<pinned> memoir`, so a separate `pip install memoir-ai` is not required when `uv` is available. Use `gpt-5.4` for PR smoke validation:

```bash
MEMOIR_STORE=/tmp/memoir-codex-smoke-store \
MEMOIR_CODEX_MODEL=gpt-5.4 \
codex exec --enable hooks --skip-git-repo-check -m gpt-5.4 \
  "Use Memoir and report status."
```

Record any smoke evidence under `/tmp`, then clean the disposable project/store before committing. Do not commit local Codex config, generated Memoir stores, or `/tmp` evidence unless a maintainer explicitly asks for a sanitized artifact.

## Reporting issues

- **Bugs:** open an issue with a minimal reproducer (CLI command or short script) and the output you got vs. expected.
- **Security:** email the maintainer rather than filing a public issue.
- **Feature requests:** describe the use case first, proposed API second.
- **Chat:** join the [Memoir Discord](https://discord.gg/trV26K5T) for questions, design discussion, and showing off what you're building.

## License

By contributing, you agree your contributions are licensed under Apache-2.0 (see [LICENSE](./LICENSE)).

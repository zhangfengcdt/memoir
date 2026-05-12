# Codex Plugin

Memoir ships a Codex plugin that brings branch-aware, taxonomy-structured memory into Codex sessions. It is the Codex port of the existing Claude Code integration: session context is injected at startup, recall is nudged before substantive work, and durable facts are captured at turn end when possible.

The plugin lives in the repo at `plugins/codex/`.

## Install

Memoir's Codex plugin is distributed through the repository marketplace in `zhangfengcdt/memoir`. In Codex, run `/plugins`, add the `memoir` marketplace from `zhangfengcdt/memoir`, restart Codex if prompted, then choose **Memoir Plugins** and install `memoir`.

You can also register the marketplace from the CLI:

```bash
codex plugin marketplace add zhangfengcdt/memoir
```

The repository marketplace lives at `.agents/plugins/marketplace.json`; its `source.path` is `./plugins/codex`, resolved relative to the repository root.

For local development or PR validation from a checkout, register that checkout as the marketplace root instead:

```bash
codex plugin marketplace add /absolute/path/to/memoir
```

Codex installs plugins from marketplace entries into its plugin cache, so after changing local plugin files, restart Codex or refresh the marketplace before retesting.

Enable hooks in Codex:

```toml
[features]
hooks = true
```

For one-off tests, pass `--enable hooks`. Codex v0.129.0 warns that `[features].codex_hooks` is deprecated; use `[features].hooks` for new installs.

Codex installs plugin skills today, but does not yet activate lifecycle hooks bundled by marketplace plugins (tracked upstream in [openai/codex#16430](https://github.com/openai/codex/issues/16430)). Until plugin-bundled hooks are loaded by Codex itself, install Memoir's bundled hooks into your user hooks file after installing the plugin:

```bash
PLUGIN_ROOT=$(find "${CODEX_HOME:-$HOME/.codex}/plugins/cache" \
  -path '*/memoir/memoir/*/.codex-plugin/plugin.json' -print -quit \
  | sed 's#/.codex-plugin/plugin.json$##')
bash "$PLUGIN_ROOT/scripts/install-codex-hooks.sh"
```

This writes `SessionStart`, `UserPromptSubmit`, and `Stop` hooks to `~/.codex/hooks.json`. To remove them:

```bash
bash "$PLUGIN_ROOT/scripts/install-codex-hooks.sh" uninstall
```

After installing the bridge, Codex may show:

```text
⚠ 3 hooks need review before they can run. Open /hooks to review them.
```

Open `/hooks`, review each Memoir hook, and press `t` to trust it. Hooks do not run until they are trusted.

Each project gets a store under `~/.memoir/<slug>/`, derived from the session cwd. Override with `MEMOIR_STORE=/path/to/store`.

To inspect the same store the plugin uses, resolve the store first instead of running bare `memoir status` from the project directory:

```bash
PLUGIN_ROOT=/path/to/memoir/plugins/codex
STORE=$("$PLUGIN_ROOT/scripts/derive-store-path.sh" /path/to/project)
"$PLUGIN_ROOT/scripts/memoir-cli.sh" -s "$STORE" status
"$PLUGIN_ROOT/scripts/memoir-cli.sh" --json -s "$STORE" summarize --keys "*" -n default
```

## CLI resolution

The plugin shells out to the `memoir` CLI through `scripts/memoir-cli.sh`. It picks, in order:

1. **`memoir` on `PATH`** — install with `pip install memoir-ai`, `pipx install memoir-ai`, or `uv tool install memoir-ai`.
2. **`uvx` on `PATH`** — transparent fallback as `uvx --from memoir-ai==<pinned> memoir ...` with zero manual install. The pin is set in `scripts/resolve-memoir-cli.sh` (`MEMOIR_AI_PIN`) so a silent PyPI publish cannot change behavior under you.
3. **`uv` on `PATH`** — fallback as `uv tool run --from memoir-ai==<pinned> memoir ...` for environments without the `uvx` shim.
4. **Neither** — the plugin disables capture/recall and surfaces an install hint in the status line.

LLM extraction uses Codex auth through `codex exec`, not Claude Code's `MEMOIR_LLM_BACKEND=claude-cli` path. Override the nested extraction model with `MEMOIR_CODEX_MODEL`; otherwise the hook inherits Codex's active model from hook input and falls back to `gpt-5.4`.

## What ships

| Component | Role |
|---|---|
| `memory-recall` skill | Recalls default-namespace facts by semantic path. |
| `memoir-onboard` skill | Populates `codebase:onboard` for git repos or `project:onboard` for non-git folders. |
| `memoir-remember` skill | Explicit manual capture, replacing Claude Code's `/memoir:remember` with Codex-side path selection and `remember -p` writes. |
| `memoir-status` skill | Shows the active store, branch, commits, memory count, and namespaces. |
| `memoir-ui` skill | Launches or reopens the readonly Memoir UI for the active store. |
| `SessionStart` hook | Ensures the store exists and injects memory status, keys, unmerged hints, and onboarding snapshots. |
| `UserPromptSubmit` hook | Keeps the memoir branch aligned with the code branch and injects recall-before-acting guidance. |
| `Stop` hook | Best-effort metrics, code-change summaries, and durable-fact extraction from Codex transcript JSONL. |

## Read/write asymmetry

The Codex plugin keeps the same read/write split as the Claude Code integration:

- Reads are skill-driven. Codex can use `memory-recall` when existing memories may help, and `UserPromptSubmit` only injects a recall-before-acting hint.
- Onboarding is explicit. `memoir-onboard` is a user-invoked project indexing workflow that writes scoped `codebase:onboard` or `project:onboard` snapshots.
- General manual writes are explicit. `memoir-remember` is the Codex replacement for Claude Code's `/memoir:remember`; it writes with `memoir remember -p` so classification is done by Codex rather than Memoir's package-level LLM default. The `Stop` hook still handles best-effort auto-capture.
- `memoir-status` and `memoir-ui` replace the read-only Claude Code `/memoir:status` and `/memoir:ui` command surfaces.
- Deletion remains CLI-only through `memoir forget`.

Codex plugin slash commands, deprecated custom prompt surfaces, Claude Code statusline behavior, and `SessionEnd` cleanup are not included in v1. Use the Memoir CLI for administrative operations:

```bash
STORE="${MEMOIR_STORE:-$(bash /path/to/memoir/plugins/codex/scripts/derive-store-path.sh)}"
MEMOIR="/path/to/memoir/plugins/codex/scripts/memoir-cli.sh"

( cd "$STORE" && "$MEMOIR" -s "$STORE" remember "Prefer pytest for Python tests" -p preferences.coding.testing )
( cd "$STORE" && "$MEMOIR" --json -s "$STORE" status )
( cd "$STORE" && "$MEMOIR" -s "$STORE" ui )
```

## LLM extraction

The Stop hook uses `codex exec` for fact extraction and code-change summaries. It runs nested Codex with hooks disabled, read-only sandboxing, ignored rules, and `--skip-git-repo-check` so extraction does not recurse into Memoir capture. It uses `MEMOIR_CODEX_MODEL` when set, otherwise the active Codex model from hook input, otherwise `gpt-5.4`.

If `codex` is unavailable or the nested call fails, the hook fails open and the user turn continues. Metrics and explicit-path CLI writes still work without nested LLM extraction.

Stop capture runs only after Codex completes a turn. If the turn is interrupted or aborted before the final assistant message, there may be no Stop hook run and no auto-captured memory for that turn.

## Real Codex smoke test

Use a disposable project and store:

```bash
rm -rf /tmp/memoir-smoke /tmp/memoir-smoke-store
mkdir -p /tmp/memoir-smoke

cd /tmp/memoir-smoke
MEMOIR_STORE=/tmp/memoir-smoke-store \
MEMOIR_CODEX_MODEL=gpt-5.4 \
codex exec --enable hooks --skip-git-repo-check -m gpt-5.4 \
  "Use Memoir, remember that this smoke project prefers pytest, then report Memoir status."
```

Export evidence before cleanup:

```bash
{
  echo "# Memoir Codex Smoke Evidence"
  echo
  codex --version
  echo
  echo "model: gpt-5.4"
  echo "store: /tmp/memoir-smoke-store"
  echo
  /path/to/memoir/plugins/codex/scripts/memoir-cli.sh --json -s /tmp/memoir-smoke-store status
  /path/to/memoir/plugins/codex/scripts/memoir-cli.sh --json -s /tmp/memoir-smoke-store summarize --keys "*" -n default
} > /tmp/memoir-smoke/evidence.md
```

Clean up after recording evidence:

```bash
rm -rf /tmp/memoir-smoke /tmp/memoir-smoke-store
```

Do not commit generated stores, local Codex config, or `/tmp` evidence unless a maintainer asks for a sanitized artifact.

## Parity notes

The Codex plugin intentionally mirrors the Claude Code plugin where Codex has equivalent surfaces: `SessionStart`, `UserPromptSubmit`, `Stop`, skill-driven recall/onboarding/manual remember/status/UI, store derivation, branch auto-match, and onboarding namespaces. It does not port Claude-only slash-command markdown, deprecated custom prompt surfaces, statusline behavior, or `SessionEnd` cleanup. The first Codex-specific divergence is transcript parsing: Codex records messages and tools as `response_item.payload` objects, so the parser, metrics collector, and edit collector are separate from the Claude JSONL versions.

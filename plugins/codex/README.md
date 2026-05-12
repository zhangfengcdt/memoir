# Memoir Plugin for Codex

Give Codex a git-versioned, taxonomy-structured memory. Memoir stores durable facts at semantic paths such as `preferences.coding.style`, keeps project memories branch-aware, and can inject recall/onboarding context into future Codex sessions.

Full reference: <https://zhangfengcdt.github.io/memoir/codex/>.

## Install

Memoir's Codex plugin is distributed through the repository marketplace in `zhangfengcdt/memoir`. In Codex, run `/plugins`, add the `memoir` marketplace from `zhangfengcdt/memoir`, restart Codex if prompted, then choose **Memoir Plugins** and install `memoir`.

You can also register the marketplace from the CLI:

```bash
codex plugin marketplace add zhangfengcdt/memoir
```

For local development or PR validation from a checkout, register that checkout as the marketplace root instead:

```bash
codex plugin marketplace add /absolute/path/to/memoir
```

The marketplace file lives at `.agents/plugins/marketplace.json`; its `source.path` points to `./plugins/codex`, relative to the repository root.

Enable hooks in Codex config:

```toml
[features]
hooks = true
```

For one-off testing, pass `--enable hooks` to Codex. Older docs and builds used `[features].codex_hooks`; Codex v0.129.0 warns that name is deprecated.

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

Each project gets its own store at `~/.memoir/<slug>/`, derived from the session cwd. Override with `MEMOIR_STORE=/your/path`. Linked git worktrees share one store keyed on the main worktree path; set `MEMOIR_STORE` per worktree to opt out.

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

This mirrors the Claude Code plugin's CLI ergonomics: if `uv` is present, users do not need to install `memoir-ai` manually before enabling the plugin. LLM extraction is Codex-specific, though: the Stop hook uses Codex auth through `codex exec`, not Claude Code's `MEMOIR_LLM_BACKEND=claude-cli` path. Override the nested extraction model with `MEMOIR_CODEX_MODEL`; otherwise the hook inherits Codex's active model from hook input and falls back to `gpt-5.4`.

## What ships

| Component | Role |
|---|---|
| Skills | `memory-recall`, `memoir-onboard`, `memoir-remember`, `memoir-status`, and `memoir-ui`. |
| Hooks | `SessionStart`, `UserPromptSubmit`, and `Stop`. |
| Helper scripts | Store path resolution, CLI resolution, UI control, status command, transcript parsing, metrics, and edit collection. |
| Marketplace | `.agents/plugins/marketplace.json` points Codex at `./plugins/codex`. |

## Read/write asymmetry

The plugin keeps reads and writes intentionally asymmetric:

- Reads are skill-driven. Codex can use `memory-recall` when existing memories may help, and `UserPromptSubmit` only injects a recall-before-acting hint.
- Onboarding is explicit. `memoir-onboard` is a user-invoked project indexing workflow that writes scoped `codebase:onboard` or `project:onboard` snapshots.
- General manual writes are explicit. `memoir-remember` is the Codex replacement for Claude Code's `/memoir:remember`; it writes with `memoir remember -p` so classification is done by Codex rather than Memoir's package-level LLM default. The `Stop` hook still handles best-effort auto-capture.
- `memoir-status` and `memoir-ui` replace the read-only Claude Code `/memoir:status` and `/memoir:ui` command surfaces.
- Deletion remains CLI-only through `memoir forget`.

Codex plugin slash commands, deprecated custom prompt surfaces, Claude Code statusline behavior, and `SessionEnd` cleanup are not part of v1. Use the Memoir CLI for administrative operations:

```bash
STORE="${MEMOIR_STORE:-$(bash /path/to/memoir/plugins/codex/scripts/derive-store-path.sh)}"
MEMOIR="/path/to/memoir/plugins/codex/scripts/memoir-cli.sh"

( cd "$STORE" && "$MEMOIR" -s "$STORE" remember "Prefer pytest for Python tests" -p preferences.coding.testing )
( cd "$STORE" && "$MEMOIR" --json -s "$STORE" status )
( cd "$STORE" && "$MEMOIR" -s "$STORE" ui )
```

## Hook lifecycle

| Event | Script | Purpose |
|---|---|---|
| `SessionStart` | `hooks/session-start.sh` | Ensure the store exists, auto-match the memoir branch to the code branch, inject status, default keys, unmerged branch hints, and onboarding snapshots. |
| `UserPromptSubmit` | `hooks/user-prompt-submit.sh` | Keep the memoir branch aligned and inject a recall-before-acting hint when user memories exist and the prompt looks substantive. |
| `Stop` | `hooks/stop.sh` | Best-effort metrics, code-change summaries, and durable-fact extraction from Codex transcript JSONL. |

Disable auto-capture with `MEMOIR_NO_CAPTURE=1`. Disable metrics with `MEMOIR_NO_METRICS=1`. Disable code summaries with `MEMOIR_NO_CODE_SUMMARY=1`.

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

Then remove the smoke project and store unless the evidence file is being attached to a PR:

```bash
rm -rf /tmp/memoir-smoke /tmp/memoir-smoke-store
```

## Learn more

- Codex plugin guide: <https://zhangfengcdt.github.io/memoir/codex/>
- CLI reference: <https://zhangfengcdt.github.io/memoir/cli/>
- UI: <https://zhangfengcdt.github.io/memoir/ui/>

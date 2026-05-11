# Memoir Plugin for Codex

Give Codex a git-versioned, taxonomy-structured memory. Memoir stores durable facts at semantic paths such as `preferences.coding.style`, keeps project memories branch-aware, and can inject recall/onboarding context into future Codex sessions.

Full reference: <https://zhangfengcdt.github.io/memoir/codex/>.

## Install

From a local checkout of this repository:

```bash
codex plugin marketplace add /absolute/path/to/memoir
```

Then install `memoir-codex` from the Codex plugin UI or plugin command surface.

Enable hooks in Codex config:

```toml
[features]
hooks = true
```

For one-off testing, pass `--enable hooks` to Codex. Older docs and builds used `[features].codex_hooks`; Codex v0.129.0 warns that name is deprecated.

Each project gets its own store at `~/.memoir/<slug>/`, derived from the session cwd. Override with `MEMOIR_STORE=/your/path`. Linked git worktrees share one store keyed on the main worktree path; set `MEMOIR_STORE` per worktree to opt out.

## CLI resolution

The plugin shells out to the `memoir` CLI. It picks, in order:

1. `memoir` on `PATH`.
2. `uvx --from memoir-ai==<pinned> memoir`.
3. `uv tool run --from memoir-ai==<pinned> memoir`.

If none are available, capture and recall are disabled and the hook surfaces an install hint.

Stop-hook LLM extraction uses Codex auth through `codex exec`. Override the nested extraction model with `MEMOIR_CODEX_MODEL`; otherwise the hook uses Codex's active model when available and falls back to `gpt-5.4`.

## What ships

| Component | Role |
|---|---|
| Skills | `memory-recall` for default-namespace facts, `memoir-onboard` for `codebase:onboard` / `project:onboard` snapshots. |
| Hooks | `SessionStart`, `UserPromptSubmit`, and `Stop`. |
| Helper scripts | Store path resolution, CLI resolution, UI control, status command, transcript parsing, metrics, and edit collection. |
| Marketplace | `.agents/plugins/marketplace.json` points Codex at `./plugins/memoir-codex`. |

## Read/write asymmetry

The plugin keeps reads and writes intentionally asymmetric:

- Reads are skill-driven. Codex can use `memory-recall` when existing memories may help, and `UserPromptSubmit` only injects a recall-before-acting hint.
- Onboarding is explicit. `memoir-onboard` is a user-invoked project indexing workflow that writes scoped `codebase:onboard` or `project:onboard` snapshots.
- General manual writes are not a skill. The `Stop` hook handles best-effort auto-capture, and the manual escape hatch remains the CLI.
- Deletion remains CLI-only through `memoir forget`.

Codex plugin slash commands, deprecated custom prompt surfaces, Claude Code statusline behavior, and `SessionEnd` cleanup are not part of v1. Use the Memoir CLI for manual operations:

```bash
STORE="${MEMOIR_STORE:-$(bash /path/to/memoir/plugins/memoir-codex/scripts/derive-store-path.sh)}"
MEMOIR="/path/to/memoir/plugins/memoir-codex/scripts/memoir-cli.sh"

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

## Real Codex smoke test

Use a disposable project and store:

```bash
rm -rf /tmp/memoir-codex-smoke /tmp/memoir-codex-smoke-store
mkdir -p /tmp/memoir-codex-smoke

cd /tmp/memoir-codex-smoke
MEMOIR_STORE=/tmp/memoir-codex-smoke-store \
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
  echo "store: /tmp/memoir-codex-smoke-store"
  echo
  /path/to/memoir/plugins/memoir-codex/scripts/memoir-cli.sh --json -s /tmp/memoir-codex-smoke-store status
  /path/to/memoir/plugins/memoir-codex/scripts/memoir-cli.sh --json -s /tmp/memoir-codex-smoke-store summarize --keys "*" -n default
} > /tmp/memoir-codex-smoke/evidence.md
```

Then remove the smoke project and store unless the evidence file is being attached to a PR:

```bash
rm -rf /tmp/memoir-codex-smoke /tmp/memoir-codex-smoke-store
```

## Learn more

- Codex plugin guide: <https://zhangfengcdt.github.io/memoir/codex/>
- CLI reference: <https://zhangfengcdt.github.io/memoir/cli/>
- UI: <https://zhangfengcdt.github.io/memoir/ui/>

# Codex Plugin

Memoir ships a Codex plugin that brings branch-aware, taxonomy-structured memory into Codex sessions. It is the Codex port of the existing Claude Code integration: session context is injected at startup, recall is nudged before substantive work, and durable facts are captured at turn end when possible.

The plugin lives in the repo at `plugins/memoir-codex/`.

## Install

Memoir's Codex plugin is distributed through the repository marketplace in `zhangfengcdt/memoir`. In Codex, run `/plugins`, add the `memoir` marketplace from `zhangfengcdt/memoir`, restart Codex if prompted, then choose **Memoir Plugins** and install `memoir-codex`.

You can also register the marketplace from the CLI:

```bash
codex plugin marketplace add zhangfengcdt/memoir
```

The repository marketplace lives at `.agents/plugins/marketplace.json`; its `source.path` is `./plugins/memoir-codex`, resolved relative to the repository root.

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

Each project gets a store under `~/.memoir/<slug>/`, derived from the session cwd. Override with `MEMOIR_STORE=/path/to/store`.

The plugin shells out to the Memoir CLI. No manual `pip install` is required if `uv` is on `PATH`: the helper uses `memoir` when already installed, otherwise `uvx --from memoir-ai==<pinned> memoir`, otherwise `uv tool run --from memoir-ai==<pinned> memoir`.

## What ships

| Component | Role |
|---|---|
| `memory-recall` skill | Recalls default-namespace facts by semantic path. |
| `memoir-onboard` skill | Populates `codebase:onboard` for git repos or `project:onboard` for non-git folders. |
| `SessionStart` hook | Ensures the store exists and injects memory status, keys, unmerged hints, and onboarding snapshots. |
| `UserPromptSubmit` hook | Keeps the memoir branch aligned with the code branch and injects recall-before-acting guidance. |
| `Stop` hook | Best-effort metrics, code-change summaries, and durable-fact extraction from Codex transcript JSONL. |

## Read/write asymmetry

The Codex plugin keeps the same read/write split as the Claude Code integration:

- Reads are skill-driven. Codex can use `memory-recall` when existing memories may help, and `UserPromptSubmit` only injects a recall-before-acting hint.
- Onboarding is explicit. `memoir-onboard` is a user-invoked project indexing workflow that writes scoped `codebase:onboard` or `project:onboard` snapshots.
- General manual writes are not a skill. The `Stop` hook handles best-effort auto-capture, and the manual escape hatch remains the CLI.
- Deletion remains CLI-only through `memoir forget`.

Codex plugin slash commands, deprecated custom prompt surfaces, Claude Code statusline behavior, and `SessionEnd` cleanup are not included in v1. Use the Memoir CLI for manual operations:

```bash
STORE="${MEMOIR_STORE:-$(bash /path/to/memoir/plugins/memoir-codex/scripts/derive-store-path.sh)}"
MEMOIR="/path/to/memoir/plugins/memoir-codex/scripts/memoir-cli.sh"

( cd "$STORE" && "$MEMOIR" -s "$STORE" remember "Prefer pytest for Python tests" -p preferences.coding.testing )
( cd "$STORE" && "$MEMOIR" --json -s "$STORE" status )
( cd "$STORE" && "$MEMOIR" -s "$STORE" ui )
```

## LLM extraction

The Stop hook uses `codex exec` for fact extraction and code-change summaries. It runs nested Codex with hooks disabled, read-only sandboxing, ignored rules, and `--skip-git-repo-check` so extraction does not recurse into Memoir capture. Set `MEMOIR_CODEX_MODEL` to override the nested model; PR validation should use `gpt-5.4`.

If `codex` is unavailable or the nested call fails, the hook fails open and the user turn continues. Metrics and explicit-path CLI writes still work without nested LLM extraction.

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

Clean up after recording evidence:

```bash
rm -rf /tmp/memoir-codex-smoke /tmp/memoir-codex-smoke-store
```

Do not commit generated stores, local Codex config, or `/tmp` evidence unless a maintainer asks for a sanitized artifact.

## Parity notes

The Codex plugin intentionally mirrors the Claude Code plugin where Codex has equivalent surfaces: `SessionStart`, `UserPromptSubmit`, `Stop`, skill-driven recall/onboarding, store derivation, branch auto-match, and onboarding namespaces. It does not port Claude-only slash-command markdown, deprecated custom prompt surfaces, statusline behavior, or `SessionEnd` cleanup. The first Codex-specific divergence is transcript parsing: Codex records messages and tools as `response_item.payload` objects, so the parser, metrics collector, and edit collector are separate from the Claude JSONL versions.

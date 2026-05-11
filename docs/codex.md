# Codex Plugin

Memoir ships a Codex plugin that brings branch-aware, taxonomy-structured memory into Codex sessions. It is the Codex port of the existing Claude Code integration: session context is injected at startup, recall is nudged before substantive work, and durable facts are captured at turn end when possible.

The plugin lives in the repo at `plugins/memoir-codex/`.

## Install

From a local checkout:

```bash
codex plugin marketplace add /absolute/path/to/memoir
```

Then install `memoir-codex` from Codex's plugin UI or plugin command surface. The repository marketplace lives at `.agents/plugins/marketplace.json` and points to `./plugins/memoir-codex`.

Enable hooks in Codex:

```toml
[features]
hooks = true
```

For one-off tests, pass `--enable hooks`. Codex v0.129.0 warns that `[features].codex_hooks` is deprecated; use `[features].hooks` for new installs.

Each project gets a store under `~/.memoir/<slug>/`, derived from the session cwd. Override with `MEMOIR_STORE=/path/to/store`.

## What ships

| Component | Role |
|---|---|
| `memory-recall` skill | Recalls default-namespace facts by semantic path. |
| `memoir-onboard` skill | Populates `codebase:onboard` for git repos or `project:onboard` for non-git folders. |
| `SessionStart` hook | Ensures the store exists and injects memory status, keys, unmerged hints, and onboarding snapshots. |
| `UserPromptSubmit` hook | Keeps the memoir branch aligned with the code branch and injects recall-before-acting guidance. |
| `Stop` hook | Best-effort metrics, code-change summaries, and durable-fact extraction from Codex transcript JSONL. |

Codex plugin slash commands, Claude Code statusline behavior, and `SessionEnd` cleanup are not included in v1. Use the Memoir CLI for manual operations:

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

The Codex plugin intentionally mirrors the Claude Code plugin where Codex has equivalent surfaces: `SessionStart`, `UserPromptSubmit`, `Stop`, skills, store derivation, branch auto-match, and onboarding namespaces. The first Codex-specific divergence is transcript parsing: Codex records messages and tools as `response_item.payload` objects, so the parser, metrics collector, and edit collector are separate from the Claude JSONL versions.

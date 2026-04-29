# Memoir Plugin for Claude Code

Give Claude Code a **git-versioned, taxonomy-structured memory**. Every captured fact is classified into a semantic path (e.g. `preferences.coding.style`), stored in a per-project git repo, and recalled by path — not by chunk-matching. Memory becomes branchable, time-travelable, and cryptographically verifiable.

Full reference: [zhangfengcdt.github.io/memoir/claude_code/](https://zhangfengcdt.github.io/memoir/claude_code/).

## Install

Inside a Claude Code session:

```
/plugin marketplace add zhangfengcdt/memoir
/plugin install memoir@memoir
```

Hooks register on the next session start. Each project gets its own store at `~/.memoir/<basename>_<8-char-hash>/` (override via `MEMOIR_STORE=/your/path`).

### CLI resolution

The plugin shells out to the `memoir` CLI. It picks, in order:

1. **`memoir` on `PATH`** — install with `pip install memoir-ai`, `pipx install memoir-ai`, or `uv tool install memoir-ai`.
2. **`uvx` on `PATH`** — transparent fallback as `uvx --from memoir-ai memoir …` (~1s first-run warmup, zero install).
3. **Neither** — the plugin disables capture/recall and surfaces an install hint in the status line.

LLM calls inherit Claude Code's auth automatically (`MEMOIR_LLM_BACKEND=claude-cli`, `MEMOIR_LLM_MODEL=claude-haiku-4-5`). Override `MEMOIR_LLM_MODEL` in your shell for `sonnet` / `opus`.

## What you get

| Component | Role |
|---|---|
| **Slash commands** | `/memoir:onboard`, `/memoir:remember`, `/memoir:recall`, `/memoir:status`, `/memoir:ui`. (Admin operations like sync-branch, unmerged, taxonomy, and forget are available via the `memoir` CLI.) |
| **Skills** | `memory-recall` (user facts, auto-triggered, runs in a forked context) and `memoir-onboard` (maintains the `codebase:onboard` snapshot). |
| **Lifecycle hooks** | `SessionStart` (inject status + taxonomy + unmerged-branch suggestions), `UserPromptSubmit` (surface matching hints), `Stop` (async auto-capture of durable facts), `SessionEnd` (cleanup). |
| **Status line** | `[memoir] <branch> · N memories`, with warnings for concurrent sessions or sticky-branch mode. |

Memory branches auto-track code branches — switching to `feature/x` forks a memoir branch from `main` so you inherit all prior captures but keep new ones isolated until you promote them with `memoir sync-branch`. For deeper git operations (branch, checkout, merge, time-travel, blame, proof, verify, diff, get, keys), use the `memoir` CLI directly.

Disable per-turn auto-capture with `MEMOIR_NO_CAPTURE=1`.

## Dev install (local checkout)

Point Claude Code at your working copy:

```json
{
  "plugins": ["/path/to/memoir/plugins/claude-code"]
}
```

## MCP (optional)

The plugin does not ship an `.mcp.json` — MCP is opt-in. See the [Claude Code plugin docs](https://zhangfengcdt.github.io/memoir/claude_code/) for the `memoir-mcp` server configuration.

## Learn more

- [Claude Code plugin guide](https://zhangfengcdt.github.io/memoir/claude_code/) — hooks, auto-capture internals, sticky branches, concurrent sessions, per-command reference.
- [CLI reference](https://zhangfengcdt.github.io/memoir/cli/) — every `memoir` command and flag.
- [UI](https://zhangfengcdt.github.io/memoir/ui/) — the visual explorer launched by `/memoir:ui`.

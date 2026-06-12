# Memoir Plugin for Claude Code

Give Claude Code a **git-versioned, taxonomy-structured memory**. Every captured fact is classified into a semantic path (e.g. `preferences.coding.style`), stored in a per-project git repo, and recalled by path — not by chunk-matching. Memory becomes branchable, time-travelable, and cryptographically verifiable.

Full reference: [zhangfengcdt.github.io/memoir/claude_code/](https://zhangfengcdt.github.io/memoir/claude_code/).

## Install

Inside a Claude Code session:

```
/plugin marketplace add zhangfengcdt/memoir
/plugin install memoir@memoir
```

Hooks register on the next session start. Each project gets its own store at `~/.memoir/<slug>/` (override via `MEMOIR_STORE=/your/path`). Linked git worktrees of the same repo share one store keyed on the **main worktree's** path — so memories captured from any worktree are recallable from every other. To opt out, set `MEMOIR_STORE` per worktree.

### CLI resolution

The plugin shells out to the `memoir` CLI. It picks, in order:

1. **`memoir` on `PATH`** — install with `pip install memoir-ai`, `pipx install memoir-ai`, or `uv tool install memoir-ai`.
2. **`uvx` on `PATH`** — transparent fallback as `uvx --from memoir-ai==<pinned> memoir …` (~1s first-run warmup, zero install). The pin is set in `scripts/resolve-memoir-cli.sh` (`MEMOIR_AI_PIN`) so a silent PyPI publish can't change behavior under you.
3. **Neither** — the plugin disables capture/recall and surfaces an install hint in the status line.

LLM calls inherit Claude Code's auth automatically (`MEMOIR_LLM_BACKEND=claude-cli`, `MEMOIR_LLM_MODEL=claude-haiku-4-5`). Override `MEMOIR_LLM_MODEL` in your shell for `sonnet` / `opus`.

## What you get

| Component | Role |
|---|---|
| **Slash commands** | `/memoir:onboard`, `/memoir:remember`, `/memoir:recall`, `/memoir:status`, `/memoir:sync`, `/memoir:ui`. (Admin operations like taxonomy and forget are available via the `memoir` CLI.) |
| **Skills** | `memory-recall` (user facts, auto-triggered, runs in a forked context) and `memoir-onboard` (maintains the `codebase:onboard` snapshot). |
| **Lifecycle hooks** | `SessionStart` (inject status + taxonomy + unmerged-branch suggestions, with a guided `/memoir:sync` offer when there's meaningful unmerged work), `UserPromptSubmit` (surface matching hints), `Stop` (async auto-capture of durable facts), `SessionEnd` (cleanup). |
| **Status line** | `[memoir] <branch> · N memories`, with warnings for concurrent sessions or sticky-branch mode. |

Memory branches auto-track code branches — switching to `feature/x` forks a memoir branch from `main` so you inherit all prior captures but keep new ones isolated until you promote them with `/memoir:sync` (or `memoir sync-branch` from a terminal). For deeper git operations (branch, checkout, merge, time-travel, blame, proof, verify, diff, get, keys), use the `memoir` CLI directly.

### Branch sync

`/memoir:sync` walks you through promoting unmerged memoir branches into `main` with a select UI: merge all, choose branches, ignore branches permanently, or snooze reminders. State lives next to the store:

- `<store>/.git/plugin-ignored-branches` — one branch name per line; delete a line to unignore.
- `<store>/.git/plugin-merge-prompt-cooldown` — "snoozed until" epoch written by the snooze option.

When the total unmerged work reaches **5 commits** (and no snooze is active), SessionStart additionally asks the agent to offer the sync once that session — declining snoozes it for a day. The status-line count and the informational branch list always render regardless of snooze state.

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

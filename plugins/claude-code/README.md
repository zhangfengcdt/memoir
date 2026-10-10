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
| **Slash commands** | `/memoir:onboard`, `/memoir:remember`, `/memoir:recall`, `/memoir:status`, `/memoir:sync`, `/memoir:ui`, `/memoir:pane`. (Admin operations like taxonomy and forget are available via the `memoir` CLI.) |
| **Skills** | `memory-recall` (user facts, auto-triggered, runs in a forked context) and `memoir-onboard` (maintains the `codebase:onboard` snapshot). |
| **Lifecycle hooks** | `SessionStart` (inject status + taxonomy + unmerged-branch suggestions, with a guided `/memoir:sync` offer when there's meaningful unmerged work), `UserPromptSubmit` (surface matching hints), `Stop` (async auto-capture of durable facts), `SessionEnd` (cleanup). |
| **Status line** | `[memoir] <branch> · N memories`, with warnings for concurrent sessions or sticky-branch mode. On Claude Code 2.1.287+ the mod also appends `memoir: <branch> · N memories · +N this turn` to the hint line under the prompt, with no settings edit. |
| **Mod** (Claude Code 2.1.287+) | An in-process hooks module (`hooks/mod/`) that watches the store and drives `/memoir:pane` — a live capture feed with a taxonomy tab — plus the hint-line status above. Read-only; the shell hooks keep doing capture and recall. |

Memory branches auto-track code branches — switching to `feature/x` forks a memoir branch from `main` so you inherit all prior captures but keep new ones isolated until you promote them with `/memoir:sync` (or `memoir sync-branch` from a terminal). For deeper git operations (branch, checkout, merge, time-travel, blame, proof, verify, diff, get, keys), use the `memoir` CLI directly.

### Branch sync

`/memoir:sync` walks you through promoting unmerged memoir branches into `main` with a select UI: merge all, choose branches, ignore branches permanently, snooze reminders, or delete branches. State lives next to the store:

- `<store>/.git/plugin-ignored-branches` — one branch name per line; delete a line to unignore.
- `<store>/.git/plugin-merge-prompt-cooldown` — "snoozed until" epoch + consecutive-decline count.

When the total unmerged work reaches **5 commits** (and no snooze is active), SessionStart additionally asks the agent to offer the sync once that session. Declining backs off automatically — 1 day, then 7, then 30 on repeated declines — while an explicit snooze resets the escalation. The status-line count and the informational branch list always render regardless of snooze state.

**Auto-promotion.** When your code branch is merged into `main` via a merge commit, the next SessionStart on `main` promotes its memoir branch automatically (the promote is additive-only and conflict-free) and reports it in the status line. Squash- or rebase-merged branches aren't detected — promote those with `/memoir:sync`. Disable with `MEMOIR_AUTO_PROMOTE_MERGED=0`.

**Branch deletion.** `/memoir:sync` can delete any memoir branch except `main` and the currently-checked-out one — always behind an explicit pick, never automatically. The picker flags each branch's risk: *stale* branches (inactive 60 days, `MEMOIR_STALE_BRANCH_DAYS` to override, and either already synced or their code branch is gone) are marked safe to remove; unsynced branches carry a warning that their unmerged captures will be discarded. Deleting also cleans up the branch's sync marker and ignore-list entry, so the store's branch list stays bounded over time.

Disable per-turn auto-capture with `MEMOIR_NO_CAPTURE=1`.

### Capture feed pane and built-in status line (Claude Code 2.1.287+)

Auto-capture runs after the turn ends, so what memoir just learned is otherwise invisible until you ask. On Claude Code 2.1.287 or newer the plugin loads a [mod](https://code.claude.com/docs/en/plugins/mods/overview) that makes it visible:

- **`/memoir:pane`** opens a pane with three tabs. *Recent* lists the last ~20 captures, newest first, `●` marking the ones that landed this turn; `m` toggles the hidden `metrics.*` writes, `r` refreshes. *Taxonomy* groups the store's paths by their first segment; Enter expands a group. *Metrics* charts the per-branch turn accumulators (`metrics.turn.<branch>`) as bars across branches: turns, tool calls, tool errors, average latency, output and tool-result characters, the current branch first, the same figures the web UI's Statistics → Metrics tab shows. Docked beside the transcript in a wide fullscreen terminal, inline above the prompt otherwise. Where nothing can draw (`claude -p`, the SDK) the command prints a text summary instead.
- **Hint line.** `memoir: <branch> · N memories` is appended to the shortcuts line under the prompt, and `+N this turn` appears once the turn's captures have landed (it clears at the next turn). Nothing shows when there is no store. If your `~/.claude/settings.json` already pipes `statusline.sh` into `statusLine`, the suffix is skipped so memoir's state is not shown twice.

The mod polls the store's branch ref every 3 s (two `stat`s, no subprocess) and re-reads `git log` plus the changed memories only when it moved, so it catches every write path — the Stop hook, `/memoir:remember`, the CLI, `memoir pull`. It only ever reads. On older Claude Code versions nothing changes: the shell hooks run as before, `/memoir:pane` prints a text summary, and `scripts/statusline.sh` remains the way to get memoir into the status line.

Develop it with `claude plugin validate plugins/claude-code` and `claude plugin test plugins/claude-code` (tests in `hooks/mod/*.test.tsx`, no store or LLM needed).

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

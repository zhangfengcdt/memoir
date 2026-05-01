# Claude Code end-to-end smoke tests

Drives `claude -p` against the local `plugins/claude-code/` checkout and
asserts on the resulting hook events and memoir-store side-effects. Verifies
the user-facing plugin surface that `pypi-smoke` (CLI-only) and the plugin's
own shell tests (script-only) can't reach: that hooks, slash commands, and
skills load and behave correctly inside a real Claude Code session.

## What it tests

| Case | Surface | Assertion (loose) |
|---|---|---|
| `cc-session-start-status` | `SessionStart` hook | stream-json `hook_response` for SessionStart includes `[memoir]` |
| `cc-remember-slash-captures` | `/memoir:remember` | a key lands in `default` namespace after the call |
| `cc-recall-surfaces-prior-fact` | `memory-recall` skill | response to a recall-shaped question contains a substring of the seeded fact |
| `cc-worktree-shared-store` | `derive-store-path.sh` end-to-end | a fact captured from the main checkout is recallable from a linked `git worktree` |
| `cc-slash-command-status` | `/memoir:status` | response contains `[memoir]` and a memory count |

The Stop hook's auto-capture path is **not** asserted — `claude -p` exits as
soon as the result lands, which cancels the Stop hook mid-execution. Cases
that need a durable capture use `/memoir:remember` (synchronous, runs inside
the assistant turn) instead.

## Run locally

```bash
# requires: claude CLI on PATH, logged in via `claude /login` (or
# ANTHROPIC_API_KEY set); memoir CLI on PATH
make cc-smoke
# or directly:
bash scripts/cc-smoke/run.sh
```

## Run in CI

Triggered manually via `workflow_dispatch` only — see
`.github/workflows/cc-smoke.yml`. Not on every PR. Costs LLM credits
(~$0.50 per run against haiku).

## Cost & latency

Each case fires 1–2 `claude -p` invocations. With `claude-haiku-4-5` and the
default ~40k-token Claude Code system prompt, each invocation is roughly
**$0.05 and 5–10s** wall-clock. The whole 5-case suite is ≈ $0.50 and
≈ 60s end-to-end.

## Isolation

Each case sets `MEMOIR_STORE` to a fresh `mktemp -d` and works inside its
own `mktemp -d` project directory; no case touches `~/.memoir/`. The
worktree case is the one exception — it deliberately exercises the
default `~/.memoir/<slug>/` derivation, so it cleans up its own slug
directory on success and on failure (via the cleanup trap).

`--setting-sources project,local` is passed to `claude -p` so the tests
don't pick up the developer's user `~/.claude/settings.json`.

## Quirks discovered building this harness

These are observed behaviors of `claude -p` + plugin interaction; documented
here so future authors don't re-rediscover them.

1. **Quoted args inside slash-command prompts hang `claude -p`.** Passing
   `'/memoir:remember "I prefer tabs" -p preferences.coding.style'` makes
   the session never progress past `SessionStart`. The bare-words form
   (`/memoir:remember I prefer tabs -p preferences.coding.style`) works.
   The slash-command wrapper rejoins bare words into a single `content`
   arg, so functionality is preserved.

2. **`/memoir:remember -p <path>` doesn't honor `-p` under `claude -p`.**
   When invoked via `claude -p` with `--dangerously-skip-permissions`, the
   command's bash returns a success JSON naming the requested path, but the
   memory actually lands at the classifier-fallback key
   `context.current.session`. Running the same bash command directly in a
   shell honors `-p` correctly. Root cause not yet pinned — may be related
   to how Claude Code expands `$ARGUMENTS` in slash-command bash blocks.
   Tracked as a separate plugin bug; the smoke harness uses direct
   `memoir remember` calls to seed memories rather than the slash command.

3. **Stop hook gets `outcome:"cancelled"` in `-p` mode.** `claude -p` exits
   as soon as the result lands and kills the Stop hook mid-execution.
   Auto-capture doesn't reliably persist anything in headless mode. Don't
   write smoke cases that depend on Stop-driven captures.

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

Observed behaviors of `claude -p` + plugin interaction.

1. **Claude Code rewrites `$1`, `$2`, `$N` inside slash-command markdown
   bodies before bash runs** — even inside single-quoted bash strings.
   The substitution is 0-indexed against the slash command's whitespace-
   split arguments, so a literal `case "$1"` inside a `bash -c '...'`
   block matches the *second* word of the user's input on every iteration,
   not the bash positional arg. Any slash-command bash block that needs
   true bash positional access must shell out to a real script under
   `plugins/claude-code/scripts/` so the markdown preprocessor never sees
   the `$N` literals (see `commands/remember.md` → `scripts/remember-args.sh`
   for the template). This caused two visible symptoms before being fixed:
   (a) `/memoir:remember -p <path>` silently fell back to the LLM
   classifier's `context.current.session` key, and (b) the quoted-args form
   hung `claude -p` indefinitely.

2. **Stop hook gets `outcome:"cancelled"` in `-p` mode.** `claude -p` exits
   as soon as the result lands and kills the Stop hook mid-execution.
   Auto-capture doesn't reliably persist anything in headless mode. Don't
   write smoke cases that depend on Stop-driven captures.

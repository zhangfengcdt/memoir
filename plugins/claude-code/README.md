# memoir plugin for Claude Code

Give Claude Code a **git-versioned, taxonomy-structured memory**. Unlike vector-store plugins, memoir doesn't index chunks of text — every captured fact is classified into a named taxonomy path (`preferences.coding.languages`, `profile.professional.skills`, …) and stored as a value at that path inside a per-project git repo. That makes memory **branchable**, **time-travelable**, and **cryptographically verifiable**.

## What you get

- **Auto-capture**: after each turn, a lightweight haiku pass extracts durable facts and `memoir remember` classifies each into the taxonomy. One commit per fact.
- **Auto-recall**: a `memory-recall` skill (forked subagent) runs taxonomy-path recall, and — when asked about provenance — escalates to `blame` or `diff`. Only a curated summary returns to the main context.
- **Slash commands** for memoir's git-like superpowers: `/memoir-branch`, `/memoir-checkout`, `/memoir-merge`, `/memoir-time-travel`, `/memoir-taxonomy`, `/memoir-blame`, `/memoir-proof`, `/memoir-verify`, `/memoir-status`.
- **Zero daemons**: no watch process, no vector index, nothing to clean up.

## Install

### 1. Install memoir (prerequisite)

The plugin expects the `memoir` CLI on your `PATH`. Install from PyPI or from source:

```bash
pip install memoir-ai                # from PyPI (dist name is memoir-ai, CLI is memoir)
# or
pip install -e /path/to/memoir       # editable install from the repo
```

Verify: `memoir --version` should print a version string.

If `memoir` is not found at session start, the plugin surfaces a hint in the status line and disables capture/recall (everything else works).

#### LLM backend — no API key needed (recommended)

Memoir's classifier and search engine call an LLM internally. By default they use LiteLLM and need an `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY` etc.) of their own — separate from your Claude Code auth.

For zero-config use under Claude Code, set:

```bash
export MEMOIR_LLM_BACKEND=claude-cli
export MEMOIR_LLM_MODEL=claude-haiku-4-5   # optional, this is the default
```

When set, memoir shells out to `claude -p` instead of making direct provider API calls. Every LLM call inherits Claude Code's auth (subscription OAuth or API key — whichever you're logged in with). No `OPENAI_API_KEY`, no `ANTHROPIC_API_KEY` required. Putting these two lines in your shell profile makes the plugin work end-to-end with a single auth.

### 2. Install the plugin

**Via the marketplace (recommended)** — in Claude Code:

```
/plugin marketplace add zhangfengcdt/memoir
/plugin install memoir@memoir
```

Claude Code subscribes to the marketplace manifest at the repo root (`.claude-plugin/marketplace.json`), installs the plugin from `plugins/claude-code/`, registers its four hooks, loads the `memory-recall` skill, and exposes the `/memoir-*` commands.

**From a local checkout** — if you're developing or want to use an unreleased version:

```json
{
  "plugins": ["/path/to/memoir/plugins/claude-code"]
}
```

### 3. (Optional) Add memoir as an MCP server

The plugin does **not** ship an `.mcp.json` — MCP is opt-in. If you want Claude to be able to call `memoir_remember` / `memoir_recall` / etc. mid-turn (as native MCP tools, not via the skill), drop this into your project `.mcp.json` or `~/.claude.json`:

```json
{
  "mcpServers": {
    "memoir": {
      "command": "memoir-mcp",
      "env": {
        "MEMOIR_STORE": "/absolute/path/to/your/memoir/store"
      }
    }
  }
}
```

To find the store path this plugin uses by default for a project, run:

```bash
bash /path/to/memoir/plugins/claude-code/scripts/derive-store-path.sh /path/to/your/project
```

## How it works

### Memory branches follow code branches (by default)

When a session starts on code branch `feature/x`, the plugin auto-checks out memoir branch `feature/x`, creating it forked from memoir `main` if it doesn't exist. This means:

- A new feature branch starts **pre-loaded with all of main's captured memories** (via the fork). You're never on an empty branch.
- Captures made while on `feature/x` stay on that memoir branch — they don't mix with `main` until you promote them.
- Recall from `feature/x` reads from `feature/x` (which includes everything forked from `main` plus the branch-local captures).

**Promote to main when a feature is done**: run `/memoir-sync` while on the feature branch. This merges the branch into `main` (keeping the source for further captures). `/memoir-sync-branch <name>` merges any named branch without switching away from your current one.

**The "empty main" problem**: main stays bare unless someone captures directly on code `main`. Solved by fork-inheritance (feature branches start rich) + explicit sync at completion (main grows over time with promoted knowledge).

**Unmerged-branch suggestions**: at every SessionStart, the plugin scans all memoir branches ahead of main (active in the last 30d) and surfaces them via `additionalContext`:

```
# memoir — unmerged branches detected
- memoir/feature/a: 4 unmerged commits → /memoir-sync-branch feature/a
- memoir/feature/b: 2 unmerged commits → /memoir-sync-branch feature/b
```

You can run the suggested commands while on any branch. A branch in `$MEMOIR_STORE/.git/plugin-ignored-branches` is silently skipped (one name per line — add manually to permanently silence a dormant branch).

### Opting out: sticky experiments

If you want memoir on a branch that *doesn't* match your code branch (e.g. an isolated experiment), manually switch with `/memoir-branch experiment` or `/memoir-checkout experiment`. The plugin writes `$MEMOIR_STORE/.git/plugin-sticky-branch` — auto-match stays off until you check back out to a branch matching your code branch, at which point the marker is cleared and auto-match resumes. The status line shows `<code>+<memory>*` while sticky.

### Concurrent sessions (caveat)

If two Claude Code sessions share a `MEMOIR_STORE` and target *different* branches, memoir's single-working-tree git backend will have the checkouts fight each other. The plugin detects this via a heartbeat file per session and adds `⚠ concurrent session detected on branch <other>` to the status line. The fix is to give each session a distinct `MEMOIR_STORE`. Proper per-session isolation via prollytree worktrees is a future enhancement.

### Store location

Per-project store at `~/.memoir/<sanitized-basename>_<8-char-hash>`. The hash is a SHA-256 of the project's absolute path, so the mapping is deterministic across machines with the same checkout path. Override with `MEMOIR_STORE=/your/path` if you want a shared or custom store.

### Session-start

1. Detect `memoir` in `PATH`. If missing, surface an install hint and stop.
2. `memoir new <store> --taxonomy-builtin --no-connect` if the store doesn't exist yet. Idempotent.
3. **Auto-match memoir branch to code branch**: if you're on code branch `feature/x`, the plugin creates memoir branch `feature/x` (forked from `main`) if it doesn't exist, and checks it out. When code and memoir branches agree (the default), the status line shows just `<branch>`; when you've sticky-opted-out, it shows `<code>+<memory>*`.
4. Status line: `[memoir] <branch> · N memories · M commits`. `⚠ concurrent session detected…` is appended if another session is using the same `MEMOIR_STORE` on a different branch.
5. Inject as `additionalContext`:
   - A short taxonomy summary (user namespaces only).
   - An **unmerged-branch suggestion block** listing any memoir branches ahead of main with `/memoir-sync-branch <name>` suggestions. Stateless scan — branches ahead of main and active in the last 30 days show up until you merge them.
6. Write this session's heartbeat to `$MEMOIR_STORE/.git/plugin-active-sessions/<id>` so concurrent-session detection works.

### Per-turn capture

On the `Stop` hook (async, non-blocking):

1. Parse the last turn from Claude Code's JSONL transcript.
2. Pipe to `claude -p --model haiku` with a strict prompt that extracts **and classifies** durable facts in one shot — output format is `<taxonomy-path>\t<fact>` per line.
3. For each line, call `memoir remember "<fact>" --path <path>`, which **skips memoir's internal LLM classifier** entirely and stores at the caller-provided path.

This collapses the per-turn LLM cost from `1 + N × (4-5)` calls to **just 1** — about 2× faster end-to-end, and the per-fact `memoir remember` calls drop from ~10s each to ~0.4s. Async means the user never waits.

To disable per-session: `MEMOIR_NO_CAPTURE=1`.

### Recall

Recall is pull-based via the `memory-recall` skill. The skill runs with `context: fork`, so its intermediate work stays out of the main context.

Three layers, mapped to memoir's primitives:

- **L1 — recall** (`memoir recall "<query>"`): LLM picks taxonomy paths; returns typed values with relevance scores. Usually sufficient.
- **L2 — blame** (`memoir blame <path>`): who changed that path, when, in which commit. Memoir's answer to "expand the chunk" — except you get git history, not surrounding text.
- **L3 — diff / branch** (`memoir diff`, `memoir branch`): cross-commit or cross-branch comparison. Only used for "how did this evolve?" questions.

### Slash commands

**Branching / time-travel (memoir's differentiators)**

| Command | What it does |
|---|---|
| `/memoir-status` | Memory branch + commit/memory counts. |
| `/memoir-branch [name]` | List or create memory branches. Creating a non-code-matching name sets sticky opt-out. |
| `/memoir-checkout <branch>` | Switch Claude's memory context. Sets/clears sticky marker vs code branch. |
| `/memoir-merge <source>` | Merge with conflict strategy `ours`/`theirs`/`skip`. |
| `/memoir-sync` | Merge the current memoir branch into main (keeps source branch). |
| `/memoir-sync-branch <name>` | Merge an arbitrary branch into main without switching to it. Used by SessionStart suggestions. |
| `/memoir-time-travel <hash>` | Create a branch at a past commit and switch to it. |
| `/memoir-diff [c1] [c2] [--stat]` | Show diff between two commits. Defaults to HEAD~1..HEAD. |

**Memory ops**

| Command | What it does |
|---|---|
| `/memoir-remember "<fact>" [-p <path>] [-n <ns>]` | Manually capture a memory now (independent of Stop-hook). With `-p`, skips the classifier (~25× faster). |
| `/memoir-forget <key> [-n <ns>]` | Delete a memory (always uses `--force`; recoverable via time-travel). |
| `/memoir-keys [<glob>]` | List all keys, optionally filtered by glob (e.g. `preferences.*`). |

**Taxonomy / verification**

| Command | What it does |
|---|---|
| `/memoir-taxonomy` | Per-namespace counts + registered taxonomies. |
| `/memoir-blame <path>` | Change history for a specific taxonomy path. |
| `/memoir-proof <path>` | Generate a SHA-256 proof of the path's current value. |
| `/memoir-verify <path>` | Verify a proof — detects tampering. |

## Why memoir (vs a vector-search memory plugin)

|  | memsearch-style | memoir |
|---|---|---|
| Retrieval | BM25 + dense vectors + RRF over chunks | LLM picks taxonomy paths → direct lookup |
| Storage unit | markdown chunks | typed values at named paths |
| History | flat append-only | full git: commits, branches, merges, time-travel |
| Conflict handling | none (append-only) | merge strategies per path |
| Provenance | none | `blame` per path; Merkle proofs |
| Branching | none | first-class (experiment branches, merges) |
| Daemons | watch process, milvus | none |

Memoir gives up pure-text semantic search in exchange for **structured, auditable, branchable** memory. If you care about *"what did I decide, when, and can I prove it?"*, that's the trade you want.

## Troubleshooting

- **`[memoir] CLI not found` in the status line** — `memoir` isn't on `PATH`. The plugin intentionally has no auto-install fallback (memoir isn't on PyPI yet, and silent installs would misconfigure users). Install it as shown above.
- **Status says `0 memories` but the store exists** — the `taxonomy:v1:*` internal namespaces are filtered from the user-facing count on purpose. If you just created the store, the count is accurate.
- **Store in the wrong place** — set `MEMOIR_STORE` to override the derived path. Useful if you want a single store across multiple projects, or want to keep the store inside the repo.
- **Don't want auto-capture** — set `MEMOIR_NO_CAPTURE=1`. Recall still works.
- **`claude` CLI not found in the Stop hook** — capture is skipped silently (no facts extracted). Install the Claude Code CLI if you want auto-capture; otherwise use the MCP `memoir_remember` tool or the CLI directly.

## Layout

```
plugins/claude-code/
├── .claude-plugin/plugin.json
├── README.md
├── hooks/
│   ├── hooks.json
│   ├── common.sh
│   ├── session-start.sh
│   ├── user-prompt-submit.sh
│   ├── stop.sh
│   ├── session-end.sh
│   └── parse-transcript.sh
├── skills/memory-recall/SKILL.md
├── commands/memoir-*.md          (9 commands)
└── scripts/derive-store-path.sh
```

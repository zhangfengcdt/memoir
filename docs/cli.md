# CLI Reference

The `memoir` command is the primary shell interface to a memory store. It exposes every retrieval and mutation pipeline the Python SDK supports, plus taxonomy-inspection primitives designed for agentic callers.

This page documents the search-adjacent commands — `recall`, `get`, and `summarize` — and the cloud sync commands in depth. For mutation (`remember`, `forget`), versioning (`branch`, `checkout`, `merge`, `time-travel`, `branch-match`), and crypto (`proof`, `verify`, `blame`) commands, use `memoir <command> --help` or see the API reference.

## Setup

Set `MEMOIR_STORE` once so you can skip `-s <path>` on every call. Most usage assumes this is exported:

```bash
export MEMOIR_STORE=/path/to/store
```

Add `--json` at the group level for machine-readable output (recommended when scripting or piping into `jq`). `MEMOIR_JSON=1` in the environment has the same effect globally.

### Environment variables

| Variable | Effect |
|---|---|
| `MEMOIR_STORE` | Default store path. Avoids `-s <path>` on every call. |
| `MEMOIR_JSON` | If `1`, all commands output JSON (same as passing `--json`). |
| `MEMOIR_QUIET` | If `1`, suppresses non-essential output. |
| `MEMOIR_BRANCH` | Default target branch for `remember`, `recall`, `get`, `forget`, and `search` — per-call routing without changing the store's checked-out branch. Each command also accepts an explicit `--branch <name>` flag which overrides this variable. See [Per-call branch routing](#per-call-branch-routing-multi-agent) below. |
| `MEMOIR_MERGE_POLICY` | Global conflict-resolution strategy for `remember` when a key already exists, overriding the per-type default but below an explicit `--merge-policy`. `=replace` restores the old overwrite-everywhere behaviour. See [Conflict resolution](#memoir-remember-conflict-resolution). |
| `MEMOIR_FACET_MAX_ENTRIES` | Cap on facet entries per key for append-style writes (oldest pruned). Default `50`; `0`/`none` disables capping. |
| `MEMOIR_RECALL_MERGE` | If `llm`, enables merge-on-read: a multi-entry key's content is LLM-consolidated at read time. Off by default (the deterministic projection is used). |
| `MEMOIR_API_KEY` | memoir-cloud API key; overrides the one saved by `memoir login`. Unlocks the cloud sync commands (`remote`, `push`, `pull`, `fetch`). Unset = COMMUNITY tier, no behaviour change. Never written to disk. See [Cloud Sync](cloud.md). |
| `MEMOIR_CLOUD_URL` | memoir-cloud gateway URL for `remote add` / `push --create` when `--url` is not passed. Default: the production gateway. |

### Global flags

Flags accepted before the subcommand, on the `memoir` group itself:

| Flag | Effect |
|---|---|
| `-s, --store <path>` | Override the store path (takes precedence over `MEMOIR_STORE`). |
| `--json` | Machine-readable output for every subcommand. |
| `-q, --quiet` | Suppress non-essential output. |
| `-v, --verbose` | Enable verbose logging. |

### Per-call branch routing (multi-agent)

`remember`, `recall`, `get`, `forget`, and `search` accept `--branch <name>` (env: `MEMOIR_BRANCH`). When set, the call operates against that branch and the store's checked-out branch is restored on exit — no `memoir checkout` round-trip, no race window on shared deployments.

**Set `MEMOIR_BRANCH` once at the runtime boundary** (LangGraph node, MCP client, agent shell). Each agent process injects its own identity once instead of threading a flag through every call site:

```bash
# In agent A's process
export MEMOIR_BRANCH=agents/reviewer
memoir remember "found N+1 query in /users migration"

# In agent B's process
export MEMOIR_BRANCH=agents/builder
memoir remember "shipped pagination on /users"
```

**Or pass `--branch` per call.** Explicit flag wins over the env var:

```bash
memoir remember "API contract change" --branch=agents/reviewer
memoir recall   "N+1"                 --branch=agents/reviewer
memoir get      lessons.builder.api   --branch=agents/builder
memoir forget   stale.note            --branch=agents/builder --force
```

**Reads are isolated.** Other branches and `main` don't see an agent's working memory until it's merged:

```bash
$ memoir get lessons.reviewer.sql --branch=agents/builder
✗ default:lessons.reviewer.sql (not found)

$ memoir get lessons.reviewer.sql --branch=typo-here
✗ Failed to get: Branch 'typo-here' does not exist.
  Create it explicitly with `memoir branch typo-here`, or use a write
  command (e.g. `memoir remember --branch=typo-here ...`) to bootstrap it.
```

That last error matters — read commands refuse to silently return empty on a misspelled branch, so typos surface immediately instead of looking like "no results".

**Auto-create on first write.** No separate `memoir branch <name>` is needed for a new agent:

```bash
memoir remember "first note" --branch=agents/new-bot   # branch is bootstrapped
memoir branch                                          # → main, agents/new-bot
```

**Cross-agent synthesis** stays explicit — promote findings to the shared trunk with `memoir merge`:

```bash
memoir merge agents/reviewer --into main
memoir recall "N+1"   # now visible on main
```

After every `--branch` call the store's checked-out branch is unchanged — routing is per-call, not a checkout.

**Concurrency note.** Routing is per-process. Don't run multiple in-process writers concurrently against the same store on different branches. Separate CLI invocations are fine — they rely on the same prollytree file locking as today.

## Search commands

The three pipelines described in [Search Theory](theory/search.md) are all reachable here. Pick the one that matches how narrow or open-ended your query is.

### `memoir recall` — semantic search (in-engine)

Primary search entry point. Accepts a natural-language query and returns ranked `IntelligentSearchResult` memories. Mode is selected per call via `--mode`.

```bash
# Single-stage (default) — one LLM call, 500-800ms typical
memoir recall "what's my testing setup?"

# Tiered drill-down — 2-3 LLM calls, narrower prompts, ~1-2s typical
memoir recall "what's my testing setup?" --mode tiered

# Scope to a namespace and cap the result count
memoir recall "meeting notes" -n calendar -l 5

# Drop results below a relevance threshold (0.0-1.0)
memoir recall "programming languages" --threshold 0.5

# Machine-readable — best shape for agents / scripts / benchmarks
memoir --json recall "testing setup" --mode tiered
```

The `--json` form exposes per-stage observability. For `--mode tiered` the `step_timings` block contains `l1_survey`, `l1_pick_llm`, `descend`, `key_pick_llm`, `memory_retrieval`, `total_search` (plus `l2_pick_llm` when an L1 exceeded the 40-key escalation threshold). Every result carries `metadata.mode` so a consumer never has to guess which pipeline produced it:

```bash
memoir --json recall "testing setup" --mode tiered \
  | jq '.memories[0].metadata | {mode, step_timings}'
```

```json
{
  "mode": "tiered",
  "step_timings": {
    "step1_path_discovery": 0.012,
    "l1_survey": 0.001,
    "l1_pick_llm": 0.412,
    "descend": 0.001,
    "key_pick_llm": 0.587,
    "memory_retrieval": 0.008,
    "total_search": 1.021
  }
}
```

A/B the two modes on the same store:

```bash
memoir --json recall "testing setup" --mode single  | jq '.timing_ms'
memoir --json recall "testing setup" --mode tiered  | jq '.timing_ms'
```

#### Picking the LLM

Both `recall` and `remember` accept a `--model` flag. Resolution order:

1. `--model <name>` flag (highest priority)
2. `MEMOIR_LLM_MODEL` env var
3. `claude-haiku-4-5` default

```bash
# Default — Anthropic Haiku, requires ANTHROPIC_API_KEY
memoir recall "what's my testing setup?"

# Per-call override
memoir recall "..."   --model gpt-4o-mini      # needs OPENAI_API_KEY
memoir remember "..." --model claude-sonnet-4-5

# Shell-wide override
export MEMOIR_LLM_MODEL=gpt-4o-mini
```

As of v0.1.7, `litellm` is a default dependency, so `pip install
memoir-ai` enables both LLM-backed and direct-path commands. (Prior
to v0.1.7 you had to add the `[litellm]` extra explicitly.)

### `memoir remember` — conflict resolution

When a write lands on a key that already exists, `remember` resolves the conflict with a **merge policy**. By default the policy is derived from the key's memory type; `--merge-policy` overrides it per call. See [Conflict & Merge theory](theory/conflict-merge.md) for the full model.

| Flag | Effect |
|---|---|
| `--merge-policy <strategy>` | Force a strategy for this write: `append`, `replace`, `confidence_gated`, `llm_merge`, `merge_on_read`, or `reject`. |
| `-i, --interactive` | On a conflict, show existing vs. incoming and prompt (`replace` / `append` / `merge` / `skip`) per key. Not valid with `--json`. |
| `--replace` | Back-compat alias for `--merge-policy replace`. |

Resolution order (first one set wins): `--merge-policy` flag → `MEMOIR_MERGE_POLICY` env → **per-type default**:

| Memory type | Example keys | Default strategy |
|---|---|---|
| Episodic | `experience.*`, `metrics.code.*` | `append` |
| Semantic | `knowledge.*`, `preferences.*`, `profile.*`, `context.project.*` | `confidence_gated` |
| Procedural | `workflow.*`, `behavior.*` | `llm_merge` |
| Working | `context.current.*`, `metrics.turn.*` | `replace` |

```bash
# No flag → the key's memory type decides.
memoir remember "use spaces" -p knowledge.coding.style     # semantic → confidence_gated
memoir remember "deployed v2 at 14:00" -p experience.releases.log  # episodic → append

# Override the type default for this call only.
memoir remember "use spaces" -p knowledge.coding.style --merge-policy append
memoir remember "draft note"  -p experience.releases.log --merge-policy replace

# Resolve interactively, or refuse to clobber and inspect the conflict (JSON).
memoir remember "new value" -p knowledge.coding.style --interactive
memoir --json remember "new value" -p knowledge.coding.style --merge-policy reject
```

!!! note
    `confidence_gated` only changes behaviour for sub-1.0 confidence (LLM classifications). Caller-supplied `-p` writes are confidence `1.0`, so on a semantic key they pass the gate and effectively replace — pass `--merge-policy append`/`llm_merge` to accumulate or consolidate instead.

### `memoir get` — direct lookup by taxonomy path

No LLM, no search. Pass one or more exact keys; missing keys come back as `found: false` so you can batch speculative candidates without branching. Latency is typically <10ms.

```bash
# Single lookup
memoir get preferences.coding.style

# Batched lookup in one call
memoir get preferences.coding.style profile.professional.skills

# Scope to a namespace, JSON output
memoir --json get preferences.coding.style -n default
```

This is the primitive an outer-LLM caller-driven flow uses once it has narrowed to exact keys. From the CLI it's also the fastest way to read a known memory.

### `memoir summarize` — taxonomy surveys

Pure-compute taxonomy inspection. The building blocks behind the caller-driven `[mode=drill]` / `[mode=flat]` / `[mode=get]` patterns are directly usable from the shell when you want to understand the layout of a store without invoking any LLM.

```bash
# Full store breakdown
memoir summarize

# Taxonomy-only view, scoped to one namespace
memoir summarize taxonomy -n default

# Keys matching a glob
memoir summarize --keys "preferences.*"

# Top-level prefix histogram (L1 survey)
memoir summarize --depth 1

# Glob + depth: L2 breakdown under preferences.*
memoir summarize --keys "preferences.*" --depth 2

# JSON for scripting
memoir --json summarize --depth 1 -n default
```

A shell-only drill-down — mirror of the skill's `[mode=drill]` — is just three calls:

```bash
memoir --json summarize --depth 1 -n default
# → pick L1 prefixes from prefix_counts

memoir --json summarize --keys "preferences.*" -n default
# → pick 3-7 exact keys from matching_keys

memoir --json get preferences.coding.style preferences.tools.editor
# → stored values, <10ms
```

### When to reach for which CLI command

- You want **semantic search** over a natural-language query → `memoir recall` (add `--mode tiered` if the single-stage picker is dropping signal on your store size).
- You already know the exact **taxonomy path** → `memoir get` — skip the classifier entirely.
- You want to **inspect the taxonomy layout** (what prefixes exist, how dense each branch is) → `memoir summarize --depth N` with or without `--keys <glob>`.
- You're scripting an **agent / LLM caller** and want to avoid a nested LLM call on memoir's side → compose `summarize` + `get` yourself; this is exactly what the `memory-recall` skill does.

## Cloud sync commands

`memoir remote`, `push`, `pull`, and `fetch` round-trip a local store with [memoir-cloud](https://github.com/zhangfengcdt/memoir-cloud), so the same memories follow your agent across machines. They need a login: without one every cloud command exits 1 asking you to run `memoir login`, and nothing else in memoir changes. The rules behind the commands (addresses, what syncs, fast-forward only, key handling) are in the [Cloud Sync](cloud.md) reference; this section is a hands-on guide.

From the root of a clone of your code repo, the whole setup is:

```bash
memoir login                 # once per machine: approve in the browser
memoir push --create         # New: create <handle>/<repo name> from this repo's memories
# or
memoir remote add <owner>/<store> && memoir pull   # Open: link an existing cloud store
```

Inside a code repo memoir uses that repo's store, the one Claude Code uses (`~/.memoir/<slug>`), so neither `MEMOIR_STORE` nor `-s` is needed; `memoir login` remembers the gateway, so `--url` isn't either. On a headless machine use `echo "$KEY" | memoir login --with-key`; `MEMOIR_API_KEY` still works and overrides the saved login. The walkthrough below uses explicit names and addresses so each step is visible.

Cloud stores are addressed GitHub-style as `<owner>/<store>`, where `owner` is your handle and `store` is the store name, for example `feng-zhang/demo`. That address is what you type, what memoir prints, and (prefixed with the gateway) the git remote `origin`.

| Command | What it does |
|---|---|
| `memoir login [--url <gateway>] [--with-key]` / `memoir logout` | Save a key for this machine after approving in the browser (or from stdin); remove it and revoke it on the cloud. |
| `memoir push --create [<store>]` | Create `<your handle>/<store>` in the cloud (default name: the code repo's), link it as `origin`, and push. The usual first step. |
| `memoir remote add [<owner>/<store>] [--url <gateway>] [--force]` | Link an existing cloud store. With no argument, proposes `<your handle>/<directory name>` and asks first. |
| `memoir remote show` / `memoir remote remove` | Show the address, gateway, branch and cloud summary; or unlink. |
| `memoir push [--branch <b>]` | Upload the chunks the cloud is missing, **then** `git push`. Default: current branch. |
| `memoir fetch` | Download new refs and chunks. Moves no local branch. |
| `memoir pull [--branch <b>] [--force]` | `fetch`, then fast-forward the branch. Creates it from the cloud if missing locally; a never-used local store adopts the cloud history. `--force` replaces the local branch with the cloud copy. |
| `memoir status` | Adds `origin: <owner>/<store>` when a cloud remote is configured. |

All of them accept `--json`.

### First push from your laptop

Start from an existing store, or create one:

```bash
memoir new ~/memories
export MEMOIR_STORE=~/memories
memoir remember "Always run make lint before opening a PR"
```

Create the cloud store, link it, and push in one step. The name is yours to pick; the owner is your handle:

```bash
memoir push --create memories
```

```text
✓ pushed main to feng-zhang/memories: 3 chunks (3 new) in 1.4 s, git in 2.6 s
```

Behind the scenes this validated the name locally, created the cloud store, set the git remote `origin` to `https://<gateway>/feng-zhang/memories`, uploaded the chunks the cloud lacked in multipart batches, and only then pushed the git history. The chunks are the ProllyTree node files that hold the actual memories. If a chunk upload fails, the git push is never attempted, so the cloud never points at data it does not have. Memoir also records which hashes the server confirmed under `.git/memoir-cloud/pushed-origin`, so a second push right away needs no round trip to find out that nothing is new:

```text
✓ pushed main to feng-zhang/memories: 3 chunks (0 new) in 0.0 s, git in 0.9 s
```

`memoir status` and `memoir remote show` both tell you the address:

```text
origin:   feng-zhang/memories
Gateway:  https://api-gateway-production-ab56.up.railway.app
Branch:   main
Created:  2026-10-03T14:02:11Z
```

If the name is taken you get `store name already exists; pick another or run memoir remote add feng-zhang/memories`. If the name is invalid (spaces, a leading dot, a `.git` suffix) memoir says so before contacting the server.

### Pick it up on your desktop

You never create the local store by hand. The Claude Code plugin creates one per project on session start, and any memoir command creates one on first use. So on the second machine, open the same project, export the same key, link the store that is already there, and pull:

```bash
export MEMOIR_API_KEY=mck_...
memoir remote add feng-zhang/memories
memoir pull
```

```text
✓ origin: feng-zhang/memories
✓ created main to 7d3f1a9 (3 new chunks)
```

Because the local store had never been used, `pull` adopted the cloud history outright. From here `status`, `recall`, and `get` see the laptop's memories:

```bash
memoir status
memoir recall "lint"
```

`remote add` resolves the address first. An unknown store, or one you do not own, fails with `store feng-zhang/typo not found (or you don't own it)` and nothing is written. After `pull`, memoir also checks that the chunk named by the store's root hash was downloaded.

If the local store already holds memories of its own, `pull` refuses rather than guess:

```text
✗ local and cloud histories have diverged; cloud merge is not available yet. To discard the local memories on this branch and adopt the cloud copy: memoir pull --force --branch main
```

Either push those memories to their own cloud store (`memoir remote remove`, then `memoir push --create <other-name>`), or adopt the cloud copy with `memoir pull --force`, which replaces the local branch and keeps the tip it had before under `refs/memoir/backup/<branch>` (recover with `git branch <name> refs/memoir/backup/<branch>`).

### Linking without typing the address

Run `memoir remote add` with no argument and it proposes `<your handle>/<current directory name>` and asks before resolving. In a project folder called `memories` that is `feng-zhang/memories`. A full `https://<gateway>/<owner>/<store>` URL is accepted in place of the address.

### The daily loop

Treat it like git. Pull before you start, push when you finish:

```bash
memoir pull          # bring down anything the other machine pushed
# ... work; the agent captures memories ...
memoir push
```

```text
✓ fast-forwarded main to 9c1e2f0 (2 new chunks)
```

`fetch` downloads refs and chunks without moving any local branch, for when you want to look before you merge:

```text
✓ fetched 1 remote refs, 2 new chunks from feng-zhang/memories
```

### When the cloud is ahead

You pushed from the desktop, forgot to pull on the laptop, and kept working there. Pushing from the laptop is refused with exit code 6:

```text
✗ remote has commits you don't have; run `memoir pull` first
```

User branches on the cloud are fast-forward only, so one machine can never overwrite another's history. If the laptop has no new commits of its own, `memoir pull` then `memoir push` resolves it.

If both machines committed since the last sync, the histories have diverged and `pull` is refused too:

```text
✗ local and cloud histories have diverged; cloud merge is not available yet
```

Cloud-side merge is planned but not available yet. Until then, pick a side. To keep the cloud version, force-pull. Look at what you are giving up first; afterwards the old tip is kept under `refs/memoir/backup/main` in case you need it:

```bash
memoir fetch                                  # cloud refs + chunks are now local
memoir diff main origin/main                  # see what differs before deciding
memoir pull --force                           # main := origin/main
memoir remember "..."                         # re-add anything that mattered
memoir push
```

```text
✓ replaced main (was 3f9c2b1, kept at refs/memoir/backup/main) with origin/main at 9c1e2f0 (2 new chunks)
```

To keep the local version instead, unlink with `memoir remote remove` and start a new cloud store with `memoir push --create <new-name>`.

### More than one branch

Every verb takes `--branch`. Push an experiment branch without touching `main`:

```bash
memoir branch experiments
memoir checkout experiments
memoir remember "Trying Ruff instead of flake8 on the side project"
memoir push --branch experiments
```

On the other machine, `pull --branch` creates the branch if it does not exist locally yet:

```bash
memoir pull --branch experiments
```

```text
✓ created experiments to 4b7d0a1 (1 new chunks)
```

Branches named `cloud/...` belong to the cloud. They carry proposals the cloud generates for you, appear after `fetch` as `origin/cloud/...`, and cannot be pushed:

```text
✗ 'cloud/dedupe/42' is a cloud-owned proposal branch and cannot be pushed
```

### Scripting and agents

Every command honours `--json` (or `MEMOIR_JSON=1`). A sync step in a hook or CI job can branch on the exit code and read the counts:

```bash
if out=$(memoir --json push); then
  echo "$out" | jq '{origin, branch, chunks_uploaded, chunks_present}'
else
  case $? in
    6) memoir pull && memoir push ;;   # cloud was ahead, retry once
    1) echo "auth or network problem: $out" >&2 ;;
  esac
fi
```

```json
{
  "success": true,
  "message": "pushed main to feng-zhang/memories: 4 chunks (1 new) in 1.1 s, git in 2.4 s",
  "branch": "main",
  "origin": "feng-zhang/memories",
  "chunks_uploaded": 1,
  "chunks_present": 3,
  "pushed": true,
  "seconds": 3.6,
  "chunk_seconds": 1.1,
  "git_seconds": 2.4
}
```

Every JSON result carries the address as `origin`. `fetch` adds `chunks_downloaded` and `remote_refs`; `pull` adds `branch`, `created`, `tip`, `chunks_downloaded`, `forced`, `previous_tip`, and `backup_ref`.

To use a different gateway, such as a staging deployment, pass `--url` to `remote add` or `push --create`, or set `MEMOIR_CLOUD_URL` once. After linking, the gateway lives on the `origin` URL, so the other verbs need neither.

### Unlinking

`memoir remote remove` drops the git remote and nothing else. Local memories, history, and the cloud store are untouched.

### Troubleshooting

| Message | Cause | What to do |
|---|---|---|
| `Cloud sync requires a login` | No saved login and no `MEMOIR_API_KEY`. | `memoir login` (or `export MEMOIR_API_KEY=...`) |
| `not signed in: run memoir login` | The gateway returned 401. | The key is wrong, expired or revoked: `memoir login` again. |
| `your account has no handle yet` | You have not chosen a handle. | Open `<gateway>/app` in a browser and pick one. |
| `store <owner>/<store> not found (or you don't own it)` | Unknown address, or a store belonging to someone else. | Check the address with `memoir remote show` on the machine that created it. |
| `"str_..." is a store id` | You pasted an internal id. | Use the `<owner>/<store>` address instead. |
| `store name already exists` | `--create` with a name you already use. | Pick another name, or `memoir remote add <handle>/<name>`. |
| `remote 'origin' already exists (...); pass --force to replace it` | The store is linked already. | Use `remote show`, or `remote add ... --force` to relink. |
| `remote has commits you don't have; run memoir pull first` (exit 6) | The cloud is ahead. | `memoir pull`, then push again. |
| `local and cloud histories have diverged` (exit 6) | Both sides have commits the other lacks: both machines captured since the last sync, or the local store grew memories before it was linked. | See "When the cloud is ahead" above, or adopt the cloud copy with `memoir pull --force`. |
| `root chunk ... is missing locally after sync` | A chunk download did not complete. | Run `memoir fetch` again. |
| `object store unavailable, retry later` | The cloud's object store answered 502 three times in a row. | Wait a little and run `memoir push` again; chunks already written are not re-sent. |
| `server rejected N chunk(s)` | The server refused some chunk parts (reason listed per chunk). | Nothing was pushed to git. Fix or report the listed chunks, then push again. |

Memoir never writes the key to disk and never prints the cloud's internal store ids. If either ever appears in output, that is a bug: please report it.

## Other command groups

The rest of the CLI surface is documented inline via `--help`. Command groups at a glance:

| Group | Commands | `--help` |
|---|---|---|
| Store | `new`, `connect`, `status`, `refresh` | `memoir new --help` |
| Memory | `remember`, `recall`, `get`, `forget` | `memoir remember --help` |
| Branch | `branch`, `checkout`, `merge`, `time-travel`, `diff`, `branch-match` | `memoir branch --help` |
| Crypto | `proof`, `verify`, `blame` | `memoir proof --help` |
| Analysis | `summarize` | `memoir summarize --help` |
| Cloud sync | `remote`, `push`, `pull`, `fetch` — stores addressed as `<owner>/<store>` (requires `MEMOIR_API_KEY`; see [Cloud Sync](cloud.md)) | `memoir push --help` |

For the underlying Python APIs these commands call into, see the [API Reference](api/memoir.md).

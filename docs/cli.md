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
| `MEMORY_API_KEY` | memoir-cloud API key. Unlocks the cloud sync commands (`remote`, `push`, `pull`, `fetch`, `clone`). Unset = COMMUNITY tier, no behaviour change. Never written to disk. See [Cloud Sync](cloud.md). |
| `MEMOIR_CLOUD_URL` | memoir-cloud gateway URL for `remote add` / `clone` when `--url` is not passed. Default: the production gateway. |

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

`memoir remote`, `push`, `pull`, `fetch`, and `clone` round-trip a local store with [memoir-cloud](https://github.com/zhangfengcdt/memoir-cloud), so the same memories follow your agent across machines. They are gated on `MEMORY_API_KEY`: without it every cloud command exits 1 with `Cloud sync requires MEMORY_API_KEY (PRO)` and nothing else in memoir changes. The rules behind the commands (what syncs, fast-forward only, key handling) are in the [Cloud Sync](cloud.md) reference; this section is a hands-on guide.

```bash
export MEMORY_API_KEY=mk_...     # created on the gateway's API-keys page
```

| Command | What it does |
|---|---|
| `memoir remote add <store_id> [--url <gateway>] [--force]` | Verify the key and the store, then add a git remote named `memoir-cloud`. |
| `memoir remote add --create [--name <name>]` | Create the cloud store first (name defaults to the store directory name), then link. |
| `memoir remote show` / `memoir remote remove` | Show gateway, store id, branch, and cloud summary; or unlink. |
| `memoir push [--branch <b>]` | Upload the chunks the cloud is missing, **then** `git push`. Default: current branch. |
| `memoir fetch` | Download new refs and chunks. Moves no local branch. |
| `memoir pull [--branch <b>]` | `fetch`, then fast-forward the branch (created from the cloud if missing locally). |
| `memoir clone <store_id> <path> [--url <gateway>]` | Clone a cloud store into a new, ready-to-use local store. |

All of them accept `--json`.

### First push from your laptop

Start from an existing store, or create one:

```bash
memoir new ~/memories
export MEMOIR_STORE=~/memories
memoir remember "Always run make lint before opening a PR"
```

Create a cloud store and link the local one to it in one step:

```bash
memoir remote add --create --name "memories"
```

```text
✓ linked to cloud store str_K3mQx9...Yw at https://api-gateway-production-ab56.up.railway.app
```

This verified the key, created the cloud store, and added an ordinary git remote named `memoir-cloud`. Check it any time with `memoir remote show`:

```text
Gateway:  https://api-gateway-production-ab56.up.railway.app
Store id: str_K3mQx9...Yw
Branch:   main
Name:     memories
Created:  2026-10-03T14:02:11Z
```

Now push:

```bash
memoir push
```

```text
✓ pushed main (3 new chunks, 0 already present)
```

The chunks are the ProllyTree node files that hold the actual memories. Memoir uploads the ones the cloud lacks first and only then pushes the git history. If a chunk upload fails, the git push is never attempted, so the cloud never points at data it does not have. A second push right away moves nothing:

```text
✓ pushed main (0 new chunks, 3 already present)
```

Keep the store id from `remote show`. You need it on the other machine.

### Pick it up on your desktop

Export the same key and clone into a fresh directory:

```bash
export MEMORY_API_KEY=mk_...
memoir clone str_K3mQx9...Yw ~/memories
```

```text
✓ cloned str_K3mQx9...Yw into /Users/you/memories (3 chunks)
→ To use this store: export MEMOIR_STORE=/Users/you/memories
```

The clone is a complete memoir store with the remote already named `memoir-cloud`, so no `remote add` is needed:

```bash
export MEMOIR_STORE=~/memories
memoir status
memoir recall "lint"
```

`clone` also checks that the chunk named by the store's root hash was downloaded, and errors instead of leaving a store that opens on missing data.

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
✓ fetched 1 remote refs, 2 new chunks
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

Cloud-side merge is planned but not available yet. Until then, pick a side. To keep the cloud version and reapply your local memories on top, use git inside the store (a memoir store is an ordinary git repo):

```bash
memoir fetch                                  # cloud refs + chunks are now local
git -C "$MEMOIR_STORE" branch local-work      # keep a copy of your local history
git -C "$MEMOIR_STORE" reset --hard memoir-cloud/main   # move main to the cloud tip
memoir diff local-work main                   # see what to carry over
memoir remember "..."                         # re-add what matters
memoir push
```

To keep the local version instead, start a new cloud store with `memoir remote add --create --force` and push to that.

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

Branches named `cloud/...` belong to the cloud. They carry proposals the cloud generates for you, appear after `fetch` as `memoir-cloud/cloud/...`, and cannot be pushed:

```text
✗ 'cloud/dedupe/42' is a cloud-owned proposal branch and cannot be pushed
```

### Scripting and agents

Every command honours `--json` (or `MEMOIR_JSON=1`). A sync step in a hook or CI job can branch on the exit code and read the counts:

```bash
if out=$(memoir --json push); then
  echo "$out" | jq '{branch, chunks_uploaded, chunks_present}'
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
  "message": "pushed main (1 new chunks, 3 already present)",
  "branch": "main",
  "chunks_uploaded": 1,
  "chunks_present": 3,
  "pushed": true
}
```

`fetch` reports `chunks_downloaded` and `remote_refs`; `pull` reports `branch`, `created`, and `tip`; `clone` reports `path`, `store_id`, `branch`, and `chunks_downloaded`.

To use a different gateway, such as a staging deployment, pass `--url` to `remote add` or `clone`, or set `MEMOIR_CLOUD_URL` once. After `remote add` the URL lives on the git remote, so the other verbs need neither.

### Unlinking

`memoir remote remove` drops the git remote and nothing else. Local memories, history, and the cloud store are untouched.

### Troubleshooting

| Message | Cause | What to do |
|---|---|---|
| `Cloud sync requires MEMORY_API_KEY (PRO)` | The variable is unset in this shell. | `export MEMORY_API_KEY=...` |
| `MEMORY_API_KEY is missing or invalid` | The gateway returned 401. | Check for a typo or an expired key. |
| `GET /stores/str_... → 404` | Unknown store id, or a store owned by another account. | Copy the id from `memoir remote show` on the machine that created it. |
| `remote 'memoir-cloud' already exists; pass --force to replace it` | The store is linked already. | Use `remote show`, or `remote add ... --force` to relink. |
| `remote has commits you don't have; run memoir pull first` (exit 6) | The cloud is ahead. | `memoir pull`, then push again. |
| `local and cloud histories have diverged` (exit 6) | Both sides committed since the last sync. | See "When the cloud is ahead" above. |
| `root chunk ... is missing locally after sync` | A chunk download did not complete. | Run `memoir fetch` again. |

Memoir never writes the key to disk. If it ever appears in output, that is a bug: please report it.

## Other command groups

The rest of the CLI surface is documented inline via `--help`. Command groups at a glance:

| Group | Commands | `--help` |
|---|---|---|
| Store | `new`, `connect`, `status`, `refresh` | `memoir new --help` |
| Memory | `remember`, `recall`, `get`, `forget` | `memoir remember --help` |
| Branch | `branch`, `checkout`, `merge`, `time-travel`, `diff`, `branch-match` | `memoir branch --help` |
| Crypto | `proof`, `verify`, `blame` | `memoir proof --help` |
| Analysis | `summarize` | `memoir summarize --help` |
| Cloud sync | `remote`, `push`, `pull`, `fetch`, `clone` (requires `MEMORY_API_KEY`; see [Cloud Sync](cloud.md)) | `memoir push --help` |

For the underlying Python APIs these commands call into, see the [API Reference](api/memoir.md).

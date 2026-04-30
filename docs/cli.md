# CLI Reference

The `memoir` command is the primary shell interface to a memory store. It exposes every retrieval and mutation pipeline the Python SDK supports, plus taxonomy-inspection primitives designed for agentic callers.

This page documents the search-adjacent commands — `recall`, `get`, and `summarize` — in depth. For mutation (`remember`, `forget`), versioning (`branch`, `checkout`, `merge`, `time-travel`), and crypto (`proof`, `verify`, `blame`) commands, use `memoir <command> --help` or see the API reference.

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

### Global flags

Flags accepted before the subcommand, on the `memoir` group itself:

| Flag | Effect |
|---|---|
| `-s, --store <path>` | Override the store path (takes precedence over `MEMOIR_STORE`). |
| `--json` | Machine-readable output for every subcommand. |
| `-q, --quiet` | Suppress non-essential output. |
| `-v, --verbose` | Enable verbose logging. |

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

The `[litellm]` extra is required for any LLM-backed command:
`pip install 'memoir-ai[litellm]'`. Without it, `recall` and
auto-classifying `remember` (no `-p`) raise `ImportError` at runtime.
Direct-path operations (`remember -p <path>`, `get`, `forget`,
`branch`, `checkout`, …) work either way.

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

## Other command groups

The rest of the CLI surface is documented inline via `--help`. Command groups at a glance:

| Group | Commands | `--help` |
|---|---|---|
| Store | `new`, `connect`, `status`, `refresh` | `memoir new --help` |
| Memory | `remember`, `recall`, `get`, `forget` | `memoir remember --help` |
| Branch | `branch`, `checkout`, `merge`, `time-travel`, `diff` | `memoir branch --help` |
| Crypto | `proof`, `verify`, `blame` | `memoir proof --help` |
| Analysis | `summarize` | `memoir summarize --help` |

For the underlying Python APIs these commands call into, see the [API Reference](api/memoir.md).

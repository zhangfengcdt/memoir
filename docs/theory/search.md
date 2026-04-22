# Memoir Search Theory & Architecture

## Executive Summary

Memoir exposes three retrieval pipelines that share the same taxonomy-structured store:

- **`IntelligentSearchEngine` — `mode="single"`** (in-engine, one LLM call): the engine presents the full path inventory with content samples to an LLM and asks it to pick the relevant paths in one shot. Lowest latency when the store is small/medium; signal-to-noise degrades as the inventory grows. Total latency ~500–800ms.

- **`IntelligentSearchEngine` — `mode="tiered"`** (in-engine, staged LLM calls): the engine runs the same drill-down shape the caller-driven skill uses, but with *its own* LLM. L1 histogram (no LLM) → L1 pick → optional L2 pick when a branch is wide → key pick → batched fetch. Narrower prompts at each stage, better scaling with store size, at the cost of 2–3 LLM calls instead of 1. Typical total latency ~1–2s.

- **Caller-driven tiered retrieval** (out-of-engine, LLM-free): the CLI primitives `summarize --depth N` and `get` let an *outer* LLM (the Claude Code `memory-recall` skill is the canonical example) drive its own drill-down — **no LLM call inside memoir**. Latency is tens to hundreds of ms because no model inference happens on the retrieval side; the outer agent also contributes conversational context to the picker, which an in-engine pass cannot.

All three paths exploit pre-classified semantic paths for O(log n)-shaped lookups instead of O(n) similarity search. Where the path picker sits — inside the engine (single or tiered), or outside in the calling agent — is a factoring choice, not an algorithmic one. The single-stage and tiered in-engine modes are selected per call via the `mode` argument on `IntelligentSearchEngine.search()` (also exposed as `--mode {single,tiered}` on `memoir recall` and `?mode=…` on the UI `/api/recall` endpoint).

## Core Problem Statement

Traditional AI memory systems suffer from fundamental search inefficiencies:

- **O(n) Complexity**: Vector similarity search across entire corpus
- **High Latency**: 150-750ms for embeddings + similarity computation
- **Opaque Ranking**: Black-box similarity scores without interpretability
- **No Hierarchical Leverage**: Flat search space ignoring semantic relationships

Memoir solves this through **hierarchical semantic search** where:

- Memories are pre-organized into semantic paths (via classification)
- Search can leverage the hierarchical structure for O(log n) operations
- Path-based filtering dramatically reduces search space

## Search Philosophy

### Key Innovation
```
Traditional:                    query → embedding → O(n) similarity search → ranked results
Memoir (in-engine, single):     query → LLM path selection → O(log n) retrieval → filtered results
Memoir (in-engine, tiered):     query → LLM picks L1 → [LLM picks L2] → LLM picks keys → O(log n) retrieval
Memoir (caller-driven):         query → caller-LLM picks prefix → summarize --depth N → get
```

All three memoir pipelines exploit pre-classified semantic structure to:

- **Reduce Search Space**: Focus only on relevant taxonomy branches
- **Improve Interpretability**: Clear path-based result organization
- **Enable Prefix Queries**: Efficient hierarchical exploration
- **Leverage LLM Understanding**: True semantic query comprehension

The caller-driven mode additionally avoids a second LLM inside memoir when the caller is itself an LLM — the outer model already has the query plus session context and is a strictly better picker than a fresh in-engine pass.

## Architecture Overview

### IntelligentSearchEngine — Single-Stage Mode (`mode="single"`)

This is the default `IntelligentSearchEngine.search()` pipeline. One LLM call picks 1–3 paths from the full path inventory and the engine returns the memories at those paths.

#### Design Goals
- **Semantic Understanding**: LLM comprehends query intent
- **Path-Aware Selection**: Leverages hierarchical structure
- **Context-Rich Results**: Provides memory samples for decisions
- **Flexible Relevance**: LLM-based path selection

#### Algorithm Deep Dive

##### Stage 1: Path Discovery (10-50ms)
```python
# Get all memories to extract unique paths
all_memories = store.search(namespace_tuple, limit=1000)

# Build path information with samples
paths_info = {}
for _, path, data in all_memories:
    if path not in paths_info:
        paths_info[path] = {
            "type": "aggregated" or "single",
            "count": memory_count,
            "sample": content[:100]  # Preview
        }
```

**Path Information Structure**:
- **Type**: Aggregated vs single memory
- **Count**: Number of memories at path
- **Sample**: First 100 chars for context

This provides the LLM with:

- Complete path inventory
- Memory density information
- Content previews for informed selection

##### Stage 2: LLM Path Selection (200-500ms)
```python
prompt = f"""Given this search query: "{query}"

Please select the most relevant memory paths from:

- profile.personal.identity (5 memories): John Smith, age 28...
- preferences.technology.programming (3 memories): Loves Python...
- context.conversation.history (10 memories): Discussed AI...

Instructions:

- Select 1-3 paths most relevant to query
- Return ONLY path names, one per line
- If no paths relevant, return "NONE"
"""
```

**Prompt Engineering Details**:
- **Query Prominence**: Query shown first for focus
- **Path Context**: Each path shown with count and sample
- **Limited Selection**: 1-3 paths to prevent over-retrieval
- **Clear Format**: Line-separated paths for parsing
- **Null Case**: Explicit "NONE" for no matches

##### Stage 3: Memory Retrieval (5-20ms)
```python
for path in selected_paths[:limit]:
    path_memories = _get_memories_from_path(namespace, path, all_memories)
    results.extend(path_memories)

    if len(results) >= limit:
        break
```

**Retrieval Strategy**:
- **Path-Limited**: Only retrieve from selected paths
- **Early Termination**: Stop when limit reached
- **Memory Expansion**: Unpack aggregated memories
- **Metadata Enrichment**: Add path and source info

##### Fallback Handling
```python
except Exception as e:
    # Fallback: return first few paths
    return list(paths_info.keys())[:3]
```

**Robustness Features**:
- **LLM Failure Fallback**: Use first 3 paths
- **Parse Error Recovery**: Handle malformed LLM output
- **Empty Result Handling**: Return empty list gracefully

#### Performance Characteristics
- **Path Discovery**: 10-50ms
- **LLM Path Selection**: 200-500ms (single LLM call; prompt caching on cached sections)
- **Memory Retrieval**: 5-20ms
- **Total Latency**: 215-570ms typical (500-800ms measured end-to-end)
- **Memory Usage**: O(all_paths + selected_memories)
- **LLM Token Usage**: ~500-1500 tokens per search

#### Strengths & Limitations

**Strengths**:
- True semantic understanding
- Handles complex, abstract queries
- Leverages memory organization
- Provides reasoning transparency
- Single LLM call keeps latency bounded

**Limitations**:
- Higher latency (LLM dependency)
- Costs associated with LLM usage
- Non-deterministic results
- Requires online LLM access
- Picker sees only the query string — not the caller's conversational context

### IntelligentSearchEngine — Tiered Mode (`mode="tiered"`)

Opt in with `search(..., mode="tiered")`. Same engine, same store APIs, same result shape — but the selection work is split into narrower stages so each prompt stays small as the store grows. The pattern mirrors the caller-driven `[mode=drill]` flow (see below), only with the engine's own LLM driving instead of an outer agent.

#### When to use it over `mode="single"`

- **Large stores.** Single-stage sends every path (with content samples) in one prompt — token cost grows linearly with store size, and relevance signal thins out. Tiered mode's L1 histogram stays constant (typically 5–15 entries) and the key-pick stage only sees paths under picked L1s.
- **Signal-to-noise matters more than latency.** Tiered spends 2–3 LLM calls in sequence (~1–2s end-to-end). If the single-stage picker is good enough and latency is the bottleneck, stay on `mode="single"`.
- **You want to A/B the two against a real workload.** Because `mode` is a per-call argument (not a config knob), benchmarks and the UI can toggle without restart.

The picker in tiered mode still does not see the caller's conversational context (that's a property only the skill-side caller-driven flow has — see next section).

#### Algorithm Deep Dive

1. **L1 survey (pure compute, no LLM)** — after the shared path-discovery step loads all memories once, the engine runs `_group_by_depth(paths, 1)` over the stored keys and gets a histogram `{prefix: count}` of top-level taxonomy segments.
2. **L1 pick (LLM #1)** — the engine sends a small prompt with the query and the histogram, asking for 2–4 plausible L1 prefixes. Malformed / empty output falls back to top-N by count so the search never dies silently.
3. **Descent (pure compute)** — for each picked L1, `_filter_keys(paths, f"{L1}.*")` narrows to concrete keys. If any single L1 exceeds `L2_ESCALATION_THRESHOLD` (40 keys), that branch is marked for L2 escalation.
4. **L2 pick (optional, LLM #1.5)** — for each oversized L1, the engine groups that branch's keys by depth-2 and asks the LLM to pick 2–3 L2 sub-prefixes. Same fallback-to-top-N safety net.
5. **Key pick (LLM #2)** — the descended key set plus content samples goes into the reused `_select_relevant_paths` prompt (the same static taxonomy-aware prompt the single-stage path uses). LLM returns 3–7 exact keys.
6. **Memory retrieval (pure compute)** — picked keys are fetched from the already-loaded `memory_dict` via `_extract_memories_from_data`, same shape as single-stage.

```
query: "what's my testing setup?"

1. L1 histogram  → { preferences: 28, context: 25, workflow: 24, routine: 8, ... }
2. LLM #1        → [preferences, workflow, routine]
3. Descent       → 15 keys under preferences.*, 12 under workflow.*, 6 under routine.*
4. (no L2)       → all three L1s under the 40-key threshold
5. LLM #2        → [preferences.coding.testing, workflow.coding.testing,
                     routine.coding.testing]
6. Fetch         → 3 IntelligentSearchResult objects with step_timings + llm_prompts
```

#### Prompt stages

- **L1 pick prompt.** Query + a one-line-per-prefix histogram. Explicitly instructed to return prefix names only, one per line, or `NONE`.
- **L2 pick prompt.** Only emitted when at least one L1 triggered escalation; scoped to that branch. When multiple branches escalate in the same call, all sub-prompts are concatenated under the `l2_pick` capture key so `return_prompts=True` shows the full chain.
- **Key pick prompt.** Delegates to the existing `_select_relevant_paths` with the descended subset — this reuses the static `[STATIC_SECTION_START]` / `[STATIC_SECTION_END]` taxonomy prelude, so prompt caching still applies to this stage exactly as it does for single-stage.

#### Observability

Results from `mode="tiered"` carry the same metadata shape as single-stage but with tiered-specific keys. Callers that only care about "give me memories" see no difference; callers that inspect `metadata["step_timings"]` or `metadata["llm_prompts"]` (the benchmark, the UI's `return_prompts=1` panel, tests) see the staged breakdown.

| `step_timings` key | Present? | Meaning |
|---|---|---|
| `step1_path_discovery` | always | Shared path-discovery step (same as single-stage). |
| `l1_survey` | tiered only | Pure-compute L1 histogram. Typically <10ms. |
| `l1_pick_llm` | tiered only | LLM #1 latency. |
| `descend` | tiered only | Pure-compute filtering into concrete keys. |
| `l2_pick_llm` | tiered only *(conditional)* | Present only when at least one L1 triggered escalation. |
| `key_pick_llm` | tiered only | LLM #2 latency. |
| `memory_retrieval` | tiered only | Final fetch + shape conversion. |
| `total_search` | always | End-to-end wall time. |

`llm_prompts` keys in tiered mode are `l1_pick`, `l2_pick` (when present), and `key_pick`. `metadata["mode"]` is stamped to `"tiered"` (or `"single"` on the default path) so downstream consumers never need to guess which pipeline produced a result.

#### Fallbacks & robustness

- LLM returns `NONE` or garbage at L1 → top-N-by-count fallback on the histogram.
- LLM returns `NONE` or garbage at L2 → top-N-by-count fallback on that branch's L2 histogram.
- Descended key set is empty after all picks → return a single timing-only dummy result (mirrors single-stage's dummy-on-no-match convention) so callers can still observe timings.
- Unknown `mode` value → `ValueError` at the top of `search()`; fails loud rather than silently falling back.

#### Performance Characteristics

| Stage | Typical latency |
|---|---|
| L1 survey + descend | <20ms (pure compute) |
| L1 pick LLM | ~300–500ms |
| L2 pick LLM *(when escalated)* | ~300–500ms |
| Key pick LLM | ~400–600ms |
| Memory retrieval | ~5–20ms |
| **End-to-end** | **~1–2s** (vs. ~0.5–0.8s for single-stage) |

LLM token usage scales better than single-stage once the store is large: L1 pick costs are effectively O(1) in corpus size (histograms are small), and the key-pick stage only sees the descended subset rather than the whole inventory.

#### Mode selection API

Mode is a per-call argument, not a configuration toggle:

- **Engine:** `engine.search(query, namespace, mode="tiered")`
- **Service:** `service.recall(query, mode="tiered")` / `recall_sync(..., mode="tiered")`
- **CLI:** `memoir recall "query" --mode tiered` (default `single`)
- **UI:** `GET /api/recall?path=...&query=...&mode=tiered` (whitelisted to `single` / `tiered`)

Per-call selection was chosen over a global config so benchmarks, tests, and end-users can A/B the two pipelines on the same store without environment juggling.

### Caller-Driven Tiered Retrieval

When the caller is itself an LLM (e.g. the Claude Code `memory-recall` skill, agentic tool-use clients), running a second LLM inside memoir to pick paths is wasteful — the outer model already reads the query plus full session context and can pick better than a context-free in-engine pass. The caller-driven pipeline exposes raw primitives and lets the outer LLM drive the drill-down.

#### Primitives

Three LLM-free CLI commands compose into every retrieval shape:

- **`memoir summarize --depth N [--keys <pattern>]`** — groups taxonomy keys by the first `N` dot-separated segments and emits a `prefix_counts` histogram. `N=1` gives the L1 layout (typically 5–15 prefixes); deeper `N` drills further. Composable with `--keys <pattern>` for scoped surveys (`--keys "preferences.*" --depth 2` gives the L2 breakdown under `preferences`).
  - *Implementation*: `src/memoir/cli/commands/analysis.py` — `_filter_keys` (fnmatch) + `_group_by_depth`.
  - *Cost*: pure taxonomy scan, no LLM. ~100ms on a mid-sized store.

- **`memoir get <key> [<key>...] [-n <namespace>]`** — batched exact-path lookup. Missing keys return `found: false` rather than erroring, so the caller can include speculative candidates without branching logic.
  - *Implementation*: `src/memoir/cli/commands/memory.py` + `src/memoir/services/memory_service.py`.
  - *Cost*: <10ms for a batched lookup (merkle-tree point queries).

- **`memoir blame <path> -l N`** / **`memoir diff <a> <b>`** — escalations for history / cross-commit questions. Not on the hot path.

#### The four modes

Every response from the caller-driven path prefixes a **mode marker** so the cost/correctness trade-off is visible in the transcript:

| Mode | Trigger | Flow | Typical cost |
|---|---|---|---|
| `[mode=get]` | Query already names a path | direct `get` | <10ms |
| `[mode=flat]` | A single glob covers the scope (e.g. `*.testing.*`, `*pytest*`) | `summarize --keys <pattern>` → pick → `get` | ~100ms |
| `[mode=drill]` | Open-ended query (the default) | `summarize --depth 1` → pick 2–4 L1 prefixes → `summarize --keys "<L1>.*"` → (optional depth-2 escalation when an L1 has > 40 keys) → `get` | ~200–300ms |
| `[mode=blame]` / `[mode=diff]` | Provenance or cross-commit/branch question | run `drill` first to identify keys, then `blame -l N` or `diff <a> <b>` | +100ms on top of drill |

Markers combine when paths chain (`[mode=drill+blame]`). The legacy LLM-bundled path is tagged `[mode=recall-legacy]` and is explicitly discouraged for agent callers.

#### Drill-down walkthrough

```
query: "what's my testing setup?"

1. summarize --depth 1 -n default
   → prefix_counts: { preferences: 28, context: 25, workflow: 24, routine: 8, ... }

2. Caller-LLM picks: [preferences, workflow, routine]
   (all plausibly host testing-related facts)

3. For each pick, summarize --keys "<prefix>.*":
   - preferences.coding.testing, preferences.tools.testing, preferences.work.testing
   - workflow.coding.testing, workflow.automation.testing
   - routine.coding.testing

4. Caller-LLM picks 3–7 exact keys. Batched get:
   memoir get preferences.coding.testing preferences.tools.testing \
               workflow.coding.testing routine.coding.testing
   → 4 items, each with value.content populated.

5. Response: "[mode=drill]\n\n- You use pytest over unittest ..."
```

No LLM call on memoir's side anywhere in this flow. Total wall-time is dominated by CLI startup + the three `summarize` invocations.

#### Why the outer LLM is the better picker

- It sees the full query plus conversational context; the in-engine picker sees only the query string.
- It can make ambiguity-aware calls (fetch from 2–4 plausible prefixes, discard irrelevant results downstream) without a second round trip.
- It avoids the latency + token cost of a nested LLM invocation.
- The contract is minimal — three CLI commands, stable JSON shape — so any agent framework can consume it.

#### Performance Characteristics

| Pipeline | LLM calls in memoir | Typical wall time | Network dependence |
|---|---|---|---|
| `IntelligentSearchEngine` — `mode="single"` | 1 (path selection) | 500–800ms | Requires online LLM |
| `IntelligentSearchEngine` — `mode="tiered"` (no L2 escalation) | 2 (L1 pick + key pick) | ~1–1.5s | Requires online LLM |
| `IntelligentSearchEngine` — `mode="tiered"` (with L2 escalation) | 3 (L1 + L2 + key pick) | ~1.5–2s | Requires online LLM |
| `[mode=get]` (caller-driven) | 0 | <10ms | Local only |
| `[mode=flat]` (caller-driven) | 0 | ~100ms | Local only |
| `[mode=drill]` (caller-driven) | 0 | ~200–300ms | Local only |
| `[mode=blame]` / `[mode=diff]` (caller-driven) | 0 | +100ms | Local only |

The caller-driven modes consume zero memoir-side tokens. Tokens spent by the outer LLM to do the picking are amortized against conversational context it already has loaded — effectively free at the margin.

#### When to use which entry point

- **SDK / non-LLM caller with a small/medium store** → `IntelligentSearchEngine` with `mode="single"` — one LLM call, lowest latency.
- **SDK / non-LLM caller with a large store or noisy single-stage results** → `IntelligentSearchEngine` with `mode="tiered"` — more LLM calls, narrower prompts per stage, better scaling with store size.
- **Agent caller with its own LLM (Claude Code, agentic clients)** → caller-driven drill-down — skip nested LLM calls entirely and let the outer agent's context contribute to the picker.
- **Narrow lookup (known path, obvious pattern)** → `[mode=get]` or `[mode=flat]`; the outer LLM decides.
- **Open-ended or ambiguous query from an agent** → `[mode=drill]`; escalate to `blame` / `diff` only for explicit provenance questions.

#### Design references

- `plugins/claude-code/skills/memory-recall/SKILL.md` — canonical caller contract, decision rules, and mode-marker convention.
- `plugins/claude-code/commands/memoir-get.md` — slash-command surface for `get`.
- `plugins/claude-code/hooks/user-prompt-submit.sh` — SessionStart nudge that steers the outer LLM toward recall on non-trivial prompts.

## Search CLI Reference

The three pipelines described above are all reachable from the `memoir` CLI. Set `MEMOIR_STORE` once (recommended for agents and repeat usage) so you can skip `-s <path>` on every command:

```bash
export MEMOIR_STORE=/path/to/store
```

Add `--json` at the group level for machine-readable output (always recommended when scripting). `MEMOIR_JSON=1` as an env var has the same effect.

### `memoir recall` — in-engine search (single or tiered)

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

This is the primitive the outer-LLM caller-driven flow uses once it has narrowed to exact keys (see the skill-side walkthrough above). From the CLI it's also the fastest way to read a known memory.

### `memoir summarize` — taxonomy surveys (the caller-driven primitives)

Pure-compute taxonomy inspection. The building blocks behind `[mode=drill]` / `[mode=flat]` / `[mode=get]` are directly usable from the shell when you want to understand the layout of a store without invoking any LLM.

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

### Environment variables

| Variable | Effect |
|---|---|
| `MEMOIR_STORE` | Default store path. Avoids `-s <path>` on every call. |
| `MEMOIR_JSON` | If `1`, all commands output JSON (same as passing `--json`). |
| `MEMOIR_QUIET` | If `1`, suppresses non-essential output. |

### When to reach for which CLI command

- You want **semantic search** over a natural-language query → `memoir recall` (add `--mode tiered` if the single-stage picker is dropping signal on your store size).
- You already know the exact **taxonomy path** → `memoir get` — skip the classifier entirely.
- You want to **inspect the taxonomy layout** (what prefixes exist, how dense each branch is) → `memoir summarize --depth N` with or without `--keys <glob>`.
- You're scripting an **agent / LLM caller** and want to avoid a nested LLM call on memoir's side → compose `summarize` + `get` yourself; this is exactly what the `memory-recall` skill does.

## Advanced Search Patterns

### 1. Hierarchical Prefix Search
Exploit path structure for exploration:
```python
# Search all memories under a path prefix
prefix = "profile.professional"
memories = store.search_prefix(namespace, prefix)
```

### 2. Multi-Namespace Search
Search across multiple user namespaces:
```python
namespaces = ["user:alice", "user:bob", "shared:team"]
results = []
for ns in namespaces:
    results.extend(engine.search(query, ns, limit=3))
```

### 3. Temporal Search
Combine with version control for time-based queries:
```python
# Search at specific commit/timestamp
historical_results = engine.search(
    query, namespace,
    at_commit="abc123"  # Git-like time travel
)
```

### 4. Person-Filtered Search
Filter results by person context:
```python
# Search only memories related to a specific person
results = await engine.search(
    query="favorite food",
    namespace="user123",
    person_filter="john"
)
```

## Performance Optimization Strategies

### 1. Search Result Caching
```python
# Cache search results by query + namespace
cache_key = hash(query + namespace)
if cache_key in search_cache:
    return search_cache[cache_key]
```

### 2. Path Index Precomputation
```python
# Precompute path -> memory count mapping
path_index = {}
for _, path, data in all_memories:
    path_index[path] = path_index.get(path, 0) + 1
```

### 3. Parallel Path Retrieval
```python
# Retrieve from multiple paths concurrently
async def parallel_retrieval(paths):
    tasks = [retrieve_path(p) for p in paths]
    return await asyncio.gather(*tasks)
```

### 4. Progressive Result Loading
```python
# Return results as they're found
async def streaming_search():
    for path in selected_paths:
        memories = await get_memories(path)
        yield memories  # Stream results
```

## Implementation Details

### Memory Format Handling

The engine handles two memory formats:

**Aggregated Memory Format**:
```json
{
  "memories": [
    {"content": "...", "confidence": 0.9, "metadata": {}},
    {"content": "...", "confidence": 0.8, "metadata": {}}
  ],
  "count": 2,
  "last_updated": "2024-01-01"
}
```

**Single Memory Format**:
```json
{
  "content": "Memory content here",
  "confidence": 0.95,
  "metadata": {"source": "conversation"}
}
```

### Search Result Structure

Results use a standardized structure:
```python
@dataclass
class IntelligentSearchResult:
    path: str              # Semantic path
    content: str           # Memory content
    metadata: dict         # Additional metadata
    relevance_score: float # 0.0 to 1.0
    namespace: str         # User namespace
```

### Namespace Handling

Flexible namespace format support:
```python
# String format
namespace = "user:alice"

# Tuple format
namespace = ("user", "alice")

# Conversion
namespace_tuple = tuple(namespace.split(":"))
```

## Future Enhancements

### Planned Improvements

1. **Embedding-Enhanced Search**:
   - Combine path selection with embedding similarity
   - Use embeddings for query expansion
   - Cache embeddings for frequent queries

2. **Learning from Feedback**:
   - Track click-through rates on results
   - Adjust path selection based on usage
   - Personalized relevance models

3. **Query Understanding Pipeline**:
   - Intent classification (lookup vs exploration)
   - Entity extraction from queries
   - Query rewriting and expansion

4. **Advanced Ranking**:
   - Temporal decay for recency
   - Personalized ranking models
   - Confidence-weighted scoring

5. **Federated Search**:
   - Search across multiple memory stores
   - Cross-user memory search (with permissions)
   - Integration with external knowledge bases

6. **Search Analytics**:
   - Query performance metrics
   - Popular search patterns
   - Failed query analysis

## Theoretical Foundation

### Information Retrieval Theory

The search engine implements concepts from:

1. **Probabilistic Retrieval**:
   - LLM estimates P(relevant|path, query)
   - Bayesian inference through language understanding

2. **Hierarchical Search**:
   - Logarithmic complexity through path structure
   - Semantic clustering of related memories

### Hierarchical Search Advantages

The semantic path structure supports O(log n)-shaped lookups via two concrete mechanisms exposed as CLI primitives:

1. **Prefix-indexed summarization** — `summarize --depth N [--keys <pattern>]` groups keys by the first `N` segments in O(k) where `k` is the number of matching keys (always ≤ the full corpus). An L1 histogram is typically 5–15 entries, constant-sized from the caller's perspective regardless of how many memories exist. A depth-2 survey scoped to one L1 prefix is similarly bounded.

2. **Exact-key batched `get`** — once the caller has picked keys, retrieval is O(1) per key in the underlying ProllyTree (merkle-tree point query). Batching amortizes CLI startup across 3–7 fetches.

The "log n" label is a *shape* claim rather than a strict complexity bound — typical queries touch one depth-1 histogram + one depth-2 survey + a handful of `get`s, which is bounded independently of corpus size for well-distributed taxonomies. The formal complexity depends on branching factor at each level; in practice, depth-3 is the ceiling because the taxonomy itself is capped at 3 levels.

Additional benefits that fall out of the same structure:

- **Semantic Clustering**: Related memories are naturally grouped at a common prefix.
- **Progressive Refinement**: The caller drills only the prefixes that plausibly match, skipping irrelevant subtrees entirely.
- **Faceted Search**: `--keys <pattern>` supports arbitrary glob filters (`preferences.coding.*`, `*testing*`, `context.project.*`) composable with `--depth N`.
- **Auditable decisions**: Because mode markers (`[mode=get|flat|drill|blame|diff]`) tag every caller-driven response, the retrieval path taken is visible in the transcript — the search becomes debuggable post-hoc.

## Reference Files

Implementation entry points for the three retrieval pipelines:

| Component | File |
|---|---|
| `IntelligentSearchEngine` (both `mode="single"` and `mode="tiered"`) | `src/memoir/search/intelligent.py` |
| `_search_tiered` + L1/L2 pickers + `L2_ESCALATION_THRESHOLD` | `src/memoir/search/intelligent.py` |
| `MemoryService.recall` (passes `mode` through) | `src/memoir/services/memory_service.py` |
| `memoir recall --mode {single,tiered}` CLI flag | `src/memoir/cli/commands/memory.py` |
| UI `/api/recall?mode=…` | `src/memoir/ui/handlers/memory_handler.py` |
| `summarize --depth N` (drill-down primitive) | `src/memoir/cli/commands/analysis.py` |
| `get <key>...` (batched exact lookup) | `src/memoir/cli/commands/memory.py` |
| `get` service layer | `src/memoir/services/memory_service.py` |
| Response shapes | `src/memoir/services/models.py` |
| Caller contract + mode markers | `plugins/claude-code/skills/memory-recall/SKILL.md` |
| `get` slash command | `plugins/claude-code/commands/memoir-get.md` |
| Per-prompt recall nudge | `plugins/claude-code/hooks/user-prompt-submit.sh` |
| `--depth` CLI tests | `tests/test_cli.py` |
| Tiered-mode engine tests | `tests/test_search_tiered.py` |

## Conclusion

The Memoir search architecture demonstrates that effective memory retrieval doesn't require expensive vector similarity search. By leveraging semantic taxonomy paths, the system provides three complementary pipelines that share the same substrate:

1. **`IntelligentSearchEngine` — `mode="single"`** — one LLM call picks paths for SDK-style callers that don't have their own model. 10–50× faster than vector approaches while preserving semantic understanding.
2. **`IntelligentSearchEngine` — `mode="tiered"`** — the same engine runs the drill-down pattern in staged LLM calls (L1 pick → optional L2 pick → key pick) when the store is large enough that a single-prompt path inventory stops fitting cleanly. Narrower prompts per stage at the cost of 2–3 LLM calls.
3. **Caller-driven tiered retrieval** — LLM-free primitives (`summarize --depth N`, `get`) let agentic callers drive the drill-down themselves. Zero memoir-side tokens, ~100–300ms wall time, fully auditable via mode markers.

All three pipelines benefit from the same underlying insight: pre-classification into semantic paths transforms retrieval from finding needles in haystacks to navigating a well-organized filing cabinet. The choice between them is a factoring decision about where the picker lives and how many stages it runs — one in-engine pass for simple callers, a staged in-engine pass when the store outgrows that, and fully out-of-engine for agent callers whose outer LLM is already the best possible picker.

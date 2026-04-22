# Memoir Search Theory & Architecture

## Executive Summary

Memoir exposes two retrieval entry points that share the same taxonomy-structured store:

- **`IntelligentSearchEngine`** (in-engine, LLM-powered): a single LLM call selects relevant taxonomy paths and returns their memories. Used when the caller does not have its own LLM — e.g. direct SDK usage, non-agent scripts. Total latency ~500–800ms.

- **Caller-driven tiered retrieval** (out-of-engine, LLM-free): the primitives `summarize --depth N` and `get` let an outer LLM (the Claude Code `memory-recall` skill is the canonical example) drive its own drill-down — **no LLM call inside memoir**. Latency is tens to hundreds of ms because no model inference happens on the retrieval side.

Both paths exploit pre-classified semantic paths for O(log n)-shaped lookups instead of O(n) similarity search. Where the path picker sits — inside the engine vs. outside in the calling agent — is a factoring choice, not an algorithmic one.

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
Traditional:             query → embedding → O(n) similarity search → ranked results
Memoir (in-engine):      query → LLM path selection → O(log n) retrieval → filtered results
Memoir (caller-driven):  query → caller-LLM picks prefix → summarize --depth N → get
```

Both memoir modes exploit pre-classified semantic structure to:

- **Reduce Search Space**: Focus only on relevant taxonomy branches
- **Improve Interpretability**: Clear path-based result organization
- **Enable Prefix Queries**: Efficient hierarchical exploration
- **Leverage LLM Understanding**: True semantic query comprehension

The caller-driven mode additionally avoids a second LLM inside memoir when the caller is itself an LLM — the outer model already has the query plus session context and is a strictly better picker than a fresh in-engine pass.

## Architecture Overview

### IntelligentSearchEngine

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

| Mode | LLM calls in memoir | Typical wall time | Network dependence |
|---|---|---|---|
| `IntelligentSearchEngine` (classic) | 1 (path selection) | 500–800ms | Requires online LLM |
| `[mode=get]` | 0 | <10ms | Local only |
| `[mode=flat]` | 0 | ~100ms | Local only |
| `[mode=drill]` | 0 | ~200–300ms | Local only |
| `[mode=blame]` / `[mode=diff]` | 0 | +100ms | Local only |

The caller-driven modes consume zero memoir-side tokens. Tokens spent by the outer LLM to do the picking are amortized against conversational context it already has loaded — effectively free at the margin.

#### When to use which entry point

- **SDK / non-LLM caller (scripts, direct Python use)** → `IntelligentSearchEngine` — memoir does the picking.
- **Agent caller with its own LLM (Claude Code, agentic clients)** → caller-driven drill-down — skip the nested LLM call.
- **Narrow lookup (known path, obvious pattern)** → `[mode=get]` or `[mode=flat]`; the outer LLM decides.
- **Open-ended or ambiguous query** → `[mode=drill]`; escalate to `blame` / `diff` only for explicit provenance questions.

#### Design references

- `plugins/claude-code/skills/memory-recall/SKILL.md` — canonical caller contract, decision rules, and mode-marker convention.
- `plugins/claude-code/commands/memoir-get.md` — slash-command surface for `get`.
- `plugins/claude-code/hooks/user-prompt-submit.sh` — SessionStart nudge that steers the outer LLM toward recall on non-trivial prompts.

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

Implementation entry points for the two retrieval paths:

| Component | File |
|---|---|
| `IntelligentSearchEngine` (LLM-picker) | `src/memoir/search/intelligent.py` |
| `summarize --depth N` (drill-down primitive) | `src/memoir/cli/commands/analysis.py` |
| `get <key>...` (batched exact lookup) | `src/memoir/cli/commands/memory.py` |
| `get` service layer | `src/memoir/services/memory_service.py` |
| Response shapes | `src/memoir/services/models.py` |
| Caller contract + mode markers | `plugins/claude-code/skills/memory-recall/SKILL.md` |
| `get` slash command | `plugins/claude-code/commands/memoir-get.md` |
| Per-prompt recall nudge | `plugins/claude-code/hooks/user-prompt-submit.sh` |
| `--depth` CLI tests | `tests/test_cli.py` |

## Conclusion

The Memoir search architecture demonstrates that effective memory retrieval doesn't require expensive vector similarity search. By leveraging semantic taxonomy paths, the system provides two complementary paths that share the same substrate:

1. **`IntelligentSearchEngine`** — a single LLM call picks paths for SDK-style callers that don't have their own model. 10–50x faster than vector approaches while preserving semantic understanding.
2. **Caller-driven tiered retrieval** — LLM-free primitives (`summarize --depth N`, `get`) let agentic callers drive the drill-down themselves. Zero memoir-side tokens, ~100–300ms wall time, fully auditable via mode markers.

Both paths benefit from the same underlying insight: pre-classification into semantic paths transforms retrieval from finding needles in haystacks to navigating a well-organized filing cabinet. The choice between them is a factoring decision about where the picker lives — inside memoir for simple callers, outside in the calling agent when the caller is already an LLM with richer context.

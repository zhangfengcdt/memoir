# Memoir Universal LLM Proxy

**Design Document**

| Field | Value |
|-------|-------|
| Author | Memoir Team |
| Status | Draft |
| Created | 2025-03 |
| Last Updated | 2025-03 |

---

## 1. Executive Summary

This document describes the design of a universal LLM proxy that acts as a stateful, cost-optimizing layer between agentic systems and LLM providers. By leveraging Memoir's ProllyTree architecture, the proxy achieves bit-perfect prefix stability to maximize KV cache utilization, targeting cost reductions of up to 90% for compatible workloads.

The design is provider-agnostic and framework-agnostic, supporting integration with systems such as OpenClaw, LangGraph, CrewAI, and others.

---

## 2. Problem Statement

### 2.1 Background

Modern agentic systems generate large, repetitive prompts that incur significant costs due to inefficient token usage. LLM providers offer KV cache discounts for requests with stable prefixes, but current agent architectures fail to capitalize on this optimization due to structural inefficiencies.

### 2.2 Identified Token Inefficiencies

We categorize token waste into three patterns, using OpenClaw as a representative case study:

| Pattern | Description | Impact |
|---------|-------------|--------|
| **Heartbeat Leak** | Periodic status checks resend 15k+ tokens for minimal updates. This pattern manifests as "Recursive Planning Loops" across most agent frameworks. | High redundancy per session |
| **Jitter Problem** | Dynamic headers (e.g., timestamps, request IDs) injected at prompt start invalidate KV caches globally due to byte-level prefix changes. | Cache invalidation |
| **Capability Bloat** | Full tool schemas (JSON/XML) transmitted on every request regardless of whether they are needed for the current task. | Unnecessary token overhead |
| **History Growth** | Conversation history accumulates with each turn, breaking prefix stability even when system prompts are cached. Each new message changes the prefix, invalidating the entire cache. | Compounding cache misses |

---

## 3. Goals and Non-Goals

### 3.1 Goals

1. **Maximize KV cache hit rate** (target: >85%) across all supported LLM providers
2. **Reduce per-request costs** by structuring prompts to leverage provider cache discounts
3. **Maintain semantic equivalence** between original and optimized prompts
4. **Support multi-agent architectures** with shared context and hierarchical spawning
5. **Provide transparent integration** requiring minimal changes to existing agent systems

### 3.2 Non-Goals

- Modifying LLM response behavior or implementing guardrails
- Replacing existing agent orchestration frameworks
- Handling authentication or rate limiting (deferred to infrastructure layer)

---

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Agent System                                       │
│                    (OpenClaw, LangGraph, CrewAI)                            │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │ Token Blob (unoptimized prompt)
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Memoir Proxy                                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │   Normalization  │  │  Vector Search   │  │      Intent Engine       │  │
│  │  & Segmentation  │──│     Engine       │──│   (Model Arbitrage)      │  │
│  └──────────────────┘  └────────┬─────────┘  └──────────────────────────┘  │
│                                 │                                           │
│                    ┌────────────▼────────────┐                              │
│                    │       ProllyTree        │                              │
│                    │  (Content-Addressed     │                              │
│                    │        Cache)           │                              │
│                    └─────────────────────────┘                              │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │ Optimized Request
                              │ (Cache Anchor + Dynamic Suffix)
                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          LLM Providers                                       │
│                    (Claude, Gemini, OpenAI, etc.)                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| **Normalization & Segmentation** | Converts unstructured prompts into tiered components (Tier 1/2/3) |
| **Vector Search Engine** | Identifies ProllyTree root hashes for stable prefix blocks |
| **ProllyTree** | Stores bit-perfect, deduplicated prompt representations |
| **Intent Engine** | Analyzes request intent to enable model routing optimization |

### 4.2 Request Flow

1. Agent system generates unoptimized prompt ("Token Blob")
2. Proxy normalizes and segments the prompt into structural tiers
3. Vector search identifies matching ProllyTree nodes for stable content
4. Intent engine determines optimal routing
5. Optimized request sent to provider with cache anchor and minimal dynamic suffix

---

## 5. Detailed Design

### 5.1 Block Segmentation Methodology

The proxy employs a three-stage pipeline to transform continuous context into structured ProllyTree nodes.

#### Stage 1: Structural Delimiter Detection

Scan for common agentic markers that separate instructions from memory:

```
Regex Patterns:
  - \[(SYSTEM|POLICY|CONTEXT|TOOLS|MEMORY)\]
  - # (SOUL|AGENTS|WORKSPACE)
```

#### Stage 2: Semantic Anchor Extraction (Fallback)

When explicit delimiters are absent, the proxy uses heuristic analysis:

- **Boilerplate Hashing**: Compare first 2,000 characters against known identity database. A >90% substring match classifies content as Tier 1 (Identity).
- **Instruction Boundary Search**: Locate phrases such as "You are an assistant..." to identify registry boundaries.

#### Stage 3: Sliding Window Stability Check

Compare current request to previous session requests:

| Classification | Behavior |
|----------------|----------|
| **Frozen Blocks** | Identical text across requests promoted to Tier 1/2, locked into ProllyTree |
| **Liquid Blocks** | Changed text (messages, tool outputs) shifted to Dynamic Suffix |

### 5.2 Content-Based Identification and ProllyTree Branching

The vector search engine links incoming requests to their structural ancestry in the ProllyTree.

#### Vector Embedding to Tree Hash Resolution

1. **Embed**: Normalize and embed anchor blocks (Tier 1 & 2)
2. **Search**: Identify most similar PrefixCluster via vector search
3. **Resolve**: Return ProllyTree root hash ("Committish") for the cluster
4. **Share**: Reuse existing node hashes for matching content blocks (structural sharing)

#### Multi-Agent Branching Strategies

| Strategy | Use Case | Mechanism |
|----------|----------|-----------|
| **Fleet Sync (Horizontal)** | Multiple instances of same agent | Force-stitch all instances to identical bytes for toolbelt and soul files |
| **Swarm Swapping (Vertical)** | Manager spawning sub-agents | Link sub-agent prompt to parent branch, add specialized instructions as new leaf |

### 5.3 ProllyTree Tier Definitions

#### Tier 1: Identity Prefix (Permanent)

- **Content**: SOUL.md, AGENTS.md, tool definitions
- **Scope**: Shared across entire agent fleet
- **Stability**: Deterministic chunking ensures localized edits don't invalidate unrelated hashes

#### Tier 2: Context Branch (Semi-Stable)

- **Content**: Project-specific files, HEARTBEAT.md
- **Scope**: Per-branch or per-project
- **Normalization**: Re-align variant file orderings to canonical Prolly path for prefix stability

#### Tier 3: Dynamic Suffix (Unstable)

- **Content**: Timestamps, tool outputs, recent messages
- **Cache Control**: Marked as `cache_control: ephemeral`
- **Impact**: Only portion requiring provider recomputation

### 5.4 Conversation History Management

Conversation history presents a unique challenge: even with perfect prefix caching, **growing history breaks the cache** because each new message changes the byte sequence.

```
Turn 1: [System][Doc][User1]                    ← Cache miss (new prefix)
Turn 2: [System][Doc][User1][Asst1][User2]      ← Cache miss (prefix changed!)
Turn 3: [System][Doc][...history...][User3]     ← Cache miss (prefix changed!)
```

#### History Handling Strategies

| Strategy | Mechanism | Trade-offs |
|----------|-----------|------------|
| **Sliding Window** | Keep only last N turns in context | Loses long-term context; simple to implement |
| **Summarization** | Compress old turns into summary block | Maintains context semantics; adds LLM call overhead |
| **Hierarchical Caching** | Cache system+tools separately from history | Partial cache hits; complex implementation |
| **History Hashing** | Content-address history blocks, reuse if identical | Works for repeated patterns; limited applicability |

#### Recommended Approach: Hierarchical Caching

Structure requests to maximize partial cache hits:

```
┌─────────────────────────────────────────────────────────────┐
│ TIER 1: System + Tools (cached)                   3,000 tok │
│ ─────────────────── cache_control: ephemeral ─────────────  │
│ TIER 2: Document Context (cached per-session)    12,000 tok │
│ ─────────────────── cache_control: ephemeral ─────────────  │
│ TIER 3: Conversation History (dynamic)            2,000 tok │
│ TIER 3: Current Message (dynamic)                   100 tok │
└─────────────────────────────────────────────────────────────┘

Result: 15,000 tokens cached (88%), 2,100 tokens recomputed (12%)
```

Even though history changes break the full prefix match, providers like Claude allow **multiple cache breakpoints**, enabling partial cache utilization.

### 5.5 Provider-Specific Caching Requirements

Each LLM provider implements caching differently. The proxy must adapt its optimization strategy accordingly.

#### Claude (Anthropic)

- **Mechanism**: Explicit `cache_control` markup required
- **Header**: Requires `anthropic-beta: prompt-caching-2024-07-31`
- **Minimum**: 1,024 tokens for caching eligibility (Sonnet), 2,048 for Haiku
- **TTL**: 5 minutes (extended on cache hit)
- **Cost**: Cache writes cost 25% more; cache reads cost 90% less
- **Multiple breakpoints**: Supports up to 4 cache breakpoints per request

```python
# Claude cache control example
messages = [{
    "role": "system",
    "content": [{
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}
    }]
}]
```

#### OpenAI

- **Mechanism**: Implicit (automatic for prefixes >1,024 tokens)
- **No markup required**: Caching happens automatically
- **Supported models**: GPT-4o, GPT-4o-mini, o1-preview, o1-mini
- **TTL**: 5-10 minutes typical
- **Cost**: 50% discount on cached tokens
- **Limitation**: No explicit control; must rely on prefix stability

#### Gemini (Google)

- **Mechanism**: Implicit by default; explicit context caching available
- **Explicit caching**: Create cached content via separate API, reference by name
- **TTL**: Configurable (1 minute to 1 hour)
- **Cost**: Reduced input costs for cached content
- **Minimum**: 32,768 tokens for explicit caching

#### Provider Adapter Requirements

| Provider | Explicit Markup | Min Tokens | TTL | Multi-Breakpoint |
|----------|-----------------|------------|-----|------------------|
| Claude | Required | 1,024-2,048 | 5 min | Yes (up to 4) |
| OpenAI | Not needed | ~1,024 | 5-10 min | No |
| Gemini | Optional | 32,768 | Configurable | N/A |

### 5.6 Cache Economics and Decision Heuristics

Caching is not always beneficial. Anthropic charges a **25% premium for cache writes**, meaning sessions with low reuse rates may pay more than uncached requests.

#### When to Cache

| Scenario | Cache? | Rationale |
|----------|--------|-----------|
| Multi-turn conversation (5+ turns) | ✅ Yes | Amortizes write cost across reads |
| Document analysis (10+ questions) | ✅ Yes | High reuse of document context |
| One-shot request | ❌ No | No reuse; pays write premium for nothing |
| Short prompt (<1,024 tokens) | ❌ No | Below minimum threshold |
| Rapidly changing context | ❌ No | Cache invalidated before reuse |

#### Cache Decision Algorithm

```python
def should_request_caching(
    prompt_tokens: int,
    expected_turns: int,
    ttl_seconds: int = 300
) -> bool:
    MIN_TOKENS = 1024
    WRITE_PREMIUM = 0.25  # 25% extra for cache write
    READ_DISCOUNT = 0.90  # 90% savings on cache read

    if prompt_tokens < MIN_TOKENS:
        return False

    # Break-even: 1 write + N reads vs (N+1) uncached
    # 1.25 + N * 0.10 < (N + 1) * 1.0
    # 1.25 + 0.10N < N + 1
    # 0.25 < 0.90N
    # N > 0.28

    # Need at least 1 cache read to break even
    # But account for TTL - will turns happen within window?
    return expected_turns >= 2
```

---

## 6. Advanced Features

### 6.1 Intent-Based Model Arbitrage

The proxy analyzes request intent signatures to route to cost-appropriate models. The classification system uses a **15-dimension weighted scoring algorithm** that runs entirely locally without LLM calls, based on the production-tested approach from [claw-llm-router](https://github.com/donnfelker/claw-llm-router).

#### Model Tiers

| Tier | Score Range | Use Cases | Default Models |
|------|-------------|-----------|----------------|
| **SIMPLE** | ≤ 0.0 | Greetings, simple Q&A, acknowledgments | Gemini Flash, GPT-4o-mini |
| **MEDIUM** | 0.0 - 0.3 | General tasks, summarization, explanations | Claude Haiku, GPT-4o |
| **COMPLEX** | 0.3 - 0.5 | Multi-step reasoning, code review, analysis | Claude Sonnet, GPT-4 |
| **REASONING** | ≥ 0.5 | Novel algorithms, architecture design, research | Claude Opus, o1-preview |

#### 15-Dimension Weighted Classifier

The classifier analyzes each request across 15 dimensions with calibrated weights:

| Dimension | Weight | Description |
|-----------|--------|-------------|
| `reasoningMarkers` | 0.17 | Keywords: "analyze", "explain why", "reasoning", "logic", "proof", "derive" |
| `codePresence` | 0.14 | Contains code blocks, function definitions, or programming syntax |
| `simpleIndicators` | 0.11 | Keywords: "hi", "hello", "thanks", "yes", "no", "ok" (negative weight) |
| `questionComplexity` | 0.10 | Multi-part questions, "how and why", comparative analysis |
| `contextLength` | 0.09 | Token count thresholds: >50k = +0.3, >100k = +0.5 |
| `technicalTerms` | 0.08 | Domain-specific vocabulary density |
| `mathPresence` | 0.07 | Mathematical notation, equations, numerical analysis |
| `structuredOutput` | 0.06 | Requests for JSON, tables, formatted data |
| `creativeWriting` | 0.05 | Story, poetry, creative content generation |
| `multiStepTask` | 0.04 | Sequential instructions: "first...then...finally" |
| `ambiguity` | 0.03 | Vague requests requiring clarification |
| `domainExpertise` | 0.03 | Specialized knowledge requirements |
| `timeConstraint` | 0.01 | Urgency indicators (minimal impact) |
| `languageComplexity` | 0.01 | Sentence structure and vocabulary level |
| `emotionalContent` | 0.01 | Sentiment and emotional context |

#### Keyword Detection

```
REASONING_KEYWORDS = [
  "analyze", "explain why", "reasoning", "logic", "proof", "derive",
  "theorem", "hypothesis", "conclude", "deduce", "infer", "evaluate",
  "compare and contrast", "trade-offs", "implications", "consequences"
]

CODE_KEYWORDS = [
  "implement", "function", "class", "algorithm", "debug", "refactor",
  "optimize", "test", "deploy", "architecture", "design pattern"
]

SIMPLE_KEYWORDS = [
  "hi", "hello", "thanks", "thank you", "yes", "no", "ok", "okay",
  "sure", "great", "bye", "goodbye", "please", "help"
]

MATH_KEYWORDS = [
  "calculate", "compute", "solve", "equation", "formula", "integral",
  "derivative", "probability", "statistics", "proof"
]
```

#### Scoring Algorithm

```python
def classify_intent(request: str, context_tokens: int) -> Tier:
    score = 0.0

    # Apply weighted dimension scores
    for dimension, weight in DIMENSION_WEIGHTS.items():
        dimension_score = analyze_dimension(request, dimension)
        score += dimension_score * weight

    # Override rules
    if count_keywords(request, REASONING_KEYWORDS) >= 2:
        return Tier.REASONING
    if context_tokens > 100_000:
        return max(Tier.COMPLEX, score_to_tier(score))

    # Map score to tier
    if score <= 0.0:
        return Tier.SIMPLE
    elif score <= 0.3:
        return Tier.MEDIUM
    elif score <= 0.5:
        return Tier.COMPLEX
    else:
        return Tier.REASONING
```

#### Fallback Chain

When a model is unavailable or rate-limited, requests cascade through the fallback chain:

```
SIMPLE → MEDIUM → COMPLEX → REASONING
```

This ensures requests are always handled, potentially by a more capable (but more expensive) model.

#### Intent Routing Examples

| Request | Score | Tier | Rationale |
|---------|-------|------|-----------|
| "Check for new messages" | -0.2 | SIMPLE | Heartbeat/status pattern |
| "Summarize this document" | 0.15 | MEDIUM | Standard task, no deep reasoning |
| "Review this PR for security issues" | 0.4 | COMPLEX | Code + analysis required |
| "Design a distributed consensus algorithm" | 0.7 | REASONING | Novel architecture + proof required |

### 6.2 Predictive Cache Warming

When vector search returns a "near hit" (high similarity but not exact match), the proxy preemptively sends a warming request to ensure the cache is hot before the actual request.

### 6.3 Git-Style Memory Rollbacks

The proxy supports rollback to a previous "clean commit" hash in the ProllyTree when the current session becomes corrupted or poisoned with errors. This enables recovery without losing accumulated context.

---

## 7. Success Metrics

| Metric | Target | Measurement Method |
|--------|--------|-------------------|
| **KV Cache Hit Rate** | >85% | Provider-reported cache utilization metrics |
| **Cost per Heartbeat** | <$0.01 | Aggregate billing for status-check requests |
| **Token Compression** | 40% reduction | Compare pre/post optimization token counts |
| **Vector Lookup Latency** | <10ms (p99) | Instrumented timing via local HNSW index |
| **Cache Write/Read Ratio** | <1:3 | Ensure reads exceed writes for positive ROI |
| **Jitter Detection Rate** | >95% | Percentage of jitter patterns successfully normalized |

### 7.1 Cache Monitoring Requirements

Effective cache optimization requires continuous monitoring of provider-reported metrics:

#### Claude Metrics

```python
# Extract from response metadata
response.usage = {
    "input_tokens": 15000,
    "cache_creation_input_tokens": 14000,  # Tokens written to cache (costly)
    "cache_read_input_tokens": 0,           # Tokens read from cache (cheap)
}
```

**Key Indicators:**

| Metric | Healthy | Warning | Action |
|--------|---------|---------|--------|
| `cache_read / cache_creation` | >3:1 | 1:1 - 3:1 | <1:1 = disable caching |
| `cache_read_input_tokens` | >0 | 0 for multiple requests | Check prefix stability |
| Consecutive cache misses | 0-1 | 2-3 | >3 = jitter detection failure |

#### Jitter Detection Dashboard

Monitor for patterns indicating cache-breaking jitter:

```
[ALERT] Session xyz-123: 5 consecutive cache misses
        Suspected jitter: timestamp in system prompt position 0-50
        Pattern: "2025-03-10T..." varies each request
        Recommendation: Move timestamp to Tier 3 (dynamic suffix)
```

---

## 8. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Provider cache behavior changes | Medium | High | Abstract provider-specific logic; implement fallback paths |
| Semantic drift from normalization | Low | High | Validate output equivalence via automated testing |
| Vector search latency at scale | Medium | Medium | Horizontal scaling with distributed HNSW indices |
| Complex agent prompts resist segmentation | Medium | Medium | Expand heuristic library; add LLM-assisted fallback |
| Cache write costs exceed savings | Medium | Medium | Implement cache decision heuristics; monitor write/read ratios |
| Conversation history breaks cache | High | High | Use hierarchical caching with multiple breakpoints; consider summarization |
| Provider TTL expiration | Medium | Low | Implement predictive cache warming; track TTL windows |

---

## 9. Implementation Phases

### Phase 1: Core Infrastructure
- Implement normalization and segmentation pipeline
- Integrate ProllyTree storage layer
- Build vector search engine with HNSW indexing

### Phase 2: Provider Integration
- Implement Claude API integration with cache anchoring
- Add Gemini and OpenAI provider adapters
- Develop intent classification engine

### Phase 3: Multi-Agent Support
- Implement fleet sync for horizontal scaling
- Add swarm swapping for hierarchical agents
- Build branch management and rollback capabilities

### Phase 4: Optimization and Hardening
- Predictive cache warming
- Performance tuning and latency optimization
- Production monitoring and alerting

---

## 10. Future Work

- **Automatic tier promotion**: ML-based detection of content stability patterns
- **Cross-session learning**: Aggregate patterns across users to improve segmentation
- **Provider-specific optimizations**: Leverage unique caching features of each provider
- **Streaming support**: Extend architecture to handle streaming responses efficiently

---

## Appendix A: Glossary

| Term | Definition |
|------|------------|
| **Cache Anchor** | ProllyTree root hash identifying the exact KV cache to use |
| **Committish** | Git-style reference to a specific ProllyTree state |
| **Frozen Block** | Content segment that remains stable across requests |
| **Liquid Block** | Content segment that changes between requests |
| **PrefixCluster** | Vector-indexed group of semantically similar stable prefixes |
| **Token Blob** | Unoptimized prompt generated by agent systems |

---

## Appendix B: References

- [Memoir ProllyTree Dependency and Architecture](https://github.com/zhangfengcdt/prollytree)
- [Anthropic Prompt Caching Documentation](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [Google Gemini Context Caching](https://ai.google.dev/gemini-api/docs/caching)
- [claw-llm-router Intent Classifier](https://github.com/donnfelker/claw-llm-router) - Reference implementation for 15-dimension weighted intent classification
- [LangChain Prompt Caching in Production](https://www.lubulabs.com/ai-blog/langchain-prompt-caching-production) - Real-world caching patterns and provider comparison
- [LangSmith Prompt Versioning](https://www.lubulabs.com/ai-blog/langsmith-prompt-versioning-production) - Prompt management patterns (complementary to caching)

---

## Appendix C: Framework Analysis Summary

Analysis of KV cache optimization potential across major agent frameworks (see `docs/design/framework_analysis.md` for details):

| Framework | Typical Tokens | Current Cacheable | With Memoir | Primary Jitter Source |
|-----------|---------------|-------------------|-------------|----------------------|
| **CrewAI** | 1,500-3,000 | 25-35% | 60-80% | Context passing between agents |
| **AutoGen** | 1,400-2,700 | 4-7% | 15-32% | Message UUIDs, timestamps |
| **MetaGPT** | 2,500-8,000 | ~20% | 40-60% | PRD/code injection, history |
| **LangGraph** | 550-4,000 | 20-40% | 60-90% | Checkpoint IDs, tool_call_ids |

Test fixtures for each framework are available in `tests/fixtures/proxy/frameworks/`.

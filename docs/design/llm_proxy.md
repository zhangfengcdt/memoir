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

---

## 6. Advanced Features

### 6.1 Intent-Based Model Arbitrage

The proxy analyzes request intent signatures to route to cost-appropriate models:

| Intent Category | Example | Recommended Model |
|-----------------|---------|-------------------|
| High-Reasoning | "Implement this feature" | Claude Sonnet / GPT-4 |
| Heartbeat/Status | "Check for new messages" | Gemini Flash / GPT-4o-mini |
| Simple Extraction | "Parse this JSON" | Haiku / Flash |

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

---

## 8. Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Provider cache behavior changes | Medium | High | Abstract provider-specific logic; implement fallback paths |
| Semantic drift from normalization | Low | High | Validate output equivalence via automated testing |
| Vector search latency at scale | Medium | Medium | Horizontal scaling with distributed HNSW indices |
| Complex agent prompts resist segmentation | Medium | Medium | Expand heuristic library; add LLM-assisted fallback |

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

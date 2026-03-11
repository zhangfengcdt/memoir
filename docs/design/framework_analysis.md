# Agent Framework KV Cache Analysis

**Analysis Date**: 2025-03-10

This document analyzes token usage patterns and KV cache optimization potential across major agent frameworks.

---

## Executive Summary

| Framework | Typical Tokens | Current Cacheable | With Normalization | Primary Jitter |
|-----------|---------------|-------------------|-------------------|----------------|
| **CrewAI** | 1,500-3,000 | 25-35% | 60-80% | Context passing |
| **AutoGen** | 1,400-2,700 | 4-7% | 15-32% | Message IDs, timestamps |
| **MetaGPT** | 2,500-8,000 | ~20% | 40-60% | Conversation history |
| **LangGraph** | 550-4,000 | 20-40% | 60-90% | Checkpoint IDs, tool_call_ids |

**Key Finding**: All frameworks have significant untapped caching potential. The Memoir proxy can improve cache hit rates by 2-4x through prefix normalization.

---

## 1. CrewAI Analysis

### Overview
CrewAI uses role-based agents working as a "crew" to accomplish tasks sequentially or in parallel.

### Prompt Structure
```
┌─────────────────────────────────────────────────────────────┐
│ ROLE DEFINITION (Cacheable)                      ~100 tokens│
│ "You are {role}. {backstory}. Your goal is: {goal}"        │
├─────────────────────────────────────────────────────────────┤
│ REACT FORMAT (Cacheable)                         ~150 tokens│
│ "Thought/Action/Final Answer format instructions..."        │
├─────────────────────────────────────────────────────────────┤
│ TOOLS DEFINITION (Cacheable)                     ~200 tokens│
│ Tool schemas and usage instructions                         │
├─────────────────────────────────────────────────────────────┤
│ CONTEXT FROM PREVIOUS AGENTS (Dynamic)        ~500-2000 tok │
│ Output from upstream agents in the crew                     │
├─────────────────────────────────────────────────────────────┤
│ CURRENT TASK (Dynamic)                          ~100-500 tok│
│ The specific task for this agent                            │
└─────────────────────────────────────────────────────────────┘
```

### Jitter Sources

| Source | Location | Impact | Fixable? |
|--------|----------|--------|----------|
| Context from previous tasks | `{context}` block | High | ✅ Hash & dedupe |
| Memory retrieval | System prompt injection | Medium | ✅ Move to user message |
| Agent name variations | `{name}` placeholder | Low | ✅ Use fixed identifiers |
| Tool descriptions | Per-agent config | Medium | ✅ Cache per agent hash |

### Token Estimates

| Scenario | Total | Cacheable Now | After Optimization |
|----------|-------|---------------|-------------------|
| Single agent, no context | 600-800 | 60-70% | 80-90% |
| Agent with 5 tools | 900-1,200 | 40-50% | 70-80% |
| Multi-agent with context | 1,500-3,000 | 25-35% | 55-75% |
| Complex crew with memory | 2,000-4,000 | 20-30% | 50-70% |

### Optimization Strategy
1. **Cache role+tools per agent hash**: ~300-400 tokens saved per request
2. **Deduplicate context**: Previous agent outputs often repeat information
3. **Move memory to user message**: Keeps system prompt stable

---

## 2. AutoGen Analysis

### Overview
Microsoft's AutoGen uses conversational multi-agent patterns with code execution capabilities.

### Prompt Structure
```
┌─────────────────────────────────────────────────────────────┐
│ SYSTEM MESSAGE (Cacheable)                        ~30-50 tok│
│ "You are a helpful AI assistant..."                         │
├─────────────────────────────────────────────────────────────┤
│ TOOL DEFINITIONS (Cacheable)                    ~200-400 tok│
│ Function schemas                                            │
├─────────────────────────────────────────────────────────────┤
│ CONVERSATION HISTORY (Dynamic, Jittery)        ~500-2000 tok│
│ Messages with UUIDs and timestamps                          │
├─────────────────────────────────────────────────────────────┤
│ ORCHESTRATOR STATE (Dynamic)                    ~200-500 tok│
│ Task ledger, progress tracking (MagenticOne)                │
└─────────────────────────────────────────────────────────────┘
```

### Jitter Sources

| Source | Frequency | Token Impact | Fixable? |
|--------|-----------|--------------|----------|
| `BaseChatMessage.id` (UUID) | Per message | ~36 tokens/msg | ✅ Strip |
| `created_at` timestamp | Per message | ~20 tokens/msg | ✅ Remove |
| Turn counter | Per turn | ~5 tokens | ✅ Normalize |
| Speaker selection prompts | Per selection | ~100-200 tokens | ⚠️ Partial |
| Code execution results | Per execution | Variable | ❌ Dynamic |

### Token Estimates

| Scenario | Total | Cacheable Now | After Optimization |
|----------|-------|---------------|-------------------|
| Single agent (basic) | 730-1,450 | 4-7% | 31-32% |
| Multi-agent selection | 1,380-2,720 | 4-6% | 15-17% |
| MagenticOne orchestration | 3,200-7,800 | 5-6% | 18-22% |
| WebSurfer agent | 2,465-6,700 | 8-12% | 20-25% |

### Optimization Strategy
1. **Strip message metadata**: Remove `id`, `created_at` before LLM call
2. **Cache role descriptions**: Normalize speaker selection prompts
3. **Separate ledger templates**: Static template + dynamic values

---

## 3. MetaGPT Analysis

### Overview
MetaGPT simulates a software development team with specialized roles (PM, Architect, Engineer, QA).

### Prompt Structure
```
┌─────────────────────────────────────────────────────────────┐
│ ROLE PREFIX (Cacheable)                          ~50-100 tok│
│ "You are {profile}, named {name}, goal is {goal}"           │
├─────────────────────────────────────────────────────────────┤
│ ACTION INSTRUCTIONS (Cacheable)                 ~200-500 tok│
│ Output format, constraints, examples                        │
├─────────────────────────────────────────────────────────────┤
│ FORMAT EXAMPLES (Cacheable)                     ~300-800 tok│
│ Mermaid diagrams, code templates                            │
├─────────────────────────────────────────────────────────────┤
│ CONTEXT (Dynamic)                             ~1000-3000 tok│
│ PRD, Design docs, code from previous roles                  │
├─────────────────────────────────────────────────────────────┤
│ CONVERSATION HISTORY (Dynamic)                 ~500-5000 tok│
│ State machine, previous outputs                             │
├─────────────────────────────────────────────────────────────┤
│ CURRENT TASK (Dynamic)                          ~200-500 tok│
│ Specific task for this role                                 │
└─────────────────────────────────────────────────────────────┘
```

### Jitter Sources

| Source | Frequency | Token Impact | Fixable? |
|--------|-----------|--------------|----------|
| Conversation history | Every turn | 500-5000+ | ⚠️ Compress |
| Previous state | State transition | 20-50 | ✅ Normalize |
| Message ID (UUID) | Every message | ~36 | ✅ Strip |
| Environment role list | Session start | 50-100 | ✅ Cache |
| PRD/Design injection | Per phase | 1000-3000 | ⚠️ Hash-based |
| Debug/error logs | Per debug cycle | 200-1000 | ✅ Summarize |

### Token Estimates by Role

| Role | Min | Typical | Max | Cacheable Now |
|------|-----|---------|-----|---------------|
| Product Manager | 800 | 2,500 | 6,000+ | 20% |
| Architect | 1,000 | 3,000 | 8,000+ | 18% |
| Engineer | 1,500 | 4,000 | 12,000+ | 15% |
| Project Manager | 600 | 1,500 | 4,000 | 25% |
| QA Engineer | 800 | 2,000 | 5,000 | 22% |

### Optimization Strategy
1. **Cache role definitions**: ~100 tokens per role
2. **Document hashing**: Content-addressed storage for PRD/Design
3. **Incremental context**: Send diffs instead of full documents
4. **History compression**: Summarize old conversation turns

---

## 4. LangGraph Analysis

### Overview
LangGraph provides graph-based orchestration for stateful AI workflows with checkpointing.

### Prompt Structure
```
┌─────────────────────────────────────────────────────────────┐
│ SYSTEM MESSAGE (Cacheable)                      ~100-500 tok│
│ Agent instructions and persona                              │
├─────────────────────────────────────────────────────────────┤
│ TOOL DEFINITIONS (Cacheable)                   ~200-2000 tok│
│ Function schemas (varies by agent complexity)               │
├─────────────────────────────────────────────────────────────┤
│ FEW-SHOT EXAMPLES (Cacheable)                  ~200-500 tok │
│ Optional demonstration examples                             │
├─────────────────────────────────────────────────────────────┤
│ CONVERSATION HISTORY (Dynamic, Jittery)        ~500-8000 tok│
│ Messages with IDs, tool_call_ids                            │
├─────────────────────────────────────────────────────────────┤
│ CURRENT QUERY (Dynamic)                         ~20-200 tok │
│ Latest user message                                         │
└─────────────────────────────────────────────────────────────┘
```

### Jitter Sources

| Source | Per-Request? | Token Impact | Fixable? |
|--------|-------------|--------------|----------|
| `checkpoint_id` (UUID) | Yes | ~36 | ✅ Strip |
| `thread_id` | Per conversation | ~20 | ⚠️ Move to suffix |
| `message.id` | Per message | ~36/msg | ✅ Strip |
| `tool_call.id` | Per tool call | ~20/call | ⚠️ Normalize |
| `run_id` | Per execution | ~36 | ✅ Strip |
| Step counter | Per superstep | ~5 | ✅ Normalize |
| Timestamps | Per checkpoint | ~20 | ✅ Remove |

### Token Estimates

| Scenario | Total | Cacheable Now | After Optimization |
|----------|-------|---------------|-------------------|
| Simple Q&A (1-2 tools) | 550 | 82% | 90%+ |
| Complex agent (10+ tools) | 4,000 | 48% | 70-80% |
| Multi-turn (5 turns) | 2,000 | 30% | 60-70% |
| With checkpointing | 2,500 | 25% | 55-65% |

### Optimization Strategy
1. **Strip checkpoint metadata**: Not needed for LLM
2. **Normalize tool_call_ids**: Use deterministic IDs
3. **Cache system + tools prefix**: Stable per deployment
4. **Move timestamps to suffix**: After cache break

---

## 5. Comparative Analysis

### Caching Potential by Framework

```
                    Current Cache Hit Rate
                    ▼
CrewAI      ████████░░░░░░░░░░░░░░░░░░░░░  25-35%
AutoGen     ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  4-7%
MetaGPT     ██████░░░░░░░░░░░░░░░░░░░░░░░░  ~20%
LangGraph   ████████████░░░░░░░░░░░░░░░░░░  20-40%

                    With Memoir Normalization
                    ▼
CrewAI      ████████████████████████░░░░░░  60-80%
AutoGen     ██████████░░░░░░░░░░░░░░░░░░░░  15-32%
MetaGPT     ████████████████░░░░░░░░░░░░░░  40-60%
LangGraph   ████████████████████████████░░  60-90%
```

### Cost Impact Analysis

Assuming $3.00/1M input tokens (Claude Sonnet) and 90% cache discount:

| Framework | Scenario | Tokens/Req | Current Cost | Optimized Cost | Savings |
|-----------|----------|------------|--------------|----------------|---------|
| CrewAI | 3-agent crew | 6,000 | $0.018 | $0.005 | 72% |
| AutoGen | 10-turn chat | 8,000 | $0.024 | $0.019 | 21% |
| MetaGPT | Full project | 25,000 | $0.075 | $0.038 | 49% |
| LangGraph | 5-turn agent | 3,500 | $0.011 | $0.003 | 73% |

### Framework-Specific Recommendations

| Framework | Primary Optimization | Secondary | Impact |
|-----------|---------------------|-----------|--------|
| **CrewAI** | Context deduplication | Role caching | High |
| **AutoGen** | Strip message metadata | Ledger templates | Medium |
| **MetaGPT** | Document hashing | History compression | High |
| **LangGraph** | Checkpoint stripping | ID normalization | High |

---

## 6. Memoir Proxy Implementation Priorities

Based on this analysis, the Memoir proxy should prioritize:

### Priority 1: Universal Jitter Removal
- Strip UUIDs (message IDs, checkpoint IDs, run IDs)
- Remove timestamps from prefix
- Normalize tool_call_ids to deterministic values

### Priority 2: Framework-Specific Normalization
- **CrewAI**: Context block deduplication
- **AutoGen**: Ledger template separation
- **MetaGPT**: Document content-addressing
- **LangGraph**: Checkpoint metadata stripping

### Priority 3: Structural Optimization
- Move dynamic content to suffix (after cache_control break)
- Canonicalize tool ordering
- Compress/summarize conversation history

---

## 7. Test Fixtures Created

Test fixtures have been created for each framework in `tests/fixtures/proxy/frameworks/`:

```
frameworks/
├── crewai/
│   └── content_crew.jsonl      # 3-agent content creation crew
├── autogen/
│   └── coding_assistant.jsonl  # Multi-turn coding session
├── metagpt/
│   └── software_team.jsonl     # 4-role software development
└── langgraph/
    └── react_agent.jsonl       # ReAct agent with tools
```

Each fixture includes:
- Session metadata
- System prompts with framework-specific patterns
- Multi-turn conversations
- Tool usage examples
- Token usage estimates
- Checkpoint/state information (where applicable)

---

## Appendix: Jitter Pattern Reference

### Common Jitter Patterns Across Frameworks

| Pattern | Frameworks | Example |
|---------|-----------|---------|
| UUID in message | All | `id: "550e8400-e29b-41d4-a716-446655440000"` |
| ISO timestamp | All | `created_at: "2025-03-10T10:00:00Z"` |
| Turn/step counter | AutoGen, LangGraph | `step: 5`, `turn: 3` |
| Dynamic speaker | CrewAI, AutoGen | `source: "researcher"` vs `source: "writer"` |
| Growing history | All | Conversation accumulates each turn |
| Tool call ID | LangGraph, AutoGen | `tool_call_id: "call_abc123"` |
| Checkpoint ref | LangGraph | `parent_checkpoint: "ckpt_0001"` |

### Normalization Strategies

| Jitter Type | Strategy | Implementation |
|-------------|----------|----------------|
| UUIDs | Strip or placeholder | Regex: `/[0-9a-f]{8}-[0-9a-f]{4}-.../` |
| Timestamps | Remove or bucket | Remove from prefix, add to suffix |
| Counters | Relative indexing | `turn: N` → `turn: current` |
| History | Hash-based dedup | Content-address repeated segments |
| Tool IDs | Deterministic generation | `call_{tool_name}_{hash}` |

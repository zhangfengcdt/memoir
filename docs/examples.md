# Examples

This section demonstrates memoir's unique Git-like versioning capabilities for AI memory systems through practical examples that showcase functionality unavailable in current agent frameworks.

## Overview: Git for AI Memory

Memoir brings Git-like version control to AI memory systems, enabling:

- **Branching**: Explore hypothetical scenarios safely
- **Time-travel**: Debug by examining memory at any point in history
- **Snapshots**: Create checkpoints for reproducible testing
- **Merging**: Combine memory states from different branches

## Traditional vs Memoir Memory Systems

```text
Traditional Agent Memory:
┌─────────────────────────────────────┐
│ uuid-1234 → "User likes Python"     │
│ uuid-5678 → "User prefers coffee"   │   Opaque storage
│ uuid-9012 → "Bug: Wrong preference" │   No history
└─────────────────────────────────────┘   No branching
         ↓ Vector search (slow)
   [Find relevant memories]

Memoir Memory System:
┌─────────────────────────────────────┐
│ profile.preferences.python          │   Semantic paths
│ preferences.daily.coffee            │   Git-like history
│ ├─ main branch                      │   Branching support
│ └─ debug branch                     │   Time-travel
└─────────────────────────────────────┘
         ↓ O(log n) lookup
   [Instant semantic retrieval]
```

## Example 1: Conversational Context Branching

**Scenario**: User asks "What if I had chosen career path X instead of Y?"

**Problem**: Current agent memory systems can't explore hypotheticals without corrupting the main memory timeline.

**Solution**: Git-like branching allows safe exploration of alternative scenarios.

[examples/context_branching](examples/context_branching.md) - **Full Example with Code Snippets**

### Quick Demo

```bash
python examples/context_branching.py
```

## Example 2: Memory State Debugging

**Scenario**: Agent makes unexpected decisions based on corrupted memories.

**Problem**: No visibility into which memories influenced specific behaviors or when corruption occurred.

**Solution**: Time-travel debugging allows examination of memory state at any point in history.

[examples/memory_debugging](examples/memory_debugging.md) - **Full Example with Code Snippets**

### Quick Demo

```bash
python examples/memory_state_debugging.py
```

## Example 3: Reproducible Testing

**Scenario**: Agent behavior varies between test runs due to memory state differences.

**Problem**: Hard to create consistent test environments for different user personas.

**Solution**: Git-like branches create isolated, reproducible test scenarios.

[examples/reproducible_testing](examples/reproducible_testing.md) - **Full Example with Code Snippets**

### Quick Demo

```bash
python examples/reproducible_testing.py
```

## Example 4: Production Debugging (Large Scale)

**Scenario**: Production system with 167+ accumulated memories needs debugging of an issue from 3 days ago.

**Problem**: Impossible to manually search through hundreds of memories to find the exact state when the problem occurred.

**Solution**: Time-travel instantly to any point in production history with complete memory context.

[examples/production_debugging](examples/production_debugging.md) - **Full Example with Code Snippets**

### Quick Demo

```bash
python examples/production_debugging.py
```

## Example 5: Versioning Control

**Scenario**: Control commit granularity to prevent overwhelming git history in batch operations.

**Problem**: Every put/delete operation creates a commit, making history noisy for bulk operations.

**Solution**: Fine-grained commit control with auto_commit flag and batch operations.

### Quick Demo

```bash
python examples/versioning_control_example.py
python examples/versioning_control.py
```

### Key Benefits

- **Backward Compatible**: Default auto_commit=True preserves existing behavior
- **Fine-grained Control**: Disable auto-commit for batch operations
- **Cleaner History**: Logical commits instead of per-operation noise
- **Better Performance**: Fewer git operations = faster batch processing
- **Flexible Workflows**: Mix auto-commit and manual batching as needed

### Usage Patterns

```python
# Traditional (unchanged)
store = ProllyTreeStore(path, auto_commit=True)  # Default
store.put(namespace, key, value)  # Commits immediately

# Batch operations
store = ProllyTreeStore(path, auto_commit=False)
store.put(namespace, key1, value1)  # No commit due to auto_commit=False
store.put(namespace, key2, value2)  # No commit due to auto_commit=False
store.commit('Batch update with 2 memories')

# Mixed approach
store.auto_commit = True
store.put(namespace, critical_key, value)  # Immediate commit
store.auto_commit = False
store.put(namespace, batch_key1, value1)  # No commit due to auto_commit=False
store.commit('Batch of non-critical updates')
```

## Performance Comparison

Memory System Performance:

| Operation | Traditional Vector DB | Memoir (Git-like) | Improvement |
| --- | --- | --- | --- |
| Search 100 memories | 150-750ms | 0.1-1ms | 150-750x faster |
| Store memory | 200-600ms | 20-30ms | 7-30x faster |
| Time-travel debug | Not supported | <1ms | Impossible → Instant |
| Branch exploration | Not supported | <1ms | Impossible → Instant |
| Memory corruption recovery | Manual search | <1ms | Hours → Seconds |

## Key Benefits Summary

### Memory Branching
- **Safe Exploration**: Test hypotheticals without corrupting main timeline
- **Instant Switching**: Move between different memory states instantly
- **Perfect Isolation**: Branches completely separate, no cross-contamination
- **Traditional**: Single timeline, no branching, corruption risk

### Time-Travel Debugging
- **Historical Context**: See exact memory state at any point in time
- **Corruption Detection**: Identify exactly when and where problems occurred
- **Root Cause Analysis**: Compare memory states across timeline
- **Traditional**: No history, debugging impossible after corruption

### Reproducible Testing
- **Test Isolation**: Each test runs in completely clean environment
- **Consistent Results**: Same test produces identical results every time
- **Parallel Testing**: Multiple scenarios without interference
- **Traditional**: Tests contaminate each other, inconsistent results

### Production Debugging
- **Large Scale**: Handle 100s-1000s of memories without performance loss
- **Time-Travel**: Jump to any point in production history instantly
- **Safe Fixes**: Test fixes in isolation before production deployment
- **Traditional**: Manual search impossible at scale, no historical context

## Getting Started

To try these examples yourself:

1. **Install Dependencies**:

    ```bash
    pip install langchain-openai memoir-ai
    ```

2. **Set API Key** (for LLM-powered examples):

    ```bash
    export OPENAI_API_KEY=your-api-key-here
    ```

3. **Run Examples**:

    ```bash
    # Fast demos (no LLM required)
    python examples/context_branching.py
    python examples/memory_state_debugging.py
    python examples/reproducible_testing.py
    python examples/production_debugging.py
    python examples/versioning_control_example.py
    python examples/versioning_control.py
    ```

## Next Steps

- **Integration Guide**: [quickstart](quickstart.md) - Integrate memoir into your agent
- **API Reference**: [api/memoir](api/memoir.md) - Complete API documentation
- **Architecture**: [architecture](architecture.md) - Deep dive into system design
- **Performance**: Benchmark memoir against your current memory system

These examples demonstrate capabilities that **no current agent memory system provides**. Memoir's Git-like versioning opens up entirely new possibilities for AI agent development, testing, and production debugging.

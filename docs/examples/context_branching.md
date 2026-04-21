# Conversational Context Branching

**Scenario**: User asks "What if I had chosen career path X instead of Y?"

**Problem**: Current agent memory systems can't explore hypotheticals without corrupting the main memory timeline.

**Solution**: Git-like branching allows safe exploration of alternative scenarios.

## Overview

Traditional agent memory systems face a fundamental problem when users want to explore hypothetical scenarios. Any "what if" exploration permanently alters the agent's memory, corrupting the main timeline with speculative information.

Memoir solves this with **Git-like branching** - create separate branches to explore alternatives while keeping the main timeline completely intact.

## Memory Branching Diagram

```text
Timeline Branching for Hypothetical Exploration:

main branch:     A──B──C──D
                        │
                        └─→ E──F──G  (alternative branch)
                            │
                            └─→ "What if Google career?"

A: CS Degree 2020
B: Startup Backend Job
C: Senior Engineer Promotion
D: Current State (preserved)

E: Google Frontend Job (hypothetical)
F: React/UI Systems Focus
G: YouTube Tech Lead

Key Benefits:
• Main timeline (A-D) remains unchanged
• Alternative exploration (E-G) isolated in separate branch
• Can switch between timelines instantly
• Safe to explore without corruption
```

## Key Code Snippets

### Initial Setup

```python
import asyncio
import tempfile
import os
from memoir.store.prolly_adapter import ProllyTreeStore

# Create memory store with versioning enabled
temp_dir = tempfile.mkdtemp()
prolly_path = os.path.join(temp_dir, "memory_store")

prolly_store = ProllyTreeStore(
    path=prolly_path,
    enable_versioning=True,  # Enable Git-like features
    cache_size=10000,
)
```

### Building Main Timeline

```python
namespace = "user123"

# Store user's actual career path
await prolly_store.store_memory_async(
    namespace,
    "I graduated with a computer science degree in 2020",
    "profile.education.degree"
)

await prolly_store.store_memory_async(
    namespace,
    "I chose to work at a startup doing backend development",
    "profile.career.current.startup"
)

await prolly_store.store_memory_async(
    namespace,
    "I've been promoted to senior engineer after 3 years",
    "profile.career.progression.senior"
)

# Create snapshot of main timeline
main_snapshot = f"main_timeline_{int(time.time())}"
prolly_store.create_time_snapshot(main_snapshot)
print(f"Main timeline snapshot: {main_snapshot}")
```

### Creating Alternative Branch

```python
# Create branch for hypothetical exploration
alternative_branch = f"alternative_path_{int(time.time())}"
prolly_store.tree.create_branch(alternative_branch)
prolly_store.tree.checkout(alternative_branch)

print(f"Created branch: {alternative_branch}")
print("Now exploring: What if I had joined Google instead?")
```

### Exploring Alternative Timeline

```python
# Store hypothetical career memories in alternative branch
await prolly_store.store_memory_async(
    namespace,
    "What if I had joined Google as a frontend engineer instead?",
    "profile.career.hypothetical.google"
)

await prolly_store.store_memory_async(
    namespace,
    "At Google, I would have focused on React and large-scale UI systems",
    "profile.skills.hypothetical.frontend"
)

await prolly_store.store_memory_async(
    namespace,
    "I might have become a tech lead for YouTube's frontend team",
    "profile.career.hypothetical.youtube_lead"
)

# Create snapshot of alternative timeline
alt_snapshot = f"alt_timeline_{int(time.time())}"
prolly_store.create_time_snapshot(alt_snapshot)
```

### Timeline Comparison

```python
# Compare memories across branches
print("Comparing timelines...")

# Current branch (alternative)
alt_memories = prolly_store.search((namespace,), limit=10)
print("Alternative timeline memories:")
for _, path, data in alt_memories[:3]:
    print(f"  [{path}] {data}")

# Switch to main branch
prolly_store.tree.checkout("main")
main_memories = prolly_store.search((namespace,), limit=10)
print("\nMain timeline memories:")
for _, path, data in main_memories[:3]:
    print(f"  [{path}] {data}")
```

### Branch Cleanup

```python
# Safe cleanup - return to main, alternative branch preserved
prolly_store.tree.checkout("main")
print("Switched back to main timeline")
print("Alternative branch exploration complete - main timeline preserved")
```

## Running the Example

```bash
python examples/context_branching.py
```

## Sample Output

```text
# Conversational Context Branching Demo
Demonstrate safe exploration of hypothetical scenarios

Initializing memory system...
Memory store created at: /tmp/tmpxxx/memory_store

Building main timeline: Actual career path
Main timeline snapshot: main_timeline_1755877155

Creating alternative branch: alternative_path_1755877183
Switched to branch 'alternative_path_1755877183'

Exploring alternative career path...
Alternative timeline snapshot: alt_timeline_1755877259

Comparing career memories across branches

Alternative timeline skills:
- I've been promoted to senior engineer after 3 years
- I chose to work at a startup doing backend development
- At Google, I would have focused on React and large-scale UI systems

Main timeline skills:
- I've been promoted to senior engineer after 3 years
- I chose to work at a startup doing backend development

Key Insight: Safe exploration without memory corruption
  - Different branches contain isolated memories
  - Main timeline preserved during hypothetical exploration
```

## Key Benefits

**Safe Exploration**
: Test hypotheticals without corrupting main timeline

**Instant Switching**
: Move between different memory states instantly

**Perfect Isolation**
: Branches completely separate, no cross-contamination

**Preserved History**
: Main timeline remains intact for future use

**Traditional Limitation**
: Single timeline, no branching, corruption risk

## Use Cases

- **Career counseling**: "What if I had studied medicine instead?"
- **Financial planning**: "What if I had invested in real estate?"
- **Life coaching**: "What if I had moved to a different city?"
- **Product decisions**: "What if we had chosen a different tech stack?"
- **Strategic planning**: "What if market conditions were different?"

## Next Steps

- Try the **Memory State Debugging** example: [memory_debugging](memory_debugging.md)
- Learn about **Reproducible Testing**: [reproducible_testing](reproducible_testing.md)
- See **Production Debugging**: [production_debugging](production_debugging.md)
- View the complete **API Reference**: [../api/memoir](../api/memoir.md)

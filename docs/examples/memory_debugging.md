# Memory State Debugging

**Scenario**: Agent makes unexpected decisions based on corrupted memories.

**Problem**: No visibility into which memories influenced specific behaviors or when corruption occurred.

**Solution**: Time-travel debugging allows examination of memory state at any point in history.

## Overview

Traditional agent memory systems suffer from opacity - when an agent makes a bad decision, there's no way to examine what memories influenced that decision or when corruption occurred. Debugging becomes impossible once the memory state is corrupted.

Memoir provides **time-travel debugging** - jump to any point in the agent's memory history and examine the exact state that influenced decisions.

## Time-Travel Debugging Diagram

```text
Memory Corruption Detection & Recovery:

Timeline: commit1 ──→ commit2 ──→ commit3 ──→ CORRUPT ──→ FIXED
            │           │           │           │         │
            │           │           │           │         └─ Corrected
            │           │           │           └─ Bad memory
            │           │           └─ Clean state
            │           └─ Coffee added
            └─ Python preference

Debugging Process:

1. Agent makes bad decision (CORRUPT state)
2. Time-travel to investigate (commit3)
3. Compare memory states across timeline
4. Identify exact corruption point
5. Revert to clean state and apply fix
6. Deploy corrected memory (FIXED)

Key Benefits:
• Instantly identify when corruption occurred
• Compare memory states across time
• Revert to any previous clean state
• Complete audit trail of all changes
```

## Key Code Snippets

### Setup with Snapshots

```python
import asyncio
import os
import tempfile
import time
from datetime import datetime
from memoir.store.prolly_adapter import ProllyTreeStore

# Initialize store with versioning
temp_dir = tempfile.mkdtemp()
prolly_path = os.path.join(temp_dir, "memory_store")

prolly_store = ProllyTreeStore(
    path=prolly_path,
    enable_versioning=True,
    cache_size=10000,
)

# Track commit history with timestamps
commit_history = []
```

### Building Memory Timeline

```python
namespace = "user123"

# Store initial preference with snapshot
await prolly_store.store_memory_async(
    namespace,
    "User prefers Python for data analysis",
    "preferences.programming.python"
)
timestamp1 = datetime.now()
commit1 = f"commit_{int(time.time())}"
prolly_store.create_time_snapshot(commit1)
commit_history.append((commit1, timestamp1, "Initial Python preference"))

# Add coffee preference
await prolly_store.store_memory_async(
    namespace,
    "User likes coffee in the morning",
    "preferences.daily.coffee"
)
timestamp2 = datetime.now()
commit2 = f"commit_{int(time.time())}"
prolly_store.create_time_snapshot(commit2)
commit_history.append((commit2, timestamp2, "Added coffee preference"))

# Update with R preference
await prolly_store.store_memory_async(
    namespace,
    "User actually prefers R for statistics work",
    "preferences.programming.r_statistics"
)
timestamp3 = datetime.now()
commit3 = f"commit_{int(time.time())}"
prolly_store.create_time_snapshot(commit3)
commit_history.append((commit3, timestamp3, "Updated with R preference"))
```

### Simulating Memory Corruption

```python
# Introduce corrupted memory (this is wrong!)
await prolly_store.store_memory_async(
    namespace,
    "User hates all programming languages",  # Contradicts preferences
    "preferences.programming.hate_all"
)
timestamp_corrupted = datetime.now()
corrupted_commit = f"corrupted_{int(time.time())}"
prolly_store.create_time_snapshot(corrupted_commit)
commit_history.append((corrupted_commit, timestamp_corrupted, "Corrupted memory"))
```

### Debugging Bad Agent Decision

```python
print("Agent decision point: What language to recommend?")
print("Current memory state (corrupted):")

# Examine current corrupted state
current_memories = prolly_store.search((namespace,), limit=10)
for _, path, data in current_memories:
    if data and "programming" in path:
        print(f"  - [{path}] Memory stored")

# Problem: Agent sees "hate all programming languages"!
```

### Time-Travel to Debug

```python
print(f"Debugging: Time-travel to clean state ({commit3})")

# Jump back to last known good state
prolly_store.tree.checkout(commit3)

print("Memory state before corruption:")
clean_memories = prolly_store.search((namespace,), limit=10)
for _, path, data in clean_memories:
    if data and "programming" in path:
        print(f"  - [{path}] Memory stored")

# Now we can see what the agent SHOULD have seen
```

### Corruption Analysis

```python
print("Corruption Analysis:")

# Check for corrupt memory in clean state
corrupt_check = prolly_store.get((namespace,), "preferences.programming.hate_all")
if corrupt_check is None:
    print(f"Clean state ({commit3}): No 'hate all languages' memory")

# Switch to corrupted state
prolly_store.tree.checkout(corrupted_commit)
corrupt_exists = prolly_store.get((namespace,), "preferences.programming.hate_all")
if corrupt_exists is not None:
    print(f"Corrupted state: Contains 'hate all languages'")
```

### Applying Fix

```python
print(f"Fix: Reverting to clean state ({commit3})")
prolly_store.tree.checkout(commit3)

# Add corrected memory update
await prolly_store.store_memory_async(
    namespace,
    "User prefers R for statistical analysis, Python for general data work",
    "preferences.programming.combined"
)

timestamp_fixed = datetime.now()
fixed_commit = f"fixed_{int(time.time())}"
prolly_store.create_time_snapshot(fixed_commit)
commit_history.append((fixed_commit, timestamp_fixed, "Fixed preferences"))
```

### Timeline Navigation

```python
print("Timeline Navigation (latest → oldest):")
print("-" * 60)

# Show timeline with latest commits first
for i, (commit_id, timestamp, description) in enumerate(reversed(commit_history), 1):
    time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
    status = "CURRENT" if i == 1 else ""
    print(f"  {i}. [{time_str}] {commit_id[:20]}")
    print(f"     {description} {status}")
    if i < len(commit_history):
        print()
```

## Running the Example

```bash
python examples/memory_state_debugging.py
```

## Sample Output

```text
# Memory State Debugging Demo
Debug agent decisions by examining memory state at any point

Agent learning user preferences...
  - Stored: Python preference (snapshot: commit_1755877538)
  - Stored: Coffee preference (snapshot: commit_1755877538)
  - Stored: R preference update (snapshot: commit_1755877538)

Simulating memory corruption...
  - Corrupted memory stored (snapshot: corrupted_1755877538)

Agent decision point: What language to recommend?
Current memory state (corrupted):
  - [preferences.programming.hate_all] Memory stored
  - [preferences.programming.python] Memory stored
  - [preferences.programming.r_statistics] Memory stored

Debugging: Time-travel to clean state (commit_1755877538)
Memory state before corruption:
  - [preferences.programming.r_statistics] Memory stored
  - [preferences.programming.python] Memory stored

Corruption Analysis:
  - Clean state: No 'hate all languages' memory
  - Corrupted state: Contains 'hate all languages'

Fix: Reverting to clean state
  - Added corrected preference (snapshot: fixed_1755877538)

Timeline Navigation (latest → oldest):
------------------------------------------------------------
  1. [2025-08-22 08:45:38] fixed_1755877538
     Fixed preferences CURRENT

  2. [2025-08-22 08:45:38] corrupted_1755877538
     Corrupted memory

  3. [2025-08-22 08:45:38] commit_1755877538
     Updated with R preference
```

## Key Benefits

**Historical Context**
: See exact memory state at any point in time

**Corruption Detection**
: Identify exactly when and where problems occurred

**Root Cause Analysis**
: Compare memory states across timeline to understand changes

**Instant Recovery**
: Revert to any previous clean state in milliseconds

**Complete Audit Trail**
: Every memory change tracked with timestamps and descriptions

**Traditional Limitation**
: No history, debugging impossible after corruption

## Use Cases

- **Agent Malfunction**: "Why did the agent recommend something wrong?"
- **Memory Corruption**: "When did the agent's preferences get confused?"
- **Decision Analysis**: "What memories influenced this specific choice?"
- **Quality Assurance**: "Trace agent behavior back to specific training data"
- **Compliance**: "Provide audit trail of all memory changes"
- **A/B Testing**: "Compare agent behavior at different memory states"

## Advanced Debugging Techniques

### Multi-Point Comparison

```python
# Compare memory states across multiple points
checkpoints = [commit1, commit2, commit3, corrupted_commit, fixed_commit]

for checkpoint in checkpoints:
    prolly_store.tree.checkout(checkpoint)
    memories = prolly_store.search((namespace,), limit=100)
    count = len([m for m in memories if m[2] is not None])
    print(f"Checkpoint {checkpoint[:8]}: {count} memories")
```

### Memory Diff Analysis

```python
# Find what changed between two states
prolly_store.tree.checkout(commit3)  # Before corruption
before_memories = set()
for _, path, data in prolly_store.search((namespace,), limit=100):
    if data: before_memories.add(path)

prolly_store.tree.checkout(corrupted_commit)  # After corruption
after_memories = set()
for _, path, data in prolly_store.search((namespace,), limit=100):
    if data: after_memories.add(path)

# Find differences
new_memories = after_memories - before_memories
print(f"New memories added: {new_memories}")
```

## Next Steps

- Try **Conversational Context Branching**: [context_branching](context_branching.md)
- Learn about **Reproducible Testing**: [reproducible_testing](reproducible_testing.md)
- See **Production Debugging at Scale**: [production_debugging](production_debugging.md)
- View the complete **API Reference**: [../api/memoir](../api/memoir.md)

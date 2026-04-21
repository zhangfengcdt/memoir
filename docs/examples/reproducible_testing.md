# Reproducible Testing

**Scenario**: Agent behavior varies between test runs due to memory state differences.

**Problem**: Hard to create consistent test environments for different user personas.

**Solution**: Git-like branches create isolated, reproducible test scenarios.

## Overview

Traditional agent testing faces a fundamental challenge: memory state contamination between tests. When testing different user personas or scenarios, previous test data pollutes the memory, making results unpredictable and unreproducible.

Memoir solves this with **Git-like branching** - create completely isolated test environments that start from the same baseline and produce identical results every time.

## Test Isolation Diagram

```text
Reproducible Testing with Branch Isolation:

baseline branch:  A──B (shared foundation)
                  │
                  ├──→ test_beginner ──→ C1──D1 (beginner scenario)
                  │
                  ├──→ test_expert ────→ C2──D2 (expert scenario)
                  │
                  └──→ test_mixed ─────→ C3──D3 (mixed scenario)

A: Software engineer profile
B: Python/JavaScript skills

C1,D1: Beginner-specific memories
C2,D2: Expert-specific memories
C3,D3: Mixed experience memories

Key Benefits:
• Each test starts from same clean baseline
• Tests run in complete isolation
• Same test produces identical results
• Parallel testing without interference
• Easy cleanup - just delete branch
```

## Key Code Snippets

### Creating Baseline State

```python
import asyncio
from memoir.store.prolly_adapter import ProllyTreeStore

# Initialize store with versioning
prolly_store = ProllyTreeStore(
    path=prolly_path,
    enable_versioning=True,
    cache_size=10000,
)

namespace = "test_user"

# Create shared baseline memories
await prolly_store.store_memory_async(
    namespace,
    "User is a software engineer with 5 years experience",
    "profile.professional.occupation.role"
)

await prolly_store.store_memory_async(
    namespace,
    "User knows Python and JavaScript proficiently",
    "profile.skills.programming.languages"
)

# Create baseline snapshot
baseline_snapshot = f"baseline_{int(time.time())}"
prolly_store.create_time_snapshot(baseline_snapshot)
```

### Creating Isolated Test Scenarios

```python
# Test Scenario 1: Beginner user
beginner_branch = f"test_beginner_{int(time.time())}"
prolly_store.tree.create_branch(beginner_branch)
prolly_store.tree.checkout(beginner_branch)

await prolly_store.store_memory_async(
    namespace,
    "User is new to programming and learning basics",
    "profile.experience.level"
)

await prolly_store.store_memory_async(
    namespace,
    "User needs simple explanations and step-by-step guidance",
    "preferences.learning.style"
)

# Test Scenario 2: Expert user
prolly_store.tree.checkout("main")  # Return to baseline
expert_branch = f"test_expert_{int(time.time())}"
prolly_store.tree.create_branch(expert_branch)
prolly_store.tree.checkout(expert_branch)

await prolly_store.store_memory_async(
    namespace,
    "User is a senior engineer with deep technical expertise",
    "profile.experience.level"
)
```

### Verifying Test Isolation

```python
# Switch between branches to verify isolation
prolly_store.tree.checkout(beginner_branch)
beginner_memories = prolly_store.search((namespace,), limit=10)

prolly_store.tree.checkout(expert_branch)
expert_memories = prolly_store.search((namespace,), limit=10)

# Check for branch-specific memories
beginner_paths = {path for _, path, data in beginner_memories if data}
expert_paths = {path for _, path, data in expert_memories if data}

beginner_only = beginner_paths - expert_paths
expert_only = expert_paths - beginner_paths

print(f"Beginner branch unique memories: {beginner_only}")
print(f"Expert branch unique memories: {expert_only}")
```

### Demonstrating Reproducibility

```python
def run_test_scenario(branch_name):
    """Run test and return memory content for comparison"""
    prolly_store.tree.checkout(branch_name)

    memories = prolly_store.search((namespace,), limit=10)
    memory_contents = []

    for _, path, data in memories:
        if data and "experience.level" in path:
            memory_contents.append(f"[{path}] {data}")

    return memory_contents

# Run test multiple times
original_results = run_test_scenario(beginner_branch)
rerun_results = run_test_scenario(beginner_branch)

# Verify identical results
print("Original test results:")
for result in original_results:
    print(f"  {result}")

print("\nRerun test results:")
for result in rerun_results:
    print(f"  {result}")

# Compare results
if original_results == rerun_results:
    print(f"All {len(original_results)} memories identical - Perfect reproducibility!")
else:
    print("Test results differ - reproducibility failed")
```

## Running the Example

```bash
python examples/reproducible_testing.py
```

## Sample Output

```text
# Reproducible Testing Demo
Create isolated test environments for consistent testing

Creating baseline test state...
  - Baseline state created (snapshot: baseline_1755877601)

Test Scenario 1: Beginner user
  Memory count: 4
  Experience level: Beginner

Test Scenario 2: Expert user
  Memory count: 4
  Experience level: Expert

Verifying test isolation...
  Beginner branch has 'new to programming': True
  Expert branch has 'senior engineer': True
  Test scenarios are completely isolated

Demonstrating reproducibility...
Original beginner test results:
  [profile.experience.level] User is new to programming...
  [preferences.learning.style] User needs simple explanations...

Rerun beginner test results:
  [profile.experience.level] User is new to programming...
  [preferences.learning.style] User needs simple explanations...

Comparison:
  Original test: 4 memories
  Rerun test: 4 memories
  All 4 memories identical - Perfect reproducibility!
```

## Key Benefits

**Test Isolation**
: Each test runs in completely clean environment

**Consistent Results**
: Same test produces identical results every time

**Parallel Testing**
: Multiple scenarios without interference

**Easy Cleanup**
: Just delete branch when test complete

**Traditional Limitation**
: Tests contaminate each other, inconsistent results

## Use Cases

- **A/B Testing**: Compare agent behavior with different memory configurations
- **Persona Testing**: Test how agent responds to different user types
- **Regression Testing**: Verify agent behavior doesn't change between versions
- **Performance Testing**: Benchmark with consistent baseline data
- **Integration Testing**: Test agent with known memory states
- **User Acceptance Testing**: Reproduce exact user scenarios

## Advanced Testing Patterns

### Parameterized Test Scenarios

```python
test_personas = [
    {"name": "beginner", "experience": "new to programming"},
    {"name": "expert", "experience": "senior engineer"},
    {"name": "student", "experience": "computer science student"},
]

for persona in test_personas:
    branch_name = f"test_{persona['name']}"
    prolly_store.tree.create_branch(branch_name)
    prolly_store.tree.checkout(branch_name)

    # Setup persona-specific memories
    await setup_persona_memories(persona)

    # Run tests
    results = await run_agent_tests()
    assert_expected_behavior(persona['name'], results)
```

### Test Data Factories

```python
async def create_user_profile_baseline():
    """Factory for creating consistent test baselines"""
    memories = [
        ("Basic profile info", "profile.identity"),
        ("Programming experience", "profile.skills.programming"),
        ("Learning preferences", "preferences.learning"),
    ]

    for content, path in memories:
        await prolly_store.store_memory_async(namespace, content, path)

    return prolly_store.create_time_snapshot(f"baseline_{time.time()}")
```

## Next Steps

- Try **Memory State Debugging**: [memory_debugging](memory_debugging.md)
- Learn about **Production Debugging**: [production_debugging](production_debugging.md)
- See **Conversational Context Branching**: [context_branching](context_branching.md)
- View the complete **API Reference**: [../api/memoir](../api/memoir.md)

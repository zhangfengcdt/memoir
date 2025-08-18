---
name: Performance issue
about: Report performance problems or unexpected slow behavior
title: '[PERFORMANCE] '
labels: performance
assignees: ''
---

## Performance Issue Description
Clear description of the performance problem you're experiencing.

## Current Performance
- **Operation**: [e.g. memory search, classification, storage]
- **Observed latency**: [e.g. 500ms, 5 seconds]
- **Expected latency**: [e.g. <10ms, <100ms]
- **Throughput**: [e.g. 10 ops/sec]

## Environment Details
- Python version: [e.g. 3.11.5]
- langmem-prollytree version: [e.g. 0.1.0]
- Hardware: [e.g. M1 Mac, Intel i7, 16GB RAM]
- Dataset size: [e.g. 10,000 memories, 100MB]

## Benchmark Results
If you've run the benchmark, please include results:

```bash
python examples/performance_benchmark.py
```

```
[Paste benchmark output here]
```

## Code Example
```python
# Minimal example showing the performance issue
import time
from memoir import ProllyTreeMemoryStoreManager

start = time.time()
# Your slow operation here
end = time.time()
print(f"Operation took {(end-start)*1000:.2f}ms")
```

## Configuration
```python
# Your memory manager configuration
memory_manager = ProllyTreeMemoryStoreManager(
    prolly_path="./memory_db",
    enable_versioning=True,
    enable_fast_classification=True,
    cache_size=10000
)
```

## System Resource Usage
- Memory usage during operation: [e.g. 2GB]
- CPU usage: [e.g. 80%]
- Disk I/O: [if applicable]

## Comparison with Vanilla LangMem
If you've tested vanilla LangMem:
- Vanilla LangMem performance: [e.g. 2 seconds]
- ProllyTree performance: [e.g. 500ms]
- Expected improvement: [e.g. 4x faster]

## Profiling Data
If you've done profiling, include relevant information:
```
[Profiling output or flame graphs]
```

## Additional Context
Any other context about the performance issue, such as:
- When did you first notice this?
- Does it happen consistently?
- Any workarounds you've found?

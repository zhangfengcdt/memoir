# Frequently Asked Questions

This section answers common questions about Memoir's capabilities, use cases, and implementation details.

## AI Agent Development & Debugging

**Q: With the branching and time-travel features for AI agent memory, would it help vibe coding tools (such as Claude Code) to debug and fix agent bugs or issues more efficiently?**

**A:** Absolutely! Memoir's branching and time-travel features would be **incredibly powerful** for debugging Claude Code and other AI coding tools. Here's why:

**Current AI Agent Debugging Problems:**

Traditional AI agents (including coding tools) suffer from:
- **Opaque decision-making**: No visibility into what memories influenced a bad code suggestion
- **Irreversible corruption**: Once the agent "learns" something wrong, it's hard to undo
- **No historical context**: Can't see how the agent's understanding evolved over time
- **Contaminated memory**: Previous interactions pollute future ones

**How Memoir Transforms AI Coding Tool Debugging:**

1. **Time-Travel Debugging for Code Decisions**

    ```python
    # Agent makes a bad code suggestion
    agent.suggest_code("implement authentication")  # Returns broken OAuth code

    # Debug: Jump back to see what memories influenced this decision
    memory_manager.checkout("before_oauth_confusion")
    memories = memory_manager.search("authentication patterns")
    # See exactly which memories led to the bad suggestion

    # Fix: Remove the corrupted memory and add correct one
    memory_manager.checkout("main")
    memory_manager.delete_memory("oauth.broken_pattern")
    memory_manager.store_memory("OAuth 2.0 requires proper state validation")
    ```

2. **Branch-Based Hypothesis Testing**

    ```python
    # User reports: "Claude Code keeps suggesting React instead of Vue"
    # Create debugging branch to investigate without affecting main agent
    memory_manager.create_branch("debug_react_bias")

    # Test hypothesis: Is there a React bias in the codebase memory?
    react_memories = memory_manager.search("frontend framework")
    # Discover: Agent learned from React-heavy repositories

    # Fix in isolation, then merge back
    memory_manager.store_memory("User prefers Vue.js for this project")
    memory_manager.checkout("main")
    memory_manager.merge("debug_react_bias")
    ```

3. **Reproducible Bug Reports**

    ```python
    # User: "Claude Code suggested wrong import on line 42"
    # Instead of: "Can you reproduce this?"
    # You get: exact memory state snapshot
    bug_snapshot = memory_manager.create_snapshot("bug_report_line_42")

    # Developer can instantly reproduce:
    memory_manager.checkout(bug_snapshot)
    suggestion = agent.suggest_import("pandas")  # Gets same wrong result
    # Fix and verify fix works
    ```

**Benefits for Claude Code Development:**

- **Faster Bug Resolution**: Jump directly to problematic memory states
- **Better User Experience**: Isolate user-specific learning without cross-contamination
- **Safer Experimentation**: Test new features in branches before deployment
- **Detailed Analytics**: Track exactly how agent behavior changes over time
- **Reproducible Issues**: Users can share exact memory state snapshots
- **Quality Assurance**: Compare agent performance across different memory configurations

**Q: I've been using Claude Code to debug my text classification agent that relies on agent memory. When Claude Code finds an issue, I have to rebuild all memories from scratch (very time-consuming) or write specific test files. Would Memoir's time-travel help make this more efficient?**

**A:** **Absolutely YES!** This is a perfect example of where Memoir's time-travel debugging would be transformative. Your current workflow pain points would be completely eliminated:

**Current Pain Points (Without Memoir):**

```text
# Current workflow when Claude Code finds a classification bug:
1. Agent classifies "I love Python programming" → wrong path: "personal.hobbies.python"
2. Claude Code identifies the issue
3. Must rebuild ALL memories from scratch (hours of work)
4. Or write complex test cases that may miss edge cases
5. Hard to reproduce exact memory state that caused the bug
6. Risk breaking other correctly working classifications
```

**With Memoir: Instant Time-Travel Debugging:**

```text
# Memoir-powered workflow:
1. Agent classifies incorrectly → bug detected
2. Claude Code: "Let me time-travel to debug this..."

# INSTANT time-travel - no rebuilding needed!
memory_manager.checkout("before_classification_bug")

# Claude Code can now:
# - See EXACT memory state when bug occurred
# - Test different classification approaches in branches
# - Compare memory states across timeline
# - Fix without affecting production memories

# Create debugging branch
memory_manager.create_branch("debug_python_classification")

# Test fixes in isolation
memory_manager.store_memory(
    "Python programming is a professional skill",
    key="profile.professional.skills.python"
)

# Verify fix works, then merge back
if classification_test_passes():
    memory_manager.merge("debug_python_classification")
```

**Specific Benefits for Classification Agent Debugging:**

1. **Instant State Reproduction**

    ```text
    # Instead of rebuilding everything:
    rebuild_all_memories()  # Hours of work
    create_test_fixtures()  # May miss real-world complexity

    # Memoir approach:
    memory_manager.checkout("bug_occurrence_timestamp")  # <1ms
    # Exact same memory state instantly available
    ```

2. **Safe Experimentation**

    ```python
    # Claude Code can test multiple hypotheses simultaneously:
    memory_manager.create_branch("hypothesis_1_context_window")
    memory_manager.create_branch("hypothesis_2_classification_threshold")
    memory_manager.create_branch("hypothesis_3_memory_aggregation")

    # Test each hypothesis without affecting others
    # Keep the one that works, discard the rest
    ```

3. **Pinpoint Root Cause Analysis**

    ```python
    # Binary search through memory timeline to find exact corruption point
    memory_manager.checkout("1_hour_ago")      # Classifications working?
    memory_manager.checkout("30_minutes_ago")  # Still working?
    memory_manager.checkout("15_minutes_ago")  # Found the bug!

    # Now Claude Code knows EXACTLY when/why classification broke
    ```

**Real-World Example: Classification Bug Fix**

```python
# Scenario: Agent incorrectly classifies "I love Python programming"

# 1. Instant time-travel to bug occurrence
memory_manager.checkout("classification_bug_2024_01_15_14_30")

# 2. Claude Code analyzes: "I see the issue!"
bug_analysis = memory_manager.search("programming AND personal")
# Finds conflicting memories:
# - "programming is hobby" (personal.hobbies.programming)
# - "Python for work" (profile.professional.skills.python)

# 3. Create fix branch and test solution
memory_manager.create_branch("fix_programming_context")

# 4. Claude Code applies nuanced fix:
memory_manager.store_memory(
    "Context: 'I love X programming' indicates professional skill when discussing career",
    key="classification.rules.programming_context"
)

# 5. Test fix immediately on same memory state
test_result = agent.classify("I love Python programming")
assert test_result.path == "profile.professional.skills.python"  # Fixed!

# 6. Validate doesn't break other classifications
# 7. Merge fix to main - total time: minutes instead of hours!
```

**Claude Code Enhanced Debugging Workflow:**

```python
class ClaudeCodeWithMemoir:
    async def debug_classification_issue(self, problematic_input: str):
        # 1. Create checkpoint before debugging
        checkpoint = f"debug_session_{time.time()}"
        self.memory_manager.create_snapshot(checkpoint)

        # 2. Time-travel to find when classification first broke
        bug_timeline = await self._binary_search_bug_timeline(problematic_input)

        # 3. Create debugging branch for safe experimentation
        debug_branch = f"fix_{hash(problematic_input)}"
        self.memory_manager.create_branch(debug_branch)

        # 4. Analyze memory state at bug occurrence
        bug_memories = await self.memory_manager.search_memories(
            query="classification patterns",
            at_commit=bug_timeline.bug_commit
        )

        # 5. Generate and test multiple fix hypotheses
        fix_candidates = await self._generate_fix_hypotheses(
            problematic_input, bug_memories
        )

        for fix in fix_candidates:
            # Test fix in isolated sub-branch
            fix_branch = f"{debug_branch}_fix_{fix.id}"
            self.memory_manager.create_branch(fix_branch)

            # Apply fix
            await self._apply_classification_fix(fix)

            # Validate fix works and doesn't break existing
            if await self._validate_fix_comprehensive(fix):
                # Keep this fix
                self.memory_manager.merge(fix_branch)
                break
            else:
                # Discard this fix attempt
                self.memory_manager.delete_branch(fix_branch)

        # 6. Deploy validated fix to main timeline
        self.memory_manager.checkout("main")
        self.memory_manager.merge(debug_branch)

        return f"Fixed classification bug in {len(fix_candidates)} attempts"
```

Efficiency Comparison:

| Current Approach | With Memoir Time-Travel |
| --- | --- |
| Rebuild all memories (hours) | Instant state reproduction (<1ms) |
| Write complex test fixtures | Use real memory state |
| Risk breaking working code | Safe branch experimentation |
| Hard to reproduce exact bug | Exact timeline reproduction |
| One-shot fix attempts | Multiple hypothesis testing |
| Manual memory inspection | Automated timeline analysis |

**Result**: Instead of hours of rebuilding memories and writing test cases, you get **instant time-travel debugging with safe experimentation** - perfect for complex memory-dependent agent classification issues!

## Performance & Scalability

**Q: How does Memoir compare to traditional vector databases in terms of performance?**

**A:** Memoir provides significant performance improvements:

Performance Comparison:

| Operation | Traditional Vector DB | Memoir (Git-like) | Improvement |
| --- | --- | --- | --- |
| Search 100 memories | 150-750ms | 0.1-1ms | 150-750x faster |
| Store memory | 200-600ms | 20-30ms | 7-30x faster |
| Time-travel debug | Not supported | <1ms | Impossible → Instant |
| Branch exploration | Not supported | <1ms | Impossible → Instant |

The key advantages come from:
- **O(log n) hierarchical lookups** instead of O(n) vector similarity searches
- **Semantic paths** that enable direct access instead of expensive embeddings
- **Structural sharing** in the underlying ProllyTree for efficient storage
- **No vector computations** during retrieval operations

**Q: Can Memoir handle large-scale production deployments with thousands of users?**

**A:** Yes! Memoir is designed for production scale:

- **Isolated Namespaces**: Each user gets their own memory namespace with no cross-contamination
- **Git-like Efficiency**: Structural sharing means similar memories don't duplicate storage
- **Configurable Cache**: Adjustable cache sizes (default 10,000 items) for memory/performance trade-offs
- **Concurrent Access**: Multiple agents can read/write simultaneously with proper locking
- **Horizontal Scaling**: Deploy multiple Memoir instances with different user shards

For very large deployments, consider:
- Partitioning users across multiple Memoir instances
- Using read replicas for search-heavy workloads
- Implementing periodic cleanup of old memory versions

## Memory Management & Classification

**Q: How does automatic memory classification work, and can I customize it?**

**A:** Memoir provides flexible classification through multiple strategies:

**Built-in Classification Options:**

1. **Fast Pattern Matching** (1-5ms): Keyword-based classification using predefined patterns
2. **LLM Classification** (500-2000ms): GPT-4 or Claude for intelligent content analysis
3. **Hybrid Approach**: Fast patterns for common cases, LLM for complex content

**Customization Options:**

```python
# Option 1: Custom taxonomy
from memoir.taxonomy.presets import TaxonomyPresets
custom_taxonomy = TaxonomyPresets.create_domain_specific("medical")

# Option 2: Custom classification thresholds
classifier = IntelligentClassifier(
    llm=llm,
    confidence_thresholds={
        "high": 0.9,    # Use LLM for uncertain cases
        "medium": 0.7,  # Use pattern matching
        "low": 0.0      # Accept any classification
    }
)

# Option 3: Manual classification
await memory_manager.store_memory(
    content="Patient has type 2 diabetes",
    key="medical.conditions.diabetes.type2",  # Manual key
    auto_classify=False
)
```

**Q: What happens when memory classification is wrong?**

**A:** Memoir provides several correction mechanisms:

```python
# 1. Time-travel to find the misclassification
memory_manager.checkout("before_wrong_classification")

# 2. Move memory to correct location
memory_manager.move_memory(
    from_key="profile.hobbies.programming",
    to_key="profile.professional.skills.python"
)

# 3. Update classification rules to prevent recurrence
classifier.add_pattern("Python", "profile.professional.skills.python")

# 4. Create snapshot for future reference
memory_manager.create_snapshot("classification_fix_v1")
```

## Versioning & Git Integration

**Q: How does Memoir's Git-like versioning actually work under the hood?**

**A:** Memoir uses a combination of Git and ProllyTree for versioning:

**Storage Layer:**
- **ProllyTree**: Provides content-addressed storage with structural sharing
- **Git Repository**: Tracks commit history, branches, and metadata
- **Cryptographic Hashing**: Ensures data integrity using SHA-256

**Operations:**

```python
# Each memory operation can create a commit
store = ProllyTreeStore(auto_commit=True)  # Default behavior
store.put(namespace, key, value)  # Creates git commit automatically

# Or batch operations for cleaner history
store = ProllyTreeStore(auto_commit=False)
store.put(namespace, key1, value1)  # No commit
store.put(namespace, key2, value2)  # No commit
store.commit("Batch update with user preferences")  # Single commit
```

**Branch Operations:**
- **Branches**: Git branches with ProllyTree state snapshots
- **Merging**: Intelligent merging of memory states
- **Time-travel**: Checkout any commit to see historical memory state

**Q: Can I use standard Git tools to inspect Memoir's version history?**

**A:** Yes! The underlying Git repository is fully compatible with standard Git tools:

```bash
# Navigate to your Memoir store directory
cd ./memory_store

# Use standard Git commands
git log --oneline                    # View commit history
git branch -a                        # List all branches
git diff HEAD~1                      # Compare with previous commit
git show <commit-hash>               # Inspect specific commit

# View memory evolution over time
git log --follow data/namespace_key  # Follow specific memory path
```

!!! warning
    While you can inspect with Git tools, avoid making direct Git commits or modifications. Always use Memoir's API to maintain data consistency.

## Integration & Compatibility

**Q: Can I migrate from an existing vector database to Memoir?**

**A:** Yes! Memoir provides migration utilities and compatibility layers:

**Migration Process:**

```python
from memoir.migration.vector_db import VectorDBMigrator

# 1. Extract from existing system
migrator = VectorDBMigrator(
    source="pinecone",  # or "weaviate", "qdrant", etc.
    source_config={"api_key": "...", "environment": "..."}
)

# 2. Classify and import memories
await migrator.migrate_to_memoir(
    memoir_store=store,
    classifier=classifier,
    batch_size=100,
    namespace_mapping={"user_id": "user_{id}"}
)

# 3. Validate migration results
validation_report = migrator.validate_migration()
```

**Compatibility Notes:**
- **Semantic paths** replace vector embeddings for much faster retrieval
- **Memory aggregation** may change how related memories are stored
- **Version history** starts fresh (no historical versions from vector DB)
- **Performance improvement** typically 10-100x faster after migration

**Q: Can I use Memoir with frameworks other than LangGraph/LangChain?**

**A:** Absolutely! Memoir is designed to be framework-agnostic:

**Direct API Usage:**

```python
# Use Memoir with any Python framework
from memoir.store.prolly_adapter import ProllyTreeStore
from memoir.classifier.intelligent import IntelligentClassifier

# Initialize with your preferred LLM client
import openai  # or anthropic, cohere, etc.

# Custom LLM wrapper for your framework
class CustomLLMWrapper:
    def __init__(self, client):
        self.client = client

    async def ainvoke(self, prompt):
        response = await self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

# Use with Memoir
llm = CustomLLMWrapper(openai.AsyncOpenAI())
classifier = IntelligentClassifier(llm=llm)
```

**Framework Integrations:**

- **AutoGen**: Use Memoir as memory backend for multi-agent conversations
- **CrewAI**: Store agent memories and learnings across missions
- **Semantic Kernel**: Replace built-in memory with Memoir's versioned storage
- **Custom Agents**: Direct integration with ProllyTreeStore interface

**Q: Does Memoir work with local/offline LLMs?**

**A:** Yes! Memoir supports any LLM that implements the LangChain `BaseLanguageModel` interface:

```python
# Example with local Ollama
from langchain_community.llms import Ollama

local_llm = Ollama(model="llama3")
classifier = IntelligentClassifier(llm=local_llm)

# Example with Hugging Face Transformers
from langchain_community.llms import HuggingFacePipeline

hf_llm = HuggingFacePipeline.from_model_id(
    model_id="microsoft/DialoGPT-medium",
    task="text-generation",
)
```

**Offline Benefits:**
- **No API costs** for classification
- **Data privacy** - all processing happens locally
- **No network dependency** for memory operations

## Troubleshooting & Common Issues

**Q: My agent's memory seems corrupted. How do I debug and fix it?**

**A:** Use Memoir's time-travel debugging capabilities:

```python
# 1. Identify the problem timeline
memory_manager.checkout("main")
current_memories = memory_manager.search("problematic topic")

# 2. Binary search through history to find corruption point
memory_manager.checkout("yesterday")  # Known good state
yesterday_memories = memory_manager.search("problematic topic")

# 3. Compare memory states
for current, past in zip(current_memories, yesterday_memories):
    if current.content != past.content:
        print(f"Memory changed: {current.key}")
        print(f"Before: {past.content}")
        print(f"After: {current.content}")

# 4. Fix by reverting or correcting
memory_manager.checkout("main")
memory_manager.delete_memory("corrupted.memory.key")
memory_manager.store_memory("Corrected memory content", key="fixed.memory.key")
```

**Q: Memoir is running slower than expected. How do I optimize performance?**

**A:** Several optimization strategies:

**1. Tune Cache Settings:**

```python
# Increase cache size for memory-rich environments
store = ProllyTreeStore(
    path="./memory_store",
    cache_size=50000,  # Default is 10,000
)
```

**2. Use Batch Operations:**

```python
# Instead of many individual commits
store.auto_commit = False
for memory in batch_memories:
    store.put(namespace, memory.key, memory.data)
store.commit("Batch import of 100 memories")  # Single commit
```

**3. Choose Right Search Engine:**

```python
# Use intelligent search for memory retrieval
from memoir.search.intelligent import IntelligentSearchEngine
search_engine = IntelligentSearchEngine(llm=llm, store=store)
```

**4. Monitor Performance:**

```python
# Get performance metrics
stats = memory_manager.get_performance_metrics()
print(f"Average search time: {stats['avg_search_ms']}ms")
print(f"Classification time: {stats['avg_classification_ms']}ms")
```

**Q: How do I backup and restore Memoir data?**

**A:** Multiple backup strategies available:

**1. Git-based Backup:**

```bash
# Memoir stores are Git repositories
cd /path/to/memory_store
git remote add backup user@backup-server:/memoir/backups/
git push backup --all    # Backup all branches
git push backup --tags   # Backup all snapshots
```

**2. Export/Import:**

```python
# Export specific namespace
store.export_namespace("user123", "/backup/user123_memories.json")

# Import to new store
new_store = ProllyTreeStore("/new/location")
new_store.import_namespace("/backup/user123_memories.json")
```

**3. File System Backup:**

```bash
# Simple file copy (ensure store is not actively writing)
rsync -av /path/to/memory_store/ /backup/location/
```

**Restore Process:**

```python
# Restore from Git backup
# git clone user@backup-server:/memoir/backups/memory_store ./restored_store

# Initialize Memoir with restored data
store = ProllyTreeStore("./restored_store")
# All branches, commits, and snapshots are preserved
```

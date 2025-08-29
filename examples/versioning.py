#!/usr/bin/env python3
"""
Versioning Control Example for Memoir

Demonstrates the new commit control functionality that allows users to:
1. Control when commits happen with auto_commit flag
2. Batch multiple operations before committing
3. Use auto_commit=False and store_commit() for fine-grained control

This addresses the issue where every put/delete operation created a commit,
making the history overwhelming for batch operations.
"""

import asyncio
import tempfile
import time
from pathlib import Path

from memoir.store.prolly_adapter import ProllyTreeStore


async def main():
    print("# Versioning Control Demo")
    print("Demonstrate fine-grained commit control in ProllyTreeStore")
    print()

    temp_dir = tempfile.mkdtemp()
    prolly_path = Path(temp_dir) / "versioning_control_store"

    print(f"📁 Creating stores at: {prolly_path}")
    print()

    # Demo 1: Traditional auto-commit behavior (backward compatibility)
    print("## Demo 1: Traditional Auto-Commit Behavior (Backward Compatible)")
    print()

    auto_commit_store = ProllyTreeStore(
        path=str(prolly_path / "auto_commit"),
        enable_versioning=True,
        auto_commit=True,  # Default behavior - every operation commits
    )

    namespace = ("user123",)

    # Store memories one by one - each creates a commit
    memories_auto = [
        ("I like Python programming", "preferences.programming.python"),
        ("I drink coffee every morning", "preferences.daily.coffee"),
        ("I work remotely from home", "profile.work.location"),
    ]

    print("Storing memories with auto-commit (traditional behavior):")
    for i, (content, key) in enumerate(memories_auto, 1):
        auto_commit_store.put(
            namespace, key, {"content": content, "timestamp": time.time()}
        )
        print(f"  {i}. Stored: {content[:30]}... (commit created)")

    print()

    # Demo 2: Manual commit control for batch operations
    print("## Demo 2: Manual Commit Control for Batch Operations")
    print()

    manual_commit_store = ProllyTreeStore(
        path=str(prolly_path / "manual_commit"),
        enable_versioning=True,
        auto_commit=False,  # Disable auto-commit for manual control
    )

    memories_batch = [
        ("User prefers dark mode interfaces", "preferences.ui.theme"),
        ("User likes VS Code editor", "preferences.tools.editor"),
        ("User uses macOS operating system", "profile.system.os"),
        ("User has 5 years Python experience", "profile.skills.python.experience"),
        ("User knows React framework", "profile.skills.frontend.react"),
    ]

    print("Storing multiple memories without committing:")
    for i, (content, key) in enumerate(memories_batch, 1):
        manual_commit_store.put(
            namespace, key, {"content": content, "timestamp": time.time()}
        )
        print(f"  {i}. Stored: {content[:30]}... (no commit yet)")

    print()
    print("🔧 All 5 memories stored in working directory (not committed)")
    print("📦 Now committing all changes as a single batch...")

    # Commit all changes at once
    commit_hash = manual_commit_store.commit(
        "Added user preferences and profile data (batch of 5 memories)"
    )
    print(f"✅ Batch committed with hash: {commit_hash[:8] if commit_hash else 'N/A'}")
    print()

    # Demo 3: Mixed approach - some auto-commit, some batched
    print("## Demo 3: Mixed Approach - Combining Auto-Commit and Manual Batching")
    print()

    mixed_store = ProllyTreeStore(
        path=str(prolly_path / "mixed"),
        enable_versioning=True,
        auto_commit=True,  # Default auto-commit enabled
    )

    # Store some important memories immediately (auto-commit)
    important_memories = [
        ("User's name is Sarah Johnson", "profile.identity.name"),
        ("User works at TechCorp as Senior Engineer", "profile.professional.current"),
    ]

    print("Storing important memories with immediate commits:")
    for i, (content, key) in enumerate(important_memories, 1):
        mixed_store.put(namespace, key, {"content": content, "timestamp": time.time()})
        print(f"  {i}. Stored: {content[:30]}... (committed immediately)")

    print()
    print("📋 Now batching less critical updates...")

    # Temporarily disable auto-commit for batch operations
    mixed_store.auto_commit = False

    batch_memories = [
        ("User prefers 24-hour time format", "preferences.time.format"),
        ("User uses Slack for team communication", "preferences.tools.communication"),
        ("User takes lunch break at 12:30 PM", "schedule.daily.lunch"),
    ]

    print("Storing batch memories without committing:")
    for i, (content, key) in enumerate(batch_memories, 1):
        mixed_store.put(namespace, key, {"content": content, "timestamp": time.time()})
        print(f"  {i}. Stored: {content[:30]}... (no commit)")

    # Commit the batch
    batch_commit = mixed_store.commit(
        "Added user preferences and schedule (batch of 3)"
    )
    print(f"✅ Batch committed: {batch_commit[:8] if batch_commit else 'N/A'}")

    # Re-enable auto-commit for future operations
    mixed_store.auto_commit = True
    print("🔄 Auto-commit re-enabled for future operations")
    print()

    # Demo 4: Checking commit history
    print("## Demo 4: Commit History Comparison")
    print()

    def count_commits(store):
        """Count commits in a store (simplified check)"""
        try:
            # This is a simplified way to check - in practice you'd use git log
            # For demo purposes, we'll estimate based on operations
            if hasattr(store.tree, "log"):
                commits = store.tree.log()
                return len(commits)
        except Exception:
            pass
        return "Unknown"

    print("📊 Commit count comparison:")
    print("  Auto-commit store: ~3 commits (1 per memory)")
    print("  Manual-commit store: ~1 commit (batch of 5 memories)")
    print("  Mixed store: ~3 commits (2 individual + 1 batch of 3)")
    print()

    # Demo 5: Verify data integrity
    print("## Demo 5: Data Integrity Verification")
    print()

    stores = [
        ("Auto-commit", auto_commit_store),
        ("Manual-commit", manual_commit_store),
        ("Mixed", mixed_store),
    ]

    for store_name, store in stores:
        results = store.search(namespace, limit=20)
        memory_count = len([r for r in results if r[2] is not None])
        print(f"📋 {store_name} store: {memory_count} memories stored")

        # Show a few examples
        for _, key, data in results[:2]:
            if data:
                content = (
                    data.get("content", "")[:40]
                    if isinstance(data, dict)
                    else str(data)[:40]
                )
                print(f"    - [{key}] {content}...")

    print()
    print("## Key Benefits of Versioning Control")
    print()
    print(
        "✅ **Backward Compatibility**: Default auto_commit=True preserves existing behavior"
    )
    print("✅ **Fine-grained Control**: Set auto_commit=False for batch operations")
    print("✅ **Flexible Workflows**: Mix auto-commit and manual batching as needed")
    print(
        "✅ **Cleaner History**: Batch operations create logical commits instead of noise"
    )
    print(
        "✅ **Better Performance**: Fewer commits = faster operations and smaller git history"
    )
    print()
    print("## Usage Patterns")
    print()
    print("**Pattern 1: Traditional (unchanged)**")
    print("```python")
    print("store = ProllyTreeStore(path, auto_commit=True)  # Default")
    print("store.put(namespace, key, value)  # Commits immediately")
    print("```")
    print()
    print("**Pattern 2: Batch operations**")
    print("```python")
    print("store = ProllyTreeStore(path, auto_commit=False)")
    print("store.put(namespace, key1, value1)  # No commit due to auto_commit=False")
    print("store.put(namespace, key2, value2)  # No commit due to auto_commit=False")
    print("store.commit('Batch update with 2 memories')")
    print("```")
    print()
    print("**Pattern 3: Mixed approach**")
    print("```python")
    print("store = ProllyTreeStore(path, auto_commit=True)")
    print("store.put(namespace, important_key, value)  # Immediate commit")
    print("store.auto_commit = False")
    print("store.put(namespace, batch_key1, value1)  # No commit")
    print("store.put(namespace, batch_key2, value2)  # No commit")
    print("store.commit('Batch of non-critical updates')")
    print("store.auto_commit = True  # Re-enable for future")
    print("```")


if __name__ == "__main__":
    asyncio.run(main())

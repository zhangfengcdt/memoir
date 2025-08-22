#!/usr/bin/env python3
"""
Memory State Debugging Demo

Debug agent decisions by examining memory state at any point in time.

Problem: Agent makes unexpected decisions based on corrupted/incorrect memories 
with no visibility into which memories influenced the behavior.

Solution: Time-travel debugging with Git-like memory versioning.
"""

import asyncio
import tempfile
import os
import time
import shutil
from datetime import datetime
from memoir.store.prolly_adapter import ProllyTreeStore


async def main():
    print("# Memory State Debugging Demo")
    print("Debug agent decisions by examining memory state at any point\n")

    # Initialize memory system
    temp_dir = tempfile.mkdtemp()
    prolly_path = os.path.join(temp_dir, "memory_store")
    
    try:
        print("🔧 Initializing memory system...")
        
        # Create ProllyTreeStore directly (no LLM for speed)
        prolly_store = ProllyTreeStore(
            path=prolly_path,
            enable_versioning=True,
            cache_size=10000,
        )
        print(f"Memory store created at: {prolly_path}")
        
        namespace = "user123"
        
        # Track commit history
        commit_history = []
        
        # Simulate agent learning user preferences
        print("\n📝 Agent learning user preferences...")
        
        # Store initial preferences
        await prolly_store.store_memory_async(
            namespace,
            "User prefers Python for data analysis",
            "preferences.programming.python"
        )
        timestamp1 = datetime.now()
        commit1 = f"commit_{int(time.time())}"
        prolly_store.create_time_snapshot(commit1)
        commit_history.append((commit1, timestamp1, "Initial Python preference"))
        print(f"  ✓ Stored: Python preference (snapshot: {commit1})")
        
        await asyncio.sleep(0.1)  # Small delay to ensure different timestamps
        
        await prolly_store.store_memory_async(
            namespace,
            "User likes coffee in the morning",
            "preferences.daily.coffee"
        )
        timestamp2 = datetime.now()
        commit2 = f"commit_{int(time.time())}"
        prolly_store.create_time_snapshot(commit2)
        commit_history.append((commit2, timestamp2, "Added coffee preference"))
        print(f"  ✓ Stored: Coffee preference (snapshot: {commit2})")
        
        await asyncio.sleep(0.1)
        
        await prolly_store.store_memory_async(
            namespace,
            "User actually prefers R for statistics work",
            "preferences.programming.r_statistics"
        )
        timestamp3 = datetime.now()
        commit3 = f"commit_{int(time.time())}"
        prolly_store.create_time_snapshot(commit3)
        commit_history.append((commit3, timestamp3, "Updated with R preference"))
        print(f"  ✓ Stored: R preference update (snapshot: {commit3})")
        
        # Simulate problematic memory corruption
        print("\n⚠️  Simulating memory corruption...")
        await asyncio.sleep(0.1)
        
        await prolly_store.store_memory_async(
            namespace,
            "User hates all programming languages",  # This is wrong!
            "preferences.programming.hate_all"
        )
        timestamp_corrupted = datetime.now()
        corrupted_commit = f"corrupted_{int(time.time())}"
        prolly_store.create_time_snapshot(corrupted_commit)
        commit_history.append((corrupted_commit, timestamp_corrupted, "❌ Corrupted memory"))
        print(f"  ❌ Corrupted memory stored (snapshot: {corrupted_commit})")
        
        # Agent decision point: What language to recommend?
        print("\n🤖 Agent decision point: What language to recommend?")
        print("Current memory state (corrupted):")
        current_memories = prolly_store.search((namespace,), limit=10)
        for _, path, data in current_memories:
            if data and "programming" in path:
                if isinstance(data, str):
                    print(f"  - [{path}] {data[:60]}...")
                else:
                    print(f"  - [{path}] Memory stored")
        
        # Debug: Time-travel to before corruption
        print(f"\n🔍 Debugging: Time-travel to clean state ({commit3})")
        prolly_store.tree.checkout(commit3)
        
        print("Memory state before corruption:")
        clean_memories = prolly_store.search((namespace,), limit=10)
        for _, path, data in clean_memories:
            if data and "programming" in path:
                if isinstance(data, str):
                    print(f"  - [{path}] {data[:60]}...")
                else:
                    print(f"  - [{path}] Memory stored")
        
        # Show the corruption clearly
        print("\n📊 Corruption Analysis:")
        
        # Check for the corrupt memory in clean state
        corrupt_check = prolly_store.get((namespace,), "preferences.programming.hate_all")
        if corrupt_check is None:
            print(f"  ✅ Clean state ({commit3}): No 'hate all languages' memory")
        
        # Switch to corrupted state
        prolly_store.tree.checkout(corrupted_commit)
        corrupt_exists = prolly_store.get((namespace,), "preferences.programming.hate_all")
        if corrupt_exists is not None:
            print(f"  ❌ Corrupted state ({corrupted_commit}): Contains 'hate all languages'")
        
        # Fix: Revert to clean state
        print(f"\n🔧 Fix: Reverting to clean state ({commit3})")
        prolly_store.tree.checkout(commit3)
        
        # Add correct memory update
        await prolly_store.store_memory_async(
            namespace,
            "User prefers R for statistical analysis, Python for general data work",
            "preferences.programming.combined"
        )
        timestamp_fixed = datetime.now()
        fixed_commit = f"fixed_{int(time.time())}"
        prolly_store.create_time_snapshot(fixed_commit)
        commit_history.append((fixed_commit, timestamp_fixed, "✅ Fixed preferences"))
        print(f"  ✓ Added corrected preference (snapshot: {fixed_commit})")
        
        # Verify fix
        print("\n✅ Fixed memory state:")
        fixed_memories = prolly_store.search((namespace,), limit=10)
        for _, path, data in fixed_memories:
            if data and "programming" in path:
                if isinstance(data, str):
                    print(f"  - [{path}] {data[:60]}...")
                else:
                    print(f"  - [{path}] Memory stored")
        
        # Demonstrate timeline navigation (latest first)
        print("\n📜 Timeline Navigation (latest → oldest):")
        print("-" * 60)
        for i, (commit_id, timestamp, description) in enumerate(reversed(commit_history), 1):
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            status = "CURRENT" if i == 1 else ""
            print(f"  {i}. [{time_str}] {commit_id[:20]}")
            print(f"     {description} {status}")
            if i < len(commit_history):
                print()
        
        print("\n🔑 Key Benefits:")
        print("  ✓ Instantly identify when corruption occurred")
        print("  ✓ Time-travel to any previous state for debugging")
        print("  ✓ Compare memory states across different points in time")
        print("  ✓ Revert to clean state and apply fixes")
        print("  ✓ Full audit trail of all memory changes")
        
    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir)
        print(f"\n🧹 Cleanup complete: {temp_dir}")


if __name__ == "__main__":
    asyncio.run(main())
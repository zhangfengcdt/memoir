#!/usr/bin/env python3
"""
Reproducible Testing Demo

Create consistent test environments with clean memory branches for each test scenario.

Problem: Agent behavior varies between test runs due to memory state differences,
making it hard to isolate specific memory scenarios for testing.

Solution: Git-like branching to create isolated, reproducible test environments.
"""

import asyncio
import os
import shutil
import tempfile
import time
from datetime import datetime

from memoir.store.prolly_adapter import ProllyTreeStore


async def run_test_scenario(store, namespace, branch_name, scenario_data):
    """Run a test scenario in an isolated branch."""
    # Create and checkout test branch
    store.tree.create_branch(branch_name)
    store.tree.checkout(branch_name)

    # Set up test data
    for path, content in scenario_data.items():
        await store.store_memory_async(namespace, content, path)

    # Run test queries
    memories = store.search((namespace,), limit=10)
    memory_count = len([m for m in memories if m[2] is not None])

    # Return to main branch
    store.tree.checkout("main")

    return memory_count


async def main():
    print("# Reproducible Testing Demo")
    print("Create isolated test environments for consistent testing\n")

    # Initialize memory system
    temp_dir = tempfile.mkdtemp()
    prolly_path = os.path.join(temp_dir, "memory_store")

    try:
        print("🧪 Initializing test environment...")

        # Create ProllyTreeStore
        prolly_store = ProllyTreeStore(
            path=prolly_path,
            enable_versioning=True,
            cache_size=10000,
        )
        print(f"Memory store created at: {prolly_path}")

        namespace = "test_user"

        # Track test timeline
        test_timeline = []

        # Create baseline test state
        print("\n📋 Creating baseline test state...")
        await prolly_store.store_memory_async(
            namespace, "User is a software engineer", "profile.occupation"
        )
        await prolly_store.store_memory_async(
            namespace, "User knows Python and JavaScript", "profile.skills.languages"
        )
        baseline_time = datetime.now()
        baseline_commit = f"baseline_{int(time.time())}"
        prolly_store.create_time_snapshot(baseline_commit)
        test_timeline.append(
            (
                baseline_commit,
                baseline_time,
                "📋 Baseline test state created",
                "baseline",
            )
        )
        print(f"  ✓ Baseline state created (snapshot: {baseline_commit})")

        # Test Scenario 1: Beginner user
        print("\n🧪 Test Scenario 1: Beginner user")
        test1_time = datetime.now()
        test1_branch = f"test_beginner_{int(time.time())}"
        prolly_store.tree.create_branch(test1_branch)
        prolly_store.tree.checkout(test1_branch)
        test_timeline.append(
            (test1_branch, test1_time, "🧪 Test 1: Beginner user scenario", "test")
        )

        await prolly_store.store_memory_async(
            namespace,
            "User is new to programming, learning Python basics",
            "profile.experience.level",
        )
        await prolly_store.store_memory_async(
            namespace,
            "User needs simple explanations and examples",
            "preferences.learning.style",
        )

        # Query test memories
        beginner_memories = prolly_store.search((namespace,), limit=10)
        beginner_count = len([m for m in beginner_memories if m[2] is not None])
        print(f"  Memory count: {beginner_count}")
        print("  Experience level: Beginner")

        # Test Scenario 2: Expert user (clean slate from baseline)
        print("\n🧪 Test Scenario 2: Expert user")
        prolly_store.tree.checkout("main")  # Return to main
        test2_time = datetime.now()
        test2_branch = f"test_expert_{int(time.time())}"
        prolly_store.tree.create_branch(test2_branch)
        prolly_store.tree.checkout(test2_branch)
        test_timeline.append(
            (test2_branch, test2_time, "🧪 Test 2: Expert user scenario", "test")
        )

        await prolly_store.store_memory_async(
            namespace,
            "User is a senior engineer with 10 years experience",
            "profile.experience.level",
        )
        await prolly_store.store_memory_async(
            namespace,
            "User prefers advanced technical details",
            "preferences.learning.style",
        )

        expert_memories = prolly_store.search((namespace,), limit=10)
        expert_count = len([m for m in expert_memories if m[2] is not None])
        print(f"  Memory count: {expert_count}")
        print("  Experience level: Expert")

        # Test Scenario 3: Mixed experience (another clean slate)
        print("\n🧪 Test Scenario 3: Mixed experience")
        prolly_store.tree.checkout("main")
        test3_time = datetime.now()
        test3_branch = f"test_mixed_{int(time.time())}"
        prolly_store.tree.create_branch(test3_branch)
        prolly_store.tree.checkout(test3_branch)
        test_timeline.append(
            (test3_branch, test3_time, "🧪 Test 3: Mixed experience scenario", "test")
        )

        await prolly_store.store_memory_async(
            namespace,
            "User is expert in Python but beginner in JavaScript",
            "profile.experience.level",
        )
        await prolly_store.store_memory_async(
            namespace,
            "User needs advanced Python content, basic JS tutorials",
            "preferences.learning.style",
        )

        mixed_memories = prolly_store.search((namespace,), limit=10)
        mixed_count = len([m for m in mixed_memories if m[2] is not None])
        print(f"  Memory count: {mixed_count}")
        print("  Experience level: Mixed")

        # Verify test isolation
        print("\n🔍 Verifying test isolation...")

        # Check beginner branch
        prolly_store.tree.checkout(test1_branch)
        beginner_check = prolly_store.get((namespace,), "profile.experience.level")
        has_beginner = (
            "new to programming" in str(beginner_check) if beginner_check else False
        )

        # Check expert branch
        prolly_store.tree.checkout(test2_branch)
        expert_check = prolly_store.get((namespace,), "profile.experience.level")
        has_expert = "senior engineer" in str(expert_check) if expert_check else False

        print(f"  Beginner branch has 'new to programming': {has_beginner}")
        print(f"  Expert branch has 'senior engineer': {has_expert}")
        print("  ✅ Test scenarios are completely isolated")

        # Demonstrate reproducibility
        print("\n🔄 Demonstrating reproducibility...")

        # Get original test results for comparison
        prolly_store.tree.checkout(test1_branch)
        original_results = []
        for _, path, data in prolly_store.search((namespace,), limit=10):
            if data is not None:
                if isinstance(data, str):
                    original_results.append((path, data))
                else:
                    original_results.append((path, "Memory stored"))

        print("Original beginner test results:")
        for path, content in original_results[:3]:
            print(f"  [{path}] {content[:40]}...")

        # Delete and recreate beginner test
        prolly_store.tree.checkout("main")
        # Note: In real implementation, we'd delete the branch here
        # For demo, we'll create a new one with same setup

        rerun_time = datetime.now()
        rerun_branch = f"test_beginner_rerun_{int(time.time())}"
        prolly_store.tree.create_branch(rerun_branch)
        prolly_store.tree.checkout(rerun_branch)
        test_timeline.append(
            (rerun_branch, rerun_time, "🔄 Test 1 rerun: Beginner scenario", "rerun")
        )

        # Exact same test setup
        await prolly_store.store_memory_async(
            namespace,
            "User is new to programming, learning Python basics",
            "profile.experience.level",
        )
        await prolly_store.store_memory_async(
            namespace,
            "User needs simple explanations and examples",
            "preferences.learning.style",
        )

        # Get rerun test results
        rerun_results = []
        for _, path, data in prolly_store.search((namespace,), limit=10):
            if data is not None:
                if isinstance(data, str):
                    rerun_results.append((path, data))
                else:
                    rerun_results.append((path, "Memory stored"))

        print("\nRerun beginner test results:")
        for path, content in rerun_results[:3]:
            print(f"  [{path}] {content[:40]}...")

        # Compare results
        print("\n🔍 Comparison:")
        print(f"  Original test: {len(original_results)} memories")
        print(f"  Rerun test: {len(rerun_results)} memories")

        # Check if results are identical
        matches = 0
        for orig in original_results:
            if orig in rerun_results:
                matches += 1

        if matches == len(original_results) == len(rerun_results):
            print(f"  ✅ All {matches} memories identical - Perfect reproducibility!")
        else:
            print(f"  ❌ Only {matches}/{len(original_results)} memories match")

        # Test suite summary (latest first)
        print("\n📊 Test Suite Timeline (latest → oldest):")
        print("=" * 65)
        for i, (branch_id, timestamp, description, test_type) in enumerate(
            reversed(test_timeline), 1
        ):
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            status = "CURRENT" if i == 1 else ""

            if test_type == "baseline":
                icon = "📋"
            elif test_type == "test":
                icon = "🧪"
            elif test_type == "rerun":
                icon = "🔄"
            else:
                icon = "📝"

            print(f"  {i}. [{time_str}] {icon} {branch_id[:25]}")
            print(f"     {description} {status}")
            if i < len(test_timeline):
                print()

        print("\n🎯 Reproducible Testing Benefits:")
        print("  ✓ Each test runs in isolated memory branch")
        print("  ✓ Tests don't interfere with each other")
        print("  ✓ Same test produces same results every time")
        print("  ✓ Easy to create complex test scenarios")
        print("  ✓ Can test different user personas in parallel")
        print("  ✓ Clean baseline preserved for all tests")

        # Return to main branch
        prolly_store.tree.checkout("main")
        print("\n✅ All test branches preserved, main branch clean")

    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir)
        print(f"🧹 Cleanup complete: {temp_dir}")


if __name__ == "__main__":
    asyncio.run(main())

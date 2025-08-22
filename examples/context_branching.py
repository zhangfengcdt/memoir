#!/usr/bin/env python3
"""
Conversational Context Branching - Fast Demo Version

Demonstrate memoir's Git-like branching without the LLM overhead.
Uses direct semantic paths for instant execution.

Scenario: User asks "What if I had chosen career path X instead of Y?"
"""

import asyncio
import tempfile
import os
import time
import shutil
from memoir.store.prolly_adapter import ProllyTreeStore


async def main():
    print("# Conversational Context Branching Demo (Fast Version)")
    print("Demonstrate safe exploration of hypothetical scenarios\n")

    # Initialize memory system
    temp_dir = tempfile.mkdtemp()
    prolly_path = os.path.join(temp_dir, "memory_store")
    
    try:
        print("Initializing memory system...")
        
        # Create ProllyTreeStore directly (no LLM needed for this demo)
        prolly_store = ProllyTreeStore(
            path=prolly_path,
            enable_versioning=True,
            cache_size=10000,
        )
        print(f"Memory store created at: {prolly_path}")
        
        # Build main timeline: User's actual career path
        namespace = "user123"
        main_snapshot = f"main_timeline_{int(time.time())}"
        print(f"\nBuilding main timeline...")
        
        # Store memories directly with semantic paths
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
        prolly_store.create_time_snapshot(main_snapshot)
        print(f"✅ Main timeline snapshot created: {main_snapshot}")
        
        # Create branch for hypothetical scenario
        alternative_branch = f"alternative_path_{int(time.time())}"
        print(f"\n🌿 Creating alternative branch: {alternative_branch}")
        
        prolly_store.tree.create_branch(alternative_branch)
        prolly_store.tree.checkout(alternative_branch)
        print(f"✅ Switched to branch '{alternative_branch}' for hypothetical exploration")
        
        # Explore alternative: Big Tech career path
        print("\n🔮 Exploring alternative career path...")
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
        print(f"✅ Alternative timeline snapshot: {alt_snapshot}")
        
        # Compare timelines by examining stored memories
        print(f"\n📊 Comparing timelines...")
        
        # Get memories from alternative branch
        print("\nAlternative timeline memories:")
        alt_memories = prolly_store.search((namespace,), limit=10)
        for _, path, data in alt_memories[:4]:
            if data is None:
                continue
            if isinstance(data, dict) and "memories" in data:
                for mem in data["memories"][:1]:
                    print(f"  [{path}] {mem['content'][:60]}...")
            elif isinstance(data, dict):
                content = data.get("content", str(data))
                print(f"  [{path}] {content[:60]}...")
            else:
                print(f"  [{path}] {str(data)[:60]}...")
        
        # Switch back to main branch
        prolly_store.tree.checkout("main")
        
        print("\nMain timeline memories:")
        main_memories = prolly_store.search((namespace,), limit=10)
        for _, path, data in main_memories[:3]:
            if data is None:
                continue
            if isinstance(data, dict) and "memories" in data:
                for mem in data["memories"][:1]:
                    print(f"  [{path}] {mem['content'][:60]}...")
            elif isinstance(data, dict):
                content = data.get("content", str(data))
                print(f"  [{path}] {content[:60]}...")
            else:
                print(f"  [{path}] {str(data)[:60]}...")
        
        # Show the key difference
        print(f"\n🔑 Key Insights:")
        print(f"  ✓ Main timeline: Contains original startup career path")
        print(f"  ✓ Alternative branch: Contains Google/YouTube hypothetical")
        print(f"  ✓ Branches are completely isolated - no memory corruption")
        print(f"  ✓ Can switch between timelines instantly")
        
        # Demonstrate that alternative memories don't exist in main
        print(f"\n🔍 Verification: Checking for Google memories in main timeline...")
        google_check = prolly_store.get((namespace,), "profile.career.hypothetical.google")
        if google_check is None:
            print("  ✅ Confirmed: No Google memories in main timeline")
        else:
            print("  ❌ Error: Found Google memories in main timeline!")
        
        # Switch back to alternative to verify those memories exist there
        prolly_store.tree.checkout(alternative_branch)
        google_alt = prolly_store.get((namespace,), "profile.career.hypothetical.google")
        if google_alt is not None:
            print("  ✅ Confirmed: Google memories exist in alternative branch")
        
        # Final cleanup
        prolly_store.tree.checkout("main")
        print(f"\n✅ Switched back to main timeline")
        print("Alternative branch exploration complete - main timeline preserved")
        
    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir)
        print(f"🧹 Temporary directory cleaned up: {temp_dir}")


if __name__ == "__main__":
    asyncio.run(main())
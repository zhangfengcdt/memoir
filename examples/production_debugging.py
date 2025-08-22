#!/usr/bin/env python3
"""
Production Debugging Demo

Time-travel to exact moments of user complaints and examine agent memory state.

Problem: User reports "agent acted weird yesterday" but impossible to debug 
without seeing the exact memory state that influenced the decision.

Solution: Git-like time-travel to any point in history for debugging.
"""

import asyncio
import tempfile
import os
import time
import shutil
from datetime import datetime, timedelta
from memoir.store.prolly_adapter import ProllyTreeStore


async def main():
    print("# Production Debugging Demo")
    print("Time-travel to debug production issues from user reports\n")

    # Initialize memory system
    temp_dir = tempfile.mkdtemp()
    prolly_path = os.path.join(temp_dir, "memory_store")
    
    try:
        print("🚀 Initializing production memory system...")
        
        # Create ProllyTreeStore 
        prolly_store = ProllyTreeStore(
            path=prolly_path,
            enable_versioning=True,
            cache_size=10000,
        )
        print(f"Memory store created at: {prolly_path}")
        
        namespace = "user456"
        
        # Track production timeline
        production_timeline = []
        
        # Simulate realistic production environment with many memories
        print("\n📅 Simulating realistic production environment...")
        print("Building up production memory store with user interactions over time...")
        
        # Simulate 6 months of production usage (150+ memories)
        print("\n🏗️  Building production history (6 months of user interactions)...")
        
        # Build realistic production history: 4 weeks × 7 days × 3 interactions = 84 base memories
        # Plus additional categories for realistic variety
        memory_count = 0
        
        # Week 1-4: Initial user onboarding and preferences
        for week in range(1, 5):
            for day in range(1, 8):  # 7 days per week
                for interaction in range(2, 5):  # 3 interactions per day
                    memory_count += 1
                    
                    # Vary the type of memories
                    if interaction == 2:
                        await prolly_store.store_memory_async(
                            namespace,
                            f"User completed task on day {day} of week {week}",
                            f"activities.daily.week{week}.day{day}.task{interaction}"
                        )
                    elif interaction == 3:
                        await prolly_store.store_memory_async(
                            namespace,
                            f"User preference noted during week {week}",
                            f"preferences.discovered.week{week}.day{day}.pref{interaction}"
                        )
                    else:
                        await prolly_store.store_memory_async(
                            namespace,
                            f"General interaction week {week} day {day}",
                            f"interactions.general.week{week}.day{day}.interaction{interaction}"
                        )
        
        # Add more diverse memory types for realism
        memory_types = [
            ("search", "Search queries and results"),
            ("errors", "Error messages and resolutions"), 
            ("settings", "Configuration changes"),
            ("feedback", "User feedback and ratings"),
            ("sessions", "Session information"),
            ("analytics", "Usage analytics"),
        ]
        
        for mem_type, description in memory_types:
            for i in range(10):  # 10 of each type
                memory_count += 1
                await prolly_store.store_memory_async(
                    namespace,
                    f"{description} #{i+1}",
                    f"system.{mem_type}.entry{i+1}"
                )
        
        # Get memory count after initial buildup
        initial_memories = prolly_store.search((namespace,), limit=200)
        initial_count = len([m for m in initial_memories if m[2] is not None])
        print(f"✓ Built initial production history: {initial_count} memories")
        
        # Create checkpoint after initial buildup
        initial_checkpoint = f"checkpoint_initial_{int(time.time())}"
        prolly_store.create_time_snapshot(initial_checkpoint)
        initial_time = datetime.now()
        production_timeline.append((initial_checkpoint, initial_time, f"📊 Production checkpoint: {initial_count} memories", "checkpoint"))
        
        await asyncio.sleep(0.1)
        
        # Day 1: Normal operations
        print("\nDay 1 (Monday): User sets UI preferences")
        await prolly_store.store_memory_async(
            namespace,
            "User prefers minimal UI designs",
            "preferences.ui.style.minimal"
        )
        day1_time = datetime.now()
        day1_commit = f"day1_{int(time.time())}"
        prolly_store.create_time_snapshot(day1_commit)
        production_timeline.append((day1_commit, day1_time, "📋 User sets minimal UI preference", "normal"))
        print(f"  ✓ 09:00 - UI preference saved (snapshot: {day1_commit})")
        
        await asyncio.sleep(0.1)
        
        # Day 2: More preferences
        print("\nDay 2 (Tuesday): User sets theme preferences")
        await prolly_store.store_memory_async(
            namespace,
            "User likes dark mode for coding",
            "preferences.ui.theme.dark"
        )
        day2_time = datetime.now()
        day2_commit = f"day2_{int(time.time())}"
        prolly_store.create_time_snapshot(day2_commit)
        production_timeline.append((day2_commit, day2_time, "🎨 User adds dark mode preference", "normal"))
        print(f"  ✓ 14:30 - Theme preference saved (snapshot: {day2_commit})")
        
        await asyncio.sleep(0.1)
        
        # Day 3: Problem occurs - agent gives bad recommendation
        print("\nDay 3 (Wednesday): Agent malfunction")
        await prolly_store.store_memory_async(
            namespace,
            "Agent recommended bright neon colors for dashboard",  # Conflicts with minimal UI!
            "agent.recommendations.bad_ui"
        )
        problem_time = datetime.now()
        problem_commit = f"problem_{int(time.time())}"
        prolly_store.create_time_snapshot(problem_commit)
        production_timeline.append((problem_commit, problem_time, "❌ Agent recommends neon colors (BUG)", "error"))
        print(f"  ❌ 11:15 - Bad recommendation logged (snapshot: {problem_commit})")
        print("     Agent recommended neon colors despite minimal UI preference!")
        
        await asyncio.sleep(0.1)
        
        # Add more memories to simulate continued usage
        print("\n📈 Simulating continued production usage...")
        for i in range(20):  # Add 20 more memories after the problem
            await prolly_store.store_memory_async(
                namespace,
                f"Continued user activity after problem {i+1}",
                f"activities.post_problem.activity{i+1}"
            )
        
        # Get current total memory count
        final_memories = prolly_store.search((namespace,), limit=300)
        final_count = len([m for m in final_memories if m[2] is not None])
        print(f"✓ Total production memories: {final_count}")
        
        # Day 4: User reports issue
        print("\nDay 4 (Thursday): User complaint received")
        report_time = datetime.now()
        production_timeline.append(("USER_REPORT", report_time, "📧 User complaint: 'terrible colors yesterday'", "report"))
        print(f"  📧 10:00 - User reports: 'Agent recommended terrible colors yesterday at 11:15 AM'")
        print(f"     Report timestamp: {report_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  📊 Current production state: {final_count} memories accumulated")
        
        # Production debugging: Time-travel to exact moment
        print(f"\n🔍 Production Debugging Challenge:")
        print(f"   Current state: {final_count} memories in production")
        print(f"   Need to debug: Problem from 3 days ago")
        print(f"   Traditional approach: Search through {final_count} memories manually ❌")
        print(f"   Memoir approach: Time-travel to exact snapshot ✅")
        
        print(f"\n⏰ Time-traveling to problem moment ({problem_commit})...")
        prolly_store.tree.checkout(problem_commit)
        
        # Show memory state at problem time
        problem_memories = prolly_store.search((namespace,), limit=200)
        problem_count = len([m for m in problem_memories if m[2] is not None])
        
        print(f"\n📊 Memory state at problem time:")
        print(f"   Total memories then: {problem_count}")
        print(f"   Current memories now: {final_count}")
        print(f"   🎯 Time-traveled back through {final_count - problem_count} memories instantly!")
        
        print("\n🔍 Relevant memories that influenced the bad decision:")
        ui_memories = []
        for _, path, data in problem_memories:
            if data and ("ui" in path or "recommendation" in path):
                ui_memories.append((path, data))
                if isinstance(data, str):
                    print(f"  - [{path}] {data[:60]}...")
                else:
                    print(f"  - [{path}] Memory stored")
        
        print(f"\n💡 Key insight: At problem time, agent had only {problem_count} memories")
        print(f"   vs {final_count} memories in current production")
        
        # Root cause analysis - demonstrate time travel to middle of timeline
        print("\n🔬 Root Cause Analysis:")
        print("   Let's check the initial production state (halfway through timeline)")
        
        # Time-travel to initial checkpoint (middle of timeline)
        prolly_store.tree.checkout(initial_checkpoint)
        initial_count_check = len([m for m in prolly_store.search((namespace,), limit=300) if m[2] is not None])
        print(f"\n⏰ Time-traveled to initial checkpoint ({initial_checkpoint[:20]})...")
        print(f"   Memory state at checkpoint: {initial_count_check} memories")
        
        # Now check state just before problem
        print(f"\n⏰ Time-traveling to just before problem ({day2_commit})...")
        prolly_store.tree.checkout(day2_commit)
        pre_problem_memories = prolly_store.search((namespace,), limit=300)
        pre_problem_count = len([m for m in pre_problem_memories if m[2] is not None])
        
        print(f"   Memory state before problem: {pre_problem_count} memories")
        print(f"   UI-related memories:")
        for _, path, data in pre_problem_memories:
            if data and "ui" in path:
                if isinstance(data, str):
                    print(f"  - [{path}] {data[:60]}...")
                else:
                    print(f"  - [{path}] Memory stored")
        
        print(f"\n📈 Timeline progression:")
        print(f"   Initial checkpoint: {initial_count_check} memories")
        print(f"   Before problem: {pre_problem_count} memories")  
        print(f"   At problem time: {problem_count} memories")
        print(f"   Current production: {final_count} memories")
        
        print("\n💡 Root cause identified:")
        print("  Agent had correct preferences (minimal UI + dark mode)")
        print("  but recommendation logic had a bug that ignored these preferences")
        print(f"  🎯 Debugged by time-traveling through {final_count} memories in seconds!")
        
        # Create debug branch from last good state
        print(f"\n🔧 Creating debug branch from clean state ({day2_commit})")
        prolly_store.tree.checkout(day2_commit)
        debug_branch = f"debug_fix_{int(time.time())}"
        prolly_store.tree.create_branch(debug_branch)
        prolly_store.tree.checkout(debug_branch)
        print(f"  ✓ Created branch: {debug_branch}")
        
        # Test fix in debug branch
        print("\n🧪 Testing fix in debug branch...")
        await prolly_store.store_memory_async(
            namespace,
            "Agent recommended subtle grays and whites for minimal dashboard design",
            "agent.recommendations.corrected_ui"
        )
        fix_commit = f"fix_{int(time.time())}"
        prolly_store.create_time_snapshot(fix_commit)
        print(f"  ✓ Corrected recommendation stored (snapshot: {fix_commit})")
        
        # Verify fix
        print("\n✅ Verification in debug branch:")
        fix_verification = prolly_store.get((namespace,), "agent.recommendations.corrected_ui")
        if fix_verification:
            print("  ✓ Correct recommendation: subtle grays and whites")
            print("  ✓ Aligns with user's minimal UI preference")
        
        # Deploy fix: Switch back to main
        print("\n🚀 Deploying fix to production...")
        prolly_store.tree.checkout("main")
        
        # Apply the fix
        await prolly_store.store_memory_async(
            namespace,
            "Agent logic fixed - now respects UI preferences",
            "agent.fixes.ui_preference_bug"
        )
        deployed_time = datetime.now()
        deployed_commit = f"deployed_{int(time.time())}"
        prolly_store.create_time_snapshot(deployed_commit)
        production_timeline.append((deployed_commit, deployed_time, "✅ Production fix deployed", "fix"))
        print(f"  ✓ Fix deployed to production (snapshot: {deployed_commit})")
        
        # Production timeline summary (latest first)
        print("\n📜 Production Timeline (latest → oldest):")
        print("=" * 70)
        for i, (commit_id, timestamp, description, event_type) in enumerate(reversed(production_timeline), 1):
            time_str = timestamp.strftime("%Y-%m-%d %H:%M:%S")
            status = "CURRENT" if i == 1 else ""
            
            if event_type == "error":
                icon = "🚨"
            elif event_type == "fix":
                icon = "🔧"
            elif event_type == "report":
                icon = "📧"
            else:
                icon = "📝"
                
            if commit_id == "USER_REPORT":
                print(f"  {i}. [{time_str}] {icon} USER REPORT")
            else:
                print(f"  {i}. [{time_str}] {icon} {commit_id[:20]}")
            print(f"     {description} {status}")
            if i < len(production_timeline):
                print()
        
        print(f"\n🔧 Debug branch: {debug_branch} - Fix tested in isolation")
        
        print("\n🎯 Production Debugging Benefits (Large Scale):")
        print(f"  ✓ Handle {final_count}+ memories without performance degradation")
        print("  ✓ Time-travel to ANY point in history instantly")
        print("  ✓ Compare memory states across months of production data")
        print("  ✓ Debug issues from weeks/months ago with exact context")
        print("  ✓ No need to search through hundreds of memories manually")
        print("  ✓ Test fixes in isolation without affecting production")
        print("  ✓ Complete Git-like audit trail for compliance")
        print("  ✓ Scale to thousands of memories with O(log n) performance")
        
        print(f"\n🚀 What this demo shows:")
        print(f"  • Traditional debugging: Search {final_count} memories manually")
        print(f"  • Memoir debugging: Instant time-travel to exact moments")
        print(f"  • Perfect for production systems with extensive memory history")
        
    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir)
        print(f"\n🧹 Cleanup complete: {temp_dir}")


if __name__ == "__main__":
    asyncio.run(main())
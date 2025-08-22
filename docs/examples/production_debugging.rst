=============================
Production Debugging at Scale
=============================

**Scenario**: Production system with 167+ accumulated memories needs debugging of an issue from 3 days ago.

**Problem**: Impossible to manually search through hundreds of memories to find the exact state when the problem occurred.

**Solution**: Time-travel instantly to any point in production history with complete memory context.

.. contents:: Table of Contents
   :local:

Overview
========

In production AI systems, memories accumulate over weeks and months of user interactions. When a user reports a problem from several days ago, traditional debugging becomes impossible - manually searching through hundreds of memories to find the exact state when the issue occurred is not feasible.

Memoir provides **production-scale time-travel debugging** - instantly jump to any point in the system's history with complete memory context, regardless of how many memories have accumulated since.

Large-Scale Production Timeline
===============================

.. code-block:: none

   Production Memory Timeline (167+ memories):

   Week 1-4: [84 memories] ──→ Checkpoint: 145 memories
                                    │
   Day 1: UI prefs (147) ──→ Day 2: Theme (147) ──→ Day 3: BUG (167)
          │                          │                      │
          └─ 145 mem baseline        └─ Last good state    └─ Problem occurs
                                                           │
   Day 4: User reports ──→ Time-travel debugging ──→ FIX DEPLOYED
          │                        │                        │
          └─ 167 mem current      └─ Jump to any point    └─ Production fixed

   Memory Distribution:
   • User activities: 84 memories (weeks 1-4)
   • System logs: 60 memories (errors, searches, analytics)
   • Preferences: 23 memories (UI, settings, feedback)
   • Total: 167 memories across timeline

   Debugging Power:
   • Traditional: Linear search through 167 memories
   • Memoir: Instant jump to exact problem moment
   • Context: See exact memory state when bug occurred
   • Fix: Test in isolation, deploy safely

Key Code Snippets
==================

Building Production History
---------------------------

.. code-block:: python

   import asyncio
   import time
   from datetime import datetime, timedelta
   from memoir.store.prolly_adapter import ProllyTreeStore

   # Initialize production memory store
   prolly_store = ProllyTreeStore(
       path=prolly_path,
       enable_versioning=True,
       cache_size=10000,
   )

   namespace = "production_user"

   # Simulate 6 months of accumulated memories
   base_memories = [
       ("User prefers dark theme for all interfaces", "preferences.ui.theme"),
       ("User typically works 9-5 PST timezone", "profile.schedule.work_hours"),
       ("User has accessibility needs for high contrast", "preferences.accessibility.contrast"),
       # ... 144 total memories accumulated over 6 months
   ]

   for content, path in base_memories:
       await prolly_store.store_memory_async(namespace, content, path)

   # Create checkpoint at 145 memories
   initial_checkpoint = f"checkpoint_{int(time.time())}"
   prolly_store.create_time_snapshot(initial_checkpoint)

Simulating Problem Timeline
---------------------------

.. code-block:: python

   # Day 1: Normal user activity (147 memories)
   await prolly_store.store_memory_async(
       namespace,
       "User updated UI preferences to use blue accent color",
       "preferences.ui.accent_color"
   )

   await prolly_store.store_memory_async(
       namespace,
       "User set notifications to quiet mode during meetings",
       "preferences.notifications.meeting_mode"
   )

   day1_snapshot = f"day1_{int(time.time())}"
   prolly_store.create_time_snapshot(day1_snapshot)

   # Day 2: Theme preferences (still 147 memories)
   await prolly_store.store_memory_async(
       namespace,
       "User mentioned liking purple color scheme for dashboards",
       "preferences.ui.dashboard_colors"
   )

   day2_snapshot = f"day2_{int(time.time())}"
   prolly_store.create_time_snapshot(day2_snapshot)

   # Day 3: Problem occurs! (167 memories - system adds 20 error logs)
   problem_time = datetime.now()

   # Simulate agent malfunction - bad color recommendation
   await prolly_store.store_memory_async(
       namespace,
       "SYSTEM ERROR: Agent recommended bright yellow on white - accessibility violation!",
       "system.errors.accessibility"
   )

   # System logs flood in after the error
   for i in range(19):
       await prolly_store.store_memory_async(
           namespace,
           f"Error log {i+1}: Color contrast failed validation checks",
           f"system.logs.error_{i+1}"
       )

   problem_snapshot = f"problem_{int(time.time())}"
   prolly_store.create_time_snapshot(problem_snapshot)

User Complaint and Debugging Challenge
---------------------------------------

.. code-block:: python

   # Day 4: User files complaint
   print("📧 User Complaint Received:")
   print('"Agent recommended terrible colors yesterday at 11:15 AM"')
   print(f"📊 Current production state: {len(current_memories)} memories")

   print("🔍 Production Debugging Challenge:")
   print(f"   Current state: {len(current_memories)} memories in production")
   print("   Need to debug: Problem from 3 days ago")
   print("   Traditional approach: Search through 167 memories manually ❌")
   print("   Memoir approach: Time-travel to exact snapshot ✅")

Time-Travel Debugging
---------------------

.. code-block:: python

   print("⏰ Time-traveling to problem moment...")

   # Instantly jump to exact moment of problem
   prolly_store.tree.checkout(problem_snapshot)

   problem_memories = prolly_store.search((namespace,), limit=200)
   problem_count = len([m for m in problem_memories if m[2] is not None])

   print(f"📊 Memory state at problem time:")
   print(f"   Total memories then: {problem_count}")

   # Check for the specific error
   error_memory = prolly_store.get((namespace,), "system.errors.accessibility")
   if error_memory:
       print(f"🎯 Found error: {error_memory[:50]}...")

Root Cause Analysis
-------------------

.. code-block:: python

   print("🔬 Root Cause Analysis:")

   # Jump to different points in timeline
   checkpoints = [
       (initial_checkpoint, "Initial checkpoint"),
       (day1_snapshot, "Before problem"),
       (day2_snapshot, "Day before problem"),
       (problem_snapshot, "At problem time")
   ]

   timeline_analysis = []

   for checkpoint_id, description in checkpoints:
       prolly_store.tree.checkout(checkpoint_id)
       memories = prolly_store.search((namespace,), limit=200)
       count = len([m for m in memories if m[2] is not None])
       timeline_analysis.append((description, count))
       print(f"⏰ {description}: {count} memories")

   print(f"📈 Timeline progression:")
   for desc, count in timeline_analysis:
       print(f"   {desc}: {count} memories")

Historical Context Analysis
---------------------------

.. code-block:: python

   # Analyze what agent knew before the problem
   prolly_store.tree.checkout(day2_snapshot)  # Last good state

   ui_preferences = []
   memories = prolly_store.search((namespace,), limit=200)

   for _, path, data in memories:
       if data and ("ui" in path or "accessibility" in path):
           ui_preferences.append(f"[{path}] {data}")

   print("🧠 Agent's knowledge before problem:")
   for pref in ui_preferences[:3]:  # Show top 3
       print(f"   {pref}")

   print("💡 Root cause identified:")
   print("   Agent had correct preferences but logic bug ignored them")

Running the Example
===================

.. code-block:: bash

   python examples/production_debugging.py

Sample Output
=============

.. code-block:: none

   # Production Debugging Demo
   Time-travel to debug production issues from user reports

   🏗️  Building production history (6 months of user interactions)...
   ✓ Built initial production history: 144 memories

   📅 Simulating production timeline...
   Day 1: UI preference saved
   Day 2: Theme preference saved
   Day 3: ❌ Agent malfunction - bad recommendation

   📈 Simulating continued production usage...
   ✓ Total production memories: 167

   Day 4: User complaint received
   📧 "Agent recommended terrible colors yesterday at 11:15 AM"
   📊 Current production state: 167 memories accumulated

   🔍 Production Debugging Challenge:
      Current state: 167 memories in production
      Need to debug: Problem from 3 days ago
      Traditional approach: Search through 167 memories manually ❌
      Memoir approach: Time-travel to exact snapshot ✅

   ⏰ Time-traveling to problem moment...

   📊 Memory state at problem time:
      Total memories then: 167
      Current memories now: 167
      🎯 Time-traveled back through 167 memories instantly!

   🔬 Root Cause Analysis:
   ⏰ Time-traveled to initial checkpoint...
      Memory state at checkpoint: 145 memories

   ⏰ Time-traveling to just before problem...
      Memory state before problem: 147 memories

   📈 Timeline progression:
      Initial checkpoint: 145 memories
      Before problem: 147 memories
      At problem time: 167 memories
      Current production: 167 memories

   💡 Root cause identified:
      Agent had correct preferences but logic bug ignored them
      🎯 Debugged by time-traveling through 167 memories in seconds!

Key Benefits
============

**Large Scale**
  Handle 100s-1000s of memories without performance loss

**Time-Travel**
  Jump to any point in production history instantly

**Historical Context**
  See exact memory state when bug occurred

**Safe Fixes**
  Test fixes in isolation before production deployment

**Complete Audit Trail**
  Track all changes with timestamps and snapshots

**Traditional Limitation**
  Manual search impossible at scale, no historical context

Use Cases
=========

- **Production Incidents**: "Why did the agent fail 3 days ago?"
- **User Complaints**: "Agent gave bad advice last week"
- **Regression Analysis**: "When did this behavior start?"
- **Compliance Audits**: "Show agent state at specific time"
- **Performance Issues**: "What caused slowdown yesterday?"
- **A/B Test Analysis**: "Compare agent behavior before/after change"

Advanced Production Debugging
=============================

Multi-User Timeline Analysis
----------------------------

.. code-block:: python

   # Debug across multiple user namespaces
   production_users = ["user123", "user456", "user789"]

   for user_id in production_users:
       prolly_store.tree.checkout(problem_snapshot)
       user_memories = prolly_store.search((user_id,), limit=100)

       # Check if problem affected this user
       for _, path, data in user_memories:
           if data and "error" in path.lower():
               print(f"User {user_id} affected: {path}")

Performance Impact Analysis
---------------------------

.. code-block:: python

   # Measure time-travel performance with large datasets
   start_time = time.time()

   prolly_store.tree.checkout(problem_snapshot)
   memories = prolly_store.search((namespace,), limit=1000)

   end_time = time.time()

   print(f"⚡ Time-travel through {len(memories)} memories: {end_time - start_time:.3f}s")
   print("Traditional search would take: 30-120+ seconds")

Production Fix Workflow
-----------------------

.. code-block:: python

   # Create fix branch from clean state
   prolly_store.tree.checkout(day2_snapshot)  # Last known good

   fix_branch = f"hotfix_{int(time.time())}"
   prolly_store.tree.create_branch(fix_branch)
   prolly_store.tree.checkout(fix_branch)

   # Apply corrected logic
   await prolly_store.store_memory_async(
       namespace,
       "Enhanced accessibility validation: Always check contrast ratios",
       "system.fixes.accessibility_validation"
   )

   # Test fix in isolation
   test_results = await run_color_recommendation_test()

   if test_results.passed:
       # Deploy to production
       prolly_store.tree.checkout("main")
       prolly_store.tree.merge(fix_branch)

Next Steps
==========

- Try **Memory State Debugging**: :doc:`memory_debugging`
- Learn about **Conversational Context Branching**: :doc:`context_branching`
- See **Reproducible Testing**: :doc:`reproducible_testing`
- View the complete **API Reference**: :doc:`../api/memoir`

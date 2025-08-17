#!/usr/bin/env python3
"""
Demonstrate the Intelligent Taxonomy Classification system with real LLM.
"""

import asyncio
import json
import os
import sys

from langmem_prollytree.core.prolly_adapter import ProllyTreeStore
from langmem_prollytree.taxonomy.intelligent_classifier import IntelligentClassifier
from langmem_prollytree.taxonomy.iterative_taxonomy import LLMIterativeTaxonomy
from langmem_prollytree.taxonomy.semantic_classifier import SemanticClassifier
from langmem_prollytree.taxonomy.taxonomy_presets import TaxonomyVersion


def get_llm():
    """Get OpenAI LLM instance - requires API key and langchain-openai."""
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("   ❌ Error: OPENAI_API_KEY environment variable is required")
        print("      Set your OpenAI API key: export OPENAI_API_KEY=your-api-key-here")
        print("      Get an API key at: https://platform.openai.com/api-keys")
        sys.exit(1)

    # Try to import and create OpenAI LLM
    try:
        from langchain_openai import ChatOpenAI

        print("   ✅ Using OpenAI GPT-4o-mini for classification")
        return ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=api_key,
            max_tokens=500,
        )
    except ImportError:
        print("   ❌ Error: langchain-openai package is required")
        print("      Install with: pip install langchain-openai")
        sys.exit(1)


def show_taxonomy_structure(taxonomy, title="Current Taxonomy Structure"):
    """Show the current taxonomy structure."""
    print(f"\n📁 {title}")
    print("-" * 50)

    info = taxonomy.get_taxonomy_info()
    stats = taxonomy.get_expansion_statistics()

    print(f"Version: {info['version']}")
    print(f"Total paths: {stats['total_paths']}")
    print(f"Dynamic paths: {stats['dynamic_paths']}")

    # Group paths by first-level category
    all_paths = taxonomy.get_all_paths()
    structure = {}

    for path in all_paths:
        if path == "other":
            continue
        parts = path.split(".")
        if parts[0] not in structure:
            structure[parts[0]] = []
        if len(parts) > 1:
            structure[parts[0]].append(".".join(parts[1:]))

    print("\nCurrent structure:")
    for category, subcategories in sorted(structure.items()):
        print(f"  {category}/")
        if subcategories:
            for subcat in sorted(set(subcategories))[:5]:  # Show first 5
                print(f"    └─ {subcat}")
            if len(set(subcategories)) > 5:
                print(f"    └─ ... and {len(set(subcategories)) - 5} more")
        else:
            print("    └─ (empty)")


async def demonstrate_memory_update_actions(intelligent_classifier):
    """Demonstrate REPLACE, APPEND, and MERGE memory actions with REAL LLM calls."""
    print("\n" + "=" * 80)
    print("💾 Memory Update Actions Demo (REAL LLM RESPONSES)")
    print("=" * 80)
    print("🤖 Using REAL LLM to decide how to handle memory updates when content")
    print("   is stored to the same memory path multiple times...")
    print("   (The LLM will determine whether to REPLACE, APPEND, or MERGE)")

    # Test content for the same memory path
    memory_path = "profile.personal.location"
    namespace = ("memory", intelligent_classifier.taxonomy_version.value)

    test_contents = [
        {
            "content": "I live in San Francisco, California",
            "description": "Initial location storage",
            "expected_action": "STORE",
        },
        {
            "content": "I just moved to New York City",
            "description": "Updated location - should REPLACE old location",
            "expected_action": "REPLACE",
        },
        {
            "content": "I also have a vacation home in Miami",
            "description": "Additional location info - should APPEND",
            "expected_action": "APPEND",
        },
        {
            "content": "I frequently travel between NYC and Miami for work",
            "description": "Related travel info - should MERGE with existing",
            "expected_action": "MERGE",
        },
    ]

    print(f"\n📍 Testing memory updates for path: {memory_path}")
    print("-" * 50)

    for i, test in enumerate(test_contents, 1):
        print(f"\n[{i}] {test['description']}")
        print(f'Content: "{test["content"]}"')
        print(f"🎯 Expected action: {test['expected_action']}")
        print("-" * 40)

        # Show existing content before update
        try:
            existing = intelligent_classifier.memory_store.get(namespace, memory_path)
            if existing:
                existing_content = existing.get("content", "")
                print(
                    f'📖 Existing content: "{existing_content[:50]}{"..." if len(existing_content) > 50 else ""}"'
                )
            else:
                print("📖 No existing content")
        except Exception:
            print("📖 No existing content")

        # Store content directly to trigger update logic
        try:
            # First store the content
            if i == 1:
                # First item - just store it
                intelligent_classifier.memory_store.put(
                    namespace,
                    memory_path,
                    {
                        "content": test["content"],
                        "metadata": {"source": "demo", "step": i},
                    },
                )
                print("   ✅ Action: STORE (new memory)")
            else:
                # Subsequent items - use the memory update logic
                existing_data = intelligent_classifier.memory_store.get(
                    namespace, memory_path
                )
                if existing_data:
                    # Call the update handler directly
                    update_result = await intelligent_classifier._handle_memory_update(
                        test["content"],
                        existing_data,
                        memory_path,
                        namespace,
                        {"source": "demo", "step": i},
                    )
                    actual_action = update_result["action"].value
                    print(f"   ✅ Action: {actual_action.upper()}")
                    print(f"   📝 Reasoning: {update_result['reasoning']}")

                    # Show the updated content
                    updated = intelligent_classifier.memory_store.get(
                        namespace, memory_path
                    )
                    if updated:
                        new_content = updated.get("content", "")
                        print(
                            f'   📄 Updated content: "{new_content[:100]}{"..." if len(new_content) > 100 else ""}"'
                        )

        except Exception as e:
            print(f"   ❌ Error: {e}")

    # Show final memory state
    print(f"\n📋 Final memory state for {memory_path}:")
    try:
        final_memory = intelligent_classifier.memory_store.get(namespace, memory_path)
        if final_memory:
            final_content = final_memory.get("content", "")
            print(f"   {final_content}")
        else:
            print("   (no content)")
    except Exception:
        print("   (unable to retrieve)")


async def demonstrate_intelligent_taxonomy():
    """Demonstrate the intelligent taxonomy classification with real LLM and memory storage."""
    print("=" * 80)
    print("🧠 Intelligent Memory System Demo with Real LLM & Storage")
    print("=" * 80)

    # Get real LLM
    llm = get_llm()

    # Setup memory store
    print("\n🗄️  Setting up memory store...")
    from pathlib import Path

    data_dir = Path("/tmp/intelligent_taxonomy_demo")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Create a simple classifier for the store
    classifier = SemanticClassifier(llm=None)

    store = ProllyTreeStore(
        path=str(data_dir),
        classifier=classifier,
        enable_versioning=False,
    )

    # Create intelligent classifier with memory store access
    print("🧠 Creating intelligent classifier with memory store access...")
    intelligent_classifier = IntelligentClassifier(
        llm=llm,
        memory_store=store,
        taxonomy_version=TaxonomyVersion.GENERAL,
        confidence_thresholds={
            "high": 0.85,  # Higher threshold to make high confidence harder
            "medium": 0.6,  # Medium range
            "low": 0.0,
        },
        min_items_for_expansion=1,  # Lower threshold for easier expansion triggering
    )

    # Show initial structure
    show_taxonomy_structure(
        intelligent_classifier.taxonomy, "Initial Taxonomy Structure"
    )

    # Test cases designed to demonstrate all four classification actions
    test_cases = [
        # 1. SKIP - Not memory-worthy content
        {
            "content": "Hello, how are you today?",
            "description": "SKIP: Simple greeting - not memory-worthy",
            "expected_action": "skip",
        },
        {
            "content": "The current time is 3:47 PM",
            "description": "SKIP: Transient temporal information",
            "expected_action": "skip",
        },
        # 2. CLASSIFY - High confidence, clear existing category
        {
            "content": "John Smith is the new CEO of TechCorp as of January 2024",
            "description": "CLASSIFY: High-confidence professional information",
            "expected_action": "classify",
        },
        {
            "content": "User always prefers dark mode interface with minimal animations",
            "description": "CLASSIFY: Clear interface preference",
            "expected_action": "classify",
        },
        # 3. EXPAND - Low confidence, very specific content needing new subcategories
        {
            "content": "I specialize in 16th-century Venetian glass-blowing techniques using soda-lime glass",
            "description": "EXPAND: Very specific craft skill - needs specialized subcategory",
            "expected_action": "expand",
        },
        {
            "content": "I practice competitive speed-solving of Rubik's cubes, my best time is 8.3 seconds using CFOP method",
            "description": "EXPAND: Specific hobby requiring detailed categorization",
            "expected_action": "expand",
        },
        # 4. USE_PARENT - Moderately specific but better suited to broader category
        {
            "content": "I sometimes work on various creative projects in my spare time",
            "description": "USE_PARENT: Vague creative activity - use broader category",
            "expected_action": "use_parent",
        },
        {
            "content": "I have some experience with different programming languages over the years",
            "description": "USE_PARENT: General programming experience - use broader category",
            "expected_action": "use_parent",
        },
        # 5. Additional cases to trigger expansion once we have enough items
        {
            "content": "I collect vintage fountain pens from the 1920s-1940s, especially Waterman and Parker models",
            "description": "EXPAND: Another specific collection - accumulate for expansion",
            "expected_action": "expand",
        },
        {
            "content": "I'm learning advanced jazz piano improvisation techniques, particularly bebop scales",
            "description": "EXPAND: Specific musical skill - trigger skills expansion",
            "expected_action": "expand",
        },
    ]

    print(f"\n🧪 Testing {len(test_cases)} classification scenarios with REAL LLM:")
    print("🤖 ALL responses below come from actual GPT-4o-mini calls")
    print("📋 Demonstrating all four classification actions:")
    print("   • SKIP: Not memory-worthy content")
    print("   • CLASSIFY: High confidence, existing categories")
    print("   • EXPAND: Low confidence, needs new subcategories")
    print("   • USE_PARENT: Medium confidence, use broader category")
    print("=" * 80)

    # Track which actions we successfully demonstrate
    demonstrated_actions = {"skip": [], "classify": [], "expand": [], "use_parent": []}

    for i, test in enumerate(test_cases, 1):
        print(f"\n[{i}] {test['description']}")
        print(f'Content: "{test["content"]}"')
        print(f"🎯 Expected action: {test['expected_action'].upper()}")
        print("-" * 60)

        # Show structure before processing
        current_paths = len(intelligent_classifier.taxonomy.get_all_paths())

        # Show current stored memories
        stored_memories = intelligent_classifier.get_stored_memories(limit=5)
        print(f"📚 Current stored memories: {len(stored_memories)}")

        # Perform complete memory processing with REAL LLM
        print(
            "🤖 REAL LLM CALL: Processing with GPT-4o-mini classification and memory storage..."
        )
        result = await intelligent_classifier.process_memory_with_storage(
            test["content"], {"source": "demo", "step": i}
        )

        # Show classification results
        print("\n📊 Classification Results:")
        classification = result.classification
        print(f"   Memory-worthy: {classification.is_memory}")

        if classification.is_memory:
            print(f"   Path: {classification.path}")
            print(f"   Confidence: {classification.confidence:.2f}")

            # Show actual vs expected action
            actual_action = (
                classification.suggested_action.value
                if hasattr(classification.suggested_action, "value")
                else str(classification.suggested_action)
            )
            expected_action = test["expected_action"]

            if actual_action.lower() == expected_action.lower():
                print(f"   ✅ Action: {actual_action.upper()} (matches expected)")
                demonstrated_actions[actual_action.lower()].append(i)
            else:
                print(
                    f"   ⚠️  Action: {actual_action.upper()} (expected: {expected_action.upper()})"
                )
                demonstrated_actions[actual_action.lower()].append(i)

            if "expand" in actual_action.lower():
                print(f"   🔄 Expansion details: {classification.reasoning}")
            elif "use_parent" in actual_action.lower():
                print(f"   📈 Parent category usage: {classification.reasoning}")
        else:
            # Handle SKIP case
            expected_action = test["expected_action"]
            if expected_action.lower() == "skip":
                print("   ✅ Action: SKIP (matches expected)")
                demonstrated_actions["skip"].append(i)
            else:
                print(f"   ⚠️  Action: SKIP (expected: {expected_action.upper()})")
                demonstrated_actions["skip"].append(i)

        print(f"   💭 Classification reasoning: {classification.reasoning}")

        # Show memory storage results
        print("\n💾 Memory Storage Results:")
        print(f"   Memory action: {result.memory_action.value}")
        print(f"   Storage reasoning: {result.storage_reasoning}")

        if result.memory_path:
            print(f"   Stored at path: {result.memory_path}")

        if result.previous_content:
            print(f"   Previous content: {result.previous_content[:50]}...")

        if result.new_content and result.new_content != result.previous_content:
            print(f"   New content: {result.new_content[:50]}...")

        # Show structure changes
        new_paths = len(intelligent_classifier.taxonomy.get_all_paths())
        if new_paths > current_paths:
            print(
                f"\n🎉 Taxonomy expanded! Added {new_paths - current_paths} new paths"
            )
            show_taxonomy_structure(
                intelligent_classifier.taxonomy, "Updated Taxonomy Structure"
            )
        else:
            print(f"\n📈 No structural changes (paths: {current_paths} → {new_paths})")

        print("\n" + "=" * 80)

    # Action demonstration summary
    print("\n🎯 Classification Actions Demonstrated:")
    print("-" * 50)
    for action, test_numbers in demonstrated_actions.items():
        if test_numbers:
            print(f"✅ {action.upper()}: Tests {test_numbers}")
        else:
            print(f"❌ {action.upper()}: Not demonstrated")

    all_actions_shown = all(
        test_numbers for test_numbers in demonstrated_actions.values()
    )
    if all_actions_shown:
        print("\n🎉 SUCCESS: All four classification actions were demonstrated!")
    else:
        missing = [
            action.upper()
            for action, tests in demonstrated_actions.items()
            if not tests
        ]
        print(f"\n⚠️  Missing actions: {', '.join(missing)}")

    # Final summary
    print("\n🏁 Final Summary")
    print("-" * 40)
    show_taxonomy_structure(intelligent_classifier.taxonomy, "Final Taxonomy Structure")

    # Show stored memories
    stored_memories = intelligent_classifier.get_stored_memories(limit=20)
    print("\n💾 Final Memory Storage:")
    print(f"   Total stored memories: {len(stored_memories)}")

    if stored_memories:
        print("\n📋 Stored Memory Details:")
        for i, memory in enumerate(stored_memories, 1):
            content_preview = (
                memory["content"].get("content", "")[:60]
                if isinstance(memory["content"], dict)
                else str(memory["content"])[:60]
            )
            print(f"   [{i}] {memory['path']}")
            print(f"       Content: {content_preview}...")

    # Show expansion history
    stats = intelligent_classifier.taxonomy.get_expansion_statistics()
    if stats["expansion_history"] > 0:
        print(
            f"\n📚 Expansion History: {stats['expansion_history']} expansions performed"
        )
        print(f"   Total items migrated: {stats['total_migrated']}")
    else:
        print("\n📚 No automatic expansions occurred during this demo")

    # Demonstrate memory update actions with real LLM calls
    await demonstrate_memory_update_actions(intelligent_classifier)

    # Final analysis of hierarchical consistency
    print("\n" + "=" * 80)
    print("🔍 HIERARCHICAL STRUCTURE ANALYSIS")
    print("=" * 80)

    stored_memories = intelligent_classifier.get_stored_memories(limit=20)
    if stored_memories:
        print("📊 Analyzing taxonomy structure consistency:")
        print("-" * 50)

        depth_counts = {}
        paths_by_domain = {}

        for memory in stored_memories:
            path = memory["path"]
            depth = len(path.split("."))
            domain = path.split(".")[0]

            # Count depths
            depth_counts[depth] = depth_counts.get(depth, 0) + 1

            # Group by domain
            if domain not in paths_by_domain:
                paths_by_domain[domain] = []
            paths_by_domain[domain].append(path)

        print("📏 Depth Distribution:")
        for depth in sorted(depth_counts.keys()):
            print(f"   Level {depth}: {depth_counts[depth]} paths")

        print("\n🗂️  Paths by Domain:")
        for domain, paths in paths_by_domain.items():
            print(f"   {domain}/ ({len(paths)} paths)")
            for path in sorted(paths):
                depth_indicator = "  " * len(path.split("."))
                print(f"     {depth_indicator}└─ {path}")

        print("\n📄 Content by Path:")
        print("-" * 50)
        for domain, paths in paths_by_domain.items():
            print(f"\n{domain.upper()} DOMAIN:")
            for path in sorted(paths):
                # Find the memory content for this path
                content = None
                for memory in stored_memories:
                    if memory["path"] == path:
                        if isinstance(memory["content"], dict):
                            content = memory["content"].get(
                                "content", str(memory["content"])
                            )
                        else:
                            content = str(memory["content"])
                        break

                # Truncate content for readability
                if content:
                    content_preview = (
                        content[:80] + "..." if len(content) > 80 else content
                    )
                    content_preview = content_preview.replace("\n", " ").replace(
                        "\r", " "
                    )
                else:
                    content_preview = "(no content)"

                depth_indicator = "  " * len(path.split("."))
                print(f"  {depth_indicator}🗂️  {path}")
                print(f'  {depth_indicator}    💬 "{content_preview}"')

        print("\n💡 Hierarchical Consistency Issues:")
        issues_found = []

        # Check for inconsistent depths within domains
        for domain, paths in paths_by_domain.items():
            depths = [len(p.split(".")) for p in paths]
            if max(depths) - min(depths) > 2:
                issues_found.append(
                    f"{domain}: Inconsistent depths (range {min(depths)}-{max(depths)})"
                )

        # Check for very deep paths
        deep_paths = [
            path
            for path in [m["path"] for m in stored_memories]
            if len(path.split(".")) > 4
        ]
        if deep_paths:
            issues_found.append(f"Overly deep paths (>4 levels): {deep_paths}")

        # Check for single-level paths (too broad)
        shallow_paths = [
            path
            for path in [m["path"] for m in stored_memories]
            if len(path.split(".")) == 1
        ]
        if shallow_paths:
            issues_found.append(f"Too broad paths (1 level): {shallow_paths}")

        if issues_found:
            for issue in issues_found:
                print(f"   ⚠️  {issue}")
        else:
            print("   ✅ No major consistency issues found")

        print("\n🧠 LLM-Based Semantic Appropriateness Analysis:")
        print("-" * 50)
        print("🤖 Using real LLM to evaluate content-path semantic fit...")
        print()

        # Prepare memory items for batch evaluation
        memory_items = []
        for memory in stored_memories:
            if isinstance(memory["content"], dict):
                content = memory["content"].get("content", str(memory["content"]))
            else:
                content = str(memory["content"])

            memory_items.append({"path": memory["path"], "content": content})

        # Use LLM to evaluate semantic appropriateness
        evaluations = (
            await intelligent_classifier.batch_evaluate_semantic_appropriateness(
                memory_items
            )
        )

        # Display results
        for evaluation in evaluations:
            path = evaluation["item"]["path"]
            content = evaluation["item"]["content"]

            print(f"  📝 {path}")
            print(
                f'      Content: "{content[:60]}{"..." if len(content) > 60 else ""}"'
            )
            print("      🤖 LLM Evaluation:")

            # Show quality assessment
            quality = evaluation["path_quality"]
            score = evaluation["score"]
            confidence = evaluation["confidence"]

            if quality in ["excellent", "good"]:
                print(
                    f"      ✅ {quality.title()} fit (Score: {score}/100, Confidence: {confidence:.1%})"
                )
            elif quality == "acceptable":
                print(
                    f"      ⚠️  {quality.title()} fit (Score: {score}/100, Confidence: {confidence:.1%})"
                )
            else:
                print(
                    f"      ❌ {quality.title()} fit (Score: {score}/100, Confidence: {confidence:.1%})"
                )

            print(f"      💭 Reasoning: {evaluation['reasoning']}")

            # Show issues if any
            if evaluation["issues"]:
                print(f"      ⚠️  Issues: {', '.join(evaluation['issues'])}")

            # Show suggested alternative if provided
            if evaluation["suggested_path"]:
                print(f"      💡 Suggested path: {evaluation['suggested_path']}")

            print()

        # Provide summary of semantic analysis
        excellent_count = sum(
            1 for e in evaluations if e["path_quality"] == "excellent"
        )
        good_count = sum(1 for e in evaluations if e["path_quality"] == "good")
        acceptable_count = sum(
            1 for e in evaluations if e["path_quality"] == "acceptable"
        )
        poor_count = sum(
            1 for e in evaluations if e["path_quality"] in ["poor", "completely_wrong"]
        )

        print("📊 Semantic Appropriateness Summary:")
        print(f"   ✅ Excellent: {excellent_count}")
        print(f"   ✅ Good: {good_count}")
        print(f"   ⚠️  Acceptable: {acceptable_count}")
        print(f"   ❌ Poor/Wrong: {poor_count}")

        if poor_count > 0:
            print(f"\n⚠️  {poor_count} classifications need attention!")

        print("\n🎯 Recommended Improvements:")
        print("   • Maintain 2-4 levels for most concepts")
        print("   • Use consistent intermediate categories within domains")
        print("   • Follow general → specific progression")
        print("   • Consider domain-specific organizational patterns")
        print("   • Review and reclassify items marked as 'poor' or 'completely_wrong'")
        print("   • Consider LLM suggested alternative paths for better semantic fit")
        print("   • Ensure hierarchical depth matches content specificity")

        print("=" * 60)


async def demonstrate_category_structure():
    """Show how category structure is passed to LLM."""
    print("\n" + "=" * 70)
    print("Category Structure for LLM Context")
    print("=" * 70)

    llm = get_llm()

    taxonomy = LLMIterativeTaxonomy(
        taxonomy_version=TaxonomyVersion.WORKFLOW_AUTOMATION,
        llm=llm,
    )

    # Get structure for LLM
    structure = taxonomy._get_taxonomy_structure_for_llm()

    print(f"\nTaxonomy Version: {structure['version']}")
    print(f"Total Categories: {structure['total_categories']}")

    print("\nSample Paths (first 10):")
    for path in structure["sample_paths"][:10]:
        print(f"  - {path}")

    print("\nHierarchical Structure Preview:")
    structure_preview = json.dumps(structure["structure"], indent=2)
    # Show first few lines
    lines = structure_preview.split("\n")[:15]
    for line in lines:
        print(f"  {line}")
    if len(structure_preview.split("\n")) > 15:
        print("  ...")

    print("\n💡 This structure is passed to the LLM for context-aware classification")


def main():
    """Run the demonstration."""
    print("\nIntelligent Taxonomy Classification System")
    print("=" * 70)
    print("This demo shows:")
    print("1. LLM-based memory-worthiness detection")
    print("2. Confidence-based classification")
    print("3. Automatic expansion suggestions for low confidence")
    print("4. Real-time taxonomy structure changes")
    print("5. Step-by-step classification process")
    print("\nUsing real OpenAI GPT-4o-mini for actual classification.")
    print("Requires OPENAI_API_KEY environment variable.")

    try:
        asyncio.run(demonstrate_intelligent_taxonomy())

        # Optionally show category structure
        print(
            "\n🔧 Category structure demo available via demonstrate_category_structure()"
        )
        # Uncomment the following to show category structure automatically:
        # asyncio.run(demonstrate_category_structure())

    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")

    print("\n" + "=" * 70)
    print("Key Features Demonstrated:")
    print("=" * 70)
    print("✓ Real LLM-based memory-worthiness filtering")
    print("✓ Confidence-based classification decisions")
    print("✓ Automatic taxonomy expansion for low confidence")
    print("✓ Context-aware prompting with full taxonomy structure")
    print("✓ Real-time structure changes visualization")
    print("✓ Separation of classification logic from memory storage")
    print("\n🎯 The system handles the exact classification flow specified:")
    print("   1. LLM determines if input is memory-worthy")
    print("   2. Low confidence triggers expansion or parent category use")
    print("   3. High confidence proceeds with classification")
    print("   4. Full category structure provided to LLM for context")


if __name__ == "__main__":
    main()

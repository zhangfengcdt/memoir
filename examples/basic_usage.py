"""
Basic usage example of LangMem-ProllyTree integration.

This example demonstrates how to use ProllyTreeMemoryStoreManager as a drop-in
replacement for LangMem's standard memory store, providing 10-20x performance improvements
through semantic hierarchical keys instead of vector similarity search.

Requirements:
    pip install langchain-openai
    export OPENAI_API_KEY=your-api-key-here

Usage:
    export OPENAI_API_KEY=your-api-key-here
    python examples/basic_usage.py
"""

import asyncio
import os
import sys
import tempfile

from memoir import ProllyTreeMemoryStoreManager
from memoir.taxonomy.intelligent_classifier import IntelligentClassifier
from memoir.taxonomy.taxonomy_presets import TaxonomyVersion


def get_llm() -> object:
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

        print("   ✅ Using OpenAI GPT-4o-mini for semantic classification")
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


async def main():
    """Demonstrate basic usage of ProllyTree as a LangMem store replacement."""

    # Create temporary directory for demo
    with tempfile.TemporaryDirectory() as temp_dir:
        prolly_path = os.path.join(temp_dir, "memory_store")

        print("🚀 LangMem-ProllyTree Basic Usage Example\n")
        print("=" * 50)

        # Set up the LLM for semantic classification
        print("\n1. Setting up LLM for semantic classification:")
        llm = get_llm()

        # Create intelligent classifier with configurable aggressiveness
        # This uses GPT for smart classification with automatic taxonomy expansion
        # You can tune these parameters to control how aggressive the classifier is:

        # Conservative settings (only store high-confidence memories):
        # confidence_thresholds={"high": 0.9, "medium": 0.7, "low": 0.5}

        # Aggressive settings (store almost everything):
        # confidence_thresholds={"high": 0.6, "medium": 0.3, "low": 0.0}

        # Default balanced settings:
        classifier = IntelligentClassifier(
            llm=llm,
            taxonomy_version=TaxonomyVersion.GENERAL,
            confidence_thresholds={
                "high": 0.8,  # High confidence threshold - memories above this are stored immediately
                "medium": 0.5,  # Medium confidence threshold - memories above this are considered good
                "low": 0.0,  # CRITICAL: Low confidence threshold - anything below this gets REJECTED
            },
            min_items_for_expansion=2,  # Lower threshold for demo - higher values = less taxonomy expansion
        )
        print("   🎯 Using balanced aggressiveness settings (low threshold = 0.0)")
        print("   💡 IMPORTANT: The 'low' threshold controls what gets stored!")
        print("   💡 Try setting low=0.5 or low=0.7 to be more selective")

        # Initialize ProllyTreeMemoryStoreManager
        # This replaces LangMem's InMemoryStore with 10-20x better performance
        print("\n2. Initializing ProllyTree Memory Store:")
        # Create a simple classifier for the store
        from memoir.taxonomy.semantic_classifier import SemanticClassifier

        simple_classifier = SemanticClassifier(llm=None)

        memory_manager = ProllyTreeMemoryStoreManager(
            prolly_path=prolly_path,
            classifier=simple_classifier,
            enable_versioning=True,  # Git-like versioning for audit trails
        )

        # Set up intelligent classifier with the store
        classifier.memory_store = memory_manager.prolly_store
        print("   ✅ ProllyTree store initialized with versioning")

        user_id = "user123"

        # Store memories with semantic classification
        print("\n3. Storing memories with semantic classification:")

        memories_to_store = [
            "My name is Sarah Johnson and I'm 32 years old.",
            "I work as a senior software engineer at TechCorp in San Francisco.",
            "I prefer dark mode in all my development environments and applications.",
            "My primary programming language is Python, but I also use JavaScript for frontend work.",
            "I drink coffee every morning, specifically a double espresso with oat milk.",
            "I have 8 years of experience in machine learning and data science.",
            "My favorite IDE is VS Code with the Monokai Pro theme.",
            "I graduated from Stanford University with a Computer Science degree in 2014.",
        ]

        for i, memory_text in enumerate(memories_to_store, 1):
            # Use intelligent classifier for better classification
            result = await classifier.process_memory_with_storage(
                memory_text, metadata={"user_id": user_id, "source": "demo"}
            )
            print(f"   [{i}] Stored: '{memory_text[:40]}...'")
            print(f"       → Path: {result.classification.path}")
            print(f"       → Confidence: {result.classification.confidence:.2f}")
            print(f"       → Action: {result.classification.suggested_action}")
            if result.classification.reasoning:
                print(f"       → Reasoning: {result.classification.reasoning[:60]}...")

        # Retrieve stored memories
        print("\n4. Retrieving memories with intelligent search:")

        # Search queries using intelligent classifier's retrieval
        queries = [
            "What is the user's name and age?",
            "Where does the user work and what is their role?",
            "What are the user's IDE and theme preferences?",
            "What does the user drink in the morning?",
        ]

        for query in queries:
            results = classifier.get_stored_memories(limit=10)
            # Simple text matching for demo - in production you'd use semantic search
            exclude_words = {
                "what",
                "is",
                "the",
                "user",
                "and",
                "does",
                "are",
                "where",
                "how",
            }
            query_keywords = [
                word.lower()
                for word in query.lower().split()
                if word.lower() not in exclude_words
            ]

            # Score memories by keyword relevance
            scored_memories = []
            for memory in results:
                content_str = str(memory["content"]).lower()
                matches = sum(1 for keyword in query_keywords if keyword in content_str)
                if matches > 0:
                    # Boost score for exact phrase matches
                    phrase_bonus = 2 if " ".join(query_keywords) in content_str else 0
                    score = matches + phrase_bonus
                    scored_memories.append((score, memory))

            # Sort by relevance score (highest first)
            scored_memories.sort(reverse=True, key=lambda x: x[0])

            print(f"\n   🔍 Query: '{query}'")
            if scored_memories:
                best_memory = scored_memories[0][1]
                content = best_memory["content"]
                if isinstance(content, dict):
                    content = content.get("content", str(content))
                print(f"   📝 Found: {content}")
            else:
                print("   📝 No specific match found")

        # Show intelligent semantic organization
        print("\n5. Intelligent semantic organization:")
        all_memories = classifier.get_stored_memories(limit=100)

        # Group by taxonomy paths
        path_groups = {}
        for memory in all_memories:
            path = memory["path"]
            if path not in path_groups:
                path_groups[path] = []
            path_groups[path].append(memory)

        print("   Memories intelligently organized by semantic paths:")
        for path in sorted(path_groups.keys()):
            memories = path_groups[path]
            print(f"   📁 {path}: {len(memories)} memories")
            for memory in memories:
                content = memory.get("content", str(memory.get("data", "")))
                if isinstance(content, dict):
                    content = content.get("content", str(content))
                print(f"       - {content[:80]}{'...' if len(content) > 80 else ''}")


if __name__ == "__main__":
    asyncio.run(main())

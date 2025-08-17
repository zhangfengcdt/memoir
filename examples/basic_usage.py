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

from langmem_prollytree import ProllyTreeMemoryStoreManager
from langmem_prollytree.taxonomy.iterative_taxonomy import LLMIterativeTaxonomy
from langmem_prollytree.taxonomy.semantic_classifier import SemanticClassifier


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

        # Create LLM-driven iterative taxonomy
        # This uses GPT to intelligently expand the taxonomy based on unclassified content
        taxonomy = LLMIterativeTaxonomy(
            llm=llm,  # Same LLM used for expansion
            min_items_threshold=3,
            enable_combinations=True,
        )
        classifier = SemanticClassifier(llm=llm, taxonomy=taxonomy)

        # Initialize ProllyTreeMemoryStoreManager
        # This replaces LangMem's InMemoryStore with 10-20x better performance
        print("\n2. Initializing ProllyTree Memory Store:")
        memory_manager = ProllyTreeMemoryStoreManager(
            prolly_path=prolly_path,
            classifier=classifier,
            enable_versioning=True,  # Git-like versioning for audit trails
        )
        print("   ✅ ProllyTree store initialized with versioning")

        # Get the store for direct operations
        store = memory_manager.prolly_store
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
            memory = await store.store_memory_async(user_id, memory_text)
            print(f"   [{i}] Stored: '{memory_text[:40]}...'")
            print(f"       → Path: {memory.key}")
            print(f"       → Confidence: {memory.confidence:.2f}")

        # Retrieve stored memories
        print("\n4. Retrieving memories with intelligent search:")

        # Search for personal information
        results = await store.retrieve_memories_async(
            user_id, "What is the user's name and age?", limit=3
        )
        print("\n   🔍 Query: 'What is the user's name and age?'")
        if results:
            print(f"   📝 Found: {results[0].content}")

        # Search for work information
        results = await store.retrieve_memories_async(
            user_id, "Where does the user work and what is their role?", limit=3
        )
        print("\n   🔍 Query: 'Where does the user work and what is their role?'")
        if results:
            print(f"   📝 Found: {results[0].content}")

        # Search for UI preferences
        results = await store.retrieve_memories_async(
            user_id, "What are the user's IDE and theme preferences?", limit=3
        )
        print("\n   🔍 Query: 'What are the user's IDE and theme preferences?'")
        if results:
            print(f"   📝 Found: {results[0].content}")

        # Search for beverage preferences
        results = await store.retrieve_memories_async(
            user_id, "What does the user drink in the morning?", limit=3
        )
        print("\n   🔍 Query: 'What does the user drink in the morning?'")
        if results:
            print(f"   📝 Found: {results[0].content}")

        # Show semantic organization
        print("\n5. Automatic semantic organization:")
        all_results = store.search((user_id,), limit=100)
        paths = set()
        for _, key, _ in all_results:
            category = key.split(".")[0] if "." in key else key
            paths.add(category)

        print("   Memories automatically organized by category:")
        for category in sorted(paths):
            count = sum(1 for _, k, _ in all_results if k.startswith(category))
            print(f"   📁 {category}: {count} memories")
            for _, key, content in all_results:
                if key.startswith(category):
                    print(f"       - {content}")


if __name__ == "__main__":
    asyncio.run(main())

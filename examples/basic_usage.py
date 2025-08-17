"""
Basic usage example of LangMem-ProllyTree integration.

This example demonstrates how to use ProllyTreeMemoryStoreManager as a drop-in
replacement for LangMem's standard memory store, providing 10-20x performance improvements
through semantic hierarchical keys instead of vector similarity search.

Requirements:
    pip install langchain-openai
    export OPENAI_API_KEY=your-api-key-here

To run with mock LLM (no API key required):
    python examples/basic_usage.py --mock
"""

import asyncio
import os
import sys
import tempfile
from typing import Optional

from langmem_prollytree import ProllyTreeMemoryStoreManager
from langmem_prollytree.taxonomy.iterative_taxonomy import LLMIterativeTaxonomy
from langmem_prollytree.taxonomy.semantic_classifier import SemanticClassifier


class MockLLM:
    """Mock LLM for demonstration purposes when no API key is available."""

    async def ainvoke(self, prompt: str):
        """Simulate LLM classification based on content keywords."""
        content = prompt.lower()

        # Simple rule-based classification for demo
        if any(word in content for word in ["dark mode", "light mode", "theme"]):
            path = "preferences.interface.theme"
        elif any(word in content for word in ["python", "javascript", "rust"]):
            path = "profile.professional.skills.technical.programming"
        elif any(word in content for word in ["coffee", "tea", "drink"]):
            path = "preferences.personal.lifestyle.beverages"
        elif any(word in content for word in ["name", "called", "i'm", "i am"]):
            path = "profile.personal.identity.name"
        else:
            path = "context.conversation.recent"

        class Response:
            content = f'{{"primary_path": "{path}", "confidence": 0.85, "alternative_paths": [], "reasoning": "Classified based on keywords"}}'

        return Response()


def get_llm(use_mock: bool = False) -> Optional[object]:
    """Get LLM instance - either OpenAI or Mock based on configuration."""
    if use_mock:
        print("   ⚠️  Using MockLLM for demonstration (no API calls)")
        return MockLLM()

    # Try to use OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("   ⚠️  No OPENAI_API_KEY found. Using MockLLM instead.")
        print("      Set OPENAI_API_KEY environment variable to use real LLM")
        return MockLLM()

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
        print("   ⚠️  langchain-openai not installed.")
        print("      Install with: pip install langchain-openai")
        print("      Using MockLLM instead.")
        return MockLLM()


async def main():
    """Demonstrate basic usage of ProllyTree as a LangMem store replacement."""

    # Check for --mock flag
    use_mock = "--mock" in sys.argv

    # Create temporary directory for demo
    with tempfile.TemporaryDirectory() as temp_dir:
        prolly_path = os.path.join(temp_dir, "memory_store")

        print("🚀 LangMem-ProllyTree Basic Usage Example\n")
        print("=" * 50)

        # Set up the LLM for semantic classification
        print("\n1. Setting up LLM for semantic classification:")
        llm = get_llm(use_mock=use_mock)

        # Create LLM-driven iterative taxonomy
        # This uses GPT to intelligently expand the taxonomy based on unclassified content
        taxonomy = LLMIterativeTaxonomy(
            llm=llm,  # Same LLM used for expansion
            min_items_threshold=3,  # Expand after 3 items in 'other'
            enable_combinations=True,  # Enable pattern-based combinations
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
            "Remember that I prefer dark mode.",
            "I mainly work with Python and sometimes JavaScript.",
            "Coffee is my favorite morning drink.",
        ]

        for i, memory_text in enumerate(memories_to_store, 1):
            memory = await store.store_memory_async(user_id, memory_text)
            print(f"   [{i}] Stored: '{memory_text[:40]}...'")
            print(f"       → Path: {memory.key}")
            print(f"       → Confidence: {memory.confidence:.2f}")

        # Retrieve stored memories
        print("\n4. Retrieving memories with intelligent search:")

        # Search for lighting preferences
        results = store.retrieve_memories(
            user_id, "What are my lighting preferences?", limit=3
        )
        print("\n   🔍 Query: 'What are my lighting preferences?'")
        if results:
            print(f"   📝 Found: {results[0].content}")

        # Search for programming languages
        results = store.retrieve_memories(
            user_id, "What programming languages do I use?", limit=3
        )
        print("\n   🔍 Query: 'What programming languages do I use?'")
        if results:
            print(f"   📝 Found: {results[0].content}")

        # Search for beverage preferences
        results = store.retrieve_memories(user_id, "What do I like to drink?", limit=3)
        print("\n   🔍 Query: 'What do I like to drink?'")
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

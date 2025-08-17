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
        # Extract the actual memory content from the prompt
        if "MEMORY CONTENT:" in prompt:
            start = prompt.find("MEMORY CONTENT:") + len("MEMORY CONTENT:")
            end = prompt.find("\n\n", start)
            if end == -1:
                end = prompt.find("AVAILABLE TAXONOMY", start)
            if end == -1:
                content = prompt[start:].strip().lower()
            else:
                content = prompt[start:end].strip().lower()
        else:
            content = prompt.lower()

        # More sophisticated rule-based classification for demo
        if any(
            word in content
            for word in ["name", "sarah", "johnson", "years old", "age", "32"]
        ):
            path = "profile.personal.identity.name"
            confidence = 0.95
        elif any(
            word in content
            for word in ["engineer", "techcorp", "san francisco", "work as"]
        ):
            path = "profile.professional.current.role"
            confidence = 0.90
        elif any(
            word in content for word in ["dark mode", "light mode", "theme", "monokai"]
        ):
            path = "preferences.interface.theme"
            confidence = 0.85
        elif any(
            word in content
            for word in ["python", "javascript", "programming language", "frontend"]
        ):
            path = "profile.professional.skills.technical.programming"
            confidence = 0.90
        elif any(
            word in content
            for word in ["coffee", "espresso", "oat milk", "drink", "morning"]
        ):
            path = "preferences.personal.lifestyle.beverages"
            confidence = 0.85
        elif any(
            word in content
            for word in ["experience", "machine learning", "data science", "8 years"]
        ):
            path = "experience.professional.expertise"
            confidence = 0.85
        elif any(
            word in content
            for word in ["ide", "vs code", "editor", "development environment"]
        ):
            path = "preferences.work.tools.development"
            confidence = 0.85
        elif any(
            word in content
            for word in ["graduated", "stanford", "degree", "2014", "university"]
        ):
            path = "profile.personal.education.history"
            confidence = 0.90
        else:
            path = "context.conversation.recent"
            confidence = 0.50

        class Response:
            content = f'{{"primary_path": "{path}", "confidence": {confidence}, "alternative_paths": [], "reasoning": "Classified based on content analysis"}}'

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

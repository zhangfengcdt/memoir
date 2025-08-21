"""
Memoir Memory System Architecture Example.

This example demonstrates the clean layered architecture of Memoir's memory system,
showing how components are assembled with proper dependency injection to create
a semantic memory store with intelligent classification and search capabilities.

Architecture Overview:
    1. Storage Layer: ProllyTreeStore - Pure storage with aggregated memories at semantic paths
    2. Classification Layer: IntelligentClassifier - LLM-powered semantic path classification
    3. Search Layer: IntelligentSearchEngine - LLM-guided path selection for queries
    4. Management Layer: ProllyTreeMemoryStoreManager - Orchestrates all components

Key Design Principles:
    - Clean separation of concerns between layers
    - Dependency injection for testability and flexibility
    - Semantic hierarchical paths instead of UUID keys
    - Memory aggregation at meaningful semantic locations
    - Git-like versioning with cryptographic integrity

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
from memoir.classifier.intelligent_classifier import IntelligentClassifier
from memoir.search.intelligent_search import IntelligentSearchEngine
from memoir.taxonomy.taxonomy_presets import TaxonomyVersion


def get_llm() -> object:
    """Get OpenAI LLM instance - requires API key and langchain-openai."""
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("   ⏺ Error: OPENAI_API_KEY environment variable is required")
        print("      Set your OpenAI API key: export OPENAI_API_KEY=your-api-key-here")
        print("      Get an API key at: https://platform.openai.com/api-keys")
        sys.exit(1)

    # Try to import and create OpenAI LLM
    try:
        from langchain_openai import ChatOpenAI

        print("   ⏺ Using OpenAI GPT-4o-mini for semantic classification")
        return ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            # API key is automatically picked up from OPENAI_API_KEY environment variable
            max_tokens=500,
        )
    except ImportError:
        print("   ⏺ Error: langchain-openai package is required")
        print("      Install with: pip install langchain-openai")
        sys.exit(1)


async def main():
    """Demonstrate basic usage of ProllyTree as a LangMem store replacement."""

    # Create temporary directory for demo
    with tempfile.TemporaryDirectory() as temp_dir:
        prolly_path = os.path.join(temp_dir, "memory_store")

        print("⏺ LangMem-ProllyTree Basic Usage Example\n")
        print("=" * 50)

        # Set up the LLM for semantic classification
        print("\n1. Setting up LLM for semantic classification:")
        llm = get_llm()

        # Initialize components in proper dependency order
        print("\n2. Building Memory System Components:")
        print("   Following clean dependency injection pattern")

        # Step 1: Create the storage layer (pure storage, no dependencies)
        print("   Step 1: Creating storage layer...")
        from memoir.store.prolly_adapter import ProllyTreeStore

        prolly_store = ProllyTreeStore(
            path=prolly_path,
            enable_versioning=True,
            cache_size=10000,
        )
        print("   ⏺ ProllyTreeStore created (pure storage, no business logic)")

        # Step 2: Classifier already created (depends on LLM)
        print("   Step 2: Create classifier...")
        # Create intelligent classifier with configurable aggressiveness
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
        print("   ⏺ IntelligentClassifier configured with LLM")
        print("   ⏺ Using balanced aggressiveness settings (low threshold = 0.0)")
        print("   ⏺ IMPORTANT: The 'low' threshold controls what gets stored!")
        print("   ⏺ Try setting low=0.5 or low=0.7 to be more selective")

        # Step 3: Create the search engine (depends on LLM + store)
        print("   Step 3: Creating search engine...")
        search_engine = IntelligentSearchEngine(
            llm=llm,  # Use the same LLM for search
            store=prolly_store,
        )
        print("   ⏺ IntelligentSearchEngine configured for LLM-powered path selection")

        # Step 4: Create the memory manager (orchestrates all components)
        print("   Step 4: Creating memory manager...")
        memory_manager = ProllyTreeMemoryStoreManager(
            prolly_store=prolly_store,  # Inject storage
            classifier=classifier,  # Inject classifier
            search_engine=search_engine,  # Inject search
            enable_versioning=True,
        )
        print(
            "   ⏺ MemoryManager assembled - orchestrates storage, classification & search"
        )
        print("   ⏺ All components properly injected with clean dependencies")

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
            # Store through memory manager (which uses the intelligent classifier)
            semantic_key = await memory_manager.store_memory(
                content=memory_text,
                namespace=user_id,
                metadata={"source": "demo"},
                auto_classify=True,
            )
            print(f"   [{i}] Stored: '{memory_text[:40]}...'")
            print(f"       → Path: {semantic_key}")
            print("       → Aggregated at semantic path")

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
            # Use the memory manager's search functionality
            results = await memory_manager.search_memories(
                query=query, namespace=user_id, limit=5
            )

            print(f"\n   ⏺ Query: '{query}'")
            if results:
                # Show the best result
                best_result = results[0]
                content = best_result.content
                print(f"   ⏺ Found: {content}")
                print(f"   ⏺ Path: {best_result.id}")
            else:
                print("   ⏺ No matches found")

        # Show intelligent semantic organization with aggregated memories
        print("\n5. Intelligent semantic organization (aggregated by path):")

        # Get all aggregated memories by searching the store directly
        search_results = memory_manager.prolly_store.search((user_id,), limit=100)

        print("   Memories aggregated by semantic paths:")
        for _, path, data in search_results:
            if isinstance(data, dict) and "memories" in data:
                # This is an aggregated memory
                memory_count = data.get("count", len(data.get("memories", [])))
                print(f"   ⏺ {path}: {memory_count} aggregated memories")

                # Show a few examples from this aggregated path
                memories = data.get("memories", [])
                for j, memory_entry in enumerate(memories[:3]):  # Show first 3
                    content = memory_entry.get("content", "")
                    confidence = memory_entry.get("confidence", 0)
                    print(
                        f"       [{j + 1}] {content[:60]}... (conf: {confidence:.2f})"
                    )

                if len(memories) > 3:
                    print(f"       ... and {len(memories) - 3} more memories")
            else:
                # Legacy single memory
                content = data.get("content", str(data))
                print(f"   ⏺ {path}: {content[:60]}...")


if __name__ == "__main__":
    asyncio.run(main())

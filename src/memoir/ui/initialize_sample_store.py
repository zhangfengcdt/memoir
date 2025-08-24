#!/usr/bin/env python3
"""
Initialize a sample memory store with data and branches for UI visualization.
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from memoir import ProllyTreeMemoryStoreManager
from memoir.classifier.intelligent import IntelligentClassifier
from memoir.search.intelligent import IntelligentSearchEngine
from memoir.store.prolly_adapter import ProllyTreeStore
from memoir.taxonomy.taxonomy_presets import TaxonomyVersion


async def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Initialize sample memory store")
    parser.add_argument(
        "--store-path",
        default="/tmp/memoir_ui_store",
        help="Path where to create the memory store (default: /tmp/memoir_ui_store)"
    )
    args = parser.parse_args()
    
    # Use the store path from arguments
    store_path = args.store_path
    
    # Remove existing store if it exists
    if os.path.exists(store_path):
        import shutil
        shutil.rmtree(store_path)
    
    print(f"Initializing memory store at: {store_path}")
    
    # Check for OpenAI API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("\n⚠️  Warning: OPENAI_API_KEY not set. Using a mock LLM for demo.")
        print("   For real classification, set: export OPENAI_API_KEY=your-key")
        # Create a mock LLM for demo purposes
        from unittest.mock import MagicMock
        llm = MagicMock()
        # Mock the invoke method to return a simple classification
        llm.invoke = lambda x: type('obj', (object,), {'content': '{"primary_path": "profile.personal.name", "confidence": 0.8, "reasoning": "mock"}'})()
    else:
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                max_tokens=500,
            )
            print("✓ Using OpenAI GPT-4o-mini for intelligent classification")
        except ImportError:
            print("⚠️  langchain-openai not installed. Using mock LLM.")
            from unittest.mock import MagicMock
            llm = MagicMock()
            llm.invoke = lambda x: type('obj', (object,), {'content': '{"primary_path": "profile.personal.name", "confidence": 0.8, "reasoning": "mock"}'})()
    
    print("\n=== Setting up Memoir Components ===")
    
    # 1. Initialize storage layer
    print("1. Creating storage layer...")
    store = ProllyTreeStore(
        path=store_path,
        enable_versioning=True,
        auto_commit=False,  # We'll manually commit for demonstration
        cache_size=10000,
    )
    print("   ✓ ProllyTreeStore created with Git-like versioning")
    
    # 2. Create intelligent classifier
    print("2. Creating intelligent classifier...")
    classifier = IntelligentClassifier(
        llm=llm,
        taxonomy_version=TaxonomyVersion.GENERAL,
        confidence_thresholds={
            "high": 0.8,
            "medium": 0.5,
            "low": 0.0,  # Accept all for demo
        },
        min_items_for_expansion=2,
    )
    print("   ✓ IntelligentClassifier configured")
    
    # 3. Create search engine
    print("3. Creating search engine...")
    search_engine = IntelligentSearchEngine(
        llm=llm,
        store=store,
    )
    print("   ✓ IntelligentSearchEngine ready")
    
    # 4. Create memory manager
    print("4. Creating memory manager...")
    memory_manager = ProllyTreeMemoryStoreManager(
        prolly_store=store,
        classifier=classifier,
        search_engine=search_engine,
        enable_versioning=True,
        auto_commit=False
    )
    print("   ✓ ProllyTreeMemoryStoreManager assembled")
    
    # Initialize main branch with sample memories
    print("\n=== Adding memories to main branch ===")
    
    # Define namespace for this user
    namespace = "alice_chen"
    
    # User profile memories
    await memory_manager.store_memory(
        "User's name is Alice Chen",
        namespace=namespace,
        metadata={"type": "profile", "category": "personal"}
    )
    
    await memory_manager.store_memory(
        "Alice is a senior software engineer at TechCorp",
        namespace=namespace,
        metadata={"type": "profile", "category": "professional"}
    )
    
    await memory_manager.store_memory(
        "Alice specializes in Python, TypeScript, and distributed systems",
        namespace=namespace,
        metadata={"type": "profile", "category": "skills"}
    )
    
    # Preferences
    await memory_manager.store_memory(
        "Alice prefers dark mode in all applications",
        namespace=namespace,
        metadata={"type": "preference", "category": "ui"}
    )
    
    await memory_manager.store_memory(
        "Alice likes to receive technical explanations with code examples",
        namespace=namespace,
        metadata={"type": "preference", "category": "communication"}
    )
    
    # Project memories
    await memory_manager.store_memory(
        "Alice is working on a chatbot project using LangChain",
        namespace=namespace,
        metadata={"type": "project", "category": "current"}
    )
    
    await memory_manager.store_memory(
        "The chatbot needs to integrate with Slack and Discord",
        namespace=namespace,
        metadata={"type": "project", "category": "requirements"}
    )
    
    # Technical context
    await memory_manager.store_memory(
        "Alice uses pytest for testing and prefers TDD approach",
        namespace=namespace,
        metadata={"type": "technical", "category": "methodology"}
    )
    
    await memory_manager.store_memory(
        "Alice's team follows GitFlow branching strategy",
        namespace=namespace,
        metadata={"type": "technical", "category": "workflow"}
    )
    
    # Personal interests
    await memory_manager.store_memory(
        "Alice enjoys hiking and photography on weekends",
        namespace=namespace,
        metadata={"type": "personal", "category": "hobbies"}
    )
    
    # Commit the initial state
    commit1 = store.commit("Initial user profile and preferences")
    print(f"Commit 1: {commit1[:8] if commit1 else 'No commit'} - Initial user profile and preferences")
    
    # Add more memories
    await memory_manager.store_memory(
        "Alice mentioned she's learning Rust in her spare time",
        namespace=namespace,
        metadata={"type": "learning", "category": "programming"}
    )
    
    await memory_manager.store_memory(
        "Alice wants to build a personal knowledge management system",
        namespace=namespace,
        metadata={"type": "project", "category": "personal"}
    )
    
    commit2 = store.commit("Added learning goals and personal projects")
    print(f"Commit 2: {commit2[:8] if commit2 else 'No commit'} - Added learning goals and personal projects")
    
    # Create feature branch for experimentation
    print("\n=== Creating feature/chatbot-context branch ===")
    store.tree.create_branch("feature/chatbot-context")
    store.tree.checkout("feature/chatbot-context")
    
    # Add chatbot-specific memories
    await memory_manager.store_memory(
        "Chatbot should maintain conversation context for 24 hours",
        namespace=namespace,
        metadata={"type": "requirement", "category": "chatbot"}
    )
    
    await memory_manager.store_memory(
        "Users prefer concise responses with optional detailed explanations",
        namespace=namespace,
        metadata={"type": "preference", "category": "chatbot"}
    )
    
    await memory_manager.store_memory(
        "Chatbot needs to handle code snippets and markdown formatting",
        namespace=namespace,
        metadata={"type": "requirement", "category": "chatbot"}
    )
    
    commit3 = store.commit("Added chatbot-specific context and requirements")
    print(f"Commit 3: {commit3[:8] if commit3 else 'No commit'} - Added chatbot-specific context (feature branch)")
    
    # Create another branch for UI preferences
    store.tree.checkout("main")
    store.tree.create_branch("feature/ui-preferences")
    store.tree.checkout("feature/ui-preferences")
    
    print("\n=== Creating feature/ui-preferences branch ===")
    
    await memory_manager.store_memory(
        "Alice prefers Monaco editor for code editing",
        namespace=namespace,
        metadata={"type": "preference", "category": "editor"}
    )
    
    await memory_manager.store_memory(
        "Alice wants keyboard shortcuts similar to VSCode",
        namespace=namespace,
        metadata={"type": "preference", "category": "shortcuts"}
    )
    
    commit4 = store.commit("Added UI and editor preferences")
    print(f"Commit 4: {commit4[:8] if commit4 else 'No commit'} - Added UI preferences (feature branch)")
    
    # Switch back to main
    store.tree.checkout("main")
    
    # Add one more commit to main
    await memory_manager.store_memory(
        "Alice's team is migrating from JavaScript to TypeScript",
        namespace=namespace,
        metadata={"type": "project", "category": "migration"}
    )
    
    commit5 = store.commit("Added team migration information")
    print(f"Commit 5: {commit5[:8] if commit5 else 'No commit'} - Added team migration info (main branch)")
    
    # Create experimental branch
    store.tree.create_branch("experimental/memory-optimization")
    store.tree.checkout("experimental/memory-optimization")
    
    print("\n=== Creating experimental/memory-optimization branch ===")
    
    await memory_manager.store_memory(
        "Testing memory compression techniques for large conversations",
        namespace=namespace,
        metadata={"type": "experimental", "category": "optimization"}
    )
    
    commit6 = store.commit("Experimental memory optimization research")
    print(f"Commit 6: {commit6[:8] if commit6 else 'No commit'} - Memory optimization experiments")
    
    # Back to main
    store.tree.checkout("main")
    
    # Print summary
    print("\n" + "="*60)
    print(f"✅ Memory store initialized at: {store_path}")
    print("\nBranches created:")
    branches = store.tree.list_branches()
    current_branch = store.tree.current_branch()
    for branch in branches:
        current = " (current)" if branch == current_branch else ""
        print(f"  - {branch}{current}")
    
    print("\nSample memories stored across multiple commits and branches.")
    print("\nYou can now connect the UI to this store using:")
    print(f"  /connect {store_path}")
    
    # Also save a metadata file for the UI to read
    metadata = {
        "store_path": store_path,
        "branches": branches,
        "current_branch": store.tree.current_branch(),
        "total_memories": len(list(store.tree.list_keys()) if hasattr(store.tree, 'list_keys') else []),
        "commits": {
            "main": [commit1[:8], commit2[:8], commit5[:8]],
            "feature/chatbot-context": [commit3[:8]],
            "feature/ui-preferences": [commit4[:8]],
            "experimental/memory-optimization": [commit6[:8]]
        }
    }
    
    metadata_path = Path(store_path) / "ui_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\nMetadata saved to: {metadata_path}")


if __name__ == "__main__":
    asyncio.run(main())
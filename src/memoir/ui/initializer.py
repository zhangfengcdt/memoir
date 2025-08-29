#!/usr/bin/env python3
"""
Initialize a sample memory store with data and branches for UI visualization.
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

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
        default=os.path.join(tempfile.gettempdir(), "memoir_ui_store"),  # nosec B108
        help="Path where to create the memory store (default: system temp dir + memoir_ui_store)",
    )
    parser.add_argument(
        "--data-file",
        type=str,
        help="Path to LOCOMO JSON file containing conversations",
    )
    parser.add_argument(
        "--person",
        type=str,
        help="Person name to create memories for (required when using --data-file)",
    )
    parser.add_argument(
        "--session",
        type=str,
        help="Process specified session(s) within the conversation. Examples: 1, 1-3, 1,3,5. If not specified, process all sessions",
    )
    parser.add_argument(
        "--conversation",
        type=int,
        default=1,
        help="Conversation ID to load (1-indexed, default: 1)",
    )
    args = parser.parse_args()

    # Validate LOCOMO-specific arguments
    if args.data_file:
        if not args.person:
            print("Error: --person is required when using --data-file")
            sys.exit(1)
        if not os.path.exists(args.data_file):
            print(f"Error: Data file not found: {args.data_file}")
            sys.exit(1)

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
        llm.invoke = lambda x: type(
            "obj",
            (object,),
            {
                "content": '{"primary_path": "profile.personal.name", "confidence": 0.8, "reasoning": "mock"}'
            },
        )()
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
            llm.invoke = lambda x: type(
                "obj",
                (object,),
                {
                    "content": '{"primary_path": "profile.personal.name", "confidence": 0.8, "reasoning": "mock"}'
                },
            )()

    print("\n=== Setting up Memoir Components ===")

    # 1. Initialize storage layer
    print("1. Creating storage layer...")

    # Initialize git repository if needed for versioning
    if not os.path.exists(os.path.join(store_path, ".git")):
        print("   Initializing git repository for versioning...")
        os.makedirs(store_path, exist_ok=True)
        subprocess.run(["git", "init"], cwd=store_path, check=True, capture_output=True)

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
        auto_commit=False,
    )
    print("   ✓ ProllyTreeMemoryStoreManager assembled")

    # Choose data source: LOCOMO file or sample data
    if args.data_file:
        print(f"\n=== Processing LOCOMO data from {args.data_file} ===")
        await process_locomo_data(
            memory_manager,
            store,
            args.data_file,
            args.person,
            args.session,
            args.conversation,
        )
    else:
        print("\n=== Adding sample memories to main branch ===")
        await create_sample_memories(memory_manager, store)

    # Skip sample data commits if processing LOCOMO data
    if not args.data_file:
        await create_sample_branches_and_commits(memory_manager, store)

    # Print summary
    await print_summary(store, store_path, args.data_file)


def _parse_session_parameter(session: Optional[str]) -> Optional[list[int]]:
    """Parse session parameter to handle single values, ranges, and lists."""
    if not session:
        return None

    session_list = []
    parts = session.split(",")

    for part in parts:
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-")
                start, end = int(start.strip()), int(end.strip())
                session_list.extend(range(start, end + 1))
            except ValueError:
                raise ValueError(
                    f"Invalid session range format: {part}. Use format like '1-3'"
                )
        else:
            try:
                session_list.append(int(part))
            except ValueError:
                raise ValueError(f"Invalid session number: {part}")

    return sorted(set(session_list))


async def process_locomo_data(
    memory_manager: ProllyTreeMemoryStoreManager,
    store: ProllyTreeStore,
    data_file: str,
    person_name: str,
    session: Optional[str],
    conversation_id: int,
):
    """Process LOCOMO conversation data and ingest into memory store."""
    print(f"Loading LOCOMO data for {person_name} from conversation {conversation_id}")

    # Load conversation data
    with open(data_file) as f:
        content = f.read()

    all_conversations = json.loads(content)

    if conversation_id < 1 or conversation_id > len(all_conversations):
        raise ValueError(
            f"Invalid conversation ID {conversation_id}. Available conversations: 1-{len(all_conversations)}"
        )

    data = all_conversations[conversation_id - 1]
    conversation_data = data.get("conversation", {})

    # Parse session parameter
    session_list = _parse_session_parameter(session)

    if session_list:
        session_keys = [f"session_{s}" for s in session_list]
        available_sessions = [
            k.replace("session_", "")
            for k in conversation_data
            if k.startswith("session_") and not k.endswith("_date_time")
        ]
        missing_sessions = [
            str(s) for s in session_list if f"session_{s}" not in conversation_data
        ]
        if missing_sessions:
            print(
                f"Error: Sessions {missing_sessions} not found. Available sessions: {available_sessions}"
            )
            return
        print(f"Processing sessions: {', '.join(map(str, session_list))}")
    else:
        session_keys = [
            k
            for k in conversation_data
            if k.startswith("session_") and not k.endswith("_date_time")
        ]
        print("Processing all sessions")

    # Process memories for each session
    namespace = "default"  # Use default namespace for UI compatibility
    memories_processed = 0
    total_sessions = len(session_keys)

    print(f"Processing {total_sessions} session(s) for {person_name}...")

    for session_idx, session_key in enumerate(session_keys, 1):
        session_data = conversation_data.get(session_key, [])
        session_date_key = f"{session_key}_date_time"
        session_date = conversation_data.get(session_date_key, "unknown date")

        session_memories = []
        conversation_history = []

        print(
            f"[{session_idx}/{total_sessions}] Processing {session_key} ({session_date})..."
        )

        # Count total exchanges for this session to show progress
        total_exchanges = sum(
            1
            for exchange in session_data
            if exchange.get("speaker") == person_name
            and exchange.get("text", "").strip()
        )
        current_exchange = 0

        for exchange in session_data:
            speaker = exchange.get("speaker")
            text = str(exchange.get("text", ""))

            if text.strip():
                conversation_history.append(f"{speaker}: {text}")

            if speaker == person_name and text.strip():
                current_exchange += 1
                if (
                    total_exchanges > 1
                ):  # Only show progress for sessions with multiple exchanges
                    print(
                        f"  Processing exchange {current_exchange}/{total_exchanges}...",
                        end="\r",
                    )

                metadata = {
                    "source": "locomo_conversation",
                    "session": session_key,
                    "session_date": session_date,
                    "dia_id": exchange.get("dia_id", ""),
                    "speaker": speaker,
                }

                # Build conversation context (previous turns)
                conversation_context = []
                if len(conversation_history) > 1:
                    turns_collected = 0
                    context_turns = 5  # Number of turns to include as context

                    for prev_exchange in reversed(conversation_history[:-1]):
                        if prev_exchange.startswith(f"{person_name}:"):
                            attributed_context = f"[SELF] {prev_exchange}"
                            conversation_context.insert(0, attributed_context)
                        else:
                            attributed_context = f"[OTHER] {prev_exchange}"
                            conversation_context.insert(0, attributed_context)
                            turns_collected += 1

                        if turns_collected >= context_turns:
                            break

                session_memories.append((text, metadata, conversation_context))

        # Process all memories for this session
        if session_memories:
            print(
                f"  Processing {len(session_memories)} memories with LLM classification..."
            )

        for memory_idx, (text, metadata, conversation_context) in enumerate(
            session_memories, 1
        ):
            try:
                if len(session_memories) > 1:
                    print(
                        f"  Classifying memory {memory_idx}/{len(session_memories)}...",
                        end="\r",
                    )

                # Store memory with proper namespace
                # Include conversation context in metadata for better classification
                enhanced_metadata = {
                    **metadata,
                    "conversation_context": conversation_context,
                }
                await memory_manager.store_memory(
                    text, namespace=namespace, metadata=enhanced_metadata
                )
                memories_processed += 1
            except Exception as e:
                print(f"\n  Failed to process: {text[:50]}... Error: {e}")

        # Clear the progress line
        if session_memories and len(session_memories) > 1:
            print(" " * 50, end="\r")

        # Commit after each session
        if session_memories:
            commit_msg = (
                f"Added memories from {session_key} for {person_name} ({session_date})"
            )
            commit_hash = store.commit(commit_msg)
            print(
                f"  ✓ Committed {len(session_memories)} memories for {session_key}: {commit_hash[:8] if commit_hash else 'No commit'}"
            )

    print(f"Total memories processed: {memories_processed}")


async def create_sample_memories(
    memory_manager: ProllyTreeMemoryStoreManager, _store: ProllyTreeStore
):
    """Create sample memories (original behavior)."""
    # Use default namespace - let the system handle namespace assignment naturally
    namespace = "default"

    # User profile memories
    await memory_manager.store_memory(
        "My name is John Smith",
        namespace=namespace,
        metadata={"type": "profile", "category": "personal"},
    )

    await memory_manager.store_memory(
        "I am a senior software engineer at TechCorp",
        namespace=namespace,
        metadata={"type": "profile", "category": "professional"},
    )

    await memory_manager.store_memory(
        "I specialize in Python, TypeScript, and distributed systems",
        namespace=namespace,
        metadata={"type": "profile", "category": "skills"},
    )

    # Preferences
    await memory_manager.store_memory(
        "I prefer dark mode in all applications",
        namespace=namespace,
        metadata={"type": "preference", "category": "ui"},
    )

    await memory_manager.store_memory(
        "I like to receive technical explanations with code examples",
        namespace=namespace,
        metadata={"type": "preference", "category": "communication"},
    )

    # Project memories
    await memory_manager.store_memory(
        "I am working on a chatbot project using LangChain",
        namespace=namespace,
        metadata={"type": "project", "category": "current"},
    )

    await memory_manager.store_memory(
        "The chatbot needs to integrate with Slack and Discord",
        namespace=namespace,
        metadata={"type": "project", "category": "requirements"},
    )

    # Technical context
    await memory_manager.store_memory(
        "I use pytest for testing and prefers TDD approach",
        namespace=namespace,
        metadata={"type": "technical", "category": "methodology"},
    )

    await memory_manager.store_memory(
        "My team follows GitFlow branching strategy",
        namespace=namespace,
        metadata={"type": "technical", "category": "workflow"},
    )

    # Personal interests
    await memory_manager.store_memory(
        "I enjoy hiking and photography on weekends",
        namespace=namespace,
        metadata={"type": "personal", "category": "hobbies"},
    )


async def create_sample_branches_and_commits(
    memory_manager: ProllyTreeMemoryStoreManager, store: ProllyTreeStore
):
    """Create sample branches and commits (original behavior)."""
    namespace = "default"

    # Commit the initial state
    commit1 = store.commit("Initial user profile and preferences")
    print(
        f"Commit 1: {commit1[:8] if commit1 else 'No commit'} - Initial user profile and preferences"
    )

    # Add more memories
    await memory_manager.store_memory(
        "I am learning Rust in her spare time",
        namespace=namespace,
        metadata={"type": "learning", "category": "programming"},
    )

    await memory_manager.store_memory(
        "I want to build a personal knowledge management system",
        namespace=namespace,
        metadata={"type": "project", "category": "personal"},
    )

    commit2 = store.commit("Added learning goals and personal projects")
    print(
        f"Commit 2: {commit2[:8] if commit2 else 'No commit'} - Added learning goals and personal projects"
    )

    # Create feature branch for experimentation
    print("\n=== Creating feature/chatbot-context branch ===")
    store.tree.create_branch("feature/chatbot-context")
    store.tree.checkout("feature/chatbot-context")

    # Add chatbot-specific memories
    await memory_manager.store_memory(
        "Chatbot should maintain conversation context for 24 hours",
        namespace=namespace,
        metadata={"type": "requirement", "category": "chatbot"},
    )

    await memory_manager.store_memory(
        "Users prefer concise responses with optional detailed explanations",
        namespace=namespace,
        metadata={"type": "preference", "category": "chatbot"},
    )

    await memory_manager.store_memory(
        "Chatbot needs to handle code snippets and markdown formatting",
        namespace=namespace,
        metadata={"type": "requirement", "category": "chatbot"},
    )

    commit3 = store.commit("Added chatbot-specific context and requirements")
    print(
        f"Commit 3: {commit3[:8] if commit3 else 'No commit'} - Added chatbot-specific context (feature branch)"
    )

    # Create another branch for UI preferences
    store.tree.checkout("main")
    store.tree.create_branch("feature/ui-preferences")
    store.tree.checkout("feature/ui-preferences")

    print("\n=== Creating feature/ui-preferences branch ===")

    await memory_manager.store_memory(
        "I prefer Monaco editor for code editing",
        namespace=namespace,
        metadata={"type": "preference", "category": "editor"},
    )

    await memory_manager.store_memory(
        "I want keyboard shortcuts similar to VSCode",
        namespace=namespace,
        metadata={"type": "preference", "category": "shortcuts"},
    )

    commit4 = store.commit("Added UI and editor preferences")
    print(
        f"Commit 4: {commit4[:8] if commit4 else 'No commit'} - Added UI preferences (feature branch)"
    )

    # Switch back to main
    store.tree.checkout("main")

    # Add one more commit to main
    await memory_manager.store_memory(
        "My team is migrating from JavaScript to TypeScript",
        namespace=namespace,
        metadata={"type": "project", "category": "migration"},
    )

    commit5 = store.commit("Added team migration information")
    print(
        f"Commit 5: {commit5[:8] if commit5 else 'No commit'} - Added team migration info (main branch)"
    )

    # Create experimental branch
    store.tree.create_branch("experimental/memory-optimization")
    store.tree.checkout("experimental/memory-optimization")

    print("\n=== Creating experimental/memory-optimization branch ===")

    await memory_manager.store_memory(
        "Testing memory compression techniques for large conversations",
        namespace=namespace,
        metadata={"type": "experimental", "category": "optimization"},
    )

    commit6 = store.commit("Experimental memory optimization research")
    print(
        f"Commit 6: {commit6[:8] if commit6 else 'No commit'} - Memory optimization experiments"
    )

    # Back to main
    store.tree.checkout("main")


async def print_summary(
    store: ProllyTreeStore, store_path: str, data_file: Optional[str]
):
    """Print summary information about the initialized store."""
    print("\n" + "=" * 60)
    print(f"✅ Memory store initialized at: {store_path}")
    print("\nBranches created:")
    branches = store.tree.list_branches()
    current_branch = store.tree.current_branch()
    for branch in branches:
        current = " (current)" if branch == current_branch else ""
        print(f"  - {branch}{current}")

    if data_file:
        print(f"\nLOCOMO conversation data processed from: {data_file}")
    else:
        print("\nSample memories stored across multiple commits and branches.")

    print("\nYou can now connect the UI to this store using:")
    print(f"  /connect {store_path}")

    # Also save a metadata file for the UI to read
    metadata = {
        "store_path": store_path,
        "branches": branches,
        "current_branch": store.tree.current_branch(),
        "total_memories": len(
            list(store.tree.list_keys()) if hasattr(store.tree, "list_keys") else []
        ),
        "data_source": "locomo" if data_file else "sample",
    }

    # Only add commit info for sample data (when not using LOCOMO data)
    if not data_file:
        metadata["commits"] = {
            "main": [],  # Will be filled by sample data processing
            "feature/chatbot-context": [],
            "feature/ui-preferences": [],
            "experimental/memory-optimization": [],
        }

    metadata_path = Path(store_path) / "ui_metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nMetadata saved to: {metadata_path}")


if __name__ == "__main__":
    asyncio.run(main())

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
from typing import Any, Optional

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
        help="Path to data file containing conversations (JSON for LOCOMO or TXT for simple format)",
    )
    parser.add_argument(
        "--person",
        type=str,
        help="Person name to create memories for (required when using --data-file with JSON format)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "txt"],
        help="Input data format: 'json' for LOCOMO format, 'txt' for simple text format. Auto-detected if not specified.",
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
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing memory store instead of creating a new one",
    )
    args = parser.parse_args()

    # Auto-detect format if not specified
    if args.data_file and not args.format:
        if args.data_file.lower().endswith(".json"):
            args.format = "json"
        elif args.data_file.lower().endswith(".txt"):
            args.format = "txt"
        else:
            print(
                "Error: Could not auto-detect format. Please specify --format (json or txt)"
            )
            sys.exit(1)

    # Validate arguments
    if args.append:
        # In append mode, data file is required and store must exist
        if not args.data_file:
            print("Error: --data-file is required when using --append")
            sys.exit(1)
        if not os.path.exists(args.store_path):
            print(f"Error: Store path does not exist for appending: {args.store_path}")
            sys.exit(1)

    if args.data_file and not os.path.exists(args.data_file):
        print(f"Error: Data file not found: {args.data_file}")
        sys.exit(1)

        # Person name is now optional for JSON format - if not provided, will process all speakers
        # No validation needed here anymore

    # Use the store path from arguments
    store_path = args.store_path

    # Handle store creation vs append mode
    if args.append:
        print(f"Appending to existing memory store at: {store_path}")
    else:
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

    # Choose data source: data file or sample data
    if args.data_file:
        if args.format == "json":
            print(f"\n=== Processing LOCOMO data from {args.data_file} ===")
            await process_locomo_data(
                memory_manager,
                store,
                args.data_file,
                args.person,
                args.session,
                args.conversation,
            )
        elif args.format == "txt":
            print(f"\n=== Processing text data from {args.data_file} ===")
            await process_txt_data(memory_manager, store, args.data_file, args.session)
    else:
        # Only create sample data if not in append mode
        if not args.append:
            print("\n=== Adding sample memories to main branch ===")
            await create_sample_memories(memory_manager, store)

    # Skip sample data commits if processing data file or in append mode
    if not args.data_file and not args.append:
        await create_sample_branches_and_commits(memory_manager, store)

    # Print summary
    await print_summary(store, store_path, args.data_file)


async def process_txt_data(
    memory_manager: ProllyTreeMemoryStoreManager,
    store: ProllyTreeStore,
    data_file: str,
    session: Optional[str],
):
    """Process text data format and ingest into memory store."""
    import re
    from datetime import datetime

    print(f"Loading text data from {data_file}")

    # Read the text file
    with open(data_file, encoding="utf-8") as f:
        content = f.read()

    # Parse session parameter
    session_list = _parse_session_parameter(session)

    # Split content by session separator (lines of dashes)
    session_separator = re.compile(r"^-{5,}$", re.MULTILINE)
    sessions = session_separator.split(content)

    # Remove empty sessions
    sessions = [s.strip() for s in sessions if s.strip()]

    print(f"Found {len(sessions)} sessions in the text file")

    # Filter sessions if specific sessions requested
    if session_list:
        if max(session_list) > len(sessions):
            print(
                f"Error: Session {max(session_list)} not found. File has {len(sessions)} sessions"
            )
            return
        sessions = [sessions[i - 1] for i in session_list]  # Convert to 0-indexed
        print(f"Processing sessions: {', '.join(map(str, session_list))}")
    else:
        print("Processing all sessions")

    namespace = "default"  # Use default namespace for UI compatibility
    memories_processed = 0
    total_sessions = len(sessions)

    for session_idx, session_content in enumerate(sessions, 1):
        if session_list:
            actual_session_num = session_list[session_idx - 1]
        else:
            actual_session_num = session_idx

        print(
            f"[{session_idx}/{total_sessions}] Processing session {actual_session_num}..."
        )

        # Parse session metadata
        lines = session_content.strip().split("\n")
        date_str = None
        location = None
        content_lines = []

        for line in lines:
            line = line.strip()
            if line.startswith("#DATE:"):
                date_str = line[6:].strip()
            elif line.startswith("#LOC:"):
                location = line[5:].strip()
            elif line:  # Non-empty content line
                content_lines.append(line)

        # Parse date if provided
        session_date = "unknown date"
        timestamp = None
        if date_str:
            try:
                # Try to parse common date formats
                for fmt in [
                    "%a %b %d %H:%M:%S %Z %Y",
                    "%Y-%m-%d %H:%M:%S",
                    "%m/%d/%Y %H:%M:%S",
                ]:
                    try:
                        dt = datetime.strptime(date_str, fmt)
                        timestamp = dt.timestamp()
                        session_date = date_str
                        break
                    except ValueError:
                        continue

                # If parsing failed, use the raw string
                if timestamp is None:
                    session_date = date_str
            except Exception:
                session_date = date_str

        if not content_lines:
            print(f"  Warning: No content found in session {actual_session_num}")
            continue

        # Process each content line as a separate memory
        session_memories = []
        location_events = []
        print(f"  Processing {len(content_lines)} memory entries...")

        for line_idx, content_line in enumerate(content_lines, 1):
            if len(content_lines) > 1:
                print(
                    f"  Processing entry {line_idx}/{len(content_lines)}...", end="\r"
                )

            metadata = {
                "source": "txt_conversation",
                "session": f"session_{actual_session_num}",
                "session_date": session_date,
                "line_number": line_idx,
            }

            if location:
                metadata["location"] = location
                # Collect location events for LocationMemento processing
                location_events.append(
                    {"location": location, "description": content_line}
                )
            if timestamp:
                metadata["timestamp"] = timestamp

            try:
                await memory_manager.store_memory(
                    content_line, namespace=namespace, metadata=metadata
                )
                session_memories.append(content_line)
                memories_processed += 1
            except Exception as e:
                print(f"\n  Failed to process: {content_line[:50]}... Error: {e}")

        # Process location events if any
        if location_events:
            try:
                await memory_manager.location_manager.apply_location_events(
                    location_events,
                    metadata={
                        "session": f"session_{actual_session_num}",
                        "session_date": session_date,
                    },
                    namespace=namespace,
                )
            except Exception as e:
                print(f"\n  Failed to process location events: {e}")

        # Clear the progress line
        if len(content_lines) > 1:
            print(" " * 50, end="\r")

        # Commit after each session
        if session_memories:
            commit_msg = f"Added {len(session_memories)} memories from session {actual_session_num}"
            if date_str:
                commit_msg += f" ({session_date})"
            if location:
                commit_msg += f" at {location}"

            commit_hash = store.commit(commit_msg)
            print(
                f"  ✓ Committed {len(session_memories)} memories for session {actual_session_num}: {commit_hash[:8] if commit_hash else 'No commit'}"
            )

    print(f"Total memories processed: {memories_processed}")


class SpeakerPrefixMemoryManager:
    """
    Wrapper around ProllyTreeMemoryStoreManager that adds speaker prefixes to memory paths.
    """

    def __init__(self, memory_manager: ProllyTreeMemoryStoreManager, speaker: str):
        self.memory_manager = memory_manager
        self.speaker = speaker.lower().replace(" ", "_")

    async def store_memory(
        self,
        content: Any,
        namespace: str = "default",
        metadata: Optional[dict] = None,
        auto_classify: bool = True,
    ) -> str:
        """
        Store a memory with speaker prefix added to the semantic key.
        """
        # First, let the intelligent classifier check if it's memory-worthy
        # and get the classification path
        if auto_classify and self.memory_manager.classifier:
            classification = await self.memory_manager.classifier.classify_async(
                str(content), metadata=metadata
            )

            # Check if memory is worth storing (intelligent classifier handles this)
            if hasattr(classification, "is_memory") and not classification.is_memory:
                print(
                    f"  ⚠ Skipping non-memory-worthy content for {self.speaker}: {str(content)[:50]}..."
                )
                return None

            # Get the semantic key from classification
            if hasattr(classification, "primary_path"):
                semantic_key = classification.primary_path
            elif hasattr(classification, "path"):
                semantic_key = classification.path
            else:
                semantic_key = "context.current.session.topic.main"

            # Add speaker prefix to the semantic key
            if semantic_key and not semantic_key.startswith(self.speaker):
                semantic_key = f"{self.speaker}.{semantic_key}"
                print(f"      → Prefixed key: {semantic_key}")

            # Process timeline events if present in classification
            if (
                hasattr(classification, "timeline_events")
                and classification.timeline_events
            ):
                try:
                    await self.memory_manager.timeline_manager.apply_timeline_events(
                        classification.timeline_events, metadata, namespace=namespace
                    )
                    print(
                        f"      → Applied {len(classification.timeline_events)} timeline events"
                    )
                except Exception as e:
                    print(f"      ⚠ Failed to process timeline events: {e}")

            # Process location events if present in classification
            if (
                hasattr(classification, "location_events")
                and classification.location_events
            ):
                try:
                    await self.memory_manager.location_manager.apply_location_events(
                        classification.location_events, metadata, namespace=namespace
                    )
                    print(
                        f"      → Applied {len(classification.location_events)} location events"
                    )
                except Exception as e:
                    print(f"      ⚠ Failed to process location events: {e}")
        else:
            # Use provided key or generate one with speaker prefix
            semantic_key = metadata.get("key") if metadata else None
            if not semantic_key:
                semantic_key = f"{self.speaker}.context.current.session.topic.main"
            elif not semantic_key.startswith(self.speaker):
                semantic_key = f"{self.speaker}.{semantic_key}"

        # Format content with metadata for better context
        formatted_content = self._format_content_with_metadata(content, metadata)

        # Check if there's existing content at this path and merge if needed
        try:
            # Search using namespace tuple format
            ns_tuple = (namespace,) if isinstance(namespace, str) else namespace
            search_results = list(
                await self.memory_manager.prolly_store.search(ns_tuple, semantic_key)
            )

            if search_results:
                # Extract existing content from the first result
                _, _, existing_value = search_results[0]  # (namespace, key, value)

                # Handle the nested structure from memory manager
                if isinstance(existing_value, dict):
                    # Check if it's the memory manager's wrapped format
                    if "memories" in existing_value and isinstance(
                        existing_value["memories"], list
                    ):
                        # Extract from the first memory in the list
                        if existing_value["memories"]:
                            first_memory = existing_value["memories"][0]
                            if (
                                isinstance(first_memory, dict)
                                and "content" in first_memory
                            ):
                                content_obj = first_memory["content"]
                                if (
                                    isinstance(content_obj, dict)
                                    and "raw_text" in content_obj
                                ):
                                    existing_content = content_obj["raw_text"]
                                else:
                                    existing_content = str(content_obj)
                            else:
                                existing_content = str(first_memory)
                        else:
                            existing_content = ""
                    elif "raw_text" in existing_value:
                        existing_content = existing_value["raw_text"]
                    else:
                        existing_content = str(existing_value)
                elif isinstance(existing_value, str):
                    existing_content = existing_value
                else:
                    existing_content = str(existing_value)

                # Merge with new content
                merged_content = f"{existing_content}\n\n{formatted_content}"

                # Store merged content with structure
                final_content = {
                    "raw_text": merged_content,
                    "speaker": self.speaker,
                    "last_updated": metadata.get("session_date", "unknown"),
                    "memory_type": "conversation_memory",
                }
            else:
                # First content for this path
                final_content = {
                    "raw_text": formatted_content,
                    "speaker": self.speaker,
                    "last_updated": metadata.get("session_date", "unknown"),
                    "memory_type": "conversation_memory",
                }
        except Exception as e:
            # If search fails, just store the new content
            print(f"      Note: Could not check for existing content: {e}")
            final_content = {
                "raw_text": formatted_content,
                "speaker": self.speaker,
                "last_updated": metadata.get("session_date", "unknown"),
                "memory_type": "conversation_memory",
            }

        # Store using the base memory manager with the prefixed key
        await self.memory_manager.prolly_store.store_memory_async(
            namespace, final_content, semantic_key
        )

        return semantic_key

    def _format_content_with_metadata(
        self, content: str, metadata: Optional[dict]
    ) -> str:
        """Format content with date information."""
        if not metadata:
            return content

        # Extract date metadata
        date = metadata.get("session_date", "unknown_date")

        # Format with just the date/time
        formatted = f"[{date}]\n{content}"

        return formatted


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

    # Extract all speakers from the conversation data if no specific person provided
    if not person_name:
        all_speakers = set()
        for session_key in session_keys:
            session_data = conversation_data.get(session_key, [])
            for exchange in session_data:
                speaker = exchange.get("speaker")
                if speaker and speaker.strip():
                    all_speakers.add(speaker.strip())
        speakers_to_process = sorted(all_speakers)
        print(f"Found speakers: {', '.join(speakers_to_process)}")
        print(
            f"Processing {total_sessions} session(s) for all speakers: {', '.join(speakers_to_process)}..."
        )
    else:
        speakers_to_process = [person_name]
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
        if person_name:
            total_exchanges = sum(
                1
                for exchange in session_data
                if exchange.get("speaker") == person_name
                and exchange.get("text", "").strip()
            )
        else:
            total_exchanges = sum(
                1
                for exchange in session_data
                if exchange.get("speaker") in speakers_to_process
                and exchange.get("text", "").strip()
            )
        current_exchange = 0

        for exchange in session_data:
            speaker = exchange.get("speaker")
            text = str(exchange.get("text", ""))

            if text.strip():
                conversation_history.append(f"{speaker}: {text}")

            # Process exchange if speaker matches our criteria
            should_process = (
                speaker in speakers_to_process
                if not person_name
                else speaker == person_name
            ) and text.strip()

            if should_process:
                current_exchange += 1
                if (
                    total_exchanges > 1
                ):  # Only show progress for sessions with multiple exchanges
                    print(
                        f"  Processing exchange {current_exchange}/{total_exchanges} ({speaker})...",
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

                # Create speaker-specific memory manager
                speaker_memory_manager = SpeakerPrefixMemoryManager(
                    memory_manager, metadata.get("speaker", "unknown")
                )

                # Store memory with proper namespace and speaker prefix
                # Include conversation context in metadata for better classification
                enhanced_metadata = {
                    **metadata,
                    "conversation_context": conversation_context,
                }

                stored_key = await speaker_memory_manager.store_memory(
                    text, namespace=namespace, metadata=enhanced_metadata
                )

                if (
                    stored_key
                ):  # Only count if actually stored (passed memory worth check)
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
        print(f"\nData processed from: {data_file}")
    else:
        print("\nSample memories stored across multiple commits and branches.")

    print("\nYou can now connect the UI to this store using:")
    print(f"  /connect {store_path}")


if __name__ == "__main__":
    asyncio.run(main())

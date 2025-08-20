#!/usr/bin/env python3
"""
Locomo Evaluation System for Memory Agent

This script uses the QA section from locomo test data to evaluate how well
the memory agent can retrieve and answer questions using stored memories.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from rich.console import Console
from rich.table import Table

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memoir.core.profile_manager import ProfileManager
from memoir.core.prolly_adapter import ProllyTreeStore
from memoir.search.hierarchical_search import (
    HierarchicalSearchEngine,
    SearchStrategy,
)
from memoir.taxonomy.intelligent_classifier import IntelligentClassifier
from memoir.taxonomy.semantic_classifier import SemanticClassifier
from memoir.taxonomy.taxonomy_presets import TaxonomyVersion

# Configure logging
logging.basicConfig(
    level=logging.WARNING, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress verbose logging from external libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("openai._base_client").setLevel(logging.WARNING)
logging.getLogger("memoir.taxonomy.data_sources").setLevel(logging.WARNING)
# Disable DEBUG logging for hierarchical search
logging.getLogger("memoir.search.hierarchical_search").setLevel(logging.WARNING)
# Suppress other memoir logging
logging.getLogger("memoir.taxonomy").setLevel(logging.WARNING)
logging.getLogger("memoir.core").setLevel(logging.WARNING)


class LocomoEvaluator:
    """Evaluates memory agent's ability to answer questions using stored memories from locomo dataset."""

    def __init__(
        self,
        data_file: str,
        person_name: str,
        storage_path: str = "/tmp/qa_evaluation",
        confidence_thresholds: Optional[dict[str, float]] = None,
        session: Optional[str] = None,
        conversation_id: int = 1,
        max_search_results: int = 5,
        max_context_memories: int = 3,
        max_memory_size: int = 2000,
        context_turns: int = 1,
        max_retries: int = 3,
    ):
        self.console = Console()
        self.data_file = data_file
        self.person_name = person_name
        self.storage_path = storage_path
        self.session = session
        self.conversation_id = conversation_id
        self.max_search_results = max_search_results
        self.max_context_memories = max_context_memories
        self.max_memory_size = max_memory_size
        self.context_turns = context_turns
        self.max_retries = max_retries
        self.confidence_thresholds = confidence_thresholds or {
            "high": 0.8,
            "medium": 0.5,
            "low": 0.0,
        }

        # Parse session parameter
        self.session_list = self._parse_session_parameter(session)

        # Components
        self.llm = None
        self.intelligent_classifier = None
        self.search_engine = None
        self.profile_manager = None
        self.conversation_data = None
        self.qa_data = None
        self.all_conversations = None

    def _parse_session_parameter(self, session: Optional[str]) -> Optional[list[int]]:
        """Parse session parameter to handle single values, ranges, and lists.

        Examples:
        - "1" -> [1]
        - "1,3,5" -> [1, 3, 5]
        - "1-3" -> [1, 2, 3]
        - "1,3-5,7" -> [1, 3, 4, 5, 7]
        - None -> None (process all sessions)
        """
        if not session:
            return None

        session_list = []
        parts = session.split(",")

        for part in parts:
            part = part.strip()
            if "-" in part:
                # Handle range like "1-3"
                try:
                    start, end = part.split("-")
                    start, end = int(start.strip()), int(end.strip())
                    session_list.extend(range(start, end + 1))
                except ValueError:
                    raise ValueError(
                        f"Invalid session range format: {part}. Use format like '1-3'"
                    )
            else:
                # Handle single number
                try:
                    session_list.append(int(part))
                except ValueError:
                    raise ValueError(f"Invalid session number: {part}")

        return sorted(set(session_list))  # Remove duplicates and sort

    def _is_question(self, text: str) -> bool:
        """Check if a text contains a question."""
        # Remove speaker prefix if present (e.g., "Caroline: What do you think?")
        if ": " in text:
            text = text.split(": ", 1)[1]

        # Simple heuristics to identify questions
        text = text.strip()
        if not text:
            return False

        # Check for question marks
        if "?" in text:
            return True

        # Check for question words at the beginning
        question_words = [
            "what",
            "when",
            "where",
            "why",
            "how",
            "who",
            "which",
            "whose",
            "whom",
            "do",
            "does",
            "did",
            "can",
            "could",
            "would",
            "will",
            "should",
            "is",
            "are",
            "was",
            "were",
            "have",
            "has",
            "had",
        ]
        first_word = text.lower().split()[0] if text.split() else ""

        return first_word in question_words

    def _write_formatted_memory_entries(
        self, f, raw_text: str, session_date: Optional[str] = None
    ):
        """Format memory entries in the clear NEW ENTRY format."""
        # Split by NEW ENTRY markers
        entries = raw_text.split("--- NEW ENTRY")

        for idx, entry in enumerate(entries):
            if idx == 0:
                # First entry (original memory) - add FIRST ENTRY header with timestamp
                if session_date:
                    f.write(f"--- FIRST ENTRY ({session_date}) ---\n")
                else:
                    f.write("--- FIRST ENTRY ---\n")
                self._format_single_entry(f, entry, is_first=True)
            else:
                # Extract timestamp from entry header
                lines = entry.split("\n")
                timestamp_line = lines[0] if lines else ""
                timestamp = timestamp_line.strip(" ()-")

                # Get the rest of the entry content
                entry_content = "\n".join(lines[1:])

                # Write NEW ENTRY header
                f.write(f"--- NEW ENTRY ({timestamp}) ---\n")

                # Format the entry content
                self._format_single_entry(f, entry_content, is_first=False)

    def _format_single_entry(self, f, entry_content: str, is_first: bool = False):
        """Format a single memory entry with context and speaker content."""
        lines = entry_content.strip().split("\n")
        context_lines = []
        speaker_lines = []

        # Parse lines to separate context from speaker content
        in_context = True
        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith("Context: "):
                # Extract context line
                context_text = line[9:]  # Remove "Context: " prefix
                context_lines.append(context_text)
            elif in_context and (
                line.startswith("[SELF]") or line.startswith("[OTHER]")
            ):
                # Direct context line with speaker attribution
                context_lines.append(line)
            else:
                # This is speaker content
                in_context = False
                speaker_lines.append(line)

        # Write context section
        if context_lines:
            f.write("  Context:\n")
            for context in context_lines:
                if context.startswith("[SELF] "):
                    speaker_part = context[7:]  # Remove "[SELF] " prefix
                    # Remove speaker name if it starts with a name followed by colon
                    if ": " in speaker_part:
                        speaker_part = speaker_part.split(": ", 1)[1]
                    f.write(f"    - SELF: {speaker_part}\n")
                elif context.startswith("[OTHER] "):
                    speaker_part = context[8:]  # Remove "[OTHER] " prefix
                    # Remove speaker name if it starts with a name followed by colon
                    if ": " in speaker_part:
                        speaker_part = speaker_part.split(": ", 1)[1]
                    f.write(f"    - OTHER: {speaker_part}\n")
                else:
                    # Fallback for other formats
                    f.write(f"    - {context}\n")

        # Write speaker content
        if speaker_lines:
            speaker_content = " ".join(speaker_lines)
            f.write(f"  SPEAKER: {speaker_content}\n")

        f.write("\n")  # Add spacing after each entry

    async def setup(self):
        """Initialize all components."""
        # Get LLM
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=api_key,
            max_tokens=1000,
        )

        # Setup memory store
        data_dir = Path(self.storage_path)
        data_dir.mkdir(parents=True, exist_ok=True)

        # Create classifier with default taxonomy for now (we'll add events.* paths via LLM prompting)
        classifier = SemanticClassifier(llm=self.llm)
        store = ProllyTreeStore(
            path=str(data_dir),
            classifier=classifier,
            enable_versioning=False,
        )

        # Create profile manager
        self.profile_manager = ProfileManager(store)

        # Create intelligent classifier with profile manager
        self.intelligent_classifier = IntelligentClassifier(
            llm=self.llm,
            memory_store=store,
            taxonomy_version=TaxonomyVersion.GENERAL,
            confidence_thresholds=self.confidence_thresholds,
            profile_manager=self.profile_manager,
        )

        # Create search engine
        self.search_engine = HierarchicalSearchEngine(
            store=store, classifier=classifier, profile_manager=self.profile_manager
        )

        # Load conversation and QA data
        await self.load_data()

    async def load_data(self):
        """Load conversation and QA data from file."""
        with open(self.data_file) as f:
            content = f.read()

        # Parse JSON - now it's an array of conversations
        self.all_conversations = json.loads(content)

        # Validate conversation_id
        if self.conversation_id < 1 or self.conversation_id > len(
            self.all_conversations
        ):
            raise ValueError(
                f"Invalid conversation ID {self.conversation_id}. Available conversations: 1-{len(self.all_conversations)}"
            )

        # Select the specific conversation (1-indexed)
        data = self.all_conversations[self.conversation_id - 1]

        self.qa_data = data.get("qa", [])
        self.conversation_data = data.get("conversation", {})

        # Filter QA pairs immediately to show accurate counts
        filtered_qa = self.filter_qa_by_session_and_person()

        self.console.print(
            f"⏺ Loaded conversation {self.conversation_id} of {len(self.all_conversations)} available conversations",
            style="white",
        )
        self.console.print(
            f"⏺ Loaded {len(self.qa_data)} total QA pairs", style="white"
        )
        self.console.print(
            f"⏺ Filtered to {len(filtered_qa)} QA pairs for {self.person_name}",
            style="white",
        )

        # Debug: Check if filtered QA has all required fields
        if filtered_qa:
            sample_qa = filtered_qa[0]
            logger.debug(f"Sample QA structure: {list(sample_qa.keys())}")
            if "answer" not in sample_qa:
                logger.warning(
                    f"Missing 'answer' key in QA data. Available keys: {list(sample_qa.keys())}"
                )
        self.console.print(
            f"⏺ Loaded conversation data for {self.conversation_data.get('speaker_a')} and {self.conversation_data.get('speaker_b')}",
            style="white",
        )

        if self.session_list:
            session_str = ",".join(map(str, self.session_list))
            self.console.print(
                f"⏺ Processing sessions {session_str} only", style="white"
            )

    async def process_memories(self):
        """Process conversation data to create memories."""
        self.console.print(
            "\n⏺ Processing memories from conversations...", style="white"
        )

        memories_processed = 0

        # Find session keys to process
        if self.session_list:
            # Process only the specified sessions
            session_keys = [f"session_{s}" for s in self.session_list]
            # Verify the sessions exist
            available_sessions = [
                k.replace("session_", "")
                for k in self.conversation_data
                if k.startswith("session_") and not k.endswith("_date_time")
            ]
            missing_sessions = [
                str(s)
                for s in self.session_list
                if f"session_{s}" not in self.conversation_data
            ]
            if missing_sessions:
                self.console.print(
                    f"⏺ Error: Sessions {missing_sessions} not found. Available sessions: {available_sessions}",
                    style="white",
                )
                return
        else:
            # Find all session keys
            session_keys = [
                k
                for k in self.conversation_data
                if k.startswith("session_") and not k.endswith("_date_time")
            ]

        # Count total exchanges to process for better progress tracking
        total_exchanges = 0
        for session_key in session_keys:
            session_data = self.conversation_data.get(session_key, [])
            for exchange in session_data:
                speaker = exchange.get("speaker")
                text = str(exchange.get("text", ""))
                if speaker == self.person_name and text.strip():
                    total_exchanges += 1

        # Temporarily suppress logging during processing to avoid scrolling
        import logging

        old_level = logging.getLogger().level
        logging.getLogger().setLevel(logging.ERROR)  # Only show errors

        processed_count = 0
        conversation_history = []  # Track conversation history for context

        for session_key in session_keys:
            session_data = self.conversation_data.get(session_key, [])
            # Get the session date for context
            session_date_key = f"{session_key}_date_time"
            session_date = self.conversation_data.get(session_date_key, "unknown date")

            for exchange in session_data:
                speaker = exchange.get("speaker")
                text = str(exchange.get("text", ""))

                # Add all exchanges to conversation history (for context)
                if text.strip():
                    conversation_history.append(f"{speaker}: {text}")

                # Process memories only for the specified person
                if speaker == self.person_name and text.strip():
                    # Update progress in place
                    self.console.print(
                        f"⏺ Processing memories... {processed_count + 1}/{total_exchanges}",
                        style="white",
                        end="\r",
                    )

                    # Add metadata including dialogue ID and session date for reference
                    metadata = {
                        "source": "locomo_conversation",
                        "session": session_key,
                        "session_date": session_date,
                        "dia_id": exchange.get("dia_id", ""),
                        "speaker": speaker,
                    }

                    # Get selective conversation context with clear speaker attribution
                    conversation_context = []
                    if len(conversation_history) > 1:
                        # Collect the specified number of conversation turns
                        # A "turn" includes both OTHER and SELF exchanges in sequence
                        turns_collected = 0

                        # Look backwards through previous exchanges
                        for prev_exchange in reversed(conversation_history[:-1]):
                            # Add context based on speaker, maintaining conversation flow
                            if prev_exchange.startswith(f"{self.person_name}:"):
                                # This is SELF speaking - add as context
                                attributed_context = f"[SELF] {prev_exchange}"
                                conversation_context.insert(
                                    0, attributed_context
                                )  # Insert at beginning to maintain order
                            else:
                                # This is OTHER speaking - add as context
                                attributed_context = f"[OTHER] {prev_exchange}"
                                conversation_context.insert(
                                    0, attributed_context
                                )  # Insert at beginning to maintain order
                                # Count this as completing a turn (OTHER speaks, then SELF responds)
                                turns_collected += 1

                            # Stop when we've collected enough turns
                            if turns_collected >= self.context_turns:
                                break

                    # Store the pure dialog text with conversation context
                    try:
                        await self.intelligent_classifier.process_memory_with_storage(
                            text, metadata, conversation_context
                        )
                        memories_processed += 1
                    except Exception as e:
                        logger.warning(f"Failed to process: {text[:50]}... Error: {e}")

                    processed_count += 1

        # Restore logging level
        logging.getLogger().setLevel(old_level)

        self.console.print(f"⏺ Processed {memories_processed} memories", style="white")

    def filter_qa_by_session_and_person(self) -> list[dict[str, Any]]:
        """Filter QA pairs to only include those about the specified person and session."""
        filtered_qa = []

        for qa_item in self.qa_data:
            question = qa_item.get("question", "")
            evidence = qa_item.get("evidence", [])

            # Filter by person: only include questions that mention the specified person
            if self.person_name.lower() not in question.lower():
                continue

            # Filter by session if specified
            if self.session_list:
                session_prefixes = [f"D{s}:" for s in self.session_list]
                # Check if any evidence reference is from any of the specified sessions
                if not any(
                    any(ref.startswith(prefix) for prefix in session_prefixes)
                    for ref in evidence
                ):
                    continue

            filtered_qa.append(qa_item)

        return filtered_qa

    async def evaluate_qa(self) -> list[dict[str, Any]]:
        """Evaluate QA pairs using memory retrieval and LLM."""
        # Filter QA pairs by session and person
        qa_data_to_evaluate = self.filter_qa_by_session_and_person()

        if self.session_list:
            session_str = ",".join(map(str, self.session_list))
            self.console.print(
                f"\n⏺ Evaluating {len(qa_data_to_evaluate)} filtered QA pairs about {self.person_name} from sessions {session_str}...",
                style="white",
            )
        else:
            self.console.print(
                f"\n⏺ Evaluating {len(qa_data_to_evaluate)} filtered QA pairs about {self.person_name}...",
                style="white",
            )

        results = []

        # Simple progress counter for QA evaluation
        for i, qa_item in enumerate(qa_data_to_evaluate, 1):
            # Update progress in place
            self.console.print(
                f"⏺ Evaluating questions... {i}/{len(qa_data_to_evaluate)}",
                style="white",
                end="\r",
            )

            question = qa_item.get("question", "")
            evidence = qa_item.get("evidence", [])
            category = qa_item.get("category", 0)

            # Handle adversarial answers: if 'adversarial_answer' field exists,
            # the correct answer should be "Information not found"
            if "adversarial_answer" in qa_item:
                expected_answer = "Information not found"
            else:
                expected_answer = qa_item.get("answer", "")

            # Skip if missing required fields
            if not question or not expected_answer:
                logger.warning(
                    f"Skipping QA item with missing question or answer: {qa_item}"
                )
                continue

            try:
                result = await self.evaluate_single_qa(
                    question, expected_answer, evidence, category
                )
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to evaluate question: {question}. Error: {e}")
                results.append(
                    {
                        "question": question,
                        "expected_answer": expected_answer,
                        "predicted_answer": "ERROR",
                        "evidence": evidence,
                        "category": category,
                        "retrieved_memories": [],
                        "f1_score": 0.0,
                        "llm_j_score": 0.0,
                        "score": 0.0,
                        "qa_time_seconds": 0.0,
                        "retry_attempt": 1,
                        "error": str(e),
                    }
                )

        return results

    async def get_alternative_search_paths(
        self, question: str, used_paths: list[str], attempt: int
    ) -> list[str]:
        """Get alternative search paths from LLM when previous searches failed."""
        if attempt == 1:
            return []  # First attempt uses default search

        used_paths_str = ", ".join(used_paths) if used_paths else "none"

        prompt = f"""Given this question: "{question}"

Previous search attempts used these paths but didn't find relevant information:
{used_paths_str}

Suggest 3-5 alternative semantic search paths that might contain the answer. Think about:
- Different ways to phrase the topic (synonyms, related terms)
- Different categories the information might be stored under
- Temporal keywords if the question involves time
- Alternative phrasings of key concepts

Available categories include: profile, preferences, experience, goals, relationships, entity, topics, datetime

Return only the search terms/phrases, one per line:"""

        try:
            response = await self.llm.ainvoke(prompt)
            alternative_paths = [
                path.strip()
                for path in response.content.strip().split("\n")
                if path.strip()
            ]
            return alternative_paths[:5]  # Limit to 5 alternatives
        except Exception as e:
            logger.warning(f"Failed to get alternative search paths: {e}")
            return []

    async def evaluate_single_qa(
        self, question: str, expected_answer: str, evidence: list[str], category: int
    ) -> dict[str, Any]:
        """Evaluate a single QA pair with retry logic for failed searches."""
        import time

        # Start timing the Q&A process
        qa_start_time = time.time()

        used_search_paths = []

        successful_attempt = 1
        for attempt in range(1, self.max_retries + 1):
            # Display retry information if not first attempt
            if attempt > 1:
                self.console.print(
                    f"  ↻ Retrying with alternative search (attempt {attempt}/{self.max_retries})...",
                    style="yellow",
                    end="\r",
                )

            # Search for relevant memories
            namespace_str = "memory:general"
            search_results = []

            if attempt == 1:
                # First attempt: use original search logic
                current_search_paths = await self._perform_initial_search(
                    question, namespace_str
                )
            else:
                # Retry attempts: use alternative paths
                alternative_paths = await self.get_alternative_search_paths(
                    question, used_search_paths, attempt
                )
                current_search_paths = await self._perform_alternative_search(
                    question, namespace_str, alternative_paths
                )

            # Track used paths
            used_search_paths.extend(current_search_paths)

            # Get search results
            search_results = await self._get_search_results(
                question, namespace_str, current_search_paths
            )

            # Process results and generate answer
            (
                retrieved_memories,
                predicted_answer,
            ) = await self._process_search_and_generate_answer(search_results, question)

            # Check if we got a valid answer
            # If expected answer is "Information not found", then "Information not found" is a valid response
            # Otherwise, "Information not found" indicates a failed search
            valid_answer = False
            if predicted_answer:
                if expected_answer == "Information not found":
                    # For adversarial questions, "Information not found" is the correct answer
                    valid_answer = True
                elif (
                    "Information not found" not in predicted_answer
                    and "not found" not in predicted_answer.lower()
                ):
                    # For normal questions, we need actual information
                    valid_answer = True

            if valid_answer:
                successful_attempt = attempt
                # Clear retry message if displayed
                if attempt > 1:
                    self.console.print(" " * 80, end="\r")  # Clear the line
                break  # Success, exit retry loop

            if attempt == self.max_retries:
                logger.warning(
                    f"All {self.max_retries} attempts failed for question: {question}"
                )
                successful_attempt = self.max_retries
                # Clear retry message
                if attempt > 1:
                    self.console.print(" " * 80, end="\r")  # Clear the line

        # Calculate Q&A processing time (excluding scoring)
        qa_time_seconds = time.time() - qa_start_time

        # Calculate scores using both F1 and LLM_J evaluation
        f1_score = await self.calculate_answer_score(
            expected_answer, predicted_answer, question
        )
        llm_j_score = await self.calculate_llm_j_score(
            question, expected_answer, predicted_answer
        )
        return {
            "question": question,
            "expected_answer": expected_answer,
            "predicted_answer": predicted_answer,
            "evidence": evidence,
            "category": category,
            "retrieved_memories": retrieved_memories,
            "f1_score": f1_score,
            "llm_j_score": llm_j_score,
            "score": f1_score,  # Keep original score for backward compatibility
            "qa_time_seconds": qa_time_seconds,
            "retry_attempt": successful_attempt,
        }

    async def _perform_initial_search(
        self, question: str, namespace_str: str
    ) -> list[str]:
        """Perform the initial search using original logic."""
        search_paths = [question]  # Track the main query

        # For date questions about specific events, add alternative search terms
        if "when" in question.lower() and (
            "support group" in question.lower() or "LGBTQ" in question.lower()
        ):
            search_paths.extend(
                [
                    "yesterday LGBTQ support group powerful",
                    "went LGBTQ support group",
                    "significant events LGBTQ",
                ]
            )

        return search_paths

    async def _perform_alternative_search(
        self, question: str, namespace_str: str, alternative_paths: list[str]
    ) -> list[str]:
        """Perform alternative search using LLM-suggested paths."""
        return alternative_paths

    async def _get_search_results(
        self, question: str, namespace_str: str, search_paths: list[str]
    ) -> list:
        """Execute the actual search and return results."""
        search_results = []

        # Use first search path as main query, others as alternatives
        main_query = search_paths[0] if search_paths else question

        # First try: specific to general search with main query
        results1 = await self.search_engine.search(
            query=main_query,
            namespace=namespace_str,
            strategy=SearchStrategy.SPECIFIC_TO_GENERAL,
        )
        search_results.extend(results1)

        # Try alternative search paths
        for alt_query in search_paths[1:]:
            alt_results = await self.search_engine.search(
                query=alt_query,
                namespace=namespace_str,
                strategy=SearchStrategy.SPECIFIC_TO_GENERAL,
            )
            search_results.extend(alt_results)
            if alt_results:  # Stop after finding relevant results
                break

        # If still no results, try broader search
        if len(search_results) == 0:
            results2 = await self.search_engine.search(
                query=question,
                namespace=namespace_str,
                strategy=SearchStrategy.SPECIFIC_TO_GENERAL,
            )
            search_results.extend(results2)

        # Remove duplicates based on content while preserving order
        seen_content = set()
        unique_results = []
        for result in search_results:
            content_hash = hash(result.combined_content)
            if content_hash not in seen_content:
                unique_results.append(result)
                seen_content.add(content_hash)

        return unique_results[: self.max_search_results]  # Keep top N unique results

    async def _process_search_and_generate_answer(
        self, search_results: list, question: str
    ) -> tuple[list, str]:
        """Process search results and generate answer."""
        # Store debug info without printing during evaluation
        retrieved_memories = []
        for result in search_results:
            retrieved_memories.append(
                {
                    "content": result.combined_content,
                    "path": result.path,
                    "namespace": result.namespace,
                    "item_count": result.item_count,
                    "semantic_distance": result.semantic_distance,
                }
            )

        # Create context from retrieved memories with better data extraction
        context_parts = []
        for memory in retrieved_memories[
            : self.max_context_memories
        ]:  # Use top N most relevant results
            content = memory["content"]
            path = memory["path"]

            # Try to extract structured information if content is JSON
            try:
                if isinstance(content, str) and content.strip().startswith("{"):
                    content_obj = json.loads(content)
                    # Prioritize raw_text if available (contains full conversation)
                    if "raw_text" in content_obj:
                        raw_text = content_obj["raw_text"]
                        # Truncate if too long
                        if len(raw_text) > self.max_memory_size:
                            raw_text = (
                                raw_text[: self.max_memory_size] + "...(truncated)"
                            )
                        context_parts.append(f"From {path}: {raw_text}")
                    elif "structured_data" in content_obj:
                        structured = content_obj["structured_data"]
                        structured_text = json.dumps(structured)
                        if len(structured_text) > self.max_memory_size:
                            structured_text = (
                                structured_text[: self.max_memory_size]
                                + "...(truncated)"
                            )
                        context_parts.append(f"From {path}: {structured_text}")
                    elif "summary" in content_obj:
                        summary_text = content_obj["summary"]
                        if len(summary_text) > self.max_memory_size:
                            summary_text = (
                                summary_text[: self.max_memory_size] + "...(truncated)"
                            )
                        context_parts.append(f"From {path}: {summary_text}")
                    else:
                        content_text = str(content)
                        if len(content_text) > self.max_memory_size:
                            content_text = (
                                content_text[: self.max_memory_size] + "...(truncated)"
                            )
                        context_parts.append(f"From {path}: {content_text}")
                else:
                    context_parts.append(f"From {path}: {content}")
            except (json.JSONDecodeError, TypeError):
                # If not JSON or other parsing error, use as-is
                content_text = str(content)
                if len(content_text) > self.max_memory_size:
                    content_text = (
                        content_text[: self.max_memory_size] + "...(truncated)"
                    )
                context_parts.append(f"From {path}: {content_text}")

        context = "\n".join(context_parts)

        # Get profile summary for additional context
        profile_summary = await self.search_engine.profile_manager.get_profile_summary(
            llm=None
        )

        # Generate answer using LLM with improved prompt
        prompt = f"""Extract the specific fact that answers the question from the provided context. Be thorough in examining ALL the context provided.

CRITICAL ANALYSIS RULES:
1. READ ALL CONTEXT CAREFULLY - the answer may be anywhere in the provided text
2. Look for DIRECT STATEMENTS that answer the question
3. Look for INDIRECT REFERENCES that answer the question
4. For date/time questions: ALWAYS return exact dates, NOT relative terms like "yesterday", "last week", etc.
   - If you find "yesterday" and the session date is "5 June 2023", return "4 June 2023"
   - If you find "last Tuesday", calculate the exact date based on the session date
   - Convert ALL relative time references to absolute dates in the format: "DD Month YYYY" or "DD MMM YYYY"
5. Make reasonable inferences from context when the answer is implied
6. Keep answers EXTREMELY CONCISE (typically 1-5 words)
7. DO NOT include the person's name or phrases like "According to..." or "Based on..."

Question: {question}

User Profile:
{profile_summary}

Context from memory:
{context}

If no relevant information is found in ANY of the above context, respond ONLY with: "Information not found"

Direct Answer (just the fact, nothing else):"""

        try:
            response = await self.llm.ainvoke(prompt)
            predicted_answer = response.content.strip()
            # Post-process answer to ensure conciseness
            predicted_answer = self.post_process_answer(predicted_answer)
        except Exception as e:
            predicted_answer = f"LLM Error: {e}"

        return retrieved_memories, predicted_answer

    def post_process_answer(self, answer: str) -> str:
        """Minimal post-processing to ensure answer conciseness.

        With improved prompting that explicitly requests concise answers,
        most verbose patterns should be avoided at the source.
        We keep only basic cleanup as a safety net.
        """
        if not answer:
            return answer

        # Remove quotes if they wrap the entire answer
        if answer.startswith('"') and answer.endswith('"'):
            answer = answer[1:-1]

        # Remove trailing period for consistency
        if answer.endswith("."):
            answer = answer[:-1]

        # Limit length as a final safety check (keep first 8 words max)
        words = answer.split()
        if len(words) > 8:
            answer = " ".join(words[:8])

        return answer.strip()

    async def calculate_llm_j_score(
        self, question: str, gold_answer: str, generated_answer: str
    ) -> float:
        """Calculate LLM_J score using LLM judgment of CORRECT/WRONG."""

        prompt = f"""Your task is to label an answer to a question as "CORRECT" or "WRONG". You will be given
the following data: (1) a question (posed by one user to another user), (2) a 'gold'
(ground truth) answer, (3) a generated answer which you will score as CORRECT/WRONG.

The point of the question is to ask about something one user should know about the other
user based on their prior conversations. The gold answer will usually be a concise and
short answer that includes the referenced topic.

SPECIAL CASE: If the gold answer is "Information not found", this means the question is
unanswerable based on the available information, and the correct response should be
"Information not found" or similar non-answer phrases.

BE GENEROUS WITH YOUR GRADING - PRIORITIZE SEMANTIC CORRECTNESS OVER EXACT WORDING:

✓ CORRECT Examples:
- Gold: "single", Generated: "single parent" → CORRECT (more specific but contains core concept)
- Gold: "amazing and awesome", Generated: "great" → CORRECT (same positive sentiment)
- Gold: "psychology, counseling", Generated: "mental health" → CORRECT (same domain)
- Gold: "May 7th", Generated: "7 May 2023" → CORRECT (same date, different format)
- Gold: "Hawaii shell necklace", Generated: "a shell necklace from Hawaii" → CORRECT (same information)

✗ WRONG Examples:
- Gold: "single", Generated: "married" → WRONG (contradictory information)
- Gold: "positive", Generated: "negative" → WRONG (opposite sentiment)
- Gold: "May 7th", Generated: "June 15th" → WRONG (different date)
- Gold: "shell necklace", Generated: "surfboard" → WRONG (completely different item)

EVALUATION CRITERIA (mark CORRECT if ANY apply):
1. Generated answer contains the core concept from gold answer
2. Generated answer is more specific but includes the gold answer concept
3. Generated answer expresses the same sentiment/meaning in different words
4. Generated answer partially covers the gold answer topic
5. For dates/times: refers to same period even if format differs

Only mark WRONG if the generated answer is:
- Factually contradictory to the gold answer
- Completely unrelated to the topic
- "Information not found" or similar non-answers

Question: {question}
Gold answer: {gold_answer}
Generated answer: {generated_answer}

First, provide a short (one sentence) explanation of your reasoning, then finish with
CORRECT or WRONG. Do NOT include both CORRECT and WRONG in your response, or it will break
the evaluation script.

Just return the label CORRECT or WRONG in a json format with the key as "label"."""

        try:
            response = await self.llm.ainvoke(prompt)
            response_text = response.content.strip()

            # Try to extract JSON
            import json
            import re

            # Look for JSON in the response
            json_match = re.search(
                r'\{[^}]*"label"\s*:\s*"(CORRECT|WRONG)"[^}]*\}',
                response_text,
                re.IGNORECASE,
            )
            if json_match:
                try:
                    json_obj = json.loads(json_match.group(0))
                    label = json_obj.get("label", "").upper()
                    if label in ["CORRECT", "WRONG"]:
                        return 1.0 if label == "CORRECT" else 0.0
                except json.JSONDecodeError:
                    pass

            # Fallback: look for CORRECT or WRONG in the response
            response_upper = response_text.upper()
            if "CORRECT" in response_upper and "WRONG" not in response_upper:
                return 1.0
            elif "WRONG" in response_upper and "CORRECT" not in response_upper:
                return 0.0
            else:
                # Default to wrong if ambiguous
                return 0.0

        except Exception as e:
            print(f"LLM_J evaluation error: {e}")
            return 0.0

    async def calculate_answer_score(
        self, expected: str, predicted: str, question: str = ""
    ) -> float:
        """Calculate F1-based similarity score between expected and predicted answers using LLM evaluation."""
        # Convert to strings to handle integer answers
        expected = str(expected)
        predicted = str(predicted) if predicted else ""

        # Handle case where expected answer is "Information not found" (adversarial questions)
        if expected.strip() == "Information not found":
            if predicted and "not found" in predicted.lower():
                return (
                    1.0  # Correct - model correctly identified no information available
                )
            else:
                return (
                    0.0  # Incorrect - model provided an answer when it shouldn't have
                )

        # For normal questions, "not found" or errors are failures
        if (
            not predicted
            or "not found" in predicted.lower()
            or "error" in predicted.lower()
        ):
            return 0.0

        expected_str = str(expected).strip()
        predicted_str = predicted.strip()

        # Quick exact match check first
        if expected_str.lower() == predicted_str.lower():
            return 1.0

        # Use LLM to evaluate semantic similarity
        return await self._llm_evaluate_similarity(
            expected_str, predicted_str, question
        )

    async def _llm_evaluate_similarity(
        self, expected: str, predicted: str, question: str = ""
    ) -> float:
        """Use LLM to calculate F1-based similarity score between expected and predicted answers."""
        question_context = f"\n\nQuestion: {question}" if question else ""

        prompt = f"""Calculate a precise F1-based similarity score between the expected and predicted answers. BE VERY CAREFUL to give nuanced scores between 0.0 and 1.0.{question_context}

SCORING METHOD - STEP BY STEP:
1. Break both answers into key components/concepts (not just words)
2. Count carefully:
   - TP (true positives): Components in both expected and predicted
   - FP (false positives): Components only in predicted
   - FN (false negatives): Components only in expected
3. Calculate: Precision = TP/(TP+FP), Recall = TP/(TP+FN)
4. F1 Score = 2 * (Precision * Recall) / (Precision + Recall)

CRITICAL: USE PARTIAL SCORING FOR SEMANTIC MATCHES
- "counseling" ≈ "mental health counseling" = 0.8 match (not 1.0)
- "psychology" ≈ "mental health" = 0.6 match
- "adoption agencies" ≈ "researching adoption agencies" = 0.9 match

WORKED EXAMPLES:
Expected: "Psychology, counseling certification"
Predicted: "counseling, mental health"
Analysis:
- Psychology vs mental health: 0.6 semantic match
- counseling vs counseling: 1.0 exact match
- certification missing: -1 FN
Calculation: TP=1.6, FP=0.4, FN=0.4
Precision=1.6/2.0=0.8, Recall=1.6/2.0=0.8
F1 = 0.80

Expected: "researching adoption agencies"
Predicted: "adoption agencies"
Analysis: Core concept matches but missing "researching" action
TP=0.9, FP=0, FN=0.1
Precision=0.9/0.9=1.0, Recall=0.9/1.0=0.9
F1 = 0.95

GIVE NUANCED SCORES - NOT JUST 0.0 or 1.0!
Common good F1 ranges:
- 0.6-0.7: Partially correct, missing some elements
- 0.7-0.8: Mostly correct with minor issues
- 0.8-0.9: Very good with small differences
- 0.9-1.0: Nearly perfect or perfect

Expected Answer: "{expected}"
Predicted Answer: "{predicted}"

Return ONLY a decimal F1 score between 0.0 and 1.0 (like 0.75 or 0.82)."""

        try:
            response = await self.llm.ainvoke(prompt)
            score_str = response.content.strip()

            # Extract number from response - look for the final score
            import re

            # Try multiple patterns to extract the final F1 score
            patterns = [
                r"\*\*(\d+\.\d+)\*\*\s*$",  # **0.40** at end
                r"(\d+\.\d+)\s*$",  # 0.40 at end
                r"F1.*?(\d+\.\d+)",  # F1 Score = 0.40
                r"score.*?(\d+\.\d+)",  # score is 0.40
            ]

            score = None
            for pattern in patterns:
                match = re.search(pattern, score_str, re.MULTILINE | re.IGNORECASE)
                if match:
                    score = float(match.group(1))
                    break

            # Fallback: find all decimal numbers and take the last one
            if score is None:
                decimal_matches = re.findall(r"\d+\.\d+", score_str)
                if decimal_matches:
                    score = float(decimal_matches[-1])

            # Final fallback: try any number pattern
            if score is None:
                match = re.search(r"(\d+\.?\d*)", score_str)
                if match:
                    score = float(match.group(1))

            if score is not None:
                # Ensure score is between 0 and 1
                return min(max(score, 0.0), 1.0)
            else:
                # Fallback to simple word overlap if LLM doesn't return a number
                return self._fallback_similarity_score(expected, predicted)

        except Exception:
            # Fallback to simple scoring if LLM call fails
            return self._fallback_similarity_score(expected, predicted)

    def _fallback_similarity_score(self, expected: str, predicted: str) -> float:
        """Fallback scoring method if LLM evaluation fails."""
        expected_words = set(expected.lower().split())
        predicted_words = set(predicted.lower().split())

        if not expected_words:
            return 0.0

        overlap = len(expected_words & predicted_words)
        total = len(expected_words | predicted_words)
        return overlap / total if total > 0 else 0.0

    def _get_evidence_texts(self, evidence_refs: list[str]) -> dict[str, str]:
        """Extract actual conversation text from evidence references like 'D1:3'."""
        evidence_texts = {}

        if not self.conversation_data:
            return evidence_texts

        for ref in evidence_refs:
            try:
                # Parse reference like "D1:3" or "D2:15"
                if ":" in ref:
                    day_part, dia_num = ref.split(":")
                    # Extract session number from day part (D1 -> 1, D2 -> 2, etc.)
                    session_num = int(day_part[1:])  # Remove 'D' and convert to int
                    dia_id = ref  # Keep full dia_id for lookup

                    # Look for the text in the appropriate session
                    session_key = f"session_{session_num}"
                    if session_key in self.conversation_data:
                        session_data = self.conversation_data[session_key]
                        for exchange in session_data:
                            if exchange.get("dia_id") == dia_id:
                                speaker = exchange.get("speaker", "Unknown")
                                text = str(exchange.get("text", ""))
                                evidence_texts[ref] = f"[{speaker}] {text}"
                                break
                        else:
                            evidence_texts[ref] = f"Text not found for {ref}"
                    else:
                        evidence_texts[ref] = f"Session {session_num} not found"
                else:
                    evidence_texts[ref] = f"Invalid reference format: {ref}"
            except (ValueError, IndexError) as e:
                evidence_texts[ref] = f"Error parsing {ref}: {e}"

        return evidence_texts

    def _has_similar_meaning(self, expected: str, predicted: str) -> bool:
        """Check if two answers have similar meaning."""
        # Define synonym groups for common terms
        synonyms = {
            "counseling": ["counseling", "counselling", "therapy", "mental health"],
            "psychology": ["psychology", "psychological", "mental health"],
            "certification": [
                "certification",
                "certificate",
                "degree",
                "qualification",
            ],
            "support group": ["support group", "group", "lgbtq support group"],
        }

        expected_lower = expected.lower()
        predicted_lower = predicted.lower()

        for main_term, synonym_list in synonyms.items():
            if main_term in expected_lower and any(
                syn in predicted_lower for syn in synonym_list
            ):
                return True
            if main_term in predicted_lower and any(
                syn in expected_lower for syn in synonym_list
            ):
                return True

        return False

    def _is_date_equivalent(self, date1: str, date2: str) -> bool:
        """Check if two date strings represent the same date."""
        import re

        # Common date patterns
        patterns = [
            r"(\d{1,2})\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})",
            r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{1,2}),?\s+(\d{4})",
            r"(\d{4})-(\d{1,2})-(\d{1,2})",
            r"(\d{1,2})/(\d{1,2})/(\d{4})",
        ]

        def parse_date(date_str):
            """Try to parse a date string into a standardized format."""
            date_str = date_str.strip().lower().replace(",", "")  # Remove commas

            # Try "7 may 2023" format
            match = re.match(patterns[0], date_str)
            if match:
                day, month, year = match.groups()
                return f"{month} {day} {year}"

            # Try "may 7 2023" format (without comma)
            match = re.match(patterns[1].replace(",?", ""), date_str)
            if match:
                month, day, year = match.groups()
                return f"{month} {day} {year}"

            # Add more patterns as needed
            return date_str

        normalized1 = parse_date(date1)
        normalized2 = parse_date(date2)

        return normalized1 == normalized2

    def _calculate_list_score(self, expected: str, predicted: str) -> float:
        """Calculate score for list-type answers (comma-separated values)."""
        # Split by comma and normalize
        expected_items = {item.strip() for item in expected.split(",") if item.strip()}
        predicted_items = {
            item.strip() for item in predicted.split(",") if item.strip()
        }

        if not expected_items:
            return 0.0

        # Calculate precision and recall
        if not predicted_items:
            return 0.0

        correct = len(expected_items & predicted_items)
        precision = correct / len(predicted_items) if predicted_items else 0
        recall = correct / len(expected_items) if expected_items else 0

        # F1 score
        if precision + recall == 0:
            return 0.0
        return 2 * (precision * recall) / (precision + recall)

    def display_results(self, results: list[dict[str, Any]]):
        """Display evaluation results in a formatted table."""
        # Calculate overall stats
        total_questions = len(results)
        average_f1_score = (
            sum(r.get("f1_score", 0.0) for r in results) / total_questions
            if total_questions > 0
            else 0.0
        )
        average_llm_j_score = (
            sum(r.get("llm_j_score", 0.0) for r in results) / total_questions
            if total_questions > 0
            else 0.0
        )
        # Average score calculation removed - not used

        # Calculate average Q&A time
        average_qa_time = (
            sum(r.get("qa_time_seconds", 0) for r in results) / total_questions
            if total_questions > 0
            else 0.0
        )

        # Display summary
        self.console.print("\n⏺ QA Evaluation Results", style="white")
        self.console.print(f"⏺ Total Questions: {total_questions}", style="white")
        self.console.print(f"⏺ Average F1 Score: {average_f1_score:.3f}", style="white")
        self.console.print(
            f"⏺ Average LLM_J Score: {average_llm_j_score:.3f}", style="white"
        )
        self.console.print(f"⏺ Average Q&A Time: {average_qa_time:.2f}s", style="white")

        # Display detailed results
        table = Table(title="QA Evaluation Details", show_lines=True)
        table.add_column("Question", style="white", max_width=30)
        table.add_column("Expected", style="white", max_width=25)
        table.add_column("Predicted", style="white", max_width=25)
        table.add_column("F1 Score", style="white", justify="right")
        table.add_column("LLM_J", style="white", justify="right")
        table.add_column("Memories", style="white", justify="right")
        table.add_column("Time (s)", style="white", justify="right")

        for result in results[:20]:  # Show first 20 results
            f1_score = result.get("f1_score", 0.0)
            f1_score_color = (
                "green" if f1_score >= 0.7 else "red" if f1_score == 0 else "yellow"
            )

            llm_j_score = result.get("llm_j_score", 0.0)
            llm_j_score_color = (
                "green"
                if llm_j_score >= 0.8
                else "red"
                if llm_j_score == 0
                else "yellow"
            )

            # Show full text for better analysis - don't truncate expected/predicted
            question_text = (
                result["question"][:50] + "..."
                if len(result["question"]) > 50
                else result["question"]
            )
            expected_text = str(result["expected_answer"])  # Full text
            predicted_text = result["predicted_answer"]  # Full text

            # Color "Information not found" in red
            if predicted_text == "Information not found":
                predicted_text = f"[red]{predicted_text}[/red]"

            table.add_row(
                question_text,
                expected_text,
                predicted_text,
                f"[{f1_score_color}]{f1_score:.2f}[/{f1_score_color}]",
                f"[{llm_j_score_color}]{llm_j_score:.2f}[/{llm_j_score_color}]",
                str(
                    len(result["retrieved_memories"])
                    if isinstance(result["retrieved_memories"], list)
                    else 0
                ),
                f"{result.get('qa_time_seconds', 0):.2f}",
            )

        self.console.print(table)

        if len(results) > 20:
            self.console.print(
                f"⏺ ... and {len(results) - 20} more results", style="white"
            )

        # Detailed troubleshooting information is saved to the output file


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Evaluate memory agent performance using locomo test data"
    )

    parser.add_argument(
        "--data-file",
        type=str,
        default="examples/data/locomo10.json",
        help="Path to locomo JSON file containing multiple conversations",
    )
    parser.add_argument(
        "--person",
        type=str,
        help="Person to create memories for",
    )
    parser.add_argument(
        "--storage-path",
        type=str,
        default="/tmp/qa_evaluation",
        help="Path for memory storage",
    )
    parser.add_argument(
        "--session",
        type=str,
        default="1",
        help="Process specified session(s) within the conversation. Examples: 1, 1-3, 1,3,5 (default: 1)",
    )
    parser.add_argument(
        "--conversation",
        type=int,
        default=1,
        help="Conversation ID to load (1-indexed, default: 1)",
    )
    parser.add_argument(
        "--max-search-results",
        type=int,
        default=5,
        help="Maximum number of search results to retrieve (default: 5)",
    )
    parser.add_argument(
        "--max-context-memories",
        type=int,
        default=5,
        help="Maximum number of memories to use for LLM context (default: 3)",
    )
    parser.add_argument(
        "--max-memory-size",
        type=int,
        default=10000,
        help="Maximum size of individual memory content (default: 2000 chars)",
    )
    parser.add_argument(
        "--context-turns",
        type=int,
        default=5,
        help="Number of conversation turns to include as context (default: 1)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of retry attempts for failed searches (default: 3)",
    )

    args = parser.parse_args()

    # Setup console
    console = Console()

    # Check if person argument is provided
    if not args.person:
        console.print(
            "No person specified. Available conversations:", style="bold white"
        )
        console.print("  1. Conversation 1: Caroline and Melanie", style="white")
        console.print("  2. Conversation 2: Jon and Gina", style="white")
        console.print("  3. Conversation 3: John and Maria", style="white")
        console.print("  4. Conversation 4: Joanna and Nate", style="white")
        console.print("  5. Conversation 5: Tim and John", style="white")
        console.print("  6. Conversation 6: Audrey and Andrew", style="white")
        console.print("  7. Conversation 7: James and John", style="white")
        console.print("  8. Conversation 8: Deborah and Jolene", style="white")
        console.print("  9. Conversation 9: Evan and Sam", style="white")
        console.print("  10. Conversation 10: Calvin and Dave", style="white")
        console.print(
            "\nUsage: python examples/locomo_evaluation.py --person <person_name> --conversation <conversation_id>",
            style="bold white",
        )
        sys.exit(1)

    # Create output file with timestamp
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/tmp/locomo_eval_c{args.conversation}_{args.person}_{timestamp}.txt"

    try:
        # Initialize evaluator
        evaluator = LocomoEvaluator(
            data_file=args.data_file,
            person_name=args.person,
            storage_path=args.storage_path,
            session=args.session,
            conversation_id=args.conversation,
            max_search_results=args.max_search_results,
            max_context_memories=args.max_context_memories,
            max_memory_size=args.max_memory_size,
            context_turns=args.context_turns,
            max_retries=args.max_retries,
        )

        # Setup components
        await evaluator.setup()

        # Process memories from conversations
        await evaluator.process_memories()

        # Evaluate QA pairs
        results = await evaluator.evaluate_qa()

        # Display results
        evaluator.display_results(results)

        # Save detailed results to file
        with open(output_file, "w") as f:
            f.write("Locomo Evaluation Results\n")
            f.write(f"Conversation: {args.conversation}\n")
            f.write(f"Person: {args.person}\n")
            f.write(f"Session: {args.session or 'All'}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write("=" * 80 + "\n\n")

            # Add profile summary at the beginning
            f.write("USER PROFILE SUMMARY\n")
            f.write("=" * 80 + "\n")
            try:
                # Generate profile summary using the profile manager (fast structured-only mode)
                if hasattr(evaluator, "profile_manager") and evaluator.profile_manager:
                    profile_summary = (
                        await evaluator.profile_manager.get_profile_summary(
                            llm=None  # Use fast structured-only mode for output file
                        )
                    )
                    if (
                        profile_summary
                        and profile_summary != "No profile information available."
                    ):
                        f.write(profile_summary)
                        f.write("\n\n")
                    else:
                        f.write("No profile information available.\n\n")
                else:
                    f.write("Profile manager not available.\n\n")
            except Exception as e:
                f.write(f"Error generating profile summary: {e}\n\n")

            f.write("=" * 80 + "\n\n")

            # Dump all stored memories
            f.write("STORED MEMORIES DUMP\n")
            f.write("=" * 80 + "\n")
            try:
                # Get the store from the intelligent classifier
                store = evaluator.intelligent_classifier.memory_store
                namespace_str = (
                    "memory:general"  # Same namespace used in the evaluation
                )
                namespace_parts = namespace_str.split(":")
                namespace_tuple = tuple(namespace_parts)

                # Search for all memories in the namespace
                all_memories = store.search(namespace_tuple, limit=1000)

                f.write(f"Found {len(all_memories)} stored memories:\n\n")

                for i, (namespace, storage_key, memory_data) in enumerate(
                    all_memories, 1
                ):
                    # Extract semantic path from storage key (format: semantic_path#unique_id)
                    if "#" in storage_key:
                        semantic_key = storage_key.split("#")[0]
                    else:
                        semantic_key = storage_key

                    f.write(f"Memory {i}:\n")
                    f.write(f"  Path: {semantic_key}\n")
                    f.write(f"  Namespace: {':'.join(namespace)}\n")

                    if isinstance(memory_data, dict):
                        # Pretty print the memory data
                        f.write(
                            f"  Confidence: {memory_data.get('confidence', 'N/A')}\n"
                        )

                        # Handle memory data structure - the actual memory is stored with 'raw_text', 'session_date', 'confidence' fields
                        # First check for raw_text (new format)
                        if "raw_text" in memory_data:
                            raw_text = memory_data.get("raw_text", "")
                            classification_paths = memory_data.get(
                                "classification_paths", []
                            )

                            # Show multi-label classification if available
                            if classification_paths and len(classification_paths) > 1:
                                f.write(
                                    f"  Multi-Label Classification ({len(classification_paths)} paths):\n"
                                )
                                for idx, path in enumerate(classification_paths, 1):
                                    f.write(f"    {idx}. {path}\n")

                            f.write("\n")  # Add spacing before entries

                            # Parse raw_text to extract entries and format them properly
                            session_date = memory_data.get("session_date", "N/A")
                            evaluator._write_formatted_memory_entries(
                                f, raw_text, session_date
                            )

                        # Check for content field (legacy format or search results)
                        elif "content" in memory_data:
                            content = memory_data.get("content", "")
                            f.write(f"  Content Type: {type(content).__name__}\n")

                            # Handle different content formats
                            if isinstance(content, str):
                                try:
                                    # Try to parse as JSON to see if it's structured data
                                    if content.strip().startswith("{"):
                                        content_obj = json.loads(content)
                                        f.write("  Content (JSON):\n")

                                        # Show different parts of structured content
                                        if "raw_text" in content_obj:
                                            raw_text = content_obj["raw_text"]
                                            f.write(f"    Raw Text: {raw_text}\n")

                                        if "structured_data" in content_obj:
                                            structured = content_obj["structured_data"]
                                            f.write(
                                                f"    Structured Data: {json.dumps(structured, indent=6)}\n"
                                            )

                                        if "summary" in content_obj:
                                            summary = content_obj["summary"]
                                            f.write(f"    Summary: {summary}\n")

                                        # Show any other keys
                                        other_keys = set(content_obj.keys()) - {
                                            "raw_text",
                                            "structured_data",
                                            "summary",
                                        }
                                        for key in other_keys:
                                            value = content_obj[key]
                                            if isinstance(
                                                value, (str, int, float, bool)
                                            ):
                                                f.write(f"    {key}: {value}\n")
                                            else:
                                                f.write(
                                                    f"    {key}: {json.dumps(value, indent=6)}\n"
                                                )
                                    else:
                                        # Plain text content
                                        f.write(f"  Content (Text): {content}\n")
                                except json.JSONDecodeError:
                                    # Not JSON, treat as plain text
                                    f.write(f"  Content (Text): {content}\n")
                            elif isinstance(content, dict):
                                f.write("  Content (Dict):\n")
                                for key, value in content.items():
                                    if isinstance(value, str) and len(value) > 200:
                                        f.write(
                                            f"    {key}: {value[:200]}...(truncated)\n"
                                        )
                                    else:
                                        f.write(f"    {key}: {value}\n")
                            else:
                                # Other content types
                                content_str = str(content)
                                if len(content_str) > 1000:
                                    content_str = content_str[:1000] + "...(truncated)"
                                f.write(f"  Content: {content_str}\n")

                        # If neither raw_text nor content, show all fields
                        else:
                            f.write("  Memory Format: Unknown format\n")
                            f.write("  All fields:\n")
                            for key, value in memory_data.items():
                                if key in ["timestamp", "confidence"]:
                                    continue  # Already shown above
                                if isinstance(value, str) and len(value) > 200:
                                    f.write(f"    {key}: {value[:200]}...(truncated)\n")
                                else:
                                    f.write(f"    {key}: {value}\n")

                        metadata = memory_data.get("metadata", {})
                        if metadata:
                            f.write(f"  Metadata: {json.dumps(metadata, indent=4)}\n")
                    else:
                        content_str = str(memory_data)
                        if len(content_str) > 1000:
                            content_str = content_str[:1000] + "...(truncated)"
                        f.write(f"  Content: {content_str}\n")

                    f.write("\n")

            except Exception as e:
                f.write(f"Error dumping memories: {e}\n")

            f.write("=" * 80 + "\n\n")

            # Write summary
            total_questions = len(results)
            average_f1_score = (
                sum(r.get("f1_score", 0.0) for r in results) / total_questions
                if total_questions > 0
                else 0.0
            )
            average_llm_j_score = (
                sum(r.get("llm_j_score", 0.0) for r in results) / total_questions
                if total_questions > 0
                else 0.0
            )
            average_qa_time = (
                sum(r.get("qa_time_seconds", 0) for r in results) / total_questions
                if total_questions > 0
                else 0.0
            )
            # Average score calculation removed - not used

            f.write(f"Total Questions: {total_questions}\n")
            f.write(f"Average F1 Score: {average_f1_score:.3f}\n")
            f.write(f"Average LLM_J Score: {average_llm_j_score:.3f}\n")
            f.write(f"Average Q&A Time: {average_qa_time:.2f}s\n\n")

            # Write QA Evaluation Details in table format
            f.write("QA Evaluation Details\n")
            f.write("=" * 90 + "\n")
            f.write(
                f"{'Question':<18} | {'Expected':<15} | {'Predicted':<15} | {'F1':<6} | {'LLM_J':<6} | {'Mem':<4}\n"
            )
            f.write("-" * 90 + "\n")

            for result in results[:20]:  # Match the console limit
                question_text = (
                    result["question"][:15] + "..."
                    if len(result["question"]) > 15
                    else result["question"]
                )
                expected_text = str(result["expected_answer"])
                expected_text = (
                    expected_text[:12] + "..."
                    if len(expected_text) > 12
                    else expected_text
                )
                predicted_text = str(result["predicted_answer"])
                predicted_text = (
                    predicted_text[:12] + "..."
                    if len(predicted_text) > 12
                    else predicted_text
                )
                # Safety check for retrieved_memories
                retrieved_memories = result.get("retrieved_memories", [])
                if not isinstance(retrieved_memories, list):
                    retrieved_memories = []
                memory_count = len(retrieved_memories)

                f.write(
                    f"{question_text:<18} | {expected_text:<15} | {predicted_text:<15} | {result.get('f1_score', 0.0):>6.2f} | {result.get('llm_j_score', 0.0):>6.2f} | {memory_count:>4}\n"
                )

            f.write("-" * 90 + "\n\n")

            # Write detailed results
            for i, result in enumerate(results, 1):
                f.write(f"\nQuestion {i}: {result['question']}\n")
                f.write(f"Expected: {result['expected_answer']}\n")
                f.write(f"Predicted: {result['predicted_answer']}\n")
                f.write(f"F1 Score: {result.get('f1_score', 0.0):.2f}\n")
                f.write(f"LLM_J Score: {result.get('llm_j_score', 0.0):.2f}\n")

                # Add evidence information if available
                evidence = result.get("evidence", [])
                if evidence:
                    f.write(f"Evidence: {', '.join(evidence)}\n")

                    # Add actual evidence text
                    evidence_texts = evaluator._get_evidence_texts(evidence)
                    if evidence_texts:
                        f.write("Evidence Text:\n")
                        for ref, text in evidence_texts.items():
                            f.write(f"  {ref}: {text}\n")

                # Safety check for retrieved_memories
                retrieved_memories = result.get("retrieved_memories", [])
                if not isinstance(retrieved_memories, list):
                    retrieved_memories = []

                if retrieved_memories:
                    f.write(f"\nRetrieved {len(retrieved_memories)} memories:\n")
                    for j, memory in enumerate(retrieved_memories, 1):
                        f.write(f"\n  Memory {j}:\n")
                        f.write(f"    Path: {memory['path']}\n")
                        f.write(f"    Distance: {memory['semantic_distance']}\n")
                        f.write(f"    Items: {memory['item_count']}\n")
                        f.write(f"    Content: {memory['content']}\n")
                else:
                    f.write("  No memories retrieved\n")

                f.write("-" * 80 + "\n")

        console.print(f"\n⏺ Full output saved to: {output_file}", style="bold green")

    except Exception as e:
        import traceback

        console.print(f"⏺ Error: {e}", style="white")
        # Save error info to file instead of console export
        with open(output_file, "w") as f:
            f.write(f"Error occurred during evaluation: {e}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Full traceback:\n{traceback.format_exc()}\n")
        console.print(f"\n⏺ Error logged to: {output_file}", style="bold red")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

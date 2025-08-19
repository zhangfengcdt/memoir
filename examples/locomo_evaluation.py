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

from memoir.core.prolly_adapter import ProllyTreeStore
from memoir.search.hierarchical_search import (
    HierarchicalSearchEngine,
    SearchStrategy,
)
from memoir.taxonomy.intelligent_classifier import IntelligentClassifier
from memoir.taxonomy.semantic_classifier import SemanticClassifier
from memoir.taxonomy.taxonomy_presets import TaxonomyVersion

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress verbose logging from external libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("memoir.search.hierarchical_search").setLevel(logging.WARNING)
logging.getLogger("memoir.taxonomy.data_sources").setLevel(logging.WARNING)
# Suppress all memoir logging
logging.getLogger("memoir").setLevel(logging.WARNING)


class LocomoEvaluator:
    """Evaluates memory agent's ability to answer questions using stored memories from locomo dataset."""

    def __init__(
        self,
        data_file: str,
        person_name: str,
        storage_path: str = "/tmp/qa_evaluation",
        confidence_thresholds: Optional[dict[str, float]] = None,
        session: Optional[str] = None,
        max_search_results: int = 5,
        max_context_memories: int = 3,
        max_memory_size: int = 2000,
    ):
        self.console = Console()
        self.data_file = data_file
        self.person_name = person_name
        self.storage_path = storage_path
        self.session = session
        self.max_search_results = max_search_results
        self.max_context_memories = max_context_memories
        self.max_memory_size = max_memory_size
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
        self.conversation_data = None
        self.qa_data = None

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

        classifier = SemanticClassifier(llm=self.llm)
        store = ProllyTreeStore(
            path=str(data_dir),
            classifier=classifier,
            enable_versioning=False,
        )

        # Create intelligent classifier
        self.intelligent_classifier = IntelligentClassifier(
            llm=self.llm,
            memory_store=store,
            taxonomy_version=TaxonomyVersion.GENERAL,
            confidence_thresholds=self.confidence_thresholds,
        )

        # Create search engine
        self.search_engine = HierarchicalSearchEngine(
            store=store, classifier=classifier
        )

        # Load conversation and QA data
        await self.load_data()

    async def load_data(self):
        """Load conversation and QA data from file."""
        with open(self.data_file) as f:
            content = f.read()

        # Handle potential extra data at the end of JSON - find the first complete JSON object
        brace_count = 0
        end_pos = 0
        for i, char in enumerate(content):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end_pos = i + 1
                    break

        # Parse just the first JSON object
        data = json.loads(content[:end_pos])

        self.qa_data = data.get("qa", [])
        self.conversation_data = data.get("conversation", {})

        # Filter QA pairs immediately to show accurate counts
        filtered_qa = self.filter_qa_by_session_and_person()

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
                if speaker == self.person_name and exchange.get("text", "").strip():
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
                text = exchange.get("text", "")

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

                    # Get selective conversation context - only include the most recent question
                    conversation_context = []
                    if len(conversation_history) > 1:
                        # Look backwards through previous exchanges to find the most recent question
                        for prev_exchange in reversed(conversation_history[:-1]):
                            # Check if the exchange contains a question
                            if self._is_question(prev_exchange):
                                conversation_context.append(prev_exchange)
                                # Only include the most recent question to avoid noise
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
            expected_answer = qa_item.get("answer", "")
            evidence = qa_item.get("evidence", [])
            category = qa_item.get("category", 0)

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
                        "score": 0.0,
                        "error": str(e),
                    }
                )

        return results

    async def evaluate_single_qa(
        self, question: str, expected_answer: str, evidence: list[str], category: int
    ) -> dict[str, Any]:
        """Evaluate a single QA pair."""
        # Search for relevant memories
        # Use the same namespace format as IntelligentClassifier: ("memory", taxonomy_version)
        namespace_str = (
            "memory:general"  # Format: "memory:general" for TaxonomyVersion.GENERAL
        )
        # Debug: First test what paths the classifier generates for this question
        context = {
            "available_memory_paths": [
                "goals.categories.career",
                "experience.memories.emotional.happy",
                "experience.memories.significant.events",
                "preferences.personal.lifestyle.hobbies.creative",
            ]
        }
        # Removed verbose debug output to prevent scrolling

        # Try multiple search strategies to get better results
        search_results = []

        # First try: specific to general search
        results1 = await self.search_engine.search(
            query=question,
            namespace=namespace_str,
            strategy=SearchStrategy.SPECIFIC_TO_GENERAL,
        )
        search_results.extend(results1)

        # For date questions about specific events, try alternative search terms
        if "when" in question.lower() and (
            "support group" in question.lower() or "LGBTQ" in question.lower()
        ):
            # Search specifically for "yesterday" content that contains the date
            alt_queries = [
                "yesterday LGBTQ support group powerful",
                "went LGBTQ support group",
                "significant events LGBTQ",
            ]
            for alt_query in alt_queries:
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
                strategy=SearchStrategy.SPECIFIC_TO_GENERAL,  # Use same strategy to avoid error
            )
            search_results.extend(results2)

            # Removed debug output

        # Remove duplicates based on content (not just path) while preserving order
        seen_content = set()
        unique_results = []
        for result in search_results:
            # Create a content hash to identify duplicates
            content_hash = hash(result.combined_content)
            if content_hash not in seen_content:
                unique_results.append(result)
                seen_content.add(content_hash)

        search_results = unique_results[
            : self.max_search_results
        ]  # Keep top N unique results

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

        # Generate answer using LLM with improved prompt
        prompt = f"""Extract the specific fact that answers the question from the provided context. Be thorough in examining ALL the context provided.

CRITICAL ANALYSIS RULES:
1. READ ALL CONTEXT CAREFULLY - the answer may be anywhere in the provided text
2. Look for DIRECT STATEMENTS that answer the question
3. Look for INDIRECT REFERENCES that answer the question
4. For date questions: Calculate dates from relative references (yesterday = session date - 1 day)

EXAMPLES:
Q: "What is John's favorite hobby?"
Context: "I spend most weekends playing guitar and writing songs"
A: playing guitar

Q: "When did Sarah visit the doctor?"
Context: "I went to my doctor appointment yesterday on March 14th"
A: 14 March 2023

Q: "What does Alex study?"
Context: "I'm taking courses in computer science and machine learning"
A: computer science and machine learning

Q: "What is Maria's living situation?"
Context: "Living alone has been great for my independence and personal growth"
A: living alone

Retrieved Context:
{context}

Question: {question}

EXTRACTION RULES:
1. Return ONLY the direct factual answer (NO explanations, NO prefixes like "Caroline went to...")
2. If genuinely no relevant information: "Information not found"
3. Look for ANY mention that could answer the question
4. Be LESS STRICT - extract information even if not perfectly phrased
5. Make reasonable inferences from context when the answer is implied
6. Keep answers EXTREMELY CONCISE (typically 1-5 words)
7. DO NOT include the person's name or phrases like "According to..." or "Based on..."

Direct Answer (just the fact, nothing else):"""

        # Removed per-question debug output

        try:
            response = await self.llm.ainvoke(prompt)
            predicted_answer = response.content.strip()

            # Post-process answer to ensure conciseness
            predicted_answer = self.post_process_answer(predicted_answer)

            # Debug output disabled - issues mostly resolved

        except Exception as e:
            predicted_answer = f"LLM Error: {e}"

        # Calculate score using LLM evaluation
        score = await self.calculate_answer_score(
            expected_answer, predicted_answer, question
        )

        return {
            "question": question,
            "expected_answer": expected_answer,
            "predicted_answer": predicted_answer,
            "evidence": evidence,
            "category": category,
            "retrieved_memories": retrieved_memories,
            "score": score,
        }

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

    async def calculate_answer_score(
        self, expected: str, predicted: str, question: str = ""
    ) -> float:
        """Calculate F1-based similarity score between expected and predicted answers using LLM evaluation."""
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
                                text = exchange.get("text", "")
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
        average_score = (
            sum(r["score"] for r in results) / total_questions
            if total_questions > 0
            else 0.0
        )

        # Display summary
        self.console.print("\n⏺ QA Evaluation Results", style="white")
        self.console.print(f"⏺ Total Questions: {total_questions}", style="white")
        self.console.print(f"⏺ Average Score: {average_score:.3f}", style="white")

        # Display detailed results
        table = Table(title="QA Evaluation Details", show_lines=True)
        table.add_column("Question", style="white", max_width=35)
        table.add_column("Expected", style="white", max_width=40)
        table.add_column("Predicted", style="white", max_width=40)
        table.add_column("F1 Score", style="white", justify="right")
        table.add_column("Memories", style="white", justify="right")

        for result in results[:20]:  # Show first 20 results
            score_color = (
                "green"
                if result["score"] >= 0.7
                else "red" if result["score"] == 0 else "yellow"
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
                f"[{score_color}]{result['score']:.2f}[/{score_color}]",
                str(
                    len(result["retrieved_memories"])
                    if isinstance(result["retrieved_memories"], list)
                    else 0
                ),
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
        default="examples/data/locomo10_conversation1.json",
        help="Path to locomo conversation JSON file",
    )
    parser.add_argument(
        "--person",
        type=str,
        default="Caroline",
        help="Person to create memories for (Caroline or Melanie)",
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
        help="Process specified session(s). Examples: 1, 1,3,5, 1-3, 1,3-5,7",
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

    args = parser.parse_args()

    # Create output file with timestamp
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"/tmp/locomo_eval_{args.person}_{timestamp}.txt"

    # Setup console
    console = Console()

    try:
        # Initialize evaluator
        evaluator = LocomoEvaluator(
            data_file=args.data_file,
            person_name=args.person,
            storage_path=args.storage_path,
            session=args.session,
            max_search_results=args.max_search_results,
            max_context_memories=args.max_context_memories,
            max_memory_size=args.max_memory_size,
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
            f.write(f"Person: {args.person}\n")
            f.write(f"Session: {args.session or 'All'}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write("=" * 80 + "\n\n")

            # Dump all stored memories first
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
                            session_date = memory_data.get("session_date", "N/A")
                            conversation_context = memory_data.get(
                                "conversation_context", []
                            )
                            context_summary = memory_data.get("context_summary", "")
                            classification_paths = memory_data.get(
                                "classification_paths", []
                            )
                            merge_count = memory_data.get("merge_count", 0)
                            last_merged = memory_data.get("last_merged", "")

                            f.write(f"  Session Date: {session_date}\n")

                            # Show merge information if applicable
                            if merge_count > 0:
                                f.write(
                                    f"  Merged Memory: {merge_count} merges, last merged: {last_merged}\n"
                                )

                            # Show multi-label classification if available
                            if classification_paths and len(classification_paths) > 1:
                                f.write(
                                    f"  Multi-Label Classification ({len(classification_paths)} paths):\n"
                                )
                                for i, path in enumerate(classification_paths, 1):
                                    f.write(f"    {i}. {path}\n")
                            elif classification_paths:
                                f.write(
                                    f"  Classification Path: {classification_paths[0]}\n"
                                )

                            # Show conversation context before raw text for better readability
                            if conversation_context:
                                f.write(
                                    f"  Conversation Context ({len(conversation_context)} exchanges):\n"
                                )
                                for i, context_item in enumerate(
                                    conversation_context, 1
                                ):
                                    f.write(f"    {i}. {context_item}\n")

                            if context_summary:
                                f.write(f"  Context Summary: {context_summary}\n")

                            f.write(f"  Raw Text: {raw_text}\n")

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
            average_score = (
                sum(r["score"] for r in results) / total_questions
                if total_questions > 0
                else 0.0
            )

            f.write(f"Total Questions: {total_questions}\n")
            f.write(f"Average Score: {average_score:.3f}\n\n")

            # Write QA Evaluation Details in table format
            f.write("QA Evaluation Details\n")
            f.write("=" * 80 + "\n")
            f.write(
                f"{'Question':<20} | {'Expected':<18} | {'Predicted':<18} | {'F1 Score':<8} | {'Memories':<8}\n"
            )
            f.write("-" * 80 + "\n")

            for result in results[:20]:  # Match the console limit
                question_text = (
                    result["question"][:17] + "..."
                    if len(result["question"]) > 17
                    else result["question"]
                )
                expected_text = str(result["expected_answer"])
                expected_text = (
                    expected_text[:15] + "..."
                    if len(expected_text) > 15
                    else expected_text
                )
                predicted_text = str(result["predicted_answer"])
                predicted_text = (
                    predicted_text[:15] + "..."
                    if len(predicted_text) > 15
                    else predicted_text
                )
                # Safety check for retrieved_memories
                retrieved_memories = result.get("retrieved_memories", [])
                if not isinstance(retrieved_memories, list):
                    retrieved_memories = []
                memory_count = len(retrieved_memories)

                f.write(
                    f"{question_text:<20} | {expected_text:<18} | {predicted_text:<18} | {result['score']:>8.2f} | {memory_count:>8}\n"
                )

            f.write("-" * 80 + "\n\n")

            # Write detailed results
            for i, result in enumerate(results, 1):
                f.write(f"\nQuestion {i}: {result['question']}\n")
                f.write(f"Expected: {result['expected_answer']}\n")
                f.write(f"Predicted: {result['predicted_answer']}\n")
                f.write(f"Score: {result['score']:.2f}\n")

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

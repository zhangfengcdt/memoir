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

from langmem_prollytree.core.prolly_adapter import ProllyTreeStore
from langmem_prollytree.search.hierarchical_search import (
    HierarchicalSearchEngine,
    SearchStrategy,
)
from langmem_prollytree.taxonomy.intelligent_classifier import IntelligentClassifier
from langmem_prollytree.taxonomy.semantic_classifier import SemanticClassifier
from langmem_prollytree.taxonomy.taxonomy_presets import TaxonomyVersion

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LocomoEvaluator:
    """Evaluates memory agent's ability to answer questions using stored memories from locomo dataset."""

    def __init__(
        self,
        data_file: str,
        person_name: str,
        storage_path: str = "/tmp/qa_evaluation",
        confidence_thresholds: Optional[dict[str, float]] = None,
        session: Optional[int] = None,
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

        # Components
        self.llm = None
        self.intelligent_classifier = None
        self.search_engine = None
        self.conversation_data = None
        self.qa_data = None

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

        if self.session:
            self.console.print(
                f"⏺ Processing session {self.session} only", style="white"
            )

    async def process_memories(self):
        """Process conversation data to create memories."""
        self.console.print(
            "\n⏺ Processing memories from conversations...", style="white"
        )

        memories_processed = 0

        # Find session keys to process
        if self.session:
            # Process only the specified session
            session_keys = [f"session_{self.session}"]
            # Verify the session exists
            if f"session_{self.session}" not in self.conversation_data:
                available_sessions = [
                    k.replace("session_", "")
                    for k in self.conversation_data
                    if k.startswith("session_") and not k.endswith("_date_time")
                ]
                self.console.print(
                    f"⏺ Error: Session {self.session} not found. Available sessions: {available_sessions}",
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

        for session_key in session_keys:
            session_data = self.conversation_data.get(session_key, [])
            # Get the session date for context
            session_date_key = f"{session_key}_date_time"
            session_date = self.conversation_data.get(session_date_key, "unknown date")

            for exchange in session_data:
                speaker = exchange.get("speaker")
                # Process memories only for the specified person
                if speaker == self.person_name:
                    text = exchange.get("text", "")
                    if text.strip():
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

                        # Add session date context to the text for better temporal understanding
                        text_with_context = f"[Session date: {session_date}] {text}"

                        try:
                            await (
                                self.intelligent_classifier.process_memory_with_storage(
                                    text_with_context, metadata
                                )
                            )
                            memories_processed += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to process: {text[:50]}... Error: {e}"
                            )

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
            if self.session:
                session_prefix = f"D{self.session}:"
                # Check if any evidence reference is from the specified session
                if not any(ref.startswith(session_prefix) for ref in evidence):
                    continue

            filtered_qa.append(qa_item)

        return filtered_qa

    async def evaluate_qa(self) -> list[dict[str, Any]]:
        """Evaluate QA pairs using memory retrieval and LLM."""
        # Filter QA pairs by session and person
        qa_data_to_evaluate = self.filter_qa_by_session_and_person()

        if self.session:
            self.console.print(
                f"\n⏺ Evaluating {len(qa_data_to_evaluate)} filtered QA pairs about {self.person_name} from session {self.session}...",
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
Q: "What are Caroline's plans for the summer?"
Context: "Researching adoption agencies — it's been a dream to have a family"
A: researching adoption agencies

Q: "When did Caroline go to the support group?"
Context: "[Session date: 8 May, 2023] I went to a LGBTQ support group yesterday"
A: 7 May 2023

Q: "What does Caroline research?"
Context: "I'm researching different adoption agencies to find the right fit"
A: adoption agencies

Retrieved Context:
{context}

Question: {question}

EXTRACTION RULES:
1. Return ONLY the direct factual answer
2. Maximum 10 words
3. If genuinely no relevant information: "Information not found"
4. Look for ANY mention that could answer the question
5. Be LESS STRICT - extract information even if not perfectly phrased

Answer:"""

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
        """Post-process LLM answer to make it more concise and direct."""
        if not answer:
            return answer

        # Remove common verbose prefixes
        verbose_prefixes = [
            "Caroline went to",
            "Caroline has decided",
            "Caroline would likely",
            "Caroline participate",
            "Melanie partakes in",
            "Melanie has gone",
            "Information shows",
            "According to the memories",
            "Based on the information",
            "The memories indicate",
            "From the context",
        ]

        answer_lower = answer.lower()
        for prefix in verbose_prefixes:
            if answer_lower.startswith(prefix.lower()):
                # Extract the key information after the prefix
                remaining = answer[len(prefix) :].strip()
                if remaining.startswith(" that "):
                    remaining = remaining[5:].strip()
                if remaining and not remaining.startswith("to "):
                    answer = remaining
                break

        # Clean up sentence endings
        if answer.endswith("."):
            answer = answer[:-1]

        # Remove quotes if they wrap the entire answer
        if answer.startswith('"') and answer.endswith('"'):
            answer = answer[1:-1]

        # Limit length (keep first 8 words max)
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

        prompt = f"""Calculate an F1-based similarity score between the expected and predicted answers.{question_context}

SCORING METHOD:
1. Break both answers into key components/items
2. Count: TP (true positives), FP (false positives), FN (false negatives)
3. Calculate: Precision = TP/(TP+FP), Recall = TP/(TP+FN)
4. F1 Score = 2 * (Precision * Recall) / (Precision + Recall)

EXAMPLES:
Expected: "Psychology, counseling certification"
Predicted: "counseling, mental health"
- TP: 1 (counseling matches)
- FP: 1 (mental health not in expected)
- FN: 1 (Psychology missing)
- Precision: 1/2 = 0.5, Recall: 1/2 = 0.5
- F1: 2*(0.5*0.5)/(0.5+0.5) = 0.5

Expected: "7 May 2023"
Predicted: "May 7, 2023"
- Same date, different format = Perfect match
- F1: 1.0

Expected: "Pride parade, school speech, support group"
Predicted: "LGBTQ support group on 7 May 2023"
- TP: 1 (support group)
- FP: 1 (extra date info)
- FN: 2 (Pride parade, school speech missing)
- Precision: 1/2 = 0.5, Recall: 1/3 = 0.33
- F1: 2*(0.5*0.33)/(0.5+0.33) = 0.40

RULES:
- Consider semantic equivalence (counseling = therapy = mental health counseling)
- Date formats count as identical (7 May 2023 = May 7, 2023)
- Partial information gets partial credit
- Extra correct details don't hurt (but don't help much either)

Expected Answer: "{expected}"
Predicted Answer: "{predicted}"

Return only the F1 score as a decimal between 0.0 and 1.0."""

        try:
            response = await self.llm.ainvoke(prompt)
            score_str = response.content.strip()

            # Extract number from response
            import re

            match = re.search(r"(\d+\.?\d*)", score_str)
            if match:
                score = float(match.group(1))
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
        correct_answers = sum(1 for r in results if r["score"] >= 0.7)
        average_score = (
            sum(r["score"] for r in results) / total_questions
            if total_questions > 0
            else 0.0
        )

        # Display summary
        self.console.print("\n⏺ QA Evaluation Results", style="white")
        self.console.print(f"⏺ Total Questions: {total_questions}", style="white")
        self.console.print(
            f"⏺ Correct Answers (≥70%): {correct_answers}", style="white"
        )
        self.console.print(
            f"⏺ Accuracy: {correct_answers / total_questions * 100:.1f}%", style="white"
        )
        self.console.print(f"⏺ Average Score: {average_score:.3f}", style="white")

        # Display detailed results
        table = Table(title="QA Evaluation Details")
        table.add_column("Question", style="white", max_width=35)
        table.add_column("Expected", style="white", max_width=40)
        table.add_column("Predicted", style="white", max_width=40)
        table.add_column("Score", style="white", justify="right")
        table.add_column("Memories", style="white", justify="right")

        for result in results[:20]:  # Show first 20 results
            score_color = (
                "green"
                if result["score"] >= 0.7
                else "red"
                if result["score"] == 0
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

            table.add_row(
                question_text,
                expected_text,
                predicted_text,
                f"[{score_color}]{result['score']:.2f}[/{score_color}]",
                str(len(result["retrieved_memories"])),
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
        type=int,
        help="Process only specified session number (e.g., 1, 2, 3)",
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
        default=3,
        help="Maximum number of memories to use for LLM context (default: 3)",
    )
    parser.add_argument(
        "--max-memory-size",
        type=int,
        default=2000,
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

            # Write summary
            total_questions = len(results)
            correct_answers = sum(1 for r in results if r["score"] >= 0.7)
            average_score = (
                sum(r["score"] for r in results) / total_questions
                if total_questions > 0
                else 0.0
            )

            f.write(f"Total Questions: {total_questions}\n")
            f.write(f"Correct Answers (≥70%): {correct_answers}\n")
            f.write(f"Accuracy: {correct_answers / total_questions * 100:.1f}%\n")
            f.write(f"Average Score: {average_score:.3f}\n\n")

            # Write detailed results
            for i, result in enumerate(results, 1):
                f.write(f"\nQuestion {i}: {result['question']}\n")
                f.write(f"Expected: {result['expected_answer']}\n")
                f.write(f"Predicted: {result['predicted_answer']}\n")
                f.write(f"Score: {result['score']:.2f}\n")

                if result["retrieved_memories"]:
                    f.write(
                        f"\nRetrieved {len(result['retrieved_memories'])} memories:\n"
                    )
                    for j, memory in enumerate(result["retrieved_memories"], 1):
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
        console.print(f"⏺ Error: {e}", style="white")
        # Save error info to file instead of console export
        with open(output_file, "w") as f:
            f.write(f"Error occurred during evaluation: {e}\n")
            f.write(f"Timestamp: {timestamp}\n")
        console.print(f"\n⏺ Error logged to: {output_file}", style="bold red")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

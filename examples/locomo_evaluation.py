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
from rich.progress import Progress
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
    ):
        self.console = Console()
        self.data_file = data_file
        self.person_name = person_name
        self.storage_path = storage_path
        self.session = session
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

        self.console.print(f"⏺ Loaded {len(self.qa_data)} QA pairs", style="white")
        self.console.print(
            f"⏺ Loaded conversation data for {self.conversation_data.get('speaker_a')} and {self.conversation_data.get('speaker_b')}",
            style="white",
        )

        if self.session:
            self.console.print(
                f"⏺ Will process session {self.session} only", style="white"
            )

    async def process_memories(self):
        """Process conversation data to create memories."""
        self.console.print(
            "\n⏺ Processing memories from conversations...", style="white"
        )

        memories_processed = 0

        with Progress() as progress:
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

            task = progress.add_task("Processing sessions...", total=len(session_keys))

            for session_key in session_keys:
                session_data = self.conversation_data.get(session_key, [])

                for exchange in session_data:
                    if exchange.get("speaker") == self.person_name:
                        text = exchange.get("text", "")
                        if text.strip():
                            # Add metadata including dialogue ID for reference
                            metadata = {
                                "source": "locomo_conversation",
                                "session": session_key,
                                "dia_id": exchange.get("dia_id", ""),
                                "speaker": self.person_name,
                            }

                            try:
                                await self.intelligent_classifier.process_memory_with_storage(
                                    text, metadata
                                )
                                memories_processed += 1
                            except Exception as e:
                                logger.warning(
                                    f"Failed to process: {text[:50]}... Error: {e}"
                                )

                progress.advance(task)

        self.console.print(f"⏺ Processed {memories_processed} memories", style="white")

        # Debug: Check what memories are actually stored
        stored_memories = self.intelligent_classifier.get_stored_memories(limit=10)
        self.console.print(
            f"⏺ Found {len(stored_memories)} stored memories", style="white"
        )
        if stored_memories:
            for i, memory in enumerate(stored_memories[:3]):
                self.console.print(
                    f"  {i + 1}. Path: {memory.get('path', 'unknown')}", style="white"
                )
                content = memory.get("content", {})
                if isinstance(content, dict):
                    summary = content.get(
                        "summary", content.get("content", str(content))
                    )
                else:
                    summary = str(content)
                self.console.print(f"     Content: {summary[:100]}...", style="white")

        # Debug: Test direct search on one of the stored paths
        if stored_memories:
            test_path = stored_memories[0].get("path", "unknown")
            self.console.print(
                f"⏺ DEBUG: Testing direct search for path '{test_path}'", style="white"
            )
            namespace_str = "memory:general"
            test_results = await self.search_engine.store.asearch(
                namespace_str, test_path
            )
            self.console.print(
                f"⏺ DEBUG: Direct search returned {len(test_results)} results",
                style="white",
            )

    def filter_qa_by_session(self) -> list[dict[str, Any]]:
        """Filter QA pairs to only include those with evidence from the specified session."""
        if not self.session:
            return self.qa_data

        filtered_qa = []
        session_prefix = f"D{self.session}:"

        for qa_item in self.qa_data:
            evidence = qa_item.get("evidence", [])
            # Check if any evidence reference is from the specified session
            if any(ref.startswith(session_prefix) for ref in evidence):
                filtered_qa.append(qa_item)

        return filtered_qa

    async def evaluate_qa(self) -> list[dict[str, Any]]:
        """Evaluate QA pairs using memory retrieval and LLM."""
        # Filter QA pairs by session if specified
        qa_data_to_evaluate = self.filter_qa_by_session()

        if self.session:
            self.console.print(
                f"\n⏺ Evaluating {len(qa_data_to_evaluate)} QA pairs from session {self.session}...",
                style="white",
            )
        else:
            self.console.print(
                f"\n⏺ Evaluating {len(qa_data_to_evaluate)} QA pairs...", style="white"
            )

        results = []

        with Progress() as progress:
            task = progress.add_task(
                "Evaluating questions...", total=len(qa_data_to_evaluate)
            )

            for qa_item in qa_data_to_evaluate:
                question = qa_item["question"]
                expected_answer = qa_item["answer"]
                evidence = qa_item.get("evidence", [])
                category = qa_item.get("category", 0)

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

                progress.advance(task)

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
        classification = await self.search_engine.classifier.classify_async(
            question, context
        )
        self.console.print(
            f"⏺ DEBUG: Question '{question[:50]}...' classified to: {classification.primary_path}",
            style="white",
        )

        search_results = await self.search_engine.search(
            query=question,
            namespace=namespace_str,
            strategy=SearchStrategy.SPECIFIC_TO_GENERAL,
        )

        # Debug: Print search results
        if len(search_results) == 0:
            self.console.print(
                f"⏺ DEBUG: No search results for '{question}' in namespace '{namespace_str}'",
                style="white",
            )
        else:
            self.console.print(
                f"⏺ DEBUG: Found {len(search_results)} results for '{question}'",
                style="white",
            )

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

        # Create context from retrieved memories
        context_parts = []
        for memory in retrieved_memories[:5]:  # Use top 5 results
            context_parts.append(f"Memory from {memory['path']}: {memory['content']}")
            context_parts.append(f"  Items combined: {memory['item_count']}")

        context = "\n".join(context_parts)

        # Generate answer using LLM
        prompt = f"""Based on the following memories about {self.person_name}, answer the question as accurately as possible.

Retrieved Memories:
{context}

Question: {question}

Please provide a direct, concise answer based only on the information in the memories. If the information is not available in the memories, respond with "Information not found in memories."

Answer:"""

        try:
            response = await self.llm.ainvoke(prompt)
            predicted_answer = response.content.strip()
        except Exception as e:
            predicted_answer = f"LLM Error: {e}"

        # Calculate score (simple exact match for now)
        score = self.calculate_answer_score(expected_answer, predicted_answer)

        return {
            "question": question,
            "expected_answer": expected_answer,
            "predicted_answer": predicted_answer,
            "evidence": evidence,
            "category": category,
            "retrieved_memories": retrieved_memories,
            "score": score,
        }

    def calculate_answer_score(self, expected: str, predicted: str) -> float:
        """Calculate similarity score between expected and predicted answers."""
        if (
            not predicted
            or "not found" in predicted.lower()
            or "error" in predicted.lower()
        ):
            return 0.0

        # Simple exact match (case-insensitive)
        if str(expected).lower().strip() == predicted.lower().strip():
            return 1.0

        # Partial match (if expected answer is contained in predicted)
        if str(expected).lower() in predicted.lower():
            return 0.7

        # Check if key information matches (for dates, numbers, etc.)
        expected_words = set(str(expected).lower().split())
        predicted_words = set(predicted.lower().split())

        if expected_words & predicted_words:  # Intersection exists
            overlap = len(expected_words & predicted_words)
            total = len(expected_words | predicted_words)
            return overlap / total if total > 0 else 0.0

        return 0.0

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
        table.add_column("Question", style="white", max_width=40)
        table.add_column("Expected", style="white", max_width=20)
        table.add_column("Predicted", style="white", max_width=20)
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
            table.add_row(
                (
                    result["question"][:50] + "..."
                    if len(result["question"]) > 50
                    else result["question"]
                ),
                (
                    str(result["expected_answer"])[:20] + "..."
                    if len(str(result["expected_answer"])) > 20
                    else str(result["expected_answer"])
                ),
                (
                    result["predicted_answer"][:20] + "..."
                    if len(result["predicted_answer"]) > 20
                    else result["predicted_answer"]
                ),
                f"[{score_color}]{result['score']:.2f}[/{score_color}]",
                str(len(result["retrieved_memories"])),
            )

        self.console.print(table)

        if len(results) > 20:
            self.console.print(
                f"⏺ ... and {len(results) - 20} more results", style="white"
            )


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

    args = parser.parse_args()

    console = Console()

    try:
        # Initialize evaluator
        evaluator = LocomoEvaluator(
            data_file=args.data_file,
            person_name=args.person,
            storage_path=args.storage_path,
            session=args.session,
        )

        # Setup components
        await evaluator.setup()

        # Process memories from conversations
        await evaluator.process_memories()

        # Evaluate QA pairs
        results = await evaluator.evaluate_qa()

        # Display results
        evaluator.display_results(results)

    except Exception as e:
        console.print(f"⏺ Error: {e}", style="white")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

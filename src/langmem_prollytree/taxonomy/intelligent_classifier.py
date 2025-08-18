"""
Intelligent Classifier with LLM-based classification and dynamic expansion.
Handles memory-worthiness detection, confidence-based expansion, and classification decisions.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from .iterative_taxonomy import (
    LLMExpansionStrategy,
    LLMIterativeTaxonomy,
)
from .semantic_taxonomy import get_taxonomy
from .taxonomy_presets import TaxonomyVersion

logger = logging.getLogger(__name__)


class ClassificationAction(Enum):
    """Action to take with classification."""

    SKIP = "skip"  # Not memory-worthy
    CLASSIFY = "classify"  # Classify to existing path
    EXPAND = "expand"  # Expand taxonomy for better classification
    USE_PARENT = "use_parent"  # Use more generic parent category


class MemoryAction(Enum):
    """Action to take with memory storage."""

    SKIP = "skip"  # Not stored
    STORE = "store"  # Store as new memory
    REPLACE = "replace"  # Replace existing memory
    APPEND = "append"  # Append to existing memory
    MERGE = "merge"  # Merge with existing memory


class ClassificationConfidence(Enum):
    """Confidence levels for classification."""

    HIGH = "high"  # > 0.8
    MEDIUM = "medium"  # 0.6 - 0.8
    LOW = "low"  # < 0.6


@dataclass
class ClassificationResult:
    """Result of LLM classification."""

    is_memory: bool
    path: Optional[str]
    confidence: float
    confidence_level: ClassificationConfidence
    reasoning: str
    suggested_action: ClassificationAction
    suggested_expansion: Optional[str] = None  # For low confidence
    use_parent: bool = False  # For low confidence


@dataclass
class MemoryProcessingResult:
    """Result of complete memory processing including storage."""

    classification: ClassificationResult
    memory_action: MemoryAction
    memory_path: Optional[str] = None
    previous_content: Optional[str] = None
    new_content: Optional[str] = None
    expanded_paths: list[str] = None
    success: bool = True
    storage_reasoning: str = ""


class IntelligentClassifier:
    """
    Intelligent classifier with LLM-based classification and dynamic taxonomy expansion.
    Handles memory-worthiness detection, confidence-based expansion decisions.
    """

    def __init__(
        self,
        llm: Any,
        memory_store: Optional[Any] = None,
        taxonomy_version: TaxonomyVersion = TaxonomyVersion.GENERAL,
        confidence_thresholds: Optional[dict] = None,
        expansion_strategy: LLMExpansionStrategy = LLMExpansionStrategy.FOCUSED_SUBTREE,
        min_items_for_expansion: int = 3,
    ):
        """
        Initialize the intelligent classifier.

        Args:
            llm: Language model for classification and decisions
            memory_store: Optional memory store for actual storage operations
            taxonomy_version: Taxonomy preset to use
            confidence_thresholds: Custom confidence thresholds
            expansion_strategy: Strategy for taxonomy expansion
            min_items_for_expansion: Minimum items before expansion
        """
        self.llm = llm
        self.memory_store = memory_store
        self.taxonomy_version = taxonomy_version

        # Initialize with full semantic taxonomy instead of limited iterative taxonomy
        # This gives us access to all 1000+ predefined paths including machine learning
        self.taxonomy = get_taxonomy()

        # Also keep iterative taxonomy for expansion capabilities if needed
        self.iterative_taxonomy = LLMIterativeTaxonomy(
            taxonomy_version=taxonomy_version,
            llm=llm,
            expansion_strategy=expansion_strategy,
            min_items_threshold=min_items_for_expansion,
        )

        # Confidence thresholds
        self.thresholds = confidence_thresholds or {
            "high": 0.8,
            "medium": 0.6,
            "low": 0.0,
        }

        # Track pending expansions
        self.pending_expansions = {}

    def _get_confidence_level(self, confidence: float) -> ClassificationConfidence:
        """Determine confidence level from score."""
        if confidence >= self.thresholds["high"]:
            return ClassificationConfidence.HIGH
        elif confidence >= self.thresholds["medium"]:
            return ClassificationConfidence.MEDIUM
        else:
            return ClassificationConfidence.LOW

    async def classify_input(
        self, content: str, metadata: Optional[dict] = None
    ) -> ClassificationResult:
        """
        Classify input using LLM to determine if it's memory-worthy and where to store it.

        Args:
            content: The content to classify
            metadata: Optional metadata about the content

        Returns:
            ClassificationResult with classification details
        """
        # Get current taxonomy paths
        all_paths = self.taxonomy.get_all_paths()

        # Build classification prompt
        prompt = self._build_classification_prompt(content, all_paths, metadata)

        try:
            # Call LLM for classification
            response = await self.llm.ainvoke(prompt)

            # Parse response
            result = self._parse_classification_response(response)

            # Add confidence level
            result.confidence_level = self._get_confidence_level(result.confidence)

            return result

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            # Return skip action on error
            return ClassificationResult(
                is_memory=False,
                path=None,
                confidence=0.0,
                confidence_level=ClassificationConfidence.LOW,
                reasoning=f"Classification failed: {e!s}",
                suggested_action=ClassificationAction.SKIP,
            )

    def _build_classification_prompt(
        self, content: str, paths: list[str], metadata: Optional[dict]
    ) -> str:
        """Build prompt for LLM classification."""
        # Get first-level categories for context
        first_level = [p for p in paths if "." not in p and p != "other"]

        prompt_parts = [
            "You are a memory classification system. Analyze the following input and determine:",
            "1. Is this information worth storing as a memory?",
            "   - Skip transient information (greetings, current time, weather forecasts)",
            "   - Skip very general conversations without specific personal details",
            "   - Store personal preferences, facts, skills, relationships, goals, experiences",
            "",
            "2. If yes, which taxonomy path best fits this content?",
            "3. What is your confidence in this classification (0.0 to 1.0)?",
            "   - High confidence (0.8+): Content clearly fits an existing category",
            "   - Medium confidence (0.5-0.8): Content fits reasonably well",
            "   - Low confidence (<0.5): Content is too specific/detailed for existing categories",
            "",
            f"Content to analyze: {content}",
        ]

        if metadata:
            prompt_parts.append(f"Metadata: {json.dumps(metadata)}")

        prompt_parts.extend(
            [
                "",
                "Available top-level categories:",
            ]
        )

        for category in sorted(first_level):
            prompt_parts.append(f"  - {category}")

        # Show ALL available paths to LLM for complete taxonomy coverage
        # NOTE: This approach works for current taxonomy size (~1000 paths)
        # Future scaling: May need chunking/filtering if taxonomy grows to 5K+ paths or hits LLM context limits
        all_non_other_paths = [p for p in paths if not p.endswith(".other")]
        if all_non_other_paths:
            prompt_parts.extend(
                [
                    "",
                    f"Complete taxonomy hierarchy ({len(all_non_other_paths)} available paths):",
                    "",
                ]
            )

            # Show ALL paths - no sampling to avoid missing critical paths like routine.morning or tools.ides
            for path in sorted(all_non_other_paths):
                prompt_parts.append(f"  {path}")

        prompt_parts.extend(
            [
                "",
                "Classification guidelines:",
                "- ONLY suggest COMPLETE paths that exist EXACTLY in the full taxonomy above",
                "- Use the full hierarchical path (e.g., preferences.personal.lifestyle.routine.morning)",
                "- If content doesn't fit existing paths well, use low confidence (< 0.6)",
                "- Use appropriate hierarchical depth (2-4 levels recommended)",
                "- Follow natural conceptual progression: general → specific",
                "- Avoid skipping intermediate conceptual levels",
                "- Consider existing similar paths for consistency",
                "",
                "Respond in JSON format:",
                "{",
                '  "is_memory": true/false,',
                '  "path": "suggested.path.here" or null,',
                '  "confidence": 0.0-1.0,',
                '  "reasoning": "explanation of decision and path choice"',
                "}",
            ]
        )

        return "\n".join(prompt_parts)

    def _parse_classification_response(self, response: Any) -> ClassificationResult:
        """Parse LLM classification response."""
        try:
            # Handle different response types
            if hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            # Try to parse as JSON
            # Extract JSON from response if wrapped in other text
            import re

            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                data = json.loads(json_str)

                # Debug logging to see what we're getting
                logger.info(f"Parsed LLM response: {data}")
            else:
                # Fallback parsing - log the content that failed to parse
                logger.warning(
                    f"Failed to parse JSON from LLM response: {content[:200]}..."
                )
                data = {
                    "is_memory": False,
                    "path": None,
                    "confidence": 0.0,
                    "reasoning": "Failed to parse response",
                }

            # Validate that the suggested path actually exists in taxonomy
            suggested_path = data.get("path")
            all_paths = self.taxonomy.get_all_paths()

            if suggested_path and suggested_path not in all_paths:
                logger.warning(
                    f"LLM suggested invalid path '{suggested_path}'. "
                    f"Available paths that contain relevant keywords: "
                    f"{[p for p in all_paths if any(word in p for word in suggested_path.split('.') if word != 'other')][:5]}"
                )
                # Try to find a close match or fall back to a more general path
                path_parts = suggested_path.split(".")
                for i in range(len(path_parts), 0, -1):
                    partial_path = ".".join(path_parts[:i])
                    if partial_path in all_paths:
                        logger.info(f"Using valid parent path: {partial_path}")
                        suggested_path = partial_path
                        break
                else:
                    # Fall back to top-level category if no valid path found
                    if path_parts and path_parts[0] in all_paths:
                        suggested_path = path_parts[0]
                        logger.info(
                            f"Falling back to top-level category: {suggested_path}"
                        )
                    else:
                        suggested_path = "other"
                        logger.info("Falling back to 'other' category")

            return ClassificationResult(
                is_memory=data.get("is_memory", False),
                path=suggested_path,
                confidence=float(data.get("confidence", 0.0)),
                confidence_level=ClassificationConfidence.LOW,  # Will be set later
                reasoning=data.get("reasoning", ""),
                suggested_action=(
                    ClassificationAction.CLASSIFY
                    if data.get("is_memory")
                    else ClassificationAction.SKIP
                ),
            )

        except Exception as e:
            logger.error(f"Failed to parse classification response: {e}")
            return ClassificationResult(
                is_memory=False,
                path=None,
                confidence=0.0,
                confidence_level=ClassificationConfidence.LOW,
                reasoning=f"Parse error: {e!s}",
                suggested_action=ClassificationAction.SKIP,
            )

    async def handle_low_confidence_classification(
        self,
        content: str,
        classification: ClassificationResult,
        metadata: Optional[dict] = None,
    ) -> ClassificationResult:
        """
        Handle low confidence classification by asking LLM to expand or use parent.

        Args:
            content: Original content
            classification: Initial classification result
            metadata: Optional metadata

        Returns:
            Updated classification result with expansion decision
        """
        if not classification.path:
            return classification

        # Build prompt for expansion decision
        prompt = self._build_expansion_decision_prompt(
            content, classification.path, classification.confidence, metadata
        )

        try:
            response = await self.llm.ainvoke(prompt)
            decision = self._parse_expansion_decision(response)

            if decision["action"] == "expand":
                # Trigger expansion for more specific categorization
                classification.suggested_expansion = decision.get("suggested_path")

                # Add to pending expansions
                parent_path = classification.path
                if parent_path not in self.pending_expansions:
                    self.pending_expansions[parent_path] = []
                self.pending_expansions[parent_path].append(
                    {
                        "content": content,
                        "metadata": metadata,
                        "suggested_expansion": decision.get("suggested_categories", []),
                    }
                )

                # If we have enough items, trigger expansion
                if (
                    len(self.pending_expansions[parent_path])
                    >= self.taxonomy.min_items_threshold
                ):
                    await self._trigger_expansion(parent_path)

            elif decision["action"] == "use_parent":
                # Use more generic category
                classification.use_parent = True
                parts = classification.path.split(".")
                if len(parts) > 1:
                    classification.path = ".".join(parts[:-1])
                    classification.confidence = decision.get("parent_confidence", 0.7)

            classification.reasoning += (
                f" | Expansion decision: {decision.get('reasoning', '')}"
            )

        except Exception as e:
            logger.error(f"Expansion decision failed: {e}")

        return classification

    def _build_expansion_decision_prompt(
        self, content: str, path: str, confidence: float, metadata: Optional[dict]
    ) -> str:
        """Build prompt for expansion decision."""
        prompt_parts = [
            f"The following content was classified to '{path}' with low confidence ({confidence:.2f}):",
            f"Content: {content}",
        ]

        if metadata:
            prompt_parts.append(f"Metadata: {json.dumps(metadata)}")

        prompt_parts.extend(
            [
                "",
                "Should we:",
                "1. EXPAND to more specific subcategories (if content is very detailed/specialized)",
                "   - Use when content has specific technical details, rare skills, or unique activities",
                "   - IMPORTANT: Follow proper hierarchical depth progression:",
                "     * Add ONE intermediate level at a time (don't jump from 'knowledge' to 'knowledge.quantum.entanglement.protocols')",
                "     * Use general-to-specific progression: domain → area → specialty → technique",
                "     * Examples: 'knowledge.music' → 'knowledge.music.piano' → 'knowledge.music.piano.improvisation'",
                "   - Suggest 2-3 subcategory names that follow natural conceptual hierarchies",
                "",
                "2. USE_PARENT category (if content is too vague/general for current specificity)",
                "   - Use when content is general/broad and current path is too specific",
                "   - Move up one level in the taxonomy hierarchy for better fit",
                "",
                "3. KEEP current classification (if confidence is acceptable as-is)",
                "",
                f"Current path depth: {len(path.split('.')) if path else 0} levels",
                "Recommended max depth: 4 levels for most concepts",
                "",
                "Respond in JSON format:",
                "{",
                '  "action": "expand" | "use_parent" | "keep",',
                '  "reasoning": "explanation with depth justification",',
                '  "suggested_categories": ["intermediate_category", "specific_category"] (if expanding),',
                '  "parent_confidence": 0.0-1.0 (if using parent)',
                "}",
            ]
        )

        return "\n".join(prompt_parts)

    def _parse_expansion_decision(self, response: Any) -> dict:
        """Parse expansion decision response."""
        try:
            if hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            import re

            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())

        except Exception as e:
            logger.error(f"Failed to parse expansion decision: {e}")

        return {"action": "keep", "reasoning": "Parse error, keeping original"}

    async def _trigger_expansion(self, parent_path: str):
        """Trigger taxonomy expansion for a path."""
        try:
            # Use the iterative taxonomy's expansion
            result = await self.taxonomy.expand_subtree_with_llm(parent_path)

            if result.new_paths:
                logger.info(
                    f"Expanded {parent_path} with {len(result.new_paths)} new categories"
                )

                # Reclassify pending items
                if parent_path in self.pending_expansions:
                    for item in self.pending_expansions[parent_path]:
                        # Re-classify with new categories
                        await self.process_classification(
                            item["content"], item["metadata"]
                        )

                    # Clear pending items
                    del self.pending_expansions[parent_path]

        except Exception as e:
            logger.error(f"Expansion failed for {parent_path}: {e}")

    async def process_classification(
        self, content: str, metadata: Optional[dict] = None
    ) -> ClassificationResult:
        """
        Main entry point for processing classification.

        Args:
            content: Content to classify
            metadata: Optional metadata

        Returns:
            ClassificationResult with classification details and recommended action
        """
        # Step 1: Classify the input
        classification = await self.classify_input(content, metadata)

        # Step 2: Check if it's memory-worthy
        if not classification.is_memory:
            return classification

        # Step 2.5: Validate suggested path exists in taxonomy
        if (
            classification.path
            and classification.path not in self.taxonomy.get_all_paths()
        ):
            # Path doesn't exist - mark for expansion but preserve original confidence
            # Only lower confidence if it was already very high (likely overconfident)
            if classification.confidence > 0.8:
                classification.confidence = min(classification.confidence, 0.75)
            classification.confidence_level = self._get_confidence_level(
                classification.confidence
            )
            classification.reasoning += (
                f" | Suggested path '{classification.path}' doesn't exist in taxonomy"
            )

        # Step 3: Handle based on confidence level
        if classification.confidence_level == ClassificationConfidence.LOW:
            # Handle low confidence with expansion decision
            classification = await self.handle_low_confidence_classification(
                content, classification, metadata
            )

            # Update suggested action based on expansion decision
            if classification.suggested_expansion:
                classification.suggested_action = ClassificationAction.EXPAND
            elif classification.use_parent:
                classification.suggested_action = ClassificationAction.USE_PARENT
            else:
                # For invalid paths or genuinely low confidence, suggest expansion if we have a path
                if (
                    classification.path
                    and classification.path not in self.taxonomy.get_all_paths()
                ):
                    classification.suggested_action = ClassificationAction.EXPAND
                    classification.reasoning += (
                        " | Invalid path suggests need for expansion"
                    )
                elif classification.confidence < self.thresholds["medium"]:
                    classification.suggested_action = ClassificationAction.SKIP
                    classification.reasoning += (
                        " | Confidence too low after expansion handling"
                    )

        # Step 4: Analyze and potentially improve hierarchical structure
        if classification.path and classification.is_memory:
            # Analyze hierarchical consistency
            analysis = self._analyze_hierarchical_consistency(classification.path)

            # Suggest better path if needed
            if analysis["suggested_improvements"]:
                improved_path = self._suggest_hierarchical_path(
                    content, classification.path
                )
                if improved_path != classification.path:
                    logger.info(
                        f"Suggested path improvement: {classification.path} → {improved_path}"
                    )
                    classification.path = improved_path
                    classification.reasoning += (
                        f" | Path improved for better hierarchy: {improved_path}"
                    )

            # Note: We skip iterative taxonomy tracking since we're using the full semantic taxonomy
            # The track_classification method runs domain consistency validation that may not match
            # our full taxonomy paths, causing spurious warnings

        return classification

    async def process_memory_with_storage(
        self, content: str, metadata: Optional[dict] = None
    ) -> MemoryProcessingResult:
        """
        Complete memory processing including classification and storage.

        Args:
            content: Content to process
            metadata: Optional metadata

        Returns:
            MemoryProcessingResult with classification and storage details
        """
        # Step 1: Classify the content
        classification = await self.process_classification(content, metadata)

        # Initialize result
        result = MemoryProcessingResult(
            classification=classification,
            memory_action=MemoryAction.SKIP,
            expanded_paths=[],
        )

        # Step 2: Handle based on classification
        if not classification.is_memory:
            result.storage_reasoning = "Content not memory-worthy"
            return result

        if not classification.path:
            result.storage_reasoning = "No classification path provided"
            return result

        if not self.memory_store:
            result.storage_reasoning = "No memory store available"
            result.success = False
            return result

        # Step 3: Handle memory storage
        namespace = ("memory", self.taxonomy_version.value)

        try:
            # Check for existing content
            existing = self.memory_store.get(namespace, classification.path)

            if existing is None:
                # Store new memory
                self.memory_store.put(
                    namespace,
                    classification.path,
                    {"content": content, "metadata": metadata or {}},
                )
                result.memory_action = MemoryAction.STORE
                result.memory_path = classification.path
                result.new_content = content
                result.storage_reasoning = "Stored new memory"

            else:
                # Handle existing memory
                update_result = await self._handle_memory_update(
                    content, existing, classification.path, namespace, metadata
                )
                result.memory_action = update_result["action"]
                result.memory_path = classification.path
                result.previous_content = existing.get("content", "")
                result.new_content = update_result.get("new_content")
                result.storage_reasoning = update_result["reasoning"]

        except Exception as e:
            result.success = False
            result.storage_reasoning = f"Storage failed: {e}"

        return result

    async def _handle_memory_update(
        self,
        new_content: str,
        existing_data: dict,
        path: str,
        namespace: tuple,
        metadata: Optional[dict],
    ) -> dict:
        """Handle updating existing memory content."""
        existing_content = existing_data.get("content", "")

        # Ask LLM how to handle the update
        prompt = [
            f"Memory path: {path}",
            "",
            f"Existing content: {existing_content}",
            "",
            f"New content: {new_content}",
        ]

        if metadata:
            prompt.append(f"New metadata: {json.dumps(metadata)}")

        prompt.extend(
            [
                "",
                "How should we update this memory?",
                "Options:",
                "- replace: Replace old content with new",
                "- append: Add new content to existing",
                "- merge: Intelligently combine both",
                "- skip: Keep existing, ignore new",
                "",
                "Respond in JSON:",
                "{",
                '  "action": "replace" | "append" | "merge" | "skip",',
                '  "reasoning": "explanation",',
                '  "merged_content": "..." (if merge)',
                "}",
            ]
        )

        try:
            response = await self.llm.ainvoke("\n".join(prompt))

            if hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            import re

            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                decision = json.loads(json_match.group())
            else:
                decision = {
                    "action": "append",
                    "reasoning": "Parse error, defaulting to append",
                }

            action = decision.get("action", "append")
            reasoning = decision.get("reasoning", "")

            if action == "replace":
                self.memory_store.put(
                    namespace,
                    path,
                    {"content": new_content, "metadata": metadata or {}},
                )
                return {
                    "action": MemoryAction.REPLACE,
                    "reasoning": reasoning,
                    "new_content": new_content,
                }

            elif action == "append":
                combined = f"{existing_content}\n\n{new_content}"
                combined_metadata = {
                    **existing_data.get("metadata", {}),
                    **(metadata or {}),
                }

                self.memory_store.put(
                    namespace,
                    path,
                    {"content": combined, "metadata": combined_metadata},
                )
                return {
                    "action": MemoryAction.APPEND,
                    "reasoning": reasoning,
                    "new_content": combined,
                }

            elif action == "merge":
                merged_content = decision.get(
                    "merged_content", f"{existing_content}\n{new_content}"
                )
                combined_metadata = {
                    **existing_data.get("metadata", {}),
                    **(metadata or {}),
                }

                self.memory_store.put(
                    namespace,
                    path,
                    {"content": merged_content, "metadata": combined_metadata},
                )
                return {
                    "action": MemoryAction.MERGE,
                    "reasoning": reasoning,
                    "new_content": merged_content,
                }

            else:  # skip
                return {
                    "action": MemoryAction.SKIP,
                    "reasoning": reasoning,
                    "new_content": existing_content,
                }

        except Exception as e:
            # Fallback to append on error
            combined = f"{existing_content}\n\n{new_content}"
            combined_metadata = {
                **existing_data.get("metadata", {}),
                **(metadata or {}),
            }

            self.memory_store.put(
                namespace,
                path,
                {"content": combined, "metadata": combined_metadata},
            )
            return {
                "action": MemoryAction.APPEND,
                "reasoning": f"Error in LLM decision, defaulted to append: {e}",
                "new_content": combined,
            }

    def get_stored_memories(self, limit: int = 10) -> list[dict]:
        """Get stored memories from the memory store."""
        if not self.memory_store:
            return []

        namespace = ("memory", self.taxonomy_version.value)
        try:
            results = self.memory_store.search(namespace, filter={}, limit=limit)
            memories = []
            for result in results:
                # Handle tuple format: (namespace, key, value)
                if isinstance(result, tuple) and len(result) == 3:
                    _, key, value = result
                    memories.append(
                        {
                            "path": key,
                            "content": value,
                            "timestamp": (
                                value.get("timestamp")
                                if isinstance(value, dict)
                                else None
                            ),
                        }
                    )
                # Handle object with attributes
                elif hasattr(result, "key") and hasattr(result, "value"):
                    memories.append(
                        {
                            "path": result.key,
                            "content": result.value,
                            "timestamp": getattr(result, "timestamp", None),
                        }
                    )
            return memories
        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            return []

    async def get_classification_statistics(self) -> dict:
        """Get statistics about the classification system."""
        return {
            "taxonomy_info": self.taxonomy.get_taxonomy_info(),
            "expansion_stats": self.taxonomy.get_expansion_statistics(),
            "pending_expansions": {
                path: len(items) for path, items in self.pending_expansions.items()
            },
            "confidence_thresholds": self.thresholds,
        }

    def _analyze_hierarchical_consistency(self, new_path: str) -> dict:
        """Analyze hierarchical consistency and suggest improvements."""
        all_paths = self.taxonomy.get_all_paths()
        path_parts = new_path.split(".")

        analysis = {
            "depth": len(path_parts),
            "missing_intermediates": [],
            "similar_paths": [],
            "suggested_improvements": [],
        }

        # Check for missing intermediate levels
        for i in range(1, len(path_parts)):
            intermediate = ".".join(path_parts[: i + 1])
            if intermediate not in all_paths:
                analysis["missing_intermediates"].append(intermediate)

        # Find similar paths in the same domain
        domain = path_parts[0]
        similar = [p for p in all_paths if p.startswith(domain + ".") and p != new_path]
        analysis["similar_paths"] = similar[:5]  # Top 5 similar paths

        # Suggest improvements based on depth and consistency
        if len(path_parts) > 4:
            analysis["suggested_improvements"].append(
                f"Consider reducing depth from {len(path_parts)} to 3-4 levels"
            )

        if len(analysis["missing_intermediates"]) > 1:
            analysis["suggested_improvements"].append(
                f"Add intermediate levels: {', '.join(analysis['missing_intermediates'][:-1])}"
            )

        return analysis

    def _suggest_hierarchical_path(self, content: str, initial_path: str) -> str:
        """Suggest a better hierarchical path based on content and existing taxonomy structure."""
        path_parts = initial_path.split(".")
        content_lower = content.lower()
        content_words = set(content_lower.split())

        # Get all existing paths to learn hierarchy patterns
        all_paths = self.taxonomy.get_all_paths()

        # Analyze existing structure to find better hierarchical patterns
        if len(path_parts) >= 2:
            domain = path_parts[0]

            # Find similar content-based paths in the same domain
            domain_paths = [p for p in all_paths if p.startswith(f"{domain}.")]

            best_match = None
            best_score = 0

            for existing_path in domain_paths:
                existing_parts = existing_path.split(".")
                if len(existing_parts) >= 3:  # Has intermediate levels
                    # Score based on content word overlap
                    path_words = set()
                    for part in existing_parts:
                        path_words.update(part.replace("_", " ").split())

                    overlap = content_words.intersection(path_words)
                    if overlap:
                        score = len(overlap) / len(content_words.union(path_words))
                        if score > best_score and score > 0.2:  # Minimum threshold
                            best_match = existing_path
                            best_score = score

            # If we found a good match, suggest using its intermediate structure
            if best_match:
                match_parts = best_match.split(".")
                if len(match_parts) >= 3 and len(path_parts) == 2:
                    # Use the intermediate structure from the matching path
                    intermediate = match_parts[1]  # Use the area from matching path
                    final_part = path_parts[1]  # Keep our specific category
                    return f"{domain}.{intermediate}.{final_part}"
                elif len(match_parts) >= 3 and len(path_parts) > 3:
                    # Restructure to use the better intermediate from matching path
                    intermediate = match_parts[1]
                    remaining = ".".join(path_parts[2:])
                    return f"{domain}.{intermediate}.{remaining}"

        # No improvement found based on existing structure
        return initial_path

    def get_category_structure(self) -> dict:
        """Get the current category structure for passing to LLM context."""
        all_paths = self.taxonomy.get_all_paths()

        # Analyze current structure
        depth_analysis = {}
        for depth in range(1, 6):
            paths_at_depth = [p for p in all_paths if len(p.split(".")) == depth]
            depth_analysis[f"depth_{depth}"] = len(paths_at_depth)

        return {
            "version": self.taxonomy_version.value,
            "all_paths": all_paths,
            "first_level_categories": [
                p for p in all_paths if "." not in p and p != "other"
            ],
            "structure_snapshot": self.taxonomy.export_for_llm(),
            "depth_analysis": depth_analysis,
            "total_paths": len(all_paths),
        }

    async def evaluate_semantic_appropriateness(
        self, content: str, path: str, context_paths: Optional[list[str]] = None
    ) -> dict:
        """
        Use LLM to evaluate if content semantically belongs in the assigned path.

        Args:
            content: The memory content to evaluate
            path: The taxonomy path where content is stored
            context_paths: Other similar paths for comparison context

        Returns:
            Dict with appropriateness score, reasoning, and suggestions
        """
        # Build evaluation prompt
        prompt_parts = [
            "You are a taxonomy evaluation expert. Analyze whether the given content semantically belongs in the assigned taxonomy path.",
            "",
            f'Content: "{content}"',
            f"Assigned Path: {path}",
            "",
            "Path Components Analysis:",
        ]

        # Break down path components for LLM understanding
        path_parts = path.split(".")
        for i, part in enumerate(path_parts):
            level_name = ["Domain", "Area", "Category", "Subcategory", "Detail"][
                min(i, 4)
            ]
            prompt_parts.append(f"  {level_name}: {part.replace('_', ' ').title()}")

        # Add context of similar paths if available
        if context_paths:
            prompt_parts.extend(
                [
                    "",
                    "Similar paths in taxonomy for comparison:",
                ]
            )
            for similar_path in context_paths[:5]:
                prompt_parts.append(f"  - {similar_path}")

        prompt_parts.extend(
            [
                "",
                "Evaluate:",
                "1. Does the content conceptually belong in this taxonomy path?",
                "2. Is each level of the hierarchy appropriate for this content?",
                "3. Are there better alternative paths in the taxonomy?",
                "4. Is the path depth appropriate for the content's specificity?",
                "",
                "Consider:",
                "- Semantic meaning and conceptual relationships",
                "- Logical hierarchical progression",
                "- Domain appropriateness",
                "- Content specificity vs path granularity",
                "",
                "Respond in JSON format:",
                "{",
                '  "appropriate": true/false,',
                '  "confidence": 0.0-1.0,',
                '  "score": 0-100,',
                '  "reasoning": "detailed explanation of why this classification is good/bad",',
                '  "issues": ["list", "of", "specific", "problems"] or [],',
                '  "suggested_path": "better.path.if.needed" or null,',
                '  "path_quality": "excellent" | "good" | "acceptable" | "poor" | "completely_wrong"',
                "}",
            ]
        )

        try:
            response = await self.llm.ainvoke("\n".join(prompt_parts))

            # Parse LLM response
            if hasattr(response, "content"):
                response_content = response.content
            else:
                response_content = str(response)

            # Extract JSON from response
            import re

            json_match = re.search(r"\{[^{}]*\}", response_content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                # Fallback if JSON parsing fails
                result = {
                    "appropriate": True,
                    "confidence": 0.5,
                    "score": 50,
                    "reasoning": "Could not parse LLM response",
                    "issues": ["Parse error"],
                    "suggested_path": None,
                    "path_quality": "acceptable",
                }

            # Ensure required fields exist
            result.setdefault("appropriate", result.get("score", 50) >= 70)
            result.setdefault("confidence", 0.5)
            result.setdefault("score", 50)
            result.setdefault("reasoning", "No reasoning provided")
            result.setdefault("issues", [])
            result.setdefault("suggested_path", None)
            result.setdefault("path_quality", "acceptable")

            return result

        except Exception as e:
            logger.error(f"Semantic appropriateness evaluation failed: {e}")
            return {
                "appropriate": True,
                "confidence": 0.0,
                "score": 0,
                "reasoning": f"Evaluation failed: {e}",
                "issues": ["Evaluation error"],
                "suggested_path": None,
                "path_quality": "unknown",
            }

    async def batch_evaluate_semantic_appropriateness(
        self, memory_items: list[dict]
    ) -> list[dict]:
        """
        Evaluate semantic appropriateness for multiple memory items.

        Args:
            memory_items: List of dicts with 'path' and 'content' keys

        Returns:
            List of evaluation results
        """
        results = []

        # Group by domain for context
        domain_groups = {}
        for item in memory_items:
            domain = item["path"].split(".")[0]
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(item)

        # Evaluate each item with domain context
        for item in memory_items:
            domain = item["path"].split(".")[0]
            context_paths = [
                other_item["path"]
                for other_item in domain_groups.get(domain, [])
                if other_item["path"] != item["path"]
            ]

            evaluation = await self.evaluate_semantic_appropriateness(
                item["content"], item["path"], context_paths
            )

            evaluation["item"] = item
            results.append(evaluation)

        return results

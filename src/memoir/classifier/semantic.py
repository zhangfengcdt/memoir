"""
Semantic classifier for mapping memories to taxonomy paths.
Uses LLM-based classification with caching and optimization.
"""

import hashlib
import json
import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from memoir.taxonomy.semantic import TaxonomyCategory, get_taxonomy

from .base import AdvancedTaxonomyInterface, TaxonomyInterface

logger = logging.getLogger(__name__)

# Configuration constants
MAX_PROMPT_PATHS = 100  # Maximum paths to include in classification prompt
MAX_EXAMPLE_PATHS_PER_CATEGORY = 5  # Max example paths shown per category
DEFAULT_CACHE_SIZE = 10000  # Default classification cache size
DEFAULT_FALLBACK_PATH = "context.project.stack"  # Default fallback path


class ClassificationResult(BaseModel):
    """Result of semantic classification."""

    primary_path: str = Field(description="Primary taxonomy path for the memory")
    confidence: float = Field(description="Confidence score (0-1)")
    alternative_paths: list[str] = Field(description="Alternative relevant paths")
    reasoning: str = Field(description="Brief reasoning for classification")


class SemanticClassifier:
    """
    Classifies memories into semantic taxonomy paths.
    Optimized for low-latency classification with caching.
    """

    def __init__(
        self,
        llm: Optional[Any] = None,
        taxonomy: Optional[TaxonomyInterface] = None,
        cache_size: int = DEFAULT_CACHE_SIZE,
        use_examples: bool = True,
        fallback_path: Optional[str] = None,
    ):
        """
        Initialize the semantic classifier.

        Args:
            llm: Language model for classification (optional, will use default)
            taxonomy: Taxonomy instance implementing TaxonomyInterface
                     If None, uses default SemanticTaxonomy
            cache_size: Size of the classification cache
            use_examples: Whether to include examples in prompts
            fallback_path: Custom fallback path when classification fails
        """
        self.taxonomy = taxonomy if taxonomy is not None else get_taxonomy()
        self.llm = llm
        self.use_examples = use_examples
        self.fallback_path = fallback_path or self._determine_fallback_path()
        self._cache = {}
        self._setup_classification_prompt()

    def _determine_fallback_path(self) -> str:
        """Determine appropriate fallback path based on available taxonomy."""
        try:
            all_paths = self.taxonomy.get_all_paths()

            # First, try to find the exact default fallback path for backwards compatibility
            if DEFAULT_FALLBACK_PATH in all_paths:
                return DEFAULT_FALLBACK_PATH

            # Try to find a context-related path that's reasonably specific
            context_paths = [path for path in all_paths if path.startswith("context.")]
            if context_paths:
                # Prefer paths with depth similar to the default (4-5 levels)
                preferred_paths = [
                    p for p in context_paths if 4 <= len(p.split(".")) <= 5
                ]
                if preferred_paths:
                    preferred_paths.sort(key=len)
                    return preferred_paths[0]

                # Fallback to any context path (prefer longer ones for backwards compatibility)
                context_paths.sort(key=len, reverse=True)
                return context_paths[0]

            # Try to find any 'other' category
            other_paths = [path for path in all_paths if path.endswith(".other")]
            if other_paths:
                # Prefer shorter 'other' paths
                other_paths.sort(key=len)
                return other_paths[0]

            # Use the first available path as last resort
            if all_paths:
                return all_paths[0]

        except Exception:
            pass

        # Ultimate fallback to the default path
        return DEFAULT_FALLBACK_PATH

    def _get_taxonomy_structure_info(self) -> str:
        """Generate taxonomy structure information for the prompt.

        Includes ALL paths (excluding 'other' paths) to ensure the static section
        meets the minimum token requirement for prompt caching (2048 tokens for Haiku).
        """
        try:
            # All taxonomies should implement TaxonomyInterface
            all_paths = self.taxonomy.get_all_paths()

            if not all_paths:
                return "The taxonomy structure is available but paths could not be enumerated."

            # Filter out 'other' paths for cleaner output (they're implied)
            non_other_paths = [p for p in all_paths if not p.endswith(".other")]

            # Group paths by top-level category for better organization
            categories: dict[str, list[str]] = {}
            for path in non_other_paths:
                parts = path.split(".")
                if parts:
                    category = parts[0]
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(path)

            # Generate structured description with ALL paths for prompt caching
            structure_lines = [
                f"Complete taxonomy hierarchy ({len(non_other_paths)} available paths):",
                "",
            ]

            for category, paths in sorted(categories.items()):
                structure_lines.append(f"## {category.upper()}")
                for path in sorted(paths):
                    structure_lines.append(f"  - {path}")
                structure_lines.append("")

            # Add info about 'other' categories if this is an AdvancedTaxonomy
            if isinstance(self.taxonomy, AdvancedTaxonomyInterface):
                structure_lines.append(
                    "NOTE: Each category also has 'other' subcategories for unclassified content."
                )
                structure_lines.append(
                    "Use 'other' categories when content doesn't fit existing specific paths."
                )

            return "\n".join(structure_lines)

        except Exception as e:
            logger.warning(f"Could not generate taxonomy structure info: {e}")
            return "Taxonomy structure is available. Please classify using the most appropriate path."

    def _is_valid_path(self, path: str) -> bool:
        """Check if a path is valid in the current taxonomy."""
        try:
            # All taxonomies should implement TaxonomyInterface
            return self.taxonomy.is_valid_path(path)
        except Exception as e:
            logger.warning(f"Error validating path {path}: {e}")
            return False

    def _setup_classification_prompt(self):
        """Setup the classification prompt template.

        The prompt is structured with STATIC content FIRST (for prompt caching)
        and DYNAMIC content LAST. This allows LLM providers like Anthropic to
        cache the static prefix and reduce costs by up to 90%.
        """
        # Static content first, dynamic content last for optimal prompt caching
        self.classification_template = """[STATIC_SECTION_START]
You are a semantic memory classifier. Your task is to classify the given memory content into the most appropriate path(s) from the provided taxonomy.

AVAILABLE TAXONOMY STRUCTURE:
{taxonomy_structure}

{examples}

CLASSIFICATION GUIDELINES:
1. Match content to the MOST SPECIFIC appropriate path from the available taxonomy
2. Consider the semantic meaning and context of the content
3. AVOID generic paths like 'context.current' unless content is truly about the current conversation
4. Consider confidence level:
   - High confidence (0.8-1.0): Very specific and accurate path match
   - Medium confidence (0.5-0.7): Reasonable fit but could be broader
   - Low confidence (0.0-0.4): Content is unclear or doesn't fit well
5. When unsure, use the most specific relevant category available in the taxonomy
6. Use 'other' categories when content doesn't fit existing specific paths - this helps the system learn and expand

IMPORTANT:
- Only use paths that exist in the provided taxonomy
- Prefer accuracy over specificity
- Return a valid JSON response with the required fields
- 'Other' categories help the system learn and expand over time

Return your classification as pure JSON (no markdown, no code blocks, just JSON) with:
- primary_path: The best matching taxonomy path (can be an 'other' path)
- confidence: Confidence score from 0 to 1
- alternative_paths: List of other relevant paths (max 3)
- reasoning: Brief explanation of your choice (1-2 sentences)

Think step by step:
1. Can this be clearly categorized into existing paths?
2. If uncertain, what's the closest parent category?
3. Should this go to a specific path or an 'other' category?

CRITICAL: Return ONLY the JSON object, no explanations, no markdown formatting.
[STATIC_SECTION_END]

[DYNAMIC_SECTION_START]
{context_info}

{classification_hints}

MEMORY CONTENT TO CLASSIFY:
{memory_content}
[DYNAMIC_SECTION_END]"""

    def _get_classification_examples(self) -> str:
        """Get few-shot examples for classification."""
        if not self.use_examples:
            return ""

        # Generate dynamic examples based on available taxonomy paths
        examples = self._generate_dynamic_examples()

        examples_text = "EXAMPLES:\n"
        for ex in examples:
            examples_text += f"\nMemory: {ex['memory']}\n"
            examples_text += f"Classification: {ex['path']}\n"
            examples_text += f"Confidence: {ex['confidence']}\n"
            examples_text += f"Reasoning: {ex['reasoning']}\n"

        return examples_text

    def _generate_dynamic_examples(self) -> list[dict]:
        """Generate classification examples dynamically based on available taxonomy."""
        try:
            all_paths = self.taxonomy.get_all_paths()
            if not all_paths:
                return []

            # Select diverse paths for examples (avoid being too specific to any domain)
            example_templates = [
                {
                    "memory": "My name is {example_name} and I'm 28 years old",
                    "pattern": "profile.personal.identity",
                    "confidence": 0.95,
                    "reasoning": "Personal identity information - name and age",
                },
                {
                    "memory": "I work as a software engineer at Google",
                    "pattern": "profile.professional.current",
                    "confidence": 0.90,
                    "reasoning": "Current professional role and company",
                },
                {
                    "memory": "I graduated from MIT with a CS degree",
                    "pattern": "profile.professional.education.formal",
                    "confidence": 0.90,
                    "reasoning": "Formal education history",
                },
                {
                    "memory": "My favorite IDE is {example_tool}",
                    "pattern": "preferences.technology.programming.tools",
                    "confidence": 0.85,
                    "reasoning": "Tool/IDE preference",
                },
                {
                    "memory": "I have 5 years of experience in {example_skill}",
                    "pattern": "profile.professional.skills.technical",
                    "confidence": 0.85,
                    "reasoning": "Professional skill with experience duration",
                },
                {
                    "memory": "I prefer {example_preference} for my morning routine",
                    "pattern": "preferences.personal.lifestyle",
                    "confidence": 0.80,
                    "reasoning": "Personal lifestyle preference",
                },
            ]

            examples = []
            for template in example_templates:
                # Find a suitable path that matches the pattern
                matching_path = self._find_example_path(all_paths, template["pattern"])
                if matching_path:
                    examples.append(
                        {
                            "memory": template["memory"].format(
                                example_name="John Smith",
                                example_tool="VS Code",
                                example_skill="machine learning",
                                example_preference="coffee",
                            ),
                            "path": matching_path,
                            "confidence": template["confidence"],
                            "reasoning": template["reasoning"],
                        }
                    )

            return examples

        except Exception as e:
            logger.warning(f"Could not generate dynamic examples: {e}")
            # Return minimal fallback examples if dynamic generation fails
            return [
                {
                    "memory": "User's name is John Smith",
                    "path": "profile.personal.identity",
                    "confidence": 0.9,
                    "reasoning": "Personal identity information",
                }
            ]

    def _find_example_path(self, all_paths: list[str], pattern: str) -> Optional[str]:
        """Find a suitable taxonomy path for example generation."""
        # Look for paths that contain the pattern
        candidates = [path for path in all_paths if pattern.lower() in path.lower()]

        if candidates:
            # Prefer paths that are not too deep (3-4 levels) and not 'other' categories
            good_candidates = [
                path
                for path in candidates
                if 3 <= len(path.split(".")) <= 4 and "other" not in path
            ]
            if good_candidates:
                return good_candidates[0]
            return candidates[0]

        # Fallback: find any path with appropriate top-level category
        if "identity" in pattern:
            candidates = [path for path in all_paths if path.startswith("profile.")]
        elif "preferences" in pattern:
            candidates = [path for path in all_paths if path.startswith("preferences.")]
        elif "skills" in pattern:
            candidates = [path for path in all_paths if "skill" in path.lower()]
        else:
            # For 'other' pattern, find any 'other' category
            candidates = [path for path in all_paths if path.endswith(".other")]

        return candidates[0] if candidates else None

    def _get_context_info(self, context: Optional[dict] = None) -> str:
        """Format context information for classification."""
        if not context:
            return ""

        context_parts = []
        if "user_id" in context:
            context_parts.append(f"User: {context['user_id']}")
        if "session_id" in context:
            context_parts.append(f"Session: {context['session_id']}")
        if "timestamp" in context:
            context_parts.append(f"Time: {context['timestamp']}")
        if "conversation_topic" in context:
            context_parts.append(f"Topic: {context['conversation_topic']}")
        if "available_memory_paths" in context:
            paths = context["available_memory_paths"]
            if paths:
                context_parts.append("AVAILABLE STORED MEMORY PATHS:")
                context_parts.append(
                    "You should prioritize matching to these existing paths:"
                )
                for path in sorted(paths):
                    context_parts.append(f"  - {path}")
                context_parts.append(
                    "If the query relates to stored memories, try to match one of these paths."
                )

        if context_parts:
            return "CONTEXT:\n" + "\n".join(context_parts)
        return ""

    def _compute_cache_key(
        self, memory_content: str, context: Optional[dict] = None
    ) -> str:
        """Compute a cache key for the classification."""
        content_hash = hashlib.sha256(memory_content.encode()).hexdigest()
        context_str = json.dumps(context, sort_keys=True) if context else ""
        context_hash = hashlib.sha256(context_str.encode()).hexdigest()
        return f"{content_hash}:{context_hash}"

    async def classify_async(
        self,
        memory_content: str,
        context: Optional[dict] = None,
        use_cache: bool = True,
    ) -> ClassificationResult:
        """
        Classify memory content into taxonomy path asynchronously.

        Args:
            memory_content: The memory content to classify
            context: Optional context information
            use_cache: Whether to use cached results

        Returns:
            ClassificationResult with path and metadata
        """
        # Check cache
        if use_cache:
            cache_key = self._compute_cache_key(memory_content, context)
            if cache_key in self._cache:
                # logger.debug(f"Cache hit for classification: {cache_key}")
                pass
                return self._cache[cache_key]

        # Get iterative taxonomy hints to include in prompt
        classification_hints = ""
        if hasattr(self.taxonomy, "get_classification_hints"):
            hints = self.taxonomy.get_classification_hints(memory_content)
            if hints.get("suggested_paths") or hints.get("expansion_candidates"):
                classification_hints = "\nCLASSIFICATION HINTS:\n"
                if hints.get("suggested_paths"):
                    classification_hints += f"Similar content previously found in: {', '.join(hints['suggested_paths'][:3])}\n"
                if hints.get("expansion_candidates"):
                    candidates = [
                        f"{item['path']} ({item['item_count']} items)"
                        for item in hints["expansion_candidates"][:3]
                    ]
                    classification_hints += (
                        f"Paths ready for expansion: {', '.join(candidates)}\n"
                    )
                classification_hints += (
                    "Consider these hints when choosing the most appropriate path.\n"
                )

        # Prepare prompt
        prompt_vars = {
            "memory_content": memory_content,
            "context_info": self._get_context_info(context),
            "taxonomy_structure": self._get_taxonomy_structure_info(),
            "examples": self._get_classification_examples(),
            "classification_hints": classification_hints,
        }

        # Run classification
        try:
            if self.llm:
                # Use provided LLM
                prompt_text = self.classification_template.format(**prompt_vars)
                response = await self.llm.ainvoke(prompt_text)

                # Extract content from response
                if hasattr(response, "content"):
                    content = response.content
                elif isinstance(response, str):
                    content = response
                else:
                    content = str(response)

                # Clean up the response - handle markdown code blocks
                content = content.strip()
                if "```json" in content:
                    # Extract JSON from markdown code block
                    start = content.find("```json") + 7
                    end = content.find("```", start)
                    if end > start:
                        content = content[start:end].strip()
                elif "```" in content:
                    # Extract from generic code block
                    start = content.find("```") + 3
                    end = content.find("```", start)
                    if end > start:
                        content = content[start:end].strip()

                # Parse JSON
                result_dict = json.loads(content)
            else:
                # No LLM provided - must have one for production use
                raise ValueError(
                    "No LLM provided for classification. Cannot classify without language model."
                )

            result = ClassificationResult(**result_dict)

            # Get classification hints from iterative taxonomy before processing
            hints = None
            if hasattr(self.taxonomy, "get_classification_hints"):
                hints = self.taxonomy.get_classification_hints(memory_content)

                # Apply hints to improve classification
                if hints.get("suggested_paths"):
                    # If LLM suggested a path that matches a hint, boost confidence
                    if result.primary_path in hints["suggested_paths"]:
                        result.confidence = min(1.0, result.confidence + 0.1)

                    # If no good match but we have suggestions, consider the best suggestion
                    elif result.confidence < 0.6 and hints["suggested_paths"]:
                        best_suggestion = hints["suggested_paths"][0]
                        if self._is_valid_path(best_suggestion):
                            result.alternative_paths.insert(0, best_suggestion)
                            result.reasoning += (
                                f" (Hint: similar content found in {best_suggestion})"
                            )

            # Use advanced taxonomy logic if available
            if isinstance(self.taxonomy, AdvancedTaxonomyInterface):
                # Advanced taxonomy (e.g., DynamicTaxonomy) - use smart path selection
                selected_path, final_confidence = (
                    self.taxonomy.select_path_with_fallback(
                        classification_result=result,
                        memory_content=memory_content,
                        metadata=context.get("metadata") if context else None,
                    )
                )

                # Update result with advanced taxonomy's selection
                result.primary_path = selected_path
                result.confidence = final_confidence

            else:
                # Standard taxonomy - just validate paths
                if not self._is_valid_path(result.primary_path):
                    # Find closest valid path
                    result.primary_path = self._find_closest_valid_path(
                        result.primary_path
                    )

            # Track the classification in iterative taxonomy for learning
            if hasattr(self.taxonomy, "track_classification"):
                expansion_triggered = self.taxonomy.track_classification(
                    result.primary_path,
                    memory_content,
                    {
                        "confidence": result.confidence,
                        "reasoning": result.reasoning,
                        "alternatives": result.alternative_paths,
                        "hints_used": hints is not None,
                    },
                )

                if expansion_triggered:
                    # logger.info(
                    #     f"Triggered taxonomy expansion for path: {result.primary_path}"
                    # )
                    pass

            # Cache result
            if use_cache:
                self._cache[cache_key] = result

            return result

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            # Return fallback classification
            return self._fallback_classification(memory_content)

    def classify(
        self,
        memory_content: str,
        context: Optional[dict] = None,
        use_cache: bool = True,
    ) -> ClassificationResult:
        """
        Synchronous version of classify_async.
        """
        import asyncio

        return asyncio.run(self.classify_async(memory_content, context, use_cache))

    def _find_closest_valid_path(self, invalid_path: str) -> str:
        """Find the closest valid path in the taxonomy."""
        parts = invalid_path.split(".")

        # Try progressively shorter paths
        for i in range(len(parts), 0, -1):
            test_path = ".".join(parts[:i])
            if self._is_valid_path(test_path):
                return test_path

        # Fallback to configured fallback path, but validate it exists first
        if self._is_valid_path(self.fallback_path):
            return self.fallback_path

        # Ultimate fallback: find any valid path from the first category
        all_paths = self.taxonomy.get_all_paths()
        if all_paths:
            return all_paths[0]

        # Should never reach here if taxonomy is properly initialized
        raise RuntimeError("No valid paths found in taxonomy")

    def _fallback_classification(self, memory_content: str) -> ClassificationResult:
        """Provide a fallback classification when normal classification fails."""
        fallback_path = self._find_closest_valid_path(self.fallback_path)
        return ClassificationResult(
            primary_path=fallback_path,
            confidence=0.5,
            alternative_paths=[],
            reasoning="Fallback classification due to processing error",
        )

    def batch_classify(
        self, memories: list[str], context: Optional[dict] = None
    ) -> list[ClassificationResult]:
        """
        Classify multiple memories in batch.

        Args:
            memories: List of memory contents to classify
            context: Optional shared context

        Returns:
            List of ClassificationResults
        """
        results = []
        for memory in memories:
            result = self.classify(memory, context)
            results.append(result)
        return results

    def get_statistics(self) -> dict:
        """Get classifier statistics."""
        # Get taxonomy path count using the interface
        try:
            path_count = len(self.taxonomy.get_all_paths())
        except Exception:
            path_count = 0

        return {
            "cache_size": len(self._cache),
            "taxonomy_paths": path_count,
            "taxonomy_type": type(self.taxonomy).__name__,
            "categories": len(list(TaxonomyCategory)),
        }

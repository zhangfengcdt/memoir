"""
Semantic classifier for mapping memories to taxonomy paths.
Uses LLM-based classification with caching and optimization.
"""

import hashlib
import json
import logging
from typing import Any, Optional

# from langmem.prompts import Prompt  # Not available in current version
from pydantic import BaseModel, Field

from .base import AdvancedTaxonomyInterface, TaxonomyInterface
from .semantic_taxonomy import TaxonomyCategory, get_taxonomy

logger = logging.getLogger(__name__)


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
        cache_size: int = 10000,
        use_examples: bool = True,
    ):
        """
        Initialize the semantic classifier.

        Args:
            llm: Language model for classification (optional, will use default)
            taxonomy: Taxonomy instance implementing TaxonomyInterface
                     If None, uses default SemanticTaxonomy
            cache_size: Size of the classification cache
            use_examples: Whether to include examples in prompts
        """
        self.taxonomy = taxonomy if taxonomy is not None else get_taxonomy()
        self.llm = llm
        self.use_examples = use_examples
        self._cache = {}
        self._setup_classification_prompt()

    def _get_taxonomy_structure_info(self) -> str:
        """Generate taxonomy structure information for the prompt."""
        try:
            # All taxonomies should implement TaxonomyInterface
            all_paths = self.taxonomy.get_all_paths()

            if not all_paths:
                return "The taxonomy structure is available but paths could not be enumerated."

            # Group paths by top-level category for better organization
            categories = {}
            for path in all_paths[:100]:  # Limit to prevent prompt overflow
                parts = path.split(".")
                if parts:
                    category = parts[0]
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(path)

            # Generate structured description
            structure_lines = ["Available taxonomy categories and example paths:"]
            for category, paths in sorted(categories.items()):
                structure_lines.append(f"\n• {category}:")
                # Show a few example paths from each category
                example_paths = sorted(paths)[:5]  # Show up to 5 examples
                for path in example_paths:
                    structure_lines.append(f"  - {path}")
                if len(paths) > 5:
                    structure_lines.append(
                        f"  - ... and {len(paths) - 5} more {category} paths"
                    )

            structure_lines.append(f"\nTotal paths available: {len(all_paths)}")

            # Add info about 'other' categories if this is an AdvancedTaxonomy
            if isinstance(self.taxonomy, AdvancedTaxonomyInterface):
                structure_lines.append(
                    "\nThis taxonomy includes 'other' categories at various levels for unclassified content."
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
        """Setup the classification prompt template."""
        # Dynamic template that works with different taxonomy types
        self.classification_template = """You are a semantic memory classifier. Your task is to classify the given memory content into the most appropriate path(s) from the provided taxonomy.

MEMORY CONTENT:
{memory_content}

{context_info}

AVAILABLE TAXONOMY STRUCTURE:
{taxonomy_structure}

CLASSIFICATION GUIDELINES:
1. Choose the most specific path that accurately fits the memory content
2. If the content doesn't clearly fit existing paths, use an appropriate 'other' category if available
3. Consider confidence level:
   - High confidence (0.8-1.0): Very specific and accurate path match
   - Medium confidence (0.5-0.7): Reasonable fit but could be broader
   - Low confidence (0.0-0.4): Content is unclear or doesn't fit well
4. When unsure, prefer broader/higher-level categories over forcing specific ones

{examples}

IMPORTANT:
- Only use paths that exist in the provided taxonomy
- Prefer accuracy over specificity
- Return a valid JSON response with the required fields
- 'Other' categories help the system learn and expand over time

Return your classification as a JSON object with:
- primary_path: The best matching taxonomy path (can be an 'other' path)
- confidence: Confidence score from 0 to 1
- alternative_paths: List of other relevant paths (max 3)
- reasoning: Brief explanation of your choice (1-2 sentences)

Think step by step:
1. Can this be clearly categorized into existing paths?
2. If uncertain, what's the closest parent category?
3. Should this go to a specific path or an 'other' category?"""

    def _get_classification_examples(self) -> str:
        """Get few-shot examples for classification."""
        if not self.use_examples:
            return ""

        examples = [
            {
                "memory": "User's name is John Smith",
                "path": "profile.personal.identity.name.first",
                "confidence": 0.95,
                "reasoning": "Direct personal name information - high confidence",
            },
            {
                "memory": "Prefers dark mode in IDEs",
                "path": "preferences.technology.ui.theme.dark",
                "confidence": 0.9,
                "reasoning": "Clear UI preference for development environment",
            },
            {
                "memory": "Has 5 years of Python experience",
                "path": "profile.professional.skills.technical.programming.languages",
                "confidence": 0.85,
                "reasoning": "Professional technical skill with experience duration",
            },
            {
                "memory": "I collect vintage typewriters",
                "path": "preferences.personal.other",
                "confidence": 0.6,
                "reasoning": "Unusual hobby - best fits in preferences but no specific subcategory",
            },
            {
                "memory": "My pet iguana likes to sunbathe",
                "path": "profile.other",
                "confidence": 0.5,
                "reasoning": "Pet information not in standard taxonomy - using profile.other",
            },
            {
                "memory": "I practice lucid dreaming techniques",
                "path": "behavior.other",
                "confidence": 0.55,
                "reasoning": "Unique practice related to behavior but no exact category",
            },
        ]

        examples_text = "EXAMPLES:\n"
        for ex in examples:
            examples_text += f"\nMemory: {ex['memory']}\n"
            examples_text += f"Classification: {ex['path']}\n"
            examples_text += f"Confidence: {ex['confidence']}\n"
            examples_text += f"Reasoning: {ex['reasoning']}\n"

        return examples_text

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

        if context_parts:
            return "CONTEXT:\n" + "\n".join(context_parts)
        return ""

    def _compute_cache_key(
        self, memory_content: str, context: Optional[dict] = None
    ) -> str:
        """Compute a cache key for the classification."""
        content_hash = hashlib.md5(memory_content.encode()).hexdigest()
        context_str = json.dumps(context, sort_keys=True) if context else ""
        context_hash = hashlib.md5(context_str.encode()).hexdigest()
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
                logger.debug(f"Cache hit for classification: {cache_key}")
                return self._cache[cache_key]

        # Prepare prompt
        prompt_vars = {
            "memory_content": memory_content,
            "context_info": self._get_context_info(context),
            "taxonomy_structure": self._get_taxonomy_structure_info(),
            "examples": self._get_classification_examples(),
        }

        # Run classification
        try:
            if self.llm:
                # Use provided LLM
                prompt_text = self.classification_template.format(**prompt_vars)
                response = await self.llm.ainvoke(prompt_text)
                result_dict = json.loads(response.content)
            else:
                # No LLM provided - must have one for production use
                raise ValueError(
                    "No LLM provided for classification. Cannot classify without language model."
                )

            result = ClassificationResult(**result_dict)

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

        # Default to context if nothing matches
        return "context.current.session.topic.main"

    def _fallback_classification(self, memory_content: str) -> ClassificationResult:
        """Provide a fallback classification when normal classification fails."""
        return ClassificationResult(
            primary_path="context.current.session.topic.main",
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

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
        cache_size: int = 10000,
        use_examples: bool = True,
    ):
        """
        Initialize the semantic classifier.

        Args:
            llm: Language model for classification (optional, will use default)
            cache_size: Size of the classification cache
            use_examples: Whether to include examples in prompts
        """
        self.taxonomy = get_taxonomy()
        self.llm = llm
        self.use_examples = use_examples
        self._cache = {}
        self._setup_classification_prompt()

    def _setup_classification_prompt(self):
        """Setup the classification prompt template."""
        # Simplified version without Prompt class
        self.classification_template = """You are a semantic memory classifier. Your task is to classify the given memory content into the most appropriate path(s) from a taxonomy with predefined paths and 'other' fallback categories.

MEMORY CONTENT:
{memory_content}

{context_info}

AVAILABLE TAXONOMY STRUCTURE:
Main categories with 'other' fallbacks at each level:
- profile: Personal and professional information
  - profile.other: Uncategorized profile information
- preferences: User preferences and settings
  - preferences.other: Uncategorized preferences
- experience: Past projects, achievements, and memories
  - experience.other: Uncategorized experiences
- context: Current session and temporal context
  - context.other: Uncategorized context
- knowledge: Domain expertise and facts
  - knowledge.other: Uncategorized knowledge
- relationships: People and social connections
  - relationships.other: Uncategorized relationships
- goals: Short and long-term objectives
  - goals.other: Uncategorized goals
- behavior: Patterns and decision-making
  - behavior.other: Uncategorized behaviors
- other: Content that doesn't fit any main category

CLASSIFICATION GUIDELINES:
1. If the memory clearly fits a specific predefined path, use it
2. If unsure or the content is edge-case/novel, use the appropriate '.other' path
3. Consider confidence level:
   - High confidence (0.8-1.0): Specific predefined path
   - Medium confidence (0.5-0.7): May use broader path or category.other
   - Low confidence (0.0-0.4): Use category.other or root 'other'
4. When using 'other', choose the most specific level:
   - profile.personal.other for unclear personal info
   - profile.other for unclear profile info
   - other for completely unclassifiable content

{examples}

IMPORTANT:
- The taxonomy has ~800 predefined paths plus 'other' categories at each level
- It's better to use an 'other' category than force-fit into wrong path
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

            # Validate paths
            if not self.taxonomy.is_valid_path(result.primary_path):
                # Find closest valid path
                result.primary_path = self._find_closest_valid_path(result.primary_path)

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
            if self.taxonomy.is_valid_path(test_path):
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
        return {
            "cache_size": len(self._cache),
            "taxonomy_paths": len(self.taxonomy.get_all_paths()),
            "categories": len(list(TaxonomyCategory)),
        }

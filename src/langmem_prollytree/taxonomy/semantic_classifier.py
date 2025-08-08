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
        self.classification_template = """You are a semantic memory classifier. Your task is to classify the given memory content into the most appropriate path(s) from a fixed taxonomy.

MEMORY CONTENT:
{memory_content}

{context_info}

AVAILABLE TAXONOMY PATHS (showing top-level categories):
- profile: Personal and professional information
- preferences: User preferences and settings
- experience: Past projects, achievements, and memories
- context: Current session and temporal context
- knowledge: Domain expertise and facts
- relationships: People and social connections
- goals: Short and long-term objectives
- behavior: Patterns and decision-making

CLASSIFICATION GUIDELINES:
1. Choose the MOST SPECIFIC path that accurately fits the memory
2. Consider the memory's primary purpose and use case
3. Look for explicit indicators (e.g., "I prefer" → preferences, "I work at" → profile.professional)
4. If multiple paths apply, list alternatives in order of relevance
5. Prefer paths that would make retrieval most intuitive

{examples}

IMPORTANT: The taxonomy has ~800 predefined paths. You must choose from these existing paths, not create new ones.

Return your classification as a JSON object with:
- primary_path: The best matching taxonomy path (e.g., "profile.professional.current.company.name")
- confidence: Confidence score from 0 to 1
- alternative_paths: List of other relevant paths (max 3)
- reasoning: Brief explanation of your choice (1-2 sentences)

Think step by step:
1. What type of information is this? (identity, preference, experience, etc.)
2. What is the specific aspect? (work, personal, technical, etc.)
3. What is the most granular categorization?"""

    def _get_classification_examples(self) -> str:
        """Get few-shot examples for classification."""
        if not self.use_examples:
            return ""

        examples = [
            {
                "memory": "User's name is John Smith",
                "path": "profile.personal.identity.name.first",
                "reasoning": "Direct personal name information",
            },
            {
                "memory": "Prefers dark mode in IDEs",
                "path": "preferences.technology.ui.theme.dark",
                "reasoning": "UI preference for development environment",
            },
            {
                "memory": "Has 5 years of Python experience",
                "path": "profile.professional.skills.technical.programming.languages",
                "reasoning": "Professional technical skill with experience duration",
            },
            {
                "memory": "Working on a machine learning project for customer churn prediction",
                "path": "experience.projects.current.active.name",
                "reasoning": "Current active project information",
            },
            {
                "memory": "Graduated from MIT in 2018",
                "path": "profile.professional.education.formal.institutions",
                "reasoning": "Formal education history",
            },
        ]

        examples_text = "EXAMPLES:\n"
        for ex in examples:
            examples_text += f"\nMemory: {ex['memory']}\n"
            examples_text += f"Classification: {ex['path']}\n"
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
                # Use mock classification for testing
                result_dict = self._mock_classify(memory_content)

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

    def _mock_classify(self, memory_content: str) -> dict:
        """Mock classification for testing without LLM."""
        # Simple keyword-based classification
        content_lower = memory_content.lower()

        if "name" in content_lower or "called" in content_lower:
            path = "profile.personal.identity.name.first"
        elif (
            "work" in content_lower
            or "job" in content_lower
            or "company" in content_lower
        ):
            path = "profile.professional.current.company.name"
        elif "prefer" in content_lower or "like" in content_lower:
            path = "preferences.personal.lifestyle.hobbies.active"
        elif (
            "python" in content_lower
            or "javascript" in content_lower
            or "code" in content_lower
        ):
            path = "profile.professional.skills.technical.programming.languages"
        elif "project" in content_lower:
            path = "experience.projects.current.active.name"
        elif "goal" in content_lower or "want to" in content_lower:
            path = "goals.categories.personal.growth"
        else:
            path = "context.current.session.topic.main"

        return {
            "primary_path": path,
            "confidence": 0.85,
            "alternative_paths": [],
            "reasoning": "Mock classification based on keyword matching",
        }

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


class OptimizedClassifier(SemanticClassifier):
    """
    Optimized classifier with pre-computed mappings for common queries.
    Target: 1-5ms classification without LLM calls.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._build_keyword_index()

    def _build_keyword_index(self):
        """Build keyword to path mappings for fast classification."""
        self.keyword_map = {
            # Identity keywords
            "my pronouns are": ["profile.personal.identity.gender"],
            "pronouns": ["profile.personal.identity.gender"],
            "name": ["profile.personal.identity.name"],
            "called": ["profile.personal.identity.name"],
            "age": ["profile.personal.identity.age"],
            "years old": ["profile.personal.identity.age"],
            "birthday": ["profile.personal.identity.age"],
            "location": ["profile.personal.location.current"],
            "live in": ["profile.personal.location.current"],
            "from": ["profile.personal.location.current"],
            # Work keywords (more specific first)
            "work at": ["profile.professional.current.company"],
            "i work at": ["profile.professional.current.company"],
            "manage a team": ["profile.professional.current.team"],
            "team of": ["profile.professional.current.team"],
            "company": ["profile.professional.current.company"],
            "job": ["profile.professional.current.position"],
            "salary": ["profile.professional.current.compensation"],
            "team": ["profile.professional.current.team"],
            "manage": ["profile.professional.current.team"],
            "manager": ["profile.professional.current.position"],
            "engineer": ["profile.professional.current.position"],
            "work": ["profile.professional.current"],
            # Education keywords
            "phd in": ["profile.professional.education.formal"],
            "degree in": ["profile.professional.education.formal"],
            "graduated from": ["profile.professional.education.formal"],
            "computer science": ["profile.professional.education.formal"],
            # Skills keywords
            "python": ["profile.professional.skills.technical.programming"],
            "javascript": ["profile.professional.skills.technical.programming"],
            "programming": ["profile.professional.skills.technical.programming"],
            "coding": ["profile.professional.skills.technical.programming"],
            "experience": ["profile.professional.skills.technical"],
            "years": ["profile.professional.skills.technical"],
            # Preferences keywords
            "prefer": ["preferences"],
            "like": ["preferences.personal"],
            "favorite": ["preferences.personal"],
            "dark mode": ["preferences.technology.ui.theme"],
            "theme": ["preferences.technology.ui.theme"],
            # Project keywords (more specific first)
            "working on a": ["experience.projects.current.active"],
            "machine learning project": ["experience.projects.current.active"],
            "working on": ["experience.projects.current.active"],
            "project": ["experience.projects.current.active"],
            "building": ["experience.projects.current.active"],
            # Goal keywords
            "my goal is to": ["goals.categories"],
            "goal is to": ["goals.categories"],
            "want to become": ["goals.categories"],
            "goal": ["goals.categories"],
            "want to": ["goals.categories"],
            "plan to": ["goals.timeframes.short_term"],
            "dream": ["goals.timeframes.long_term"],
            # Memory keywords
            "remember": ["experience.memories"],
            "recall": ["experience.memories"],
            "forgot": ["experience.memories"],
            # Relationship keywords
            "friend": ["relationships.people.close.friends"],
            "family": ["relationships.people.close.family"],
            "colleague": ["relationships.people.professional.colleagues"],
            "spouse": ["relationships.people.close.romantic"],
        }

    def fast_classify(self, memory_content: str) -> ClassificationResult:
        """
        Ultra-fast classification using keyword matching.
        No LLM calls, targets <5ms latency.
        """
        content_lower = memory_content.lower()

        # Find matching keywords - prioritize longer phrases
        matches = []
        # Sort by length descending to match longer phrases first
        sorted_keywords = sorted(
            self.keyword_map.items(), key=lambda x: len(x[0]), reverse=True
        )

        for keyword, paths in sorted_keywords:
            if keyword in content_lower:
                for path in paths:
                    matches.append((keyword, path))
                # Use first (longest) match only
                break

        if matches:
            # Use the most specific match
            primary_path = matches[0][1]

            # Find the most specific valid path from taxonomy
            all_paths = self.taxonomy.get_all_paths()
            best_match = primary_path
            best_length = 0

            for full_path in all_paths:
                if full_path.startswith(primary_path) and len(full_path) > best_length:
                    best_match = full_path
                    best_length = len(full_path)

            # If no longer path found, ensure the primary path itself is valid
            if not self.taxonomy.is_valid_path(best_match):
                # Find a valid parent path
                parts = primary_path.split(".")
                for i in range(len(parts), 0, -1):
                    test_path = ".".join(parts[:i])
                    if self.taxonomy.is_valid_path(test_path):
                        best_match = test_path
                        break

            return ClassificationResult(
                primary_path=best_match,
                confidence=0.9 if len(matches) > 1 else 0.7,
                alternative_paths=[m[1] for _, m in matches[1:3]],
                reasoning=f"Fast classification based on keyword: {matches[0][0]}",
            )

        # Default classification
        return ClassificationResult(
            primary_path="context.current.session.topic.main",
            confidence=0.5,
            alternative_paths=[],
            reasoning="No specific keywords found, using default context path",
        )

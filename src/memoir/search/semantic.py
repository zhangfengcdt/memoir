"""
Simple semantic search implementation using keyword matching.
Fast and efficient search without LLM dependencies.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Represents a search result for a semantic path."""

    path: str  # The semantic path
    content: str  # Content from this path
    metadata: dict  # Additional metadata
    relevance_score: float = 0.0  # Relevance score (0.0 to 1.0)
    namespace: str = ""


class SemanticSearchEngine:
    """
    Simple semantic search engine using keyword matching.

    This engine performs fast keyword-based matching against semantic paths
    and content, avoiding the complexity and latency of LLM-based approaches.
    """

    def __init__(
        self,
        store: Any,  # Any store with search and asearch methods
        max_results: int = 10,
        min_relevance_score: float = 0.1,
    ):
        """
        Initialize semantic search engine.

        Args:
            store: Memory store (ProllyTreeStore)
            max_results: Maximum number of results to return
            min_relevance_score: Minimum relevance score to include result
        """
        self.store = store
        self.max_results = max_results
        self.min_relevance_score = min_relevance_score

    async def search(
        self, query: str, namespace: str, limit: int = 10
    ) -> list[SearchResult]:
        """
        Search for relevant memories using keyword matching.

        Args:
            query: Natural language search query
            namespace: User namespace to search in
            limit: Maximum number of results

        Returns:
            List of SearchResult objects ranked by relevance
        """
        try:
            # Extract keywords from query
            keywords = self._extract_keywords(query)

            if not keywords:
                logger.warning(f"No keywords extracted from query: '{query}'")
                return []

            # Get all memories from the namespace
            namespace_tuple = (
                (namespace,)
                if isinstance(namespace, str)
                else tuple(namespace.split(":"))
            )

            # Search the store for all memories
            all_memories = self.store.search(namespace_tuple, limit=1000)

            if not all_memories:
                logger.info(f"No memories found in namespace {namespace}")
                return []

            # Score and rank results
            scored_results = []
            for _, path, data in all_memories:
                relevance_score = self._calculate_relevance(keywords, path, data)

                if relevance_score >= self.min_relevance_score:
                    # Extract content from the data
                    search_results = self._extract_search_results(
                        path, data, namespace, relevance_score
                    )
                    scored_results.extend(search_results)

            # Sort by relevance score (highest first)
            scored_results.sort(key=lambda x: x.relevance_score, reverse=True)

            # Return top results
            return scored_results[: min(limit, self.max_results)]

        except Exception as e:
            logger.error(f"Error in semantic search: {e}")
            return []

    def _extract_keywords(self, query: str) -> set[str]:
        """
        Extract meaningful keywords from a search query.

        Args:
            query: Natural language query

        Returns:
            Set of normalized keywords
        """
        # Convert to lowercase and remove punctuation
        normalized_query = re.sub(r"[^\w\s]", " ", query.lower())

        # Split into words
        words = normalized_query.split()

        # Remove common stop words
        stop_words = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "by",
            "for",
            "from",
            "has",
            "he",
            "in",
            "is",
            "it",
            "its",
            "of",
            "on",
            "that",
            "the",
            "to",
            "was",
            "will",
            "with",
            "what",
            "where",
            "when",
            "who",
            "how",
            "do",
            "does",
            "did",
            "can",
            "could",
            "should",
            "would",
            "my",
            "me",
            "i",
            "you",
            "your",
            "his",
            "her",
            "their",
            "them",
            "this",
        }

        # Filter out stop words and short words
        keywords = {word for word in words if len(word) > 2 and word not in stop_words}

        return keywords

    def _calculate_relevance(self, keywords: set[str], path: str, data: Any) -> float:
        """
        Calculate relevance score for a memory based on keyword matching.

        Args:
            keywords: Set of query keywords
            path: Semantic path
            data: Memory data

        Returns:
            Relevance score between 0.0 and 1.0
        """
        if not keywords:
            return 0.0

        score = 0.0
        max_possible_score = (
            len(keywords) * 2
        )  # Max: path match + content match per keyword

        # Score based on path matching (higher weight)
        path_lower = path.lower()
        for keyword in keywords:
            if keyword in path_lower:
                score += 1.5  # Path matches are weighted higher

        # Score based on content matching
        content_text = self._extract_content_text(data).lower()
        for keyword in keywords:
            if keyword in content_text:
                score += 1.0

        # Normalize score to 0.0-1.0 range
        return min(score / max_possible_score, 1.0) if max_possible_score > 0 else 0.0

    def _extract_content_text(self, data: Any) -> str:
        """
        Extract searchable text content from memory data.

        Args:
            data: Memory data (could be dict, string, or other format)

        Returns:
            String representation of the content
        """
        if isinstance(data, dict):
            if "memories" in data:
                # Aggregated memory format
                memories = data.get("memories", [])
                content_parts = []
                for memory in memories:
                    if isinstance(memory, dict) and "content" in memory:
                        content_parts.append(str(memory["content"]))
                return " ".join(content_parts)
            elif "content" in data:
                # Single memory format
                return str(data["content"])
            else:
                # Generic dict - concatenate all string values
                return " ".join(
                    str(v) for v in data.values() if isinstance(v, (str, int, float))
                )
        else:
            # Direct content
            return str(data)

    def _extract_search_results(
        self, path: str, data: Any, namespace: str, relevance_score: float
    ) -> list[SearchResult]:
        """
        Extract SearchResult objects from memory data.

        Args:
            path: Semantic path
            data: Memory data
            namespace: User namespace
            relevance_score: Calculated relevance score

        Returns:
            List of SearchResult objects
        """
        results = []

        if isinstance(data, dict) and "memories" in data:
            # Aggregated memory - create results for individual memories
            memories = data.get("memories", [])
            for memory in memories:
                if isinstance(memory, dict) and "content" in memory:
                    content = str(memory["content"])
                    metadata = memory.get("metadata", {})
                    metadata.update({"source": "aggregated", "path": path})

                    result = SearchResult(
                        path=path,
                        content=content,
                        metadata=metadata,
                        relevance_score=relevance_score,
                        namespace=namespace,
                    )
                    results.append(result)
        else:
            # Single memory or direct content
            content = self._extract_content_text(data)
            metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
            metadata.update({"source": "single", "path": path})

            result = SearchResult(
                path=path,
                content=content,
                metadata=metadata,
                relevance_score=relevance_score,
                namespace=namespace,
            )
            results.append(result)

        return results

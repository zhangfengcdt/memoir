"""
Hierarchical search implementation for semantic memory retrieval.
Implements specific → general search strategy with relevance scoring.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from langmem_prollytree.taxonomy.semantic_classifier import SemanticClassifier
from langmem_prollytree.taxonomy.semantic_taxonomy import get_taxonomy

logger = logging.getLogger(__name__)


class SearchStrategy(Enum):
    """Search strategy for hierarchical retrieval."""

    SPECIFIC_TO_GENERAL = "specific_to_general"  # Start specific, broaden if needed
    GENERAL_TO_SPECIFIC = "general_to_specific"  # Start broad, narrow down
    BREADTH_FIRST = "breadth_first"  # Search all at same level first
    BEST_MATCH = "best_match"  # Find best matching level directly


@dataclass
class SearchResult:
    """Represents a search result with metadata."""

    key: str
    content: Any
    relevance_score: float
    semantic_distance: int  # Distance from query path
    confidence: float
    timestamp: float
    namespace: str


class HierarchicalSearchEngine:
    """
    Implements hierarchical search over semantic taxonomy.
    Optimized for <1ms search latency using ProllyTree prefix queries.
    """

    def __init__(
        self,
        store: Any,  # Any store with asearch and alist methods
        classifier: Optional[SemanticClassifier] = None,
        min_results: int = 5,
        max_results: int = 20,
    ):
        """
        Initialize search engine.

        Args:
            store: ProllyTree store instance
            classifier: Semantic classifier for query understanding
            min_results: Minimum results before broadening search
            max_results: Maximum results to return
        """
        self.store = store
        self.taxonomy = get_taxonomy()
        if classifier is None:
            raise ValueError(
                "SemanticClassifier with LLM is required for production search"
            )
        self.classifier = classifier
        self.min_results = min_results
        self.max_results = max_results

        # Build search optimizations
        self._build_search_index()

    def _build_search_index(self):
        """Build indices for optimized search."""
        # Pre-compute common query patterns
        self.query_patterns = {
            # Question patterns → taxonomy paths
            "what.*know about": ["knowledge", "profile", "experience"],
            "what.*prefer": ["preferences"],
            "what.*working on": [
                "experience.projects.current",
                "context.current.session",
            ],
            "what.*goal": ["goals"],
            "who": ["relationships", "profile.personal.identity"],
            "when": ["context.temporal", "experience.memories"],
            "where": ["profile.personal.location", "context.current.environment"],
            "how": ["behavior", "preferences", "knowledge.learning"],
            "why": ["goals", "values", "behavior.decisions"],
            # Topic patterns
            "programming": ["profile.professional.skills.technical.programming"],
            "work": ["profile.professional", "experience.projects", "preferences.work"],
            "personal": [
                "profile.personal",
                "preferences.personal",
                "goals.categories.personal",
            ],
            "family": ["profile.personal.family", "relationships.people.close.family"],
            "health": ["profile.personal.health", "goals.categories.personal.health"],
        }

        # Pre-compute path hierarchies for fast traversal
        self.path_hierarchies = {}
        for path in self.taxonomy.get_all_paths():
            parts = path.split(".")
            self.path_hierarchies[path] = [
                ".".join(parts[: i + 1]) for i in range(len(parts))
            ]

    async def search(
        self,
        query: str,
        namespace: str,
        strategy: SearchStrategy = SearchStrategy.SPECIFIC_TO_GENERAL,
        context: Optional[dict] = None,
    ) -> list[SearchResult]:
        """
        Perform hierarchical search for memories.

        Args:
            query: Natural language query
            namespace: User namespace to search
            strategy: Search strategy to use
            context: Optional context for query understanding

        Returns:
            List of search results ranked by relevance
        """
        start_time = time.time()

        # Step 1: Understand query intent and map to taxonomy paths
        search_paths = await self._map_query_to_paths(query, context)
        logger.debug(f"Mapped query '{query}' to paths: {search_paths}")

        # Step 2: Execute hierarchical search
        if strategy == SearchStrategy.SPECIFIC_TO_GENERAL:
            results = await self._search_specific_to_general(namespace, search_paths)
        elif strategy == SearchStrategy.GENERAL_TO_SPECIFIC:
            results = await self._search_general_to_specific(namespace, search_paths)
        elif strategy == SearchStrategy.BREADTH_FIRST:
            results = await self._search_breadth_first(namespace, search_paths)
        else:  # BEST_MATCH
            results = await self._search_best_match(namespace, search_paths)

        # Step 3: Score and rank results
        ranked_results = self._rank_results(results, query)

        # Step 4: Apply result limits
        final_results = ranked_results[: self.max_results]

        search_time = (time.time() - start_time) * 1000
        logger.info(
            f"Search completed in {search_time:.2f}ms, found {len(final_results)} results"
        )

        return final_results

    async def _map_query_to_paths(
        self, query: str, context: Optional[dict]
    ) -> list[str]:
        """Map natural language query to taxonomy paths."""
        paths = []
        query_lower = query.lower()

        # Try pattern matching first (fast path)
        for pattern, suggested_paths in self.query_patterns.items():
            if pattern in query_lower or (
                pattern.startswith("what") and pattern[4:] in query_lower
            ):
                paths.extend(suggested_paths)

        # If no patterns match, use classifier
        if not paths:
            classification = await self.classifier.classify_async(query, context)
            paths.append(classification.primary_path)
            paths.extend(classification.alternative_paths)

        # Remove duplicates while preserving order
        seen = set()
        unique_paths = []
        for path in paths:
            if path not in seen:
                seen.add(path)
                unique_paths.append(path)

        return unique_paths or ["context.current.session.topic"]

    async def _search_specific_to_general(
        self, namespace: str, search_paths: list[str]
    ) -> list[SearchResult]:
        """
        Search from specific paths to more general ones.
        Most common strategy for precise retrieval.
        """
        results = []
        searched_prefixes = set()

        for base_path in search_paths:
            if len(results) >= self.min_results:
                break

            # Get path hierarchy (specific to general)
            if base_path in self.path_hierarchies:
                hierarchy = self.path_hierarchies[base_path]
            else:
                # Build hierarchy on the fly
                parts = base_path.split(".")
                hierarchy = [".".join(parts[: i + 1]) for i in range(len(parts), 0, -1)]

            # Search each level
            for level, path_prefix in enumerate(hierarchy):
                if path_prefix in searched_prefixes:
                    continue
                searched_prefixes.add(path_prefix)

                # Perform prefix search
                items = await self.store.asearch(namespace, path_prefix)

                for key, content in items:
                    result = SearchResult(
                        key=key,
                        content=content,
                        relevance_score=1.0
                        / (level + 1),  # Higher score for more specific
                        semantic_distance=level,
                        confidence=1.0,
                        timestamp=time.time(),
                        namespace=namespace,
                    )
                    results.append(result)

                # Check if we have enough results at this level
                if len(results) >= self.min_results:
                    break

        return results

    async def _search_general_to_specific(
        self, namespace: str, search_paths: list[str]
    ) -> list[SearchResult]:
        """
        Search from general to specific paths.
        Useful for exploratory queries.
        """
        results = []
        searched_prefixes = set()

        for base_path in search_paths:
            # Start from most general (root category)
            parts = base_path.split(".")

            for depth in range(1, len(parts) + 1):
                path_prefix = ".".join(parts[:depth])

                if path_prefix in searched_prefixes:
                    continue
                searched_prefixes.add(path_prefix)

                items = await self.store.asearch(namespace, path_prefix)

                for key, content in items:
                    # Calculate distance from target path
                    distance = len(parts) - depth

                    result = SearchResult(
                        key=key,
                        content=content,
                        relevance_score=1.0 / (distance + 1),
                        semantic_distance=distance,
                        confidence=1.0,
                        timestamp=time.time(),
                        namespace=namespace,
                    )
                    results.append(result)

        return results

    async def _search_breadth_first(
        self, namespace: str, search_paths: list[str]
    ) -> list[SearchResult]:
        """
        Search all paths at the same depth level first.
        Balances precision and recall.
        """
        results = []
        searched_prefixes = set()

        # Group paths by depth
        depth_groups = {}
        for path in search_paths:
            depth = len(path.split("."))
            if depth not in depth_groups:
                depth_groups[depth] = []
            depth_groups[depth].append(path)

        # Search each depth level
        for depth in sorted(depth_groups.keys(), reverse=True):
            for path in depth_groups[depth]:
                if path in searched_prefixes:
                    continue
                searched_prefixes.add(path)

                items = await self.store.asearch(namespace, path)

                for key, content in items:
                    result = SearchResult(
                        key=key,
                        content=content,
                        relevance_score=1.0
                        / (abs(depth - 3) + 1),  # Prefer medium depth
                        semantic_distance=0,
                        confidence=1.0,
                        timestamp=time.time(),
                        namespace=namespace,
                    )
                    results.append(result)

            if len(results) >= self.min_results:
                break

        return results

    async def _search_best_match(
        self, namespace: str, search_paths: list[str]
    ) -> list[SearchResult]:
        """
        Find the best matching depth level directly.
        Fastest strategy but may miss relevant results.
        """
        results = []

        # Search all paths directly
        for path in search_paths:
            items = await self.store.asearch(namespace, path)

            for key, content in items:
                result = SearchResult(
                    key=key,
                    content=content,
                    relevance_score=1.0,
                    semantic_distance=0,
                    confidence=1.0,
                    timestamp=time.time(),
                    namespace=namespace,
                )
                results.append(result)

        return results

    def _rank_results(
        self, results: list[SearchResult], query: str
    ) -> list[SearchResult]:
        """
        Rank search results by relevance.
        Combines semantic distance, recency, and confidence.
        """
        if not results:
            return []

        current_time = time.time()
        query_lower = query.lower()

        for result in results:
            # Recency score (exponential decay over time)
            age_hours = (current_time - result.timestamp) / 3600
            recency_score = 1.0 / (1.0 + age_hours / 24)  # Half-life of 24 hours

            # Keyword match score
            content_str = str(result.content).lower()
            query_words = query_lower.split()
            matches = sum(1 for word in query_words if word in content_str)
            keyword_score = matches / len(query_words) if query_words else 0

            # Combined score
            result.relevance_score = (
                result.relevance_score * 0.4  # Semantic score
                + recency_score * 0.3  # Recency
                + keyword_score * 0.2  # Keyword matches
                + result.confidence * 0.1  # Classification confidence
            )

        # Sort by relevance score
        results.sort(key=lambda r: r.relevance_score, reverse=True)

        return results

    async def search_with_fallback(
        self, query: str, namespace: str, context: Optional[dict] = None
    ) -> list[SearchResult]:
        """
        Search with automatic fallback strategies.
        Tries specific first, then broadens if needed.
        """
        # Try specific search first
        results = await self.search(
            query, namespace, SearchStrategy.SPECIFIC_TO_GENERAL, context
        )

        # If not enough results, try broader search
        if len(results) < self.min_results:
            logger.info(f"Insufficient results ({len(results)}), trying broader search")
            additional = await self.search(
                query, namespace, SearchStrategy.BREADTH_FIRST, context
            )

            # Merge results, avoiding duplicates
            seen_keys = {r.key for r in results}
            for r in additional:
                if r.key not in seen_keys:
                    results.append(r)
                    seen_keys.add(r.key)

        return results[: self.max_results]

    async def multi_hop_search(
        self, queries: list[str], namespace: str, combine_strategy: str = "union"
    ) -> list[SearchResult]:
        """
        Perform multi-hop search across multiple queries.
        Useful for complex information needs.

        Args:
            queries: List of search queries
            namespace: User namespace
            combine_strategy: "union" or "intersection"

        Returns:
            Combined search results
        """
        all_results = []
        result_sets = []

        for query in queries:
            results = await self.search(query, namespace)
            result_sets.append({r.key: r for r in results})
            all_results.extend(results)

        if combine_strategy == "intersection":
            # Only keep results that appear in all queries
            if not result_sets:
                return []

            common_keys = set(result_sets[0].keys())
            for result_set in result_sets[1:]:
                common_keys &= set(result_set.keys())

            final_results = []
            for key in common_keys:
                # Use the result with highest score
                best_result = max(
                    (rs[key] for rs in result_sets if key in rs),
                    key=lambda r: r.relevance_score,
                )
                final_results.append(best_result)

            return final_results

        else:  # union
            # Combine all results, merge duplicates
            combined = {}
            for result in all_results:
                if result.key not in combined:
                    combined[result.key] = result
                else:
                    # Keep the one with higher score
                    if result.relevance_score > combined[result.key].relevance_score:
                        combined[result.key] = result

            return sorted(
                combined.values(), key=lambda r: r.relevance_score, reverse=True
            )

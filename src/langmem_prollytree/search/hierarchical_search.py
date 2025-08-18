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


@dataclass
class SearchResult:
    """Represents a combined search result for a path."""

    path: str  # The semantic path
    combined_content: str  # All content from this path concatenated
    item_count: int  # Number of items combined
    total_length: int  # Total character length
    semantic_distance: int  # Distance from query path
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
        max_content_length: int = 10000,  # Maximum total content length
    ):
        """
        Initialize search engine.

        Args:
            store: ProllyTree store instance
            classifier: Semantic classifier for query understanding
            max_content_length: Maximum total content length to return
        """
        self.store = store
        self.taxonomy = get_taxonomy()
        if classifier is None:
            raise ValueError(
                "SemanticClassifier with LLM is required for production search"
            )
        self.classifier = classifier
        self.max_content_length = max_content_length

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

        # Step 2: Execute hierarchical search and combine results
        if strategy == SearchStrategy.SPECIFIC_TO_GENERAL:
            combined_results = await self._search_specific_to_general(
                namespace, search_paths
            )
        else:  # GENERAL_TO_SPECIFIC
            combined_results = await self._search_general_to_specific(
                namespace, search_paths
            )

        # Step 3: Apply content length limits
        final_results = self._limit_by_content_length(combined_results)

        search_time = (time.time() - start_time) * 1000
        logger.info(
            f"Search completed in {search_time:.2f}ms, found {len(final_results)} results"
        )

        return final_results

    async def _map_query_to_paths(
        self, query: str, context: Optional[dict]
    ) -> list[str]:
        """Map natural language query to taxonomy paths using LLM classification."""
        # Use the classifier to understand query intent
        classification = await self.classifier.classify_async(query, context)

        paths = [classification.primary_path]
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
        Search from specific paths to more general ones, combining content by path.
        """
        path_results = {}  # path -> combined content
        searched_prefixes = set()

        for base_path in search_paths:
            # Build path hierarchy (specific to general)
            parts = base_path.split(".")
            hierarchy = [".".join(parts[: i + 1]) for i in range(len(parts), 0, -1)]

            # Search each level from specific to general
            for level, path_prefix in enumerate(hierarchy):
                if path_prefix in searched_prefixes:
                    continue
                searched_prefixes.add(path_prefix)

                # Get all items for this path
                items = await self.store.asearch(namespace, path_prefix)

                if items:
                    # Combine all content for this path
                    contents = []
                    for _key, data in items:
                        if isinstance(data, dict):
                            content_text = str(data.get("content", ""))
                        else:
                            content_text = str(data)
                        if content_text.strip():
                            contents.append(content_text.strip())

                    if contents:
                        combined_content = " | ".join(contents)
                        path_results[path_prefix] = SearchResult(
                            path=path_prefix,
                            combined_content=combined_content,
                            item_count=len(contents),
                            total_length=len(combined_content),
                            semantic_distance=level,
                            namespace=namespace,
                        )

        # Return results ordered by semantic distance (most specific first)
        return sorted(path_results.values(), key=lambda r: r.semantic_distance)

    async def _search_general_to_specific(
        self, namespace: str, search_paths: list[str]
    ) -> list[SearchResult]:
        """
        Search from general to specific paths, combining content by path.
        Useful for exploratory queries.
        """
        path_results = {}  # path -> combined content
        searched_prefixes = set()

        for base_path in search_paths:
            # Build path hierarchy (general to specific)
            parts = base_path.split(".")
            hierarchy = [".".join(parts[: i + 1]) for i in range(len(parts))]

            # Search each level from general to specific
            for level, path_prefix in enumerate(hierarchy):
                if path_prefix in searched_prefixes:
                    continue
                searched_prefixes.add(path_prefix)

                # Get all items for this path
                items = await self.store.asearch(namespace, path_prefix)

                if items:
                    # Combine all content for this path
                    contents = []
                    for _key, data in items:
                        if isinstance(data, dict):
                            content_text = str(data.get("content", ""))
                        else:
                            content_text = str(data)
                        if content_text.strip():
                            contents.append(content_text.strip())

                    if contents:
                        combined_content = " | ".join(contents)
                        path_results[path_prefix] = SearchResult(
                            path=path_prefix,
                            combined_content=combined_content,
                            item_count=len(contents),
                            total_length=len(combined_content),
                            semantic_distance=level,
                            namespace=namespace,
                        )

        # Return results ordered by semantic distance (most general first)
        return sorted(path_results.values(), key=lambda r: r.semantic_distance)

    def _limit_by_content_length(
        self, results: list[SearchResult]
    ) -> list[SearchResult]:
        """
        Limit results by total content length instead of number of results.
        """
        if not results:
            return []

        limited_results = []
        total_length = 0

        for result in results:
            if total_length + result.total_length <= self.max_content_length:
                limited_results.append(result)
                total_length += result.total_length
            else:
                # If we can't fit the entire result, truncate it to fit
                remaining_length = self.max_content_length - total_length
                if remaining_length > 100:  # Only include if we have reasonable space
                    truncated_content = (
                        result.combined_content[:remaining_length] + "..."
                    )
                    truncated_result = SearchResult(
                        path=result.path,
                        combined_content=truncated_content,
                        item_count=result.item_count,
                        total_length=len(truncated_content),
                        semantic_distance=result.semantic_distance,
                        namespace=result.namespace,
                    )
                    limited_results.append(truncated_result)
                break

        return limited_results

    # Removed unused search methods (_search_breadth_first, _search_best_match, _rank_results)
    # These are no longer needed with the optimized approach that combines content by path

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

        # If no results, try broader search
        if not results:
            logger.info("No results found, trying broader search")
            additional = await self.search(
                query, namespace, SearchStrategy.GENERAL_TO_SPECIFIC, context
            )

            # Merge results, avoiding duplicates by path
            seen_paths = {r.path for r in results}
            for r in additional:
                if r.path not in seen_paths:
                    results.append(r)
                    seen_paths.add(r.path)

        return self._limit_by_content_length(results)

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
            result_sets.append({r.path: r for r in results})
            all_results.extend(results)

        if combine_strategy == "intersection":
            # Only keep results that appear in all queries
            if not result_sets:
                return []

            common_paths = set(result_sets[0].keys())
            for result_set in result_sets[1:]:
                common_paths &= set(result_set.keys())

            final_results = []
            for path in common_paths:
                # Use the result with highest item count
                best_result = max(
                    (rs[path] for rs in result_sets if path in rs),
                    key=lambda r: r.item_count,
                )
                final_results.append(best_result)

            return self._limit_by_content_length(final_results)

        else:  # union
            # Combine all results, merge duplicates by path
            combined = {}
            for result in all_results:
                if result.path not in combined:
                    combined[result.path] = result
                else:
                    # Keep the one with more items
                    if result.item_count > combined[result.path].item_count:
                        combined[result.path] = result

            return self._limit_by_content_length(
                sorted(combined.values(), key=lambda r: r.semantic_distance)
            )

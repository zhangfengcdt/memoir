"""
Hierarchical search implementation for semantic memory retrieval.
Implements specific → general search strategy with relevance scoring.
"""

import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from memoir.taxonomy.semantic_classifier import SemanticClassifier
from memoir.taxonomy.semantic_taxonomy import get_taxonomy

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
        profile_manager: Optional[Any] = None,  # ProfileManager for profile summaries
    ):
        """
        Initialize search engine.

        Args:
            store: ProllyTree store instance
            classifier: Semantic classifier for query understanding
            max_content_length: Maximum total content length to return
            profile_manager: ProfileManager for including profile summaries
        """
        self.store = store
        self.taxonomy = get_taxonomy()
        if classifier is None:
            raise ValueError(
                "SemanticClassifier with LLM is required for production search"
            )
        self.classifier = classifier
        self.max_content_length = max_content_length
        self.profile_manager = profile_manager

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

        # Step 1: Check if this query should use event keyword search
        event_keywords = await self._should_use_event_search(query, context)
        if event_keywords:
            logger.info(
                f"Using event keyword search for: '{query}' with keywords: {event_keywords}"
            )
            event_results = await self._search_events_by_keywords(
                query, namespace, event_keywords
            )

            # Add profile summary to event results if available
            if self.profile_manager:
                try:
                    profile_summary = await self.profile_manager.get_profile_summary(
                        llm=None
                    )
                    if (
                        profile_summary
                        and profile_summary != "No profile information available."
                    ):
                        profile_result = SearchResult(
                            path="profile.summary",
                            combined_content=profile_summary,
                            item_count=1,
                            total_length=len(profile_summary),
                            semantic_distance=0,
                            namespace=namespace,
                        )
                        event_results.insert(0, profile_result)
                except Exception as e:
                    logger.warning(
                        f"Failed to include profile summary in event search: {e}"
                    )

            search_time = (time.time() - start_time) * 1000
            logger.info(
                f"Event search completed in {search_time:.2f}ms, found {len(event_results)} results"
            )
            return event_results

        # Step 2: Understand query intent and map to taxonomy paths
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

        # Step 4: Include profile summary if profile manager is available
        if self.profile_manager:
            try:
                # Use structured-only mode (llm=None) for fast profile summaries
                # This provides all factual profile data without expensive narrative generation
                profile_summary = await self.profile_manager.get_profile_summary(
                    llm=None
                )
                if (
                    profile_summary
                    and profile_summary != "No profile information available."
                ):
                    # Add profile summary as the first result for context
                    profile_result = SearchResult(
                        path="profile.summary",
                        combined_content=profile_summary,
                        item_count=1,
                        total_length=len(profile_summary),
                        semantic_distance=0,
                        namespace=namespace,
                    )
                    final_results.insert(0, profile_result)
                    logger.info("Added profile summary to search results")
            except Exception as e:
                logger.warning(f"Failed to include profile summary: {e}")

        search_time = (time.time() - start_time) * 1000
        logger.info(
            f"Search completed in {search_time:.2f}ms, found {len(final_results)} results"
        )

        return final_results

    async def _map_query_to_paths(
        self, query: str, context: Optional[dict]
    ) -> list[str]:
        """Map natural language query to taxonomy paths using LLM classification."""
        # Get available memory paths from the store to help guide classification
        available_keys = getattr(self.store, "_keys", set())
        available_paths = set()

        for key in available_keys:
            # Extract the semantic path from keys like "memory:general:goals.categories.career"
            parts = key.split(":")
            if len(parts) >= 3:
                semantic_path = parts[2]
                # Handle case where there might be a # at the end
                if "#" in semantic_path:
                    semantic_path = semantic_path.split("#")[0]
                available_paths.add(semantic_path)

        # Enhanced context with available paths
        enhanced_context = context or {}
        if available_paths:
            enhanced_context["available_memory_paths"] = list(available_paths)
            logger.debug(
                f"Available memory paths for query '{query}': {list(available_paths)}"
            )

        # Use the classifier to understand query intent with available paths context
        classification = await self.classifier.classify_async(query, enhanced_context)
        logger.debug(
            f"Classifier returned paths for '{query}': {classification.primary_path}, alternatives: {classification.alternative_paths}"
        )

        paths = [classification.primary_path]
        paths.extend(classification.alternative_paths)

        # If classified paths don't match available ones, try to find closest matches
        if available_paths:
            matched_paths = []
            for path in paths:
                if path in available_paths:
                    matched_paths.append(path)
                else:
                    # Find paths that contain any part of the classified path
                    path_parts = path.split(".")
                    for available_path in available_paths:
                        if any(
                            part in available_path for part in path_parts[-2:]
                        ):  # Match on last 2 parts
                            matched_paths.append(available_path)
                            break
                    # If no match found, add original path anyway for fallback
                    matched_paths.append(path)
            paths = matched_paths

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
                            # Extract the most relevant content from memory data
                            # Priority: raw_text > summary > structured_data > full JSON
                            if data.get("raw_text"):
                                content_text = str(data["raw_text"]).strip()
                            elif data.get("summary"):
                                content_text = str(data["summary"]).strip()
                            elif data.get("structured_data"):
                                # For structured data, convert to readable text
                                structured = data["structured_data"]
                                if isinstance(structured, dict):
                                    # Create a readable summary from structured data
                                    import json

                                    content_text = json.dumps(
                                        structured, separators=(",", ": ")
                                    )
                                else:
                                    content_text = str(structured).strip()
                            else:
                                # Fallback to content field or minimal JSON representation
                                if "content" in data:
                                    content_text = str(data["content"]).strip()
                                else:
                                    # Only include essential fields to avoid JSON clutter
                                    essential_fields = {
                                        k: v
                                        for k, v in data.items()
                                        if k
                                        in [
                                            "content",
                                            "summary",
                                            "raw_text",
                                            "key",
                                            "timestamp",
                                        ]
                                    }
                                    import json

                                    content_text = json.dumps(
                                        essential_fields, separators=(",", ": ")
                                    )
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
                            # Extract the most relevant content from memory data
                            # Priority: raw_text > summary > structured_data > full JSON
                            if data.get("raw_text"):
                                content_text = str(data["raw_text"]).strip()
                            elif data.get("summary"):
                                content_text = str(data["summary"]).strip()
                            elif data.get("structured_data"):
                                # For structured data, convert to readable text
                                structured = data["structured_data"]
                                if isinstance(structured, dict):
                                    # Create a readable summary from structured data
                                    import json

                                    content_text = json.dumps(
                                        structured, separators=(",", ": ")
                                    )
                                else:
                                    content_text = str(structured).strip()
                            else:
                                # Fallback to content field or minimal JSON representation
                                if "content" in data:
                                    content_text = str(data["content"]).strip()
                                else:
                                    # Only include essential fields to avoid JSON clutter
                                    essential_fields = {
                                        k: v
                                        for k, v in data.items()
                                        if k
                                        in [
                                            "content",
                                            "summary",
                                            "raw_text",
                                            "key",
                                            "timestamp",
                                        ]
                                    }
                                    import json

                                    content_text = json.dumps(
                                        essential_fields, separators=(",", ": ")
                                    )
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

    async def _should_use_event_search(
        self, query: str, context: Optional[dict] = None
    ) -> Optional[list[str]]:
        """
        Ask LLM whether this query should use event keyword search and what keywords to use.

        Args:
            query: The search query
            context: Optional context for query understanding

        Returns:
            List of keywords to search for if event search should be used, None otherwise
        """
        prompt = f"""Analyze this query to determine if it's asking about specific events, activities, or happenings that would benefit from keyword-based search.

Query: "{query}"

Event queries typically ask about:
- When something happened (temporal: "When did...", "What time...")
- Where something happened (spatial: "Where did...", "At which...")
- What activities occurred ("What did they do...", "What events...")
- Who was involved in activities ("Who did they meet...", "Who attended...")

If this is an event query, extract 2-5 relevant keywords that would help find the specific events/activities mentioned.
Focus on:
- Activity types (meeting, picnic, speech, research, etc.)
- Locations (school, adoption agency, etc.)
- People involved (friends, family, specific names)
- Objects/things mentioned (necklace, painting, etc.)
- Time references (yesterday, last week, etc.)

Respond in JSON format:
{{
  "is_event_query": true/false,
  "keywords": ["keyword1", "keyword2", "keyword3"] or [],
  "reasoning": "brief explanation"
}}

Examples:
- "When did Caroline go to the LGBTQ support group?" → {{"is_event_query": true, "keywords": ["LGBTQ", "support group"], "reasoning": "Asking about when a specific activity happened"}}
- "What is Caroline's favorite color?" → {{"is_event_query": false, "keywords": [], "reasoning": "Asking about preferences, not events"}}
- "Where did Caroline have a picnic?" → {{"is_event_query": true, "keywords": ["picnic"], "reasoning": "Asking about location of specific activity"}}"""

        try:
            response = await self.classifier.llm.ainvoke(prompt)
            content = (
                response.content if hasattr(response, "content") else str(response)
            )

            # Parse JSON response
            import json
            import re

            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())

                if result.get("is_event_query", False):
                    keywords = result.get("keywords", [])
                    if keywords:
                        logger.debug(
                            f"Event query detected: {result.get('reasoning', '')}"
                        )
                        return keywords

            return None

        except Exception as e:
            logger.warning(f"Failed to analyze event query: {e}")
            return None

    async def _search_events_by_keywords(
        self, query: str, namespace: str, keywords: list[str]
    ) -> list[SearchResult]:
        """
        Search for events using keywords by loading the 3 event memories and matching keywords.

        Each event memory (events.self, events.peer, events.group) contains ALL events of that type.
        We load all 3 and do simple keyword matching within their content.

        Args:
            query: Original query for context
            namespace: User namespace
            keywords: Keywords to search for

        Returns:
            List of search results from events
        """
        # The 3 event memory keys that contain all events
        event_keys = ["events.self", "events.peer", "events.group"]

        search_results = []

        try:
            # Load each of the 3 event memories
            for event_key in event_keys:
                try:
                    # Get the event memory content
                    items = await self.store.asearch(namespace, event_key)

                    for _path, data in items:
                        # Extract text content from the event memory
                        event_content = self._extract_content_from_data(data)

                        if not event_content:
                            continue

                        # Check if any keywords match in the content
                        content_lower = event_content.lower()
                        keyword_matches = []

                        for keyword in keywords:
                            if keyword.lower() in content_lower:
                                keyword_matches.append(keyword)

                        # If we have keyword matches, include this event memory
                        if keyword_matches:
                            result = SearchResult(
                                path=event_key,
                                combined_content=event_content,
                                item_count=1,
                                total_length=len(event_content),
                                semantic_distance=0,  # Direct keyword matches
                                namespace=namespace,
                            )
                            search_results.append(result)

                            logger.debug(
                                f"Found event match in {event_key} with keywords: {keyword_matches}"
                            )

                except Exception as e:
                    logger.warning(f"Failed to search event key {event_key}: {e}")
                    continue

            logger.info(
                f"Event keyword search found {len(search_results)} results for keywords: {keywords}"
            )
            return search_results

        except Exception as e:
            logger.error(f"Event keyword search failed: {e}")
            return []

    def _extract_content_from_data(self, data: Any) -> str:
        """Extract readable content from memory data."""
        if isinstance(data, str):
            return data

        if isinstance(data, dict):
            # Priority order for extracting text content
            text_fields = ["raw_text", "content", "summary", "description"]

            for field in text_fields:
                if data.get(field):
                    return str(data[field])

            # Fallback to JSON representation
            import json

            return json.dumps(data, separators=(",", ": "))

        return str(data)

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

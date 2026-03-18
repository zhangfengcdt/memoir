"""
IntelligentSearchEngine that uses LLM to select relevant memory paths.

This engine presents all available memory paths to an LLM and asks it to select
the most relevant ones for a given query, then retrieves memories from those paths.

Features:
- Single-stage LLM path selection for low latency
- Prompt caching support via static/dynamic section markers
- Uses TaxonomyPresets for consistent classification examples
"""

import logging
from dataclasses import dataclass
from typing import Any, ClassVar, Optional

from memoir.taxonomy.taxonomy import TaxonomyPresets

logger = logging.getLogger(__name__)


@dataclass
class IntelligentSearchResult:
    """Simple search result containing memory content and metadata."""

    path: str
    content: str
    metadata: dict
    relevance_score: float = 1.0
    namespace: str = ""


class IntelligentSearchEngine:
    """
    LLM-powered search engine that intelligently selects relevant memory paths.

    This engine uses a single-stage LLM process:
    1. Gets all available memory paths from the store
    2. Asks the LLM to select relevant paths based on semantic meaning and content samples
    3. Retrieves all memories from the selected paths

    Prompt caching is supported via static/dynamic section markers.
    """

    # Cache the built static prompt
    _static_prompt_cache: ClassVar[Optional[str]] = None

    @classmethod
    def _build_static_prompt(cls) -> str:
        """
        Build the static prompt from TaxonomyPresets.

        Uses CLASSIFICATION_EXAMPLES and CATEGORY_DESCRIPTIONS for consistency
        with the IntelligentClassifier.
        """
        if cls._static_prompt_cache is not None:
            return cls._static_prompt_cache

        # Build category descriptions section
        category_lines = []
        for cat, desc in TaxonomyPresets.CATEGORY_DESCRIPTIONS.items():
            category_lines.append(f"- {cat}: {desc}")
        categories_text = "\n".join(category_lines)

        # Build classification examples section (sample ~50 for prompt size)
        # Group by category for better organization
        examples_by_category: dict[str, list[str]] = {}
        for input_text, path, _reason in TaxonomyPresets.CLASSIFICATION_EXAMPLES[:100]:
            category = path.split(".")[0]
            if category not in examples_by_category:
                examples_by_category[category] = []
            if len(examples_by_category[category]) < 6:  # Max 6 per category
                examples_by_category[category].append(f'  - "{input_text}" → {path}')

        example_lines = []
        for category in sorted(examples_by_category.keys()):
            example_lines.append(f"{category.upper()}:")
            example_lines.extend(examples_by_category[category])
        examples_text = "\n".join(example_lines)

        prompt = f"""[STATIC_SECTION_START]
You are a memory search assistant. Your task is to select the most relevant memory paths that would answer the user's query.

TAXONOMY CATEGORIES (3-level paths: category.subcategory.type):
{categories_text}

CLASSIFICATION EXAMPLES (how memories are organized):
{examples_text}

SEARCH INSTRUCTIONS:
- Consider BOTH the semantic path meaning AND the content samples provided
- Match query keywords to the taxonomy categories above
- Return ONLY the exact path names from the available paths, one per line
- If no paths are relevant to the query, return "NONE"
[STATIC_SECTION_END]

[DYNAMIC_SECTION_START]"""

        cls._static_prompt_cache = prompt
        return prompt

    def __init__(self, llm: Any, store: Any):
        """
        Initialize the intelligent search engine.

        Args:
            llm: Language model for path selection
            store: Memory store (ProllyTreeStore)
        """
        self.llm = llm
        self.store = store

    async def search(
        self,
        query: str,
        namespace: str,
        limit: int = 10,
        return_prompts: bool = False,
        person_filter: Optional[str] = None,
    ) -> list[IntelligentSearchResult]:
        """
        Search for relevant memories using LLM path selection.

        Args:
            query: Natural language search query
            namespace: User namespace to search in
            limit: Maximum number of results
            return_prompts: Whether to capture and return LLM prompts
            person_filter: Optional person name to filter paths (e.g., "john")

        Returns:
            List of IntelligentSearchResult objects
        """
        try:
            import time

            step_timings = {}
            llm_prompts = {} if return_prompts else None
            search_start = time.time()
            # Step 1: Path Discovery - Get all available paths from the store
            step1_start = time.time()
            if isinstance(namespace, str):
                namespace_tuple = tuple(namespace.split(":"))
            else:
                namespace_tuple = namespace

            # Step 1a: Get all memories from the store
            all_memories = []
            try:
                all_memories = self.store.search(namespace_tuple, limit=10000)
                logger.info(
                    f"Found {len(all_memories)} memories in namespace {namespace_tuple}"
                )

                # Apply person filtering if specified
                if person_filter:
                    person_prefix = f"{person_filter.lower()}."
                    filtered_memories = []
                    for memory_item in all_memories:
                        _, path, data = memory_item
                        if path.lower().startswith(person_prefix):
                            filtered_memories.append(memory_item)

                    logger.info(
                        f"Person filtering '{person_filter}': {len(all_memories)} -> {len(filtered_memories)} memories"
                    )
                    all_memories = filtered_memories

            except Exception as e:
                logger.error(f"Failed to search memories: {e}")
                return []

            if not all_memories:
                logger.info(f"No memories found in namespace {namespace}")
                # Return timing-only result for early exit
                step_timings["step1_path_discovery"] = round(
                    time.time() - step1_start, 3
                )
                step_timings["step2_path_selection"] = 0.0
                step_timings["step3_memory_retrieval"] = 0.0
                step_timings["total_search"] = round(time.time() - search_start, 3)

                dummy_result = IntelligentSearchResult(
                    path="",
                    content="",
                    metadata={"step_timings": step_timings, "is_timing_only": True},
                    relevance_score=0.0,
                    namespace="",
                )
                return [dummy_result]

            # Check if person filtering resulted in no memories
            if not all_memories and person_filter:
                logger.info(
                    f"No memories found for person '{person_filter}' in namespace {namespace}"
                )
                # Return timing-only result for early exit
                step_timings["step1_path_discovery"] = round(
                    time.time() - step1_start, 3
                )
                step_timings["step2_path_selection"] = 0.0
                step_timings["step3_memory_retrieval"] = 0.0
                step_timings["total_search"] = round(time.time() - search_start, 3)

                dummy_result = IntelligentSearchResult(
                    path="",
                    content="",
                    metadata={
                        "step_timings": step_timings,
                        "is_timing_only": True,
                        "person_filter": person_filter,
                    },
                    relevance_score=0.0,
                    namespace="",
                )
                return [dummy_result]

            # Step 1b: Create path info from loaded memories (like the original logic)
            paths_info = {}
            for _, path, data in all_memories:
                if path not in paths_info and data is not None:
                    # Get a preview of what's stored at this path
                    if isinstance(data, dict) and "memories" in data:
                        # Aggregated memory
                        memory_count = data.get("count", len(data.get("memories", [])))
                        sample_content = ""
                        memories = data.get("memories", [])
                        if memories:
                            content = memories[0].get("content", "")
                            sample_content = str(content)[:100] if content else ""
                        paths_info[path] = {
                            "type": "aggregated",
                            "count": memory_count,
                            "sample": sample_content,
                        }
                    elif isinstance(data, dict):
                        # Single memory
                        content = data.get("content", str(data))
                        paths_info[path] = {
                            "type": "single",
                            "count": 1,
                            "sample": str(content)[:100],
                        }
                    else:
                        # Non-dict data
                        paths_info[path] = {
                            "type": "single",
                            "count": 1,
                            "sample": str(data)[:100] if data else "",
                        }

            if not paths_info:
                logger.info("No valid paths found")
                # Return timing-only result for early exit
                step_timings["step1_path_discovery"] = round(
                    time.time() - step1_start, 3
                )
                step_timings["step2_path_selection"] = 0.0
                step_timings["step3_memory_retrieval"] = 0.0
                step_timings["total_search"] = round(time.time() - search_start, 3)

                dummy_result = IntelligentSearchResult(
                    path="",
                    content="",
                    metadata={"step_timings": step_timings, "is_timing_only": True},
                    relevance_score=0.0,
                    namespace="",
                )
                return [dummy_result]

            step_timings["step1_path_discovery"] = round(time.time() - step1_start, 3)

            # Step 2: Semantic Path Selection - Ask LLM to select relevant paths
            step2_start = time.time()
            selected_paths = await self._select_relevant_paths(
                query, paths_info, limit=limit, llm_prompts=llm_prompts
            )

            if not selected_paths:
                logger.info(f"LLM didn't select any relevant paths for query: {query}")
                # Return timing-only result for early exit
                step_timings["step2_path_selection"] = round(
                    time.time() - step2_start, 3
                )
                step_timings["step3_memory_retrieval"] = 0.0
                step_timings["total_search"] = round(time.time() - search_start, 3)

                metadata = {"step_timings": step_timings, "is_timing_only": True}
                if llm_prompts:
                    metadata["llm_prompts"] = llm_prompts
                dummy_result = IntelligentSearchResult(
                    path="",
                    content="",
                    metadata=metadata,
                    relevance_score=0.0,
                    namespace="",
                )
                return [dummy_result]

            step_timings["step2_path_selection"] = round(time.time() - step2_start, 3)

            # Step 3: Memory Retrieval - Extract results from already-loaded memories
            step3_start = time.time()
            results = []

            # Create a lookup dict for faster access (O(1) instead of O(n))
            memory_dict = {path: data for _, path, data in all_memories}

            for path in selected_paths[:limit]:  # Limit paths processed
                if path in memory_dict:
                    data = memory_dict[path]
                    path_memories = self._extract_memories_from_data(
                        namespace_tuple, path, data
                    )
                    results.extend(path_memories)

                if len(results) >= limit:
                    break

            step_timings["step3_memory_retrieval"] = round(time.time() - step3_start, 3)
            step_timings["total_search"] = round(time.time() - search_start, 3)

            # Store timing info and prompts in the results for access by the API
            for result in results:
                if hasattr(result, "metadata"):
                    if not result.metadata:
                        result.metadata = {}
                    result.metadata["step_timings"] = step_timings
                    if llm_prompts:
                        result.metadata["llm_prompts"] = llm_prompts

            # If no results but we have timing data, create a dummy result to carry timing info
            if not results and step_timings:
                metadata = {"step_timings": step_timings, "is_timing_only": True}
                if llm_prompts:
                    metadata["llm_prompts"] = llm_prompts
                dummy_result = IntelligentSearchResult(
                    path="",
                    content="",
                    metadata=metadata,
                    relevance_score=0.0,
                    namespace="",
                )
                return [dummy_result]

            return results[:limit]

        except Exception as e:
            logger.error(f"Error in intelligent search: {e}")
            # Return timing-only result even for exceptions
            if "step_timings" in locals():
                step_timings["total_search"] = round(time.time() - search_start, 3)
                dummy_result = IntelligentSearchResult(
                    path="",
                    content="",
                    metadata={"step_timings": step_timings, "is_timing_only": True},
                    relevance_score=0.0,
                    namespace="",
                )
                return [dummy_result]
            return []

    async def _select_relevant_paths(
        self,
        query: str,
        paths_info: dict,
        limit: int = 5,
        llm_prompts: Optional[dict] = None,
    ) -> list[str]:
        """
        Use LLM to select the most relevant paths for the query.

        Uses a single LLM call with both path names and content samples.
        Supports prompt caching via static/dynamic section markers.

        Args:
            query: User's search query
            paths_info: Dictionary of path -> info (with content samples)
            limit: Maximum number of paths to select

        Returns:
            List of selected path strings
        """
        # Build paths list with content samples for better selection
        paths_list = []
        for path, info in paths_info.items():
            sample = info.get("sample", "")[:100]  # Limit sample length
            count = info.get("count", 1)
            if sample:
                paths_list.append(f"- {path} ({count} memories): {sample}...")
            else:
                paths_list.append(f"- {path} ({count} memories)")

        paths_text = "\n".join(paths_list)

        # Build prompt with static/dynamic sections for caching
        static_prompt = self._build_static_prompt()
        prompt = f"""{static_prompt}
Select up to {limit} paths that most directly answer the query.

Query: "{query}"

Available memory paths with content samples:
{paths_text}

Selected paths (up to {limit}):"""

        try:
            # Store the prompt if requested
            if llm_prompts is not None:
                llm_prompts["path_selection"] = prompt

            # Call the LLM (use ainvoke since we're in async context)
            messages = [{"role": "user", "content": prompt}]
            if hasattr(self.llm, "ainvoke"):
                response = await self.llm.ainvoke(messages)
            else:
                response = self.llm.invoke(messages)

            # Parse the response
            response_text = response.content.strip()

            if response_text.upper() == "NONE":
                return []

            # Extract path names from response
            selected_paths = []
            for line in response_text.split("\n"):
                line = line.strip()
                # Handle potential formatting like "- path.name" or "path.name"
                if line.startswith("- "):
                    line = line[2:]
                if line and line in paths_info:
                    selected_paths.append(line)

            logger.info(
                f"LLM selected {len(selected_paths)} paths for query '{query}': {selected_paths}"
            )
            return selected_paths

        except Exception as e:
            logger.error(f"Error in LLM path selection: {e}")
            # Fallback: return first few paths
            return list(paths_info.keys())[:3]

    def _extract_memories_from_data(
        self, namespace_tuple: tuple, path: str, data: any
    ) -> list[IntelligentSearchResult]:
        """
        Extract memories from data for a specific path (optimized version).

        Args:
            namespace_tuple: Namespace as tuple
            path: Memory path
            data: Memory data

        Returns:
            List of search results from this data
        """
        results = []
        namespace_str = ":".join(namespace_tuple)

        if isinstance(data, dict) and "memories" in data:
            # Aggregated memory - expand all individual memories
            memories = data.get("memories", [])
            for memory_entry in memories:
                content = memory_entry.get("content", "")
                confidence = memory_entry.get("confidence", 1.0)
                metadata = memory_entry.get("metadata", {})
                metadata.update({"path": path, "source": "aggregated"})

                result = IntelligentSearchResult(
                    path=path,
                    content=str(content),
                    metadata=metadata,
                    relevance_score=confidence,
                    namespace=namespace_str,
                )
                results.append(result)
        else:
            # Single memory
            content = (
                data.get("content", str(data)) if isinstance(data, dict) else str(data)
            )
            confidence = data.get("confidence", 1.0) if isinstance(data, dict) else 1.0
            metadata = data.get("metadata", {}) if isinstance(data, dict) else {}
            metadata.update({"path": path, "source": "single"})

            result = IntelligentSearchResult(
                path=path,
                content=str(content),
                metadata=metadata,
                relevance_score=confidence,
                namespace=namespace_str,
            )
            results.append(result)

        return results

    def _get_memories_from_path(
        self, namespace_tuple: tuple, path: str, all_memories: list
    ) -> list[IntelligentSearchResult]:
        """
        Extract memories from a specific path.

        Args:
            namespace_tuple: Namespace as tuple
            path: Memory path to retrieve from
            all_memories: All memory data from store

        Returns:
            List of search results from this path
        """
        results = []

        for _, stored_path, data in all_memories:
            if stored_path != path:
                continue

            if isinstance(data, dict) and "memories" in data:
                # Aggregated memory - expand all individual memories
                memories = data.get("memories", [])
                for memory_entry in memories:
                    content = memory_entry.get("content", "")
                    confidence = memory_entry.get("confidence", 1.0)
                    metadata = memory_entry.get("metadata", {})
                    metadata.update({"path": path, "source": "aggregated"})

                    # Convert namespace tuple to string
                    namespace_str = ":".join(namespace_tuple)

                    result = IntelligentSearchResult(
                        path=path,
                        content=str(content),
                        metadata=metadata,
                        relevance_score=confidence,
                        namespace=namespace_str,
                    )
                    results.append(result)
            else:
                # Single memory
                content = data.get("content", str(data))
                confidence = data.get("confidence", 1.0)
                metadata = data.get("metadata", {})
                metadata.update({"path": path, "source": "single"})

                # Convert namespace tuple to string
                namespace_str = ":".join(namespace_tuple)

                result = IntelligentSearchResult(
                    path=path,
                    content=str(content),
                    metadata=metadata,
                    relevance_score=confidence,
                    namespace=namespace_str,
                )
                results.append(result)

        return results

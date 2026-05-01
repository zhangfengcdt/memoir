# SPDX-License-Identifier: Apache-2.0
"""
IntelligentSearchEngine that uses LLM to select relevant memory paths.

Two modes:
- ``mode="single"`` (default): one LLM call picks paths from the full path
  inventory. Lowest latency for small/medium stores.
- ``mode="tiered"``: multi-stage drill-down (L1 histogram → L1 pick → optional
  L2 pick → exact-key pick) that mirrors the caller-driven ``[mode=drill]``
  flow used by the ``memory-recall`` skill. Narrower prompts per stage; scales
  better as the store grows.

Both modes reuse the same store data (single ``store.search`` call) and emit
``step_timings`` / ``llm_prompts`` metadata so downstream consumers (UI,
benchmarks, tests) keep observability parity.
"""

import fnmatch
import logging
from dataclasses import dataclass
from typing import Any

from memoir.taxonomy.loader import TaxonomyLoader
from memoir.taxonomy.taxonomy import TaxonomyPresets

logger = logging.getLogger(__name__)

VALID_MODES = ("single", "tiered")

# Escalate to an L2 pick LLM call when a single L1 prefix yields more than this
# many keys. Mirrors the skill's drill-down rule of thumb.
L2_ESCALATION_THRESHOLD = 40


def _filter_keys(keys: list[str], pattern: str | None) -> list[str]:
    """Filter keys by fnmatch glob; pattern=None returns keys unchanged."""
    if not pattern:
        return list(keys)
    return [k for k in keys if fnmatch.fnmatch(k, pattern)]


def _group_by_depth(keys: list[str], n: int) -> dict[str, int]:
    """Group keys by first N dot-separated segments; return {prefix: count}."""
    counts: dict[str, int] = {}
    for key in keys:
        segments = key.split(".")
        prefix = ".".join(segments[:n]) if len(segments) >= n else key
        counts[prefix] = counts.get(prefix, 0) + 1
    return dict(sorted(counts.items()))


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

    Two selection pipelines are available via the ``mode`` argument on
    :meth:`search`:

    - ``mode="single"`` (default) - one LLM call picks 1-3 paths from the full
      path inventory (with content samples). Lowest latency; signal-to-noise
      degrades as the store grows.
    - ``mode="tiered"`` - staged drill-down that mirrors the caller-driven
      ``[mode=drill]`` flow used by the ``memory-recall`` skill:

      1. Pure-compute L1 histogram over stored paths.
      2. LLM #1 picks 2-4 L1 prefixes likely to hold the answer.
      3. Optional LLM #1.5 picks L2 prefixes when any picked L1 exceeds
         :data:`L2_ESCALATION_THRESHOLD` keys.
      4. LLM #2 picks 3-7 exact keys from the descended subset.
      5. Batched memory fetch via :meth:`_extract_memories_from_data`.

    Both pipelines share path-discovery pre-work and emit comparable
    ``step_timings`` / ``llm_prompts`` metadata. Prompt caching markers in the
    single-stage prompt (``[STATIC_SECTION_START]`` / ``[STATIC_SECTION_END]``)
    are also applied to the tiered key-pick stage, which reuses
    :meth:`_select_relevant_paths`.
    """

    def __init__(
        self,
        llm: Any,
        store: Any,
        taxonomy_loader: TaxonomyLoader | None = None,
    ):
        """
        Initialize the intelligent search engine.

        Args:
            llm: Language model for path selection
            store: Memory store (ProllyTreeStore)
            taxonomy_loader: Optional TaxonomyLoader for loading taxonomy from store.
                             When provided, taxonomy data is loaded from the store's taxonomy namespace.
                             When None, falls back to hardcoded TaxonomyPresets.
        """
        self.llm = llm
        self.store = store
        self._taxonomy_loader = taxonomy_loader
        self._static_prompt_cache: str | None = None

    def _get_classification_examples(
        self, limit: int = 100
    ) -> list[tuple[str, str, str]]:
        """Get classification examples from store or fallback to hardcoded.

        Args:
            limit: Maximum number of examples to return.

        Returns:
            List of (input_text, path, reasoning) tuples.
        """
        if self._taxonomy_loader:
            try:
                examples = self._taxonomy_loader.get_examples_from_store(limit=limit)
                if examples:
                    logger.debug(
                        f"[SearchEngine] Loaded {len(examples)} examples FROM STORE"
                    )
                    return examples
            except Exception as e:
                logger.warning(
                    f"[SearchEngine] Failed to load examples from store: {e}"
                )

        # Fallback to hardcoded examples
        logger.debug(f"[SearchEngine] Using FALLBACK examples (limit={limit})")
        return TaxonomyPresets.CLASSIFICATION_EXAMPLES[:limit]

    def _get_category_descriptions(self) -> dict[str, str]:
        """Get category descriptions from store or fallback to hardcoded.

        Returns:
            Dict mapping category to description.
        """
        if self._taxonomy_loader:
            try:
                descriptions = self._taxonomy_loader.get_descriptions_from_store()
                if descriptions:
                    logger.debug(
                        f"[SearchEngine] Loaded {len(descriptions)} descriptions FROM STORE"
                    )
                    return descriptions
            except Exception as e:
                logger.warning(
                    f"[SearchEngine] Failed to load descriptions from store: {e}"
                )

        # Fallback to hardcoded descriptions
        logger.debug("[SearchEngine] Using FALLBACK category descriptions")
        return TaxonomyPresets.CATEGORY_DESCRIPTIONS

    def _build_static_prompt(self) -> str:
        """
        Build the static prompt from store or TaxonomyPresets.

        Uses CLASSIFICATION_EXAMPLES and CATEGORY_DESCRIPTIONS for consistency
        with the IntelligentClassifier.
        """
        if self._static_prompt_cache is not None:
            return self._static_prompt_cache

        # Build category descriptions section (from store or fallback)
        category_lines = []
        for cat, desc in self._get_category_descriptions().items():
            category_lines.append(f"- {cat}: {desc}")
        categories_text = "\n".join(category_lines)

        # Build classification examples section (sample ~100 for prompt size)
        # Group by category for better organization
        examples_by_category: dict[str, list[str]] = {}
        for input_text, path, _reason in self._get_classification_examples(100):
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

        self._static_prompt_cache = prompt
        return prompt

    async def search(
        self,
        query: str,
        namespace: str,
        limit: int = 10,
        return_prompts: bool = False,
        person_filter: str | None = None,
        mode: str = "single",
    ) -> list[IntelligentSearchResult]:
        """
        Search for relevant memories using LLM path selection.

        Args:
            query: Natural language search query
            namespace: User namespace to search in
            limit: Maximum number of results
            return_prompts: Whether to capture and return LLM prompts
            person_filter: Optional person name to filter paths (e.g., "john")
            mode: "single" (default, one LLM call) or "tiered" (multi-stage
                drill-down: L1 pick → optional L2 pick → key pick). Unknown
                values raise ValueError.

        Returns:
            List of IntelligentSearchResult objects
        """
        if mode not in VALID_MODES:
            raise ValueError(
                f"Unknown search mode {mode!r}; expected one of {VALID_MODES}"
            )

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

            # Fork to tiered pipeline once common pre-work (namespace parsing,
            # store read, paths_info build) is done. The tiered path runs its
            # own multi-stage selection and memory retrieval, then returns.
            if mode == "tiered":
                return await self._search_tiered(
                    query=query,
                    namespace_tuple=namespace_tuple,
                    limit=limit,
                    all_memories=all_memories,
                    paths_info=paths_info,
                    step_timings=step_timings,
                    llm_prompts=llm_prompts,
                    search_start=search_start,
                )

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
                    result.metadata["mode"] = "single"
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

    async def _search_tiered(
        self,
        query: str,
        namespace_tuple: tuple,
        limit: int,
        all_memories: list,
        paths_info: dict,
        step_timings: dict,
        llm_prompts: dict | None,
        search_start: float,
    ) -> list[IntelligentSearchResult]:
        """Multi-stage drill-down selection, mirroring the skill's ``[mode=drill]``.

        Pipeline: L1 histogram → LLM picks L1 prefixes → (optional LLM L2 pick
        when an L1 is too wide) → LLM picks exact keys → batched memory fetch.
        """
        import time

        all_paths = list(paths_info.keys())

        # Step 2a: L1 survey (pure compute — no LLM).
        step_l1 = time.time()
        l1_counts = _group_by_depth(all_paths, 1)
        step_timings["l1_survey"] = round(time.time() - step_l1, 3)

        # Step 2b: L1 pick (LLM call #1).
        step_l1_llm = time.time()
        picked_l1 = await self._pick_l1_prefixes(
            query, l1_counts, limit=4, llm_prompts=llm_prompts
        )
        step_timings["l1_pick_llm"] = round(time.time() - step_l1_llm, 3)
        if not picked_l1:
            # Defensive fallback: take top-N by count so the search still
            # produces something rather than dying silently.
            picked_l1 = [
                p for p, _ in sorted(l1_counts.items(), key=lambda x: -x[1])[:3]
            ]
            logger.info(
                f"Tiered: L1 pick empty/failed, falling back to top-N by count: {picked_l1}"
            )

        # Step 2c: Descend from L1 into concrete keys.
        step_descend = time.time()
        descended_paths: list[str] = []
        oversized_l1: dict[str, list[str]] = {}
        for l1 in picked_l1:
            scoped = _filter_keys(all_paths, f"{l1}.*")
            if len(scoped) > L2_ESCALATION_THRESHOLD:
                oversized_l1[l1] = scoped
            else:
                descended_paths.extend(scoped)
        step_timings["descend"] = round(time.time() - step_descend, 3)

        # Step 2d: Optional L2 pick (LLM call #1.5) for any wide L1.
        if oversized_l1:
            step_l2_llm = time.time()
            for l1, scoped in oversized_l1.items():
                l2_counts = _group_by_depth(scoped, 2)
                picked_l2 = await self._pick_l2_prefixes(
                    query,
                    l1,
                    l2_counts,
                    limit=3,
                    llm_prompts=llm_prompts,
                )
                if not picked_l2:
                    picked_l2 = [
                        p for p, _ in sorted(l2_counts.items(), key=lambda x: -x[1])[:2]
                    ]
                    logger.info(
                        f"Tiered: L2 pick empty/failed for '{l1}', "
                        f"falling back to top-N by count: {picked_l2}"
                    )
                for l2_prefix in picked_l2:
                    descended_paths.extend(_filter_keys(scoped, f"{l2_prefix}.*"))
            step_timings["l2_pick_llm"] = round(time.time() - step_l2_llm, 3)

        # Step 2e: Key pick (LLM call #2) — choose exact keys from descended set.
        step_key_llm = time.time()
        # Dedupe while preserving order; filter to known paths_info entries.
        seen: set[str] = set()
        descended_info: dict[str, dict] = {}
        for p in descended_paths:
            if p in seen or p not in paths_info:
                continue
            seen.add(p)
            descended_info[p] = paths_info[p]

        if not descended_info:
            step_timings["key_pick_llm"] = 0.0
            step_timings["memory_retrieval"] = 0.0
            step_timings["total_search"] = round(time.time() - search_start, 3)
            metadata = {
                "step_timings": step_timings,
                "is_timing_only": True,
                "mode": "tiered",
            }
            if llm_prompts:
                metadata["llm_prompts"] = llm_prompts
            return [
                IntelligentSearchResult(
                    path="",
                    content="",
                    metadata=metadata,
                    relevance_score=0.0,
                    namespace="",
                )
            ]

        selected_paths = await self._select_relevant_paths(
            query, descended_info, limit=limit, llm_prompts=llm_prompts
        )
        # _select_relevant_paths writes under "path_selection"; rename for the
        # tiered-mode key naming the plan specifies (l1_pick / l2_pick / key_pick).
        if llm_prompts is not None and "path_selection" in llm_prompts:
            llm_prompts["key_pick"] = llm_prompts.pop("path_selection")
        step_timings["key_pick_llm"] = round(time.time() - step_key_llm, 3)

        # Step 3: Memory retrieval (same shape as single-stage).
        step_retrieval = time.time()
        memory_dict = {path: data for _, path, data in all_memories}
        results: list[IntelligentSearchResult] = []
        for path in selected_paths[:limit]:
            if path in memory_dict:
                path_memories = self._extract_memories_from_data(
                    namespace_tuple, path, memory_dict[path]
                )
                results.extend(path_memories)
            if len(results) >= limit:
                break
        step_timings["memory_retrieval"] = round(time.time() - step_retrieval, 3)
        step_timings["total_search"] = round(time.time() - search_start, 3)

        for result in results:
            if hasattr(result, "metadata"):
                if not result.metadata:
                    result.metadata = {}
                result.metadata["step_timings"] = step_timings
                result.metadata["mode"] = "tiered"
                if llm_prompts:
                    result.metadata["llm_prompts"] = llm_prompts

        if not results:
            metadata = {
                "step_timings": step_timings,
                "is_timing_only": True,
                "mode": "tiered",
            }
            if llm_prompts:
                metadata["llm_prompts"] = llm_prompts
            return [
                IntelligentSearchResult(
                    path="",
                    content="",
                    metadata=metadata,
                    relevance_score=0.0,
                    namespace="",
                )
            ]

        return results[:limit]

    async def _pick_l1_prefixes(
        self,
        query: str,
        l1_counts: dict[str, int],
        limit: int = 4,
        llm_prompts: dict | None = None,
    ) -> list[str]:
        """LLM picks 2-4 top-level prefixes likely to hold the answer."""
        if not l1_counts:
            return []

        histogram_lines = [
            f"- {prefix} ({count})" for prefix, count in l1_counts.items()
        ]
        histogram_text = "\n".join(histogram_lines)

        prompt = f"""You are a memory search assistant. You will receive a user query and a histogram of top-level taxonomy prefixes (with memory counts). Pick the prefixes most likely to contain memories that answer the query.

Query: "{query}"

Top-level prefixes in the store:
{histogram_text}

Instructions:
- Select up to {limit} prefixes whose names plausibly cover the query.
- Return ONLY prefix names, one per line. No explanation, no prose.
- If none are relevant, return "NONE".

Selected prefixes (up to {limit}):"""

        if llm_prompts is not None:
            llm_prompts["l1_pick"] = prompt

        try:
            messages = [{"role": "user", "content": prompt}]
            if hasattr(self.llm, "ainvoke"):
                response = await self.llm.ainvoke(messages)
            else:
                response = self.llm.invoke(messages)
            response_text = response.content.strip()
            if response_text.upper() == "NONE":
                return []
            valid = set(l1_counts.keys())
            picked: list[str] = []
            for line in response_text.split("\n"):
                line = line.strip().lstrip("- ").strip()
                if line and line in valid and line not in picked:
                    picked.append(line)
            logger.info(f"Tiered: L1 picked {picked} for query '{query}'")
            return picked
        except Exception as e:
            logger.error(f"Tiered: L1 pick LLM failed: {e}")
            return []

    async def _pick_l2_prefixes(
        self,
        query: str,
        l1: str,
        l2_counts: dict[str, int],
        limit: int = 3,
        llm_prompts: dict | None = None,
    ) -> list[str]:
        """LLM narrows a wide L1 prefix down to 2-3 L2 prefixes."""
        if not l2_counts:
            return []

        histogram_lines = [
            f"- {prefix} ({count})" for prefix, count in l2_counts.items()
        ]
        histogram_text = "\n".join(histogram_lines)

        prompt = f"""You are a memory search assistant drilling into a large taxonomy branch.

Query: "{query}"

The branch '{l1}' has many keys. Here is its L2 histogram:
{histogram_text}

Instructions:
- Select up to {limit} L2 prefixes under '{l1}' most likely to contain memories that answer the query.
- Return ONLY L2 prefix names (as shown above, including the '{l1}.' part), one per line.
- If none are relevant, return "NONE".

Selected prefixes (up to {limit}):"""

        # Accumulate L2 prompts per-l1 so a single query with multiple wide L1s
        # still exposes each sub-prompt to callers.
        if llm_prompts is not None:
            existing = llm_prompts.get("l2_pick")
            combined_entry = f"[l1={l1}]\n{prompt}"
            if existing:
                llm_prompts["l2_pick"] = f"{existing}\n\n{combined_entry}"
            else:
                llm_prompts["l2_pick"] = combined_entry

        try:
            messages = [{"role": "user", "content": prompt}]
            if hasattr(self.llm, "ainvoke"):
                response = await self.llm.ainvoke(messages)
            else:
                response = self.llm.invoke(messages)
            response_text = response.content.strip()
            if response_text.upper() == "NONE":
                return []
            valid = set(l2_counts.keys())
            picked: list[str] = []
            for line in response_text.split("\n"):
                line = line.strip().lstrip("- ").strip()
                if line and line in valid and line not in picked:
                    picked.append(line)
            logger.info(f"Tiered: L2 picked {picked} under '{l1}'")
            return picked
        except Exception as e:
            logger.error(f"Tiered: L2 pick LLM failed for '{l1}': {e}")
            return []

    async def _select_relevant_paths(
        self,
        query: str,
        paths_info: dict,
        limit: int = 5,
        llm_prompts: dict | None = None,
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

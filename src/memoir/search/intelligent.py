"""
IntelligentSearchEngine that uses LLM to select relevant memory paths.

This engine presents all available memory paths to an LLM and asks it to select
the most relevant ones for a given query, then retrieves memories from those paths.
"""

import logging
from dataclasses import dataclass
from typing import Any

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

    Instead of trying to do complex semantic matching, this engine:
    1. Gets all available memory paths from the store
    2. Asks the LLM to select the most relevant paths for the query
    3. Retrieves all memories from the selected paths
    """

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
        self, query: str, namespace: str, limit: int = 10
    ) -> list[IntelligentSearchResult]:
        """
        Search for relevant memories using LLM path selection.

        Args:
            query: Natural language search query
            namespace: User namespace to search in
            limit: Maximum number of results

        Returns:
            List of IntelligentSearchResult objects
        """
        try:
            # Step 1: Get all available paths from the store using list_keys()
            if isinstance(namespace, str):
                namespace_tuple = tuple(namespace.split(":"))
            else:
                namespace_tuple = namespace

            # Use VersionedKvStore's list_keys() to get ALL keys, then filter by namespace and get data
            try:
                if hasattr(self.store, "tree") and hasattr(
                    self.store.tree, "list_keys"
                ):
                    all_keys = self.store.tree.list_keys()
                elif hasattr(self.store, "_keys"):
                    all_keys = list(self.store._keys)
                else:
                    all_memories = self.store.search(namespace_tuple, limit=1000)
                    if not all_memories:
                        logger.info(f"No memories found in namespace {namespace}")
                        return []
                    all_keys = None
            except Exception:
                all_memories = self.store.search(namespace_tuple, limit=1000)
                if not all_memories:
                    logger.info(f"No memories found in namespace {namespace}")
                    return []
                all_keys = None

            if all_keys is not None:
                all_memories = []

                for key in all_keys:
                    # Convert bytes key to string if needed
                    key_str = (
                        key.decode("utf-8") if isinstance(key, bytes) else str(key)
                    )

                    # Parse the key string back to components
                    key_parts = key_str.split(":")

                    # Check if this key matches our target namespace
                    if len(key_parts) >= len(namespace_tuple):
                        key_namespace = tuple(key_parts[: len(namespace_tuple)])
                        if key_namespace == namespace_tuple:
                            # Extract the path (everything after the namespace)
                            path = (
                                ".".join(key_parts[len(namespace_tuple) :])
                                if len(key_parts) > len(namespace_tuple)
                                else key_parts[-1]
                            )

                            # Get the data for this key
                            try:
                                data = self.store.get(namespace_tuple, path)
                                if data is not None:
                                    all_memories.append((namespace_tuple, path, data))
                                else:
                                    logger.warning(f"Data is None for key {key_str}")
                            except Exception as e:
                                logger.warning(
                                    f"Could not retrieve data for key {key_str}: {e}"
                                )
                                continue

            if not all_memories:
                logger.info(f"No memories found in namespace {namespace}")
                return []

            # Extract unique paths and create path info
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
                return []

            # Step 2: Ask LLM to select relevant paths
            selected_paths = await self._select_relevant_paths(query, paths_info)

            if not selected_paths:
                logger.info(f"LLM didn't select any relevant paths for query: {query}")
                return []

            # Step 3: Retrieve memories from selected paths
            results = []
            for path in selected_paths[:limit]:  # Limit paths processed
                path_memories = self._get_memories_from_path(
                    namespace_tuple, path, all_memories
                )
                results.extend(path_memories)

                if len(results) >= limit:
                    break

            return results[:limit]

        except Exception as e:
            logger.error(f"Error in intelligent search: {e}")
            return []

    async def _select_relevant_paths(self, query: str, paths_info: dict) -> list[str]:
        """
        Use LLM to select the most relevant paths for the query.

        Args:
            query: User's search query
            paths_info: Dictionary of path -> info

        Returns:
            List of selected path strings
        """
        # Create the prompt for path selection (semantic paths only, no content samples)
        paths_list = []
        for path, _info in paths_info.items():
            paths_list.append(f"- {path}")

        paths_text = "\n".join(paths_list)

        prompt = f"""You are selecting memory paths based on semantic meaning. Find paths that would logically contain the answer to this query.

Query: "{query}"

Available paths:
{paths_text}

Example:
- Query: "What is my favorite color?" → select "preferences.personal.favorites.color"
- Query: "Where do I work?" → select "profile.professional.current.company"
- Query: "What programming languages do I know?" → select "profile.professional.skills.technical.programming"

Instructions:
- Select 1-3 paths that most directly answer the query
- Focus on semantic path meaning, not guessing content
- If asking about location → select paths with "living", "address", "location"
- If asking about work → select paths with "professional", "company", "career"
- If asking about skills → select paths with "skills", "technical"
- Return ONLY the exact path names, one per line

Selected paths:"""

        try:
            # Call the LLM
            messages = [{"role": "user", "content": prompt}]
            response = self.llm.invoke(messages)

            # Parse the response
            response_text = response.content.strip()

            if response_text.upper() == "NONE":
                return []

            # Extract path names from response
            selected_paths = []
            for line in response_text.split("\n"):
                line = line.strip()
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

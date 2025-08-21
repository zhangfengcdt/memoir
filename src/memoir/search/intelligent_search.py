"""
IntelligentSearchEngine that uses LLM to select relevant memory paths.

This engine presents all available memory paths to an LLM and asks it to select
the most relevant ones for a given query, then retrieves memories from those paths.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class IntelligentSearchResult:
    """Simple search result containing memory content and metadata."""
    path: str
    content: str
    metadata: dict
    confidence: float = 1.0


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
        self, 
        query: str, 
        namespace: str, 
        limit: int = 10
    ) -> List[IntelligentSearchResult]:
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
            # Step 1: Get all available paths from the store
            namespace_tuple = (namespace,) if isinstance(namespace, str) else tuple(namespace.split(":"))
            all_memories = self.store.search(namespace_tuple, limit=1000)
            
            if not all_memories:
                logger.info(f"No memories found in namespace {namespace}")
                return []
            
            # Extract unique paths and create path info
            paths_info = {}
            for _, path, data in all_memories:
                if path not in paths_info:
                    # Get a preview of what's stored at this path
                    if isinstance(data, dict) and "memories" in data:
                        # Aggregated memory
                        memory_count = data.get("count", len(data.get("memories", [])))
                        sample_content = ""
                        memories = data.get("memories", [])
                        if memories:
                            sample_content = memories[0].get("content", "")[:100]
                        paths_info[path] = {
                            "type": "aggregated",
                            "count": memory_count,
                            "sample": sample_content
                        }
                    else:
                        # Single memory
                        content = data.get("content", str(data))
                        paths_info[path] = {
                            "type": "single", 
                            "count": 1,
                            "sample": str(content)[:100]
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
                path_memories = self._get_memories_from_path(namespace_tuple, path, all_memories)
                results.extend(path_memories)
                
                if len(results) >= limit:
                    break
            
            return results[:limit]
            
        except Exception as e:
            logger.error(f"Error in intelligent search: {e}")
            return []
    
    async def _select_relevant_paths(
        self, 
        query: str, 
        paths_info: dict
    ) -> List[str]:
        """
        Use LLM to select the most relevant paths for the query.
        
        Args:
            query: User's search query
            paths_info: Dictionary of path -> info
            
        Returns:
            List of selected path strings
        """
        # Create the prompt for path selection
        paths_list = []
        for path, info in paths_info.items():
            sample = info["sample"][:60] + "..." if len(info["sample"]) > 60 else info["sample"]
            paths_list.append(f"- {path} ({info['count']} memories): {sample}")
        
        paths_text = "\n".join(paths_list)
        
        prompt = f"""Given this search query: "{query}"

Please select the most relevant memory paths from the following available paths:

{paths_text}

Instructions:
- Select 1-3 paths that are most likely to contain information relevant to the query
- Return ONLY the path names, one per line, no explanations
- If no paths seem relevant, return "NONE"

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
            
            logger.info(f"LLM selected {len(selected_paths)} paths for query '{query}': {selected_paths}")
            return selected_paths
            
        except Exception as e:
            logger.error(f"Error in LLM path selection: {e}")
            # Fallback: return first few paths
            return list(paths_info.keys())[:3]
    
    def _get_memories_from_path(
        self, 
        namespace_tuple: tuple, 
        path: str, 
        all_memories: list
    ) -> List[IntelligentSearchResult]:
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
                    metadata.update({
                        "path": path,
                        "source": "aggregated"
                    })
                    
                    result = IntelligentSearchResult(
                        path=path,
                        content=str(content),
                        metadata=metadata,
                        confidence=confidence
                    )
                    results.append(result)
            else:
                # Single memory
                content = data.get("content", str(data))
                confidence = data.get("confidence", 1.0)
                metadata = data.get("metadata", {})
                metadata.update({
                    "path": path,
                    "source": "single"
                })
                
                result = IntelligentSearchResult(
                    path=path,
                    content=str(content),
                    metadata=metadata,
                    confidence=confidence
                )
                results.append(result)
        
        return results
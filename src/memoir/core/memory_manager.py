"""
Enhanced MemoryStoreManager integrating LangMem with ProllyTree.
Provides high-performance semantic memory with versioning capabilities.
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Optional, Union

from langmem.knowledge.extraction import MemoryStoreManager
from pydantic import BaseModel, Field

from memoir.search.hierarchical_search import (
    HierarchicalSearchEngine,
    SearchStrategy,
)

from .profile_manager import ProfileManager
from .prolly_adapter import ProllyTreeStore

logger = logging.getLogger(__name__)


class Memory(BaseModel):
    """Represents a memory object compatible with LangMem."""

    id: str = Field(description="Memory identifier")
    content: Any = Field(description="Memory content")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Memory metadata"
    )


class MemoryVersion(BaseModel):
    """Represents a version of a memory."""

    commit_id: str
    timestamp: float
    content: Any
    metadata: dict[str, Any]
    message: str
    author: Optional[str] = None


class ProllyTreeMemoryStoreManager(MemoryStoreManager):
    """
    Enhanced MemoryStoreManager with ProllyTree backend.
    Provides semantic classification, hierarchical search, and versioning.
    """

    def __init__(
        self,
        prolly_path: str,
        model: Union[str, Any] = "gpt-3.5-turbo",  # Default model
        classifier: Optional[Any] = None,  # SemanticClassifier instance
        enable_versioning: bool = True,
        enable_fast_classification: bool = True,
        cache_size: int = 10000,
        **kwargs,
    ):
        """
        Initialize enhanced memory manager.

        Args:
            prolly_path: Path to ProllyTree database
            classifier: SemanticClassifier instance with LLM
            enable_versioning: Enable git-like versioning
            enable_fast_classification: Use optimized classifier
            cache_size: Size of internal caches
            **kwargs: Additional arguments for MemoryStoreManager
        """
        # Initialize classifier - must be provided for production use
        self.classifier = classifier

        # Initialize ProllyTree store
        self.prolly_store = ProllyTreeStore(
            path=prolly_path,
            classifier=self.classifier,
            enable_versioning=enable_versioning,
            cache_size=cache_size,
        )

        # Initialize profile manager
        self.profile_manager = ProfileManager(self.prolly_store)

        # Initialize search engine with profile manager
        self.search_engine = HierarchicalSearchEngine(
            store=self.prolly_store,
            classifier=self.classifier,
            profile_manager=self.profile_manager,
        )

        self.enable_versioning = enable_versioning
        self.enable_fast_classification = enable_fast_classification

        # Performance metrics
        self._metrics = {
            "searches": 0,
            "search_time_ms": [],
            "writes": 0,
            "write_time_ms": [],
            "classifications": 0,
            "classification_time_ms": [],
        }

        # Initialize parent class with ProllyTree store
        super().__init__(model, store=self.prolly_store, **kwargs)

    async def search_memories(
        self,
        query: str,
        namespace: str,
        strategy: SearchStrategy = SearchStrategy.SPECIFIC_TO_GENERAL,
        context: Optional[dict] = None,
        limit: int = 10,
    ) -> list[Memory]:
        """
        Search memories using hierarchical semantic search.

        Args:
            query: Natural language search query
            namespace: User namespace
            strategy: Search strategy to use
            context: Optional context for query understanding
            limit: Maximum results to return

        Returns:
            List of Memory objects
        """
        start_time = time.time()
        self._metrics["searches"] += 1

        # Use hierarchical search
        search_results = await self.search_engine.search(
            query=query, namespace=namespace, strategy=strategy, context=context
        )

        # Convert to Memory objects
        memories = []
        for result in search_results[:limit]:
            memory = Memory(
                id=result.key,
                content=result.content,
                metadata={
                    "namespace": result.namespace,
                    "relevance_score": result.relevance_score,
                    "semantic_distance": result.semantic_distance,
                    "timestamp": result.timestamp,
                },
            )
            memories.append(memory)

        search_time = (time.time() - start_time) * 1000
        self._metrics["search_time_ms"].append(search_time)

        # logger.info(
        #     f"Search completed in {search_time:.2f}ms, found {len(memories)} memories"
        # )

        return memories

    async def store_memory(
        self,
        content: Any,
        namespace: str,
        metadata: Optional[dict] = None,
        auto_classify: bool = True,
    ) -> str:
        """
        Store a memory with automatic semantic classification.

        Args:
            content: Memory content to store
            namespace: User namespace
            metadata: Optional metadata
            auto_classify: Whether to auto-classify the content

        Returns:
            Semantic key where memory was stored
        """
        start_time = time.time()
        self._metrics["writes"] += 1

        if auto_classify and self.classifier:
            # Use LLM classification
            classification_start = time.time()
            self._metrics["classifications"] += 1

            # Use async classification
            classification = await self.classifier.classify_async(str(content))
            semantic_key = classification.primary_path

            classification_time = (time.time() - classification_start) * 1000
            self._metrics["classification_time_ms"].append(classification_time)

            # Apply profile updates if detected
            if (
                hasattr(classification, "profile_updates")
                and classification.profile_updates
            ):
                try:
                    await self.profile_manager.apply_profile_updates(
                        classification.profile_updates, metadata
                    )
                    # logger.info(
                    #     f"Applied {len(classification.profile_updates)} profile updates"
                    # )
                except Exception as e:
                    logger.error(f"Failed to apply profile updates: {e}")

            # Add classification metadata
            if metadata is None:
                metadata = {}
            metadata["classification_confidence"] = classification.confidence
            metadata["classification_reasoning"] = classification.reasoning

        else:
            # Use provided key or generate one
            semantic_key = metadata.get("key") if metadata else None
            if not semantic_key:
                semantic_key = "context.current.session.topic.main"

        # Store using the synchronous method (prolly store method signature: namespace, content, key)
        self.prolly_store.store_memory(namespace, content, semantic_key)

        write_time = (time.time() - start_time) * 1000
        self._metrics["write_time_ms"].append(write_time)

        # logger.debug(f"Stored memory at {semantic_key} in {write_time:.2f}ms")

        return semantic_key

    async def get_memory_versions(
        self, semantic_key: str, namespace: str, limit: int = 10
    ) -> list[MemoryVersion]:
        """
        Get version history for a memory.

        Args:
            semantic_key: Semantic taxonomy key
            namespace: User namespace
            limit: Maximum versions to return

        Returns:
            List of memory versions
        """
        if not self.enable_versioning:
            logger.warning("Versioning is not enabled")
            return []

        history = await self.prolly_store.get_history(namespace, semantic_key, limit)

        versions = []
        for item in history:
            version = MemoryVersion(
                commit_id=item.version or "unknown",
                timestamp=item.timestamp,
                content=item.content,
                metadata=item.metadata,
                message=f"Update {semantic_key}",
            )
            versions.append(version)

        return versions

    async def time_travel(
        self, namespace: str, target_time: Union[datetime, float]
    ) -> dict[str, Any]:
        """
        Get all memories as they were at a specific time.

        Args:
            namespace: User namespace
            target_time: Target datetime or unix timestamp

        Returns:
            Dictionary of memories at that time
        """
        if isinstance(target_time, datetime):
            timestamp = target_time.timestamp()
        else:
            timestamp = target_time

        return await self.prolly_store.time_travel(namespace, timestamp)

    async def compare_memory_states(
        self,
        namespace: str,
        time1: Union[datetime, float],
        time2: Union[datetime, float],
    ) -> dict[str, Any]:
        """
        Compare memory states between two points in time.

        Args:
            namespace: User namespace
            time1: First timestamp
            time2: Second timestamp

        Returns:
            Comparison results with added/removed/changed memories
        """
        if isinstance(time1, datetime):
            time1 = time1.timestamp()
        if isinstance(time2, datetime):
            time2 = time2.timestamp()

        state1 = await self.time_travel(namespace, time1)
        state2 = await self.time_travel(namespace, time2)

        keys1 = set(state1.keys())
        keys2 = set(state2.keys())

        comparison = {
            "added": {k: state2[k] for k in keys2 - keys1},
            "removed": {k: state1[k] for k in keys1 - keys2},
            "changed": {},
            "unchanged": [],
        }

        for key in keys1 & keys2:
            if state1[key] != state2[key]:
                comparison["changed"][key] = {
                    "before": state1[key],
                    "after": state2[key],
                }
            else:
                comparison["unchanged"].append(key)

        return comparison

    async def branch_memories(self, namespace: str, branch_name: str) -> str:
        """
        Create a new branch of memories for experimentation.

        Args:
            namespace: User namespace
            branch_name: Name for the new branch

        Returns:
            Branch identifier
        """
        if not self.enable_versioning:
            raise ValueError("Branching requires versioning to be enabled")

        # Implementation would create a new branch in ProllyTree
        branch_id = f"{namespace}:{branch_name}:{time.time()}"
        # logger.info(f"Created memory branch: {branch_id}")

        return branch_id

    async def merge_memories(
        self,
        namespace: str,
        source_branch: str,
        target_branch: str = "main",
        strategy: str = "ours",
    ) -> dict[str, Any]:
        """
        Merge memories from one branch to another.

        Args:
            namespace: User namespace
            source_branch: Source branch to merge from
            target_branch: Target branch to merge into
            strategy: Merge strategy ("ours", "theirs", "union")

        Returns:
            Merge results with conflicts if any
        """
        if not self.enable_versioning:
            raise ValueError("Merging requires versioning to be enabled")

        # Implementation would handle branch merging
        merge_result = {"merged": 0, "conflicts": [], "strategy": strategy}

        # logger.info(f"Merged {source_branch} into {target_branch}")

        return merge_result

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get performance metrics for the memory system."""
        metrics = self._metrics.copy()

        # Calculate averages
        if metrics["search_time_ms"]:
            metrics["avg_search_time_ms"] = sum(metrics["search_time_ms"]) / len(
                metrics["search_time_ms"]
            )
            metrics["p95_search_time_ms"] = (
                sorted(metrics["search_time_ms"])[
                    int(len(metrics["search_time_ms"]) * 0.95)
                ]
                if len(metrics["search_time_ms"]) > 1
                else metrics["search_time_ms"][0]
            )

        if metrics["write_time_ms"]:
            metrics["avg_write_time_ms"] = sum(metrics["write_time_ms"]) / len(
                metrics["write_time_ms"]
            )

        if metrics["classification_time_ms"]:
            metrics["avg_classification_time_ms"] = sum(
                metrics["classification_time_ms"]
            ) / len(metrics["classification_time_ms"])

        # Add store statistics (synchronous method)
        try:
            store_stats = self.prolly_store.get_statistics()
            metrics["store"] = store_stats
        except Exception as e:
            logger.warning(f"Failed to get store statistics: {e}")
            metrics["store"] = {}

        return metrics

    async def optimize_memory_layout(self, namespace: str) -> dict[str, Any]:
        """
        Optimize memory layout for better performance.
        Reorganizes memories based on access patterns.

        Args:
            namespace: User namespace to optimize

        Returns:
            Optimization results
        """
        start_time = time.time()

        # Get all memories
        all_keys = await self.prolly_store.alist(namespace)

        # Analyze access patterns (would need access logs in production)
        # For now, we'll just report current organization

        category_counts = {}
        depth_counts = {}

        for key in all_keys:
            parts = key.split(".")
            if parts:
                category = parts[0]
                category_counts[category] = category_counts.get(category, 0) + 1

                depth = len(parts)
                depth_counts[depth] = depth_counts.get(depth, 0) + 1

        optimization_time = time.time() - start_time

        return {
            "total_memories": len(all_keys),
            "categories": category_counts,
            "depth_distribution": depth_counts,
            "optimization_time_seconds": optimization_time,
            "recommendations": [
                "Consider moving frequently accessed memories to shallower paths",
                "Group related memories under common prefixes for faster retrieval",
                "Archive old memories to separate namespace for better performance",
            ],
        }

    async def export_memories(
        self, namespace: str, output_path: str, format: str = "json"
    ) -> None:
        """
        Export memories to file.

        Args:
            namespace: Namespace to export
            output_path: Output file path
            format: Export format (json, csv, markdown)
        """
        self.prolly_store.export_namespace(namespace, output_path)
        # logger.info(f"Exported memories to {output_path}")

    async def import_memories(
        self, input_path: str, namespace: Optional[str] = None
    ) -> int:
        """
        Import memories from file.

        Args:
            input_path: Input file path
            namespace: Override namespace (uses file namespace if None)

        Returns:
            Number of memories imported
        """
        self.prolly_store.import_namespace(input_path, namespace)

        # Count imported memories
        if namespace:
            count = len(await self.prolly_store.alist(namespace))
        else:
            # Parse file to get count
            with open(input_path) as f:
                data = json.load(f)
                count = len(data.get("memories", {}))

        # logger.info(f"Imported {count} memories from {input_path}")
        return count

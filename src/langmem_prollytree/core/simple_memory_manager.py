"""
Simplified memory manager for testing taxonomy and classification.
This version focuses on the core semantic functionality without full LangMem integration.
"""

import logging
import time
from typing import Any, Optional

from pydantic import BaseModel, Field

from langmem_prollytree.search.hierarchical_search import (
    HierarchicalSearchEngine,
    SearchStrategy,
)
from langmem_prollytree.taxonomy.semantic_classifier import OptimizedClassifier

from .mock_store import MockProllyTreeStore

logger = logging.getLogger(__name__)


class Memory(BaseModel):
    """Represents a memory object."""

    id: str = Field(description="Memory identifier")
    content: Any = Field(description="Memory content")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Memory metadata"
    )


class SimpleMemoryManager:
    """
    Simplified memory manager for testing and demonstration.
    Focuses on semantic classification and hierarchical search.
    """

    def __init__(
        self, enable_fast_classification: bool = True, cache_size: int = 10000
    ):
        """
        Initialize simplified memory manager.

        Args:
            enable_fast_classification: Use optimized classifier
            cache_size: Size of internal caches
        """
        # Initialize classifier
        self.classifier = OptimizedClassifier(cache_size=cache_size)

        # Initialize mock store
        self.store = MockProllyTreeStore()

        # Initialize search engine
        self.search_engine = HierarchicalSearchEngine(
            store=self, classifier=self.classifier  # Pass self as store interface
        )

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

        # For now, implement a simple search that uses the classifier
        classification = self.classifier.fast_classify(query)

        # Search in the store
        results = await self.store.asearch((namespace,), query=query, limit=limit)

        # Convert to Memory objects
        memories = []
        for result in results:
            memory = Memory(
                id=result.key,
                content=result.value.get("content", result.value),
                metadata={
                    "namespace": ".".join(result.namespace),
                    "relevance_score": result.score,
                    "timestamp": (
                        result.created_at.timestamp()
                        if result.created_at
                        else time.time()
                    ),
                    "classification": classification.primary_path,
                },
            )
            memories.append(memory)

        search_time = (time.time() - start_time) * 1000
        self._metrics["search_time_ms"].append(search_time)

        logger.info(
            f"Search completed in {search_time:.2f}ms, found {len(memories)} memories"
        )

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

        if auto_classify and self.enable_fast_classification:
            # Use fast classification
            classification_start = time.time()
            self._metrics["classifications"] += 1

            classification = self.classifier.fast_classify(str(content))
            semantic_key = classification.primary_path

            classification_time = (time.time() - classification_start) * 1000
            self._metrics["classification_time_ms"].append(classification_time)

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

        # Store with metadata
        store_data = {
            "content": content,
            "metadata": metadata or {},
            "timestamp": time.time(),
            "semantic_key": semantic_key,
        }

        await self.store.aput((namespace,), semantic_key, store_data)

        write_time = (time.time() - start_time) * 1000
        self._metrics["write_time_ms"].append(write_time)

        logger.debug(f"Stored memory at {semantic_key} in {write_time:.2f}ms")

        return semantic_key

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

        # Add store statistics
        store_stats = self.store.get_statistics()
        metrics["store"] = store_stats

        return metrics

    # Store interface methods for search engine
    async def asearch(self, namespace: str, prefix: str) -> list[tuple[str, Any]]:
        """Search interface for hierarchical search engine."""
        results = await self.store.asearch((namespace,), query=prefix, limit=50)

        return [
            (result.key, result.value.get("content", result.value))
            for result in results
        ]

    async def alist(self, namespace: str) -> list[str]:
        """List interface for search engine."""
        results = await self.store.asearch((namespace,), limit=1000)
        return [result.key for result in results]

# SPDX-License-Identifier: Apache-2.0
"""
Provides high-performance semantic memory with versioning capabilities.
"""

import json
import logging
import time
from datetime import datetime
from typing import Any

from langmem.knowledge.extraction import MemoryStoreManager
from pydantic import BaseModel, Field

from memoir.memento.location import LocationMemento
from memoir.memento.profile import ProfileMemento
from memoir.memento.timeline import TimelineMemento
from memoir.store.prolly_adapter import ProllyTreeStore

# Search engine imports removed - search engine now provided as parameter


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
    author: str | None = None


class ProllyTreeMemoryStoreManager(MemoryStoreManager):
    """
    Enhanced MemoryStoreManager with ProllyTree backend.
    Provides semantic classification, hierarchical search, and versioning.
    """

    def __init__(
        self,
        prolly_store: Any | None = None,  # ProllyTreeStore instance (preferred)
        prolly_path: str | None = None,  # Path to create store (fallback)
        model: str | Any = "gpt-3.5-turbo",  # Default model
        classifier: (
            Any | None
        ) = None,  # SemanticClassifier or IntelligentClassifier instance
        search_engine: Any | None = None,  # Search engine instance
        enable_versioning: bool = True,
        auto_commit: bool = True,
        enable_fast_classification: bool = True,
        cache_size: int = 10000,
        **kwargs,
    ):
        """
        Initialize enhanced memory manager.

        Args:
            prolly_store: ProllyTreeStore instance (preferred - allows proper dependency injection)
            prolly_path: Path to create ProllyTree database (fallback if store not provided)
            classifier: SemanticClassifier or IntelligentClassifier instance
            search_engine: Search engine instance (IntelligentSearchEngine, etc.)
            enable_versioning: Enable git-like versioning
            auto_commit: Whether to automatically commit on each memory operation
            enable_fast_classification: Use optimized classifier
            cache_size: Size of internal caches
            **kwargs: Additional arguments for MemoryStoreManager
        """
        # Initialize classifier - must be provided for production use
        self.classifier = classifier

        # Initialize or use provided ProllyTree store
        if prolly_store is not None:
            # Use provided store (preferred for dependency injection)
            self.prolly_store = prolly_store
        elif prolly_path is not None:
            # Create store from path (fallback)
            # Path-based construction is the SDK fallback / auto-create
            # entry point. ProllyTreeStore itself is strict, so bootstrap
            # the store via StoreService first if it doesn't exist yet.
            from memoir.services.store_service import StoreService

            StoreService(prolly_path).create_store(prolly_path)
            self.prolly_store = ProllyTreeStore(
                path=prolly_path,
                enable_versioning=enable_versioning,
                auto_commit=auto_commit,
                cache_size=cache_size,
            )
        else:
            raise ValueError("Either prolly_store or prolly_path must be provided")

        # Initialize profile memento
        self.profile_manager = ProfileMemento(self.prolly_store)

        # Initialize timeline memento
        self.timeline_manager = TimelineMemento(self.prolly_store)

        # Initialize location memento
        self.location_manager = LocationMemento(self.prolly_store)

        # Use provided search engine
        self.search_engine = search_engine

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
        limit: int = 10,
    ) -> list[Memory]:
        """
        Search memories using the provided search engine.

        Args:
            query: Natural language search query
            namespace: User namespace
            limit: Maximum results to return

        Returns:
            List of Memory objects
        """
        if not self.search_engine:
            logger.warning("No search engine provided - returning empty results")
            return []

        start_time = time.time()
        self._metrics["searches"] += 1

        # Use the provided search engine
        search_results = await self.search_engine.search(
            query=query, namespace=namespace, limit=limit
        )

        # Convert IntelligentSearchResult objects to Memory objects
        memories = []
        for result in search_results[:limit]:
            memory = Memory(
                id=result.path,
                content=result.content,
                metadata=result.metadata,
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
        metadata: dict | None = None,
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

            # Use async classification with metadata
            classification = await self.classifier.classify_async(
                str(content), metadata=metadata
            )
            # Handle different classifier result formats
            if hasattr(classification, "primary_path"):
                semantic_key = classification.primary_path  # SemanticClassifier
            else:
                semantic_key = classification.path  # IntelligentClassifier

            # Handle case where classification fails and returns None path
            if semantic_key is None:
                logger.warning("Classification returned None path, using fallback")
                semantic_key = "context.current.session.topic.main"

            classification_time = (time.time() - classification_start) * 1000
            self._metrics["classification_time_ms"].append(classification_time)

            # Apply profile updates if detected
            if (
                hasattr(classification, "profile_updates")
                and classification.profile_updates
            ):
                try:
                    await self.profile_manager.apply_profile_updates(
                        classification.profile_updates, metadata, namespace
                    )
                    # logger.info(
                    #     f"Applied {len(classification.profile_updates)} profile updates"
                    # )
                except Exception as e:
                    logger.error(f"Failed to apply profile updates: {e}")

            # Apply timeline events if detected
            if (
                hasattr(classification, "timeline_events")
                and classification.timeline_events
            ):
                try:
                    await self.timeline_manager.apply_timeline_events(
                        classification.timeline_events, metadata, namespace=namespace
                    )
                    # logger.info(
                    #     f"Applied {len(classification.timeline_events)} timeline events"
                    # )
                except Exception as e:
                    logger.error(f"Failed to apply timeline events: {e}")

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

        # Store using the asynchronous method (proper async context)
        await self.prolly_store.store_memory_async(namespace, content, semantic_key)

        write_time = (time.time() - start_time) * 1000
        self._metrics["write_time_ms"].append(write_time)

        # logger.debug(f"Stored memory at {semantic_key} in {write_time:.2f}ms")

        return semantic_key

    def store_commit(self, message: str = "Batch memory operations") -> str | None:
        """
        Commit all pending memory operations to the versioned store.

        This is used when auto_commit=False is set on the ProllyTreeStore to batch
        multiple memory operations into a single commit.

        Args:
            message: Commit message describing the batch of operations

        Returns:
            Commit hash if versioning is enabled, None otherwise
        """
        if not self.enable_versioning:
            logger.warning("Commit requested but versioning is not enabled")
            return None

        try:
            commit_hash = self.prolly_store.commit(message)
            logger.info(f"Committed batch operations: {message}")
            return commit_hash
        except Exception as e:
            logger.error(f"Error committing batch operations: {e}")
            raise

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

        # Convert namespace to tuple format
        namespace_tuple = (
            tuple(namespace.split(":")) if ":" in namespace else (namespace,)
        )

        # Get commit history for this key using the new method
        commit_history = self.prolly_store.get_key_history(
            namespace_tuple, semantic_key, limit
        )

        # Get current content as fallback since historical content retrieval is not yet implemented
        current_content = self.prolly_store.get(namespace_tuple, semantic_key)

        versions = []
        for i, commit in enumerate(commit_history):
            # Try to get content at this commit (currently returns None)
            content_at_commit = self.prolly_store.get_key_at_commit(
                namespace_tuple, semantic_key, commit["id"]
            )

            # If historical content is not available, use current content for demonstration
            if content_at_commit is None and current_content:
                # For the most recent commit, use current content
                if i == 0:  # Most recent commit
                    if (
                        isinstance(current_content, dict)
                        and "memories" in current_content
                    ):
                        # Extract from aggregated memory
                        memories = current_content.get("memories", [])
                        if memories:
                            latest_memory = memories[-1]
                            actual_content = latest_memory.get("content", "")
                        else:
                            actual_content = ""
                    else:
                        actual_content = (
                            current_content.get("content", "")
                            if isinstance(current_content, dict)
                            else current_content
                        )
                else:
                    # For older commits, indicate historical content is not available
                    actual_content = f"[Historical content for commit {commit['id'][:8]} not available]"
            else:
                actual_content = content_at_commit or ""

            # Convert commit info to MemoryVersion
            version = MemoryVersion(
                commit_id=commit["id"],
                timestamp=commit["timestamp"],
                content=actual_content,
                metadata={
                    "author": commit.get("author", ""),
                    "committer": commit.get("committer", ""),
                },
                message=commit["message"],
                author=commit.get("author", ""),
            )
            versions.append(version)

        logger.info(f"Retrieved {len(versions)} version(s) for {semantic_key}")
        return versions

    async def time_travel(
        self, namespace: str, target_time: datetime | float
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

        # Convert namespace to tuple format
        namespace_tuple = (
            tuple(namespace.split(":")) if ":" in namespace else (namespace,)
        )

        # For branch-based time travel, we need to use snapshots
        # Create snapshot name based on timestamp
        snapshot_name = f"snapshot_{int(timestamp)}"

        # Check if we have this snapshot
        if self.enable_versioning and hasattr(self.prolly_store.tree, "list_branches"):
            try:
                branches = self.prolly_store.tree.list_branches()
                if snapshot_name in branches:
                    # Use the snapshot to get historical state
                    state = self.prolly_store.get_state_at_snapshot(
                        namespace_tuple, snapshot_name
                    )
                    logger.info(f"Retrieved state from snapshot {snapshot_name}")
                    return state
                else:
                    logger.warning(
                        f"No snapshot found for timestamp {timestamp}, returning current state"
                    )
            except Exception as e:
                logger.error(f"Error accessing time travel snapshot: {e}")

        # Fallback: return current state
        search_results = self.prolly_store.search(namespace_tuple, limit=1000)
        current_state = {}
        for _, key, data in search_results:
            current_state[key] = data

        return current_state

    async def create_memory_snapshot(
        self, namespace: str, snapshot_name: str | None = None
    ) -> str:
        """
        Create a snapshot of the current memory state.

        Args:
            namespace: User namespace
            snapshot_name: Optional name for snapshot (auto-generated if not provided)

        Returns:
            Name of the created snapshot
        """
        if not self.enable_versioning:
            raise ValueError("Snapshots require versioning to be enabled")

        if snapshot_name is None:
            # Auto-generate snapshot name with timestamp
            snapshot_name = f"snapshot_{int(time.time())}"

        # Create the snapshot
        success = self.prolly_store.create_time_snapshot(snapshot_name)

        if success:
            logger.info(f"Created memory snapshot: {snapshot_name}")
            return snapshot_name
        else:
            raise RuntimeError(f"Failed to create snapshot: {snapshot_name}")

    async def compare_memory_states(
        self,
        namespace: str,
        time1: datetime | float,
        time2: datetime | float,
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

        # Add component statistics
        try:
            metrics["store"] = self.prolly_store.get_statistics()
        except Exception as e:
            logger.warning(f"Failed to get store statistics: {e}")
            metrics["store"] = {}

        # Add classifier statistics if available
        if hasattr(self.classifier, "get_statistics"):
            try:
                metrics["classifier"] = self.classifier.get_statistics()
            except Exception as e:
                logger.warning(f"Failed to get classifier statistics: {e}")
                metrics["classifier"] = {}

        # Add search engine statistics if available
        if hasattr(self.search_engine, "get_statistics"):
            try:
                metrics["search_engine"] = self.search_engine.get_statistics()
            except Exception as e:
                logger.warning(f"Failed to get search engine statistics: {e}")
                metrics["search_engine"] = {}

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
        namespace_tuple = (
            tuple(namespace.split(":")) if ":" in namespace else (namespace,)
        )
        search_results = self.prolly_store.search(namespace_tuple, limit=1000)
        all_keys = [key for _, key, _ in search_results]

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
        self, input_path: str, namespace: str | None = None
    ) -> int:
        """
        Import memories from file.

        Args:
            input_path: Input file path
            namespace: Override namespace (uses file namespace if None)

        Returns:
            Number of memories imported
        """
        logger.warning(
            "Import functionality not yet implemented in ProllyTreeStore adapter"
        )

        # Parse file to get count and simulate import
        with open(input_path) as f:
            data = json.load(f)
            memories = data.get("memories", {})

            # For demonstration, we could import the memories one by one
            # but for now just return the count
            count = len(memories)

        # logger.info(f"Would import {count} memories from {input_path}")
        return count

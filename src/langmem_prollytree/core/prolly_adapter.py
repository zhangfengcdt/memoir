"""
ProllyTree adapter implementing LangGraph's BaseStore interface.
Provides high-performance semantic memory storage with versioning.
"""

import builtins
import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from langgraph.checkpoint.base import BaseStore
from prollytree import ProllyTree, VersionedStore
from pydantic import BaseModel, Field

from langmem_prollytree.taxonomy.semantic_classifier import OptimizedClassifier
from langmem_prollytree.taxonomy.semantic_taxonomy import get_taxonomy

logger = logging.getLogger(__name__)


class MemoryItem(BaseModel):
    """Represents a memory item in the store."""

    key: str = Field(description="Semantic taxonomy key")
    namespace: str = Field(description="User/agent namespace")
    content: Any = Field(description="Memory content")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    timestamp: float = Field(
        default_factory=time.time, description="Creation timestamp"
    )
    version: Optional[str] = Field(default=None, description="Version/commit ID")
    confidence: float = Field(default=1.0, description="Classification confidence")


class ProllyTreeStore(BaseStore):
    """
    High-performance semantic memory store using ProllyTree.
    Implements LangGraph's BaseStore interface with enhanced capabilities.
    """

    def __init__(
        self,
        path: str,
        classifier: Optional[OptimizedClassifier] = None,
        enable_versioning: bool = True,
        cache_size: int = 10000,
    ):
        """
        Initialize ProllyTree store.

        Args:
            path: Path to ProllyTree database
            classifier: Semantic classifier (will create default if None)
            enable_versioning: Whether to enable git-like versioning
            cache_size: Size of internal caches
        """
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

        # Initialize ProllyTree
        if enable_versioning:
            self.tree = VersionedStore(str(self.path))
        else:
            self.tree = ProllyTree(str(self.path))

        self.enable_versioning = enable_versioning
        self.taxonomy = get_taxonomy()
        self.classifier = classifier or OptimizedClassifier(cache_size=cache_size)

        # Performance tracking
        self._stats = {"reads": 0, "writes": 0, "searches": 0, "classifications": 0}

    def _make_key(self, namespace: str, semantic_key: str) -> str:
        """Create a full key from namespace and semantic path."""
        return f"{namespace}.{semantic_key}"

    def _parse_key(self, full_key: str) -> tuple[str, str]:
        """Parse namespace and semantic key from full key."""
        parts = full_key.split(".", 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return "", full_key

    async def aget(
        self,
        namespace: tuple[str, ...],
        key: str,
        *,
        refresh_ttl: Optional[bool] = None,
    ) -> Optional[Any]:
        """
        Get a memory item by key.

        Args:
            namespace: User/agent namespace tuple
            key: Semantic taxonomy key or memory ID
            refresh_ttl: Whether to refresh TTL (not supported)

        Returns:
            Memory content or None if not found
        """
        self._stats["reads"] += 1

        # Convert namespace tuple to string
        namespace_str = ".".join(namespace)

        # Handle both semantic keys and direct lookups
        if self.taxonomy.is_valid_path(key):
            full_key = self._make_key(namespace_str, key)
        else:
            # Assume it's a direct key lookup
            full_key = key

        try:
            # Mock implementation for now since ProllyTree integration needs actual implementation
            return None
        except Exception as e:
            logger.error(f"Error getting key {full_key}: {e}")

        return None

    def get(self, namespace: str, key: str) -> Optional[Any]:
        """Synchronous version of aget."""
        import asyncio

        return asyncio.run(self.aget(namespace, key))

    async def aput(self, namespace: str, key: str, value: Any) -> None:
        """
        Store a memory item.

        Args:
            namespace: User/agent namespace
            key: Semantic taxonomy key or custom key
            value: Memory content to store
        """
        self._stats["writes"] += 1

        # Classify if not a valid taxonomy path
        if not self.taxonomy.is_valid_path(key):
            # Try to classify the content
            classification = await self.classifier.classify_async(str(value))
            semantic_key = classification.primary_path
            confidence = classification.confidence
            self._stats["classifications"] += 1
        else:
            semantic_key = key
            confidence = 1.0

        full_key = self._make_key(namespace, semantic_key)

        # Create memory item
        item = MemoryItem(
            key=semantic_key,
            namespace=namespace,
            content=value,
            confidence=confidence,
            timestamp=time.time(),
        )

        # Store with versioning if enabled
        try:
            data = json.dumps(item.model_dump()).encode()

            if self.enable_versioning:
                commit_msg = f"Update {semantic_key} for {namespace}"
                await self.tree.put_async(full_key.encode(), data, message=commit_msg)
                item.version = self.tree.get_head()
            else:
                await self.tree.put_async(full_key.encode(), data)

            logger.debug(f"Stored {full_key} with confidence {confidence}")

        except Exception as e:
            logger.error(f"Error storing {full_key}: {e}")
            raise

    def put(self, namespace: str, key: str, value: Any) -> None:
        """Synchronous version of aput."""
        import asyncio

        asyncio.run(self.aput(namespace, key, value))

    async def adelete(self, namespace: str, key: str) -> None:
        """
        Delete a memory item.

        Args:
            namespace: User/agent namespace
            key: Semantic taxonomy key or memory ID
        """
        if self.taxonomy.is_valid_path(key):
            full_key = self._make_key(namespace, key)
        else:
            full_key = key

        try:
            if self.enable_versioning:
                commit_msg = f"Delete {key} from {namespace}"
                await self.tree.delete_async(full_key.encode(), message=commit_msg)
            else:
                await self.tree.delete_async(full_key.encode())

            logger.debug(f"Deleted {full_key}")

        except Exception as e:
            logger.error(f"Error deleting {full_key}: {e}")

    def delete(self, namespace: str, key: str) -> None:
        """Synchronous version of adelete."""
        import asyncio

        asyncio.run(self.adelete(namespace, key))

    async def asearch(self, namespace: str, prefix: str) -> list[tuple[str, Any]]:
        """
        Search for memories by prefix.

        Args:
            namespace: User/agent namespace
            prefix: Semantic path prefix to search

        Returns:
            List of (key, value) tuples
        """
        self._stats["searches"] += 1

        results = []
        search_prefix = self._make_key(namespace, prefix)

        try:
            # Use ProllyTree's efficient range query
            items = await self.tree.range_query_async(
                search_prefix.encode(), (search_prefix + "\xff").encode()
            )

            for key_bytes, value_bytes in items:
                key = key_bytes.decode()
                _, semantic_key = self._parse_key(key)

                item = MemoryItem(**json.loads(value_bytes.decode()))
                results.append((semantic_key, item.content))

        except Exception as e:
            logger.error(f"Error searching {search_prefix}: {e}")

        return results

    def search(self, namespace: str, prefix: str) -> list[tuple[str, Any]]:
        """Synchronous version of asearch."""
        import asyncio

        return asyncio.run(self.asearch(namespace, prefix))

    async def alist(self, namespace: str) -> list[str]:
        """
        List all keys in a namespace.

        Args:
            namespace: User/agent namespace

        Returns:
            List of semantic keys
        """
        keys = []
        prefix = namespace + "."

        try:
            items = await self.tree.range_query_async(
                prefix.encode(), (prefix + "\xff").encode()
            )

            for key_bytes, _ in items:
                key = key_bytes.decode()
                _, semantic_key = self._parse_key(key)
                keys.append(semantic_key)

        except Exception as e:
            logger.error(f"Error listing {namespace}: {e}")

        return keys

    def list(self, namespace: str) -> list[str]:
        """Synchronous version of alist."""
        import asyncio

        return asyncio.run(self.alist(namespace))

    # Enhanced methods beyond BaseStore

    async def get_history(
        self, namespace: str, key: str, limit: int = 10
    ) -> builtins.list[MemoryItem]:
        """
        Get version history for a memory.

        Args:
            namespace: User/agent namespace
            key: Semantic taxonomy key
            limit: Maximum number of versions to return

        Returns:
            List of memory items with version history
        """
        if not self.enable_versioning:
            # Just return current version
            current = await self.aget(namespace, key)
            if current:
                return [
                    MemoryItem(
                        key=key,
                        namespace=namespace,
                        content=current,
                        timestamp=time.time(),
                    )
                ]
            return []

        full_key = self._make_key(namespace, key)
        history = []

        try:
            versions = self.tree.get_history(full_key.encode(), limit=limit)

            for version_info in versions:
                data = version_info.get("data")
                if data:
                    item = MemoryItem(**json.loads(data.decode()))
                    item.version = version_info.get("commit_id")
                    history.append(item)

        except Exception as e:
            logger.error(f"Error getting history for {full_key}: {e}")

        return history

    async def time_travel(self, namespace: str, timestamp: float) -> dict[str, Any]:
        """
        Get all memories as they were at a specific time.

        Args:
            namespace: User/agent namespace
            timestamp: Unix timestamp to travel to

        Returns:
            Dictionary of memories at that point in time
        """
        if not self.enable_versioning:
            logger.warning("Time travel requires versioning to be enabled")
            return {}

        memories = {}

        try:
            # Find the commit closest to the timestamp
            commit_id = self.tree.find_commit_at_time(timestamp)

            if commit_id:
                # Checkout that version
                old_head = self.tree.get_head()
                self.tree.checkout(commit_id)

                # Get all memories
                items = await self.alist(namespace)
                for key in items:
                    value = await self.aget(namespace, key)
                    if value:
                        memories[key] = value

                # Restore head
                self.tree.checkout(old_head)

        except Exception as e:
            logger.error(f"Error in time travel: {e}")

        return memories

    async def get_statistics(self) -> dict[str, Any]:
        """Get store statistics."""
        stats = {
            "performance": self._stats.copy(),
            "taxonomy": self.taxonomy.get_statistics(),
            "classifier": self.classifier.get_statistics(),
        }

        if self.enable_versioning:
            stats["versioning"] = {
                "current_commit": self.tree.get_head(),
                "total_commits": self.tree.get_commit_count(),
            }

        return stats

    def batch_put(self, items: builtins.list[tuple[str, str, Any]]) -> None:
        """
        Batch insert multiple items.

        Args:
            items: List of (namespace, key, value) tuples
        """
        import asyncio

        async def _batch_put():
            tasks = []
            for namespace, key, value in items:
                tasks.append(self.aput(namespace, key, value))
            await asyncio.gather(*tasks)

        asyncio.run(_batch_put())

    def export_namespace(self, namespace: str, output_path: str) -> None:
        """
        Export all memories from a namespace to JSON.

        Args:
            namespace: Namespace to export
            output_path: Path to save JSON file
        """
        memories = {}

        for key in self.list(namespace):
            value = self.get(namespace, key)
            if value:
                memories[key] = value

        with open(output_path, "w") as f:
            json.dump(
                {
                    "namespace": namespace,
                    "timestamp": time.time(),
                    "memories": memories,
                },
                f,
                indent=2,
            )

        logger.info(f"Exported {len(memories)} memories to {output_path}")

    def import_namespace(
        self, input_path: str, namespace: Optional[str] = None
    ) -> None:
        """
        Import memories from JSON file.

        Args:
            input_path: Path to JSON file
            namespace: Override namespace (uses file namespace if None)
        """
        with open(input_path) as f:
            data = json.load(f)

        ns = namespace or data["namespace"]
        memories = data["memories"]

        items = [(ns, key, value) for key, value in memories.items()]
        self.batch_put(items)

        logger.info(f"Imported {len(memories)} memories to {ns}")

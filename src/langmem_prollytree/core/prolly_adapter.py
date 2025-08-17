"""
ProllyTree adapter implementing LangGraph's BaseStore interface.
Provides high-performance semantic memory storage with versioning.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional

from langgraph.store.base import BaseStore
from prollytree import ProllyTree, VersionedKvStore
from pydantic import BaseModel, Field

from langmem_prollytree.search.hierarchical_search import HierarchicalSearchEngine
from langmem_prollytree.taxonomy.semantic_classifier import SemanticClassifier
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
    Implements LangGraph's BaseStore interface following the reference pattern.
    """

    def __init__(
        self,
        path: str,
        classifier: Optional[SemanticClassifier] = None,
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
        super().__init__()

        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

        # Initialize git repository if using versioning and not exists
        if enable_versioning:
            import os
            import subprocess

            if not os.path.exists(os.path.join(self.path, ".git")):
                subprocess.run(["git", "init", "--quiet"], cwd=self.path, check=True)
                subprocess.run(
                    ["git", "config", "user.name", "LangMem ProllyTree"],
                    cwd=self.path,
                    check=True,
                )
                subprocess.run(
                    ["git", "config", "user.email", "langmem@example.com"],
                    cwd=self.path,
                    check=True,
                )

                # Create initial commit
                readme_path = os.path.join(self.path, "README.md")
                with open(readme_path, "w") as f:
                    f.write("# LangMem ProllyTree Store\n")
                subprocess.run(["git", "add", "."], cwd=self.path, check=True)
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit"], cwd=self.path, check=True
                )

        # Initialize ProllyTree
        if enable_versioning:
            # Create data subdirectory for VersionedKvStore
            data_dir = self.path / "data"
            data_dir.mkdir(exist_ok=True)
            self.tree = VersionedKvStore(str(data_dir))
        else:
            self.tree = ProllyTree(str(self.path))

        self.enable_versioning = enable_versioning
        self.taxonomy = get_taxonomy()
        if classifier is None:
            raise ValueError(
                "SemanticClassifier with LLM is required for production use"
            )
        self.classifier = classifier

        # Initialize search engine
        self.search_engine = HierarchicalSearchEngine(
            store=self, classifier=classifier, min_results=5
        )

        # Performance tracking
        self._stats = {"reads": 0, "writes": 0, "searches": 0, "classifications": 0}

    def _encode_value(self, value: Any) -> bytes:
        """Encode any value to bytes for storage."""
        if isinstance(value, bytes):
            return value
        elif isinstance(value, str):
            return value.encode("utf-8")
        else:
            # Use JSON for complex objects
            json_str = json.dumps(value, default=str)
            return json_str.encode("utf-8")

    def _decode_value(self, data: bytes) -> Any:
        """Decode bytes from storage back to original type."""
        if not data:
            return None
        try:
            # Try to decode as JSON first
            json_str = data.decode("utf-8")
            return json.loads(json_str)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Return as string if not JSON
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data

    # BaseStore interface methods
    def batch(self, ops: list[tuple]) -> list[Any]:
        """Batch operations - required by BaseStore."""
        results = []
        for op in ops:
            if len(op) == 2:
                method, args = op
                result = getattr(self, method)(*args)
                results.append(result)
        return results

    def abatch(self, ops: list[tuple]) -> list[Any]:
        """Async batch operations - synchronous implementation."""
        return self.batch(ops)

    def search(
        self, namespace: tuple, *, filter: Optional[dict] = None, limit: int = 10
    ) -> list[tuple]:
        """Search for items in a namespace."""
        self._stats["searches"] += 1
        prefix = ":".join(namespace) + ":"
        results = []

        try:
            # Use list_keys() to get all keys if available
            if hasattr(self.tree, "list_keys"):
                keys = self.tree.list_keys()
                count = 0
                for key in keys:
                    if count >= limit:
                        break

                    key_str = key.decode("utf-8")
                    if key_str.startswith(prefix):
                        value = self.tree.get(key)
                        decoded_value = self._decode_value(value)

                        # Apply filter if provided
                        if filter and not all(
                            decoded_value.get(k) == v
                            for k, v in filter.items()
                            if isinstance(decoded_value, dict)
                        ):
                            continue

                        # Extract item key from full key
                        item_key = key_str[len(prefix) :]
                        results.append((namespace, item_key, decoded_value))
                        count += 1
        except Exception as e:
            logger.error(f"Error searching namespace {namespace}: {e}")

        return results

    def put(self, namespace: tuple, key: str, value: dict) -> None:
        """Store a value in a namespace."""
        self._stats["writes"] += 1
        full_key = ":".join(namespace) + ":" + key
        key_bytes = full_key.encode("utf-8")
        value_bytes = self._encode_value(value)

        try:
            # Check if key exists to decide between insert/update
            existing = self.tree.get(key_bytes)
            if existing:
                self.tree.update(key_bytes, value_bytes)
            else:
                self.tree.insert(key_bytes, value_bytes)

            if self.enable_versioning:
                self.tree.commit(f"Store {key} in {':'.join(namespace)}")

        except Exception as e:
            logger.error(f"Error storing {full_key}: {e}")
            raise

    def get(self, namespace: tuple, key: str) -> Optional[dict]:
        """Retrieve a value from a namespace."""
        self._stats["reads"] += 1
        full_key = ":".join(namespace) + ":" + key
        key_bytes = full_key.encode("utf-8")

        try:
            data = self.tree.get(key_bytes)
            return self._decode_value(data) if data else None
        except Exception as e:
            logger.error(f"Error getting key {full_key}: {e}")
            return None

    def delete(self, namespace: tuple, key: str) -> None:
        """Delete a key from a namespace."""
        full_key = ":".join(namespace) + ":" + key
        key_bytes = full_key.encode("utf-8")

        try:
            self.tree.delete(key_bytes)
            if self.enable_versioning:
                self.tree.commit(f"Delete {key} from {':'.join(namespace)}")
        except Exception as e:
            logger.error(f"Error deleting {full_key}: {e}")

    # Enhanced methods for semantic memory functionality
    async def store_memory_async(
        self, namespace: str, content: Any, key: Optional[str] = None
    ) -> MemoryItem:
        """
        Store a memory with automatic semantic classification.

        Args:
            namespace: User/agent namespace
            content: Memory content to store
            key: Optional explicit key (will classify if None)

        Returns:
            MemoryItem with classification results
        """
        if key and self.taxonomy.is_valid_path(key):
            semantic_key = key
            confidence = 1.0
        else:
            # Classify the content
            classification = await self.classifier.classify_async(str(content))
            semantic_key = classification.primary_path
            confidence = classification.confidence
            self._stats["classifications"] += 1

        # Create memory item
        item = MemoryItem(
            key=semantic_key,
            namespace=namespace,
            content=content,
            confidence=confidence,
            timestamp=time.time(),
        )

        # Store using BaseStore interface
        self.put((namespace,), semantic_key, item.model_dump())

        if self.enable_versioning and hasattr(self.tree, "get_head"):
            item.version = self.tree.get_head()

        return item

    def store_memory(
        self, namespace: str, content: Any, key: Optional[str] = None
    ) -> MemoryItem:
        """Synchronous wrapper for store_memory_async."""
        import asyncio

        # Check if we're already in an event loop
        try:
            asyncio.get_running_loop()
            # We're in an event loop, use fallback
            in_event_loop = True
        except RuntimeError:
            # No event loop running, we can use asyncio.run
            in_event_loop = False

        if not in_event_loop:
            return asyncio.run(self.store_memory_async(namespace, content, key))
        else:
            # We're already in an event loop, need to use different approach
            # For now, provide a fallback classification
            if key and self.taxonomy.is_valid_path(key):
                semantic_key = key
                confidence = 1.0
            else:
                # Use a simple fallback classification
                semantic_key = "context.current.session.topic.main"
                confidence = 0.5
                self._stats["classifications"] += 1

            # Create memory item
            item = MemoryItem(
                key=semantic_key,
                namespace=namespace,
                content=content,
                confidence=confidence,
                timestamp=time.time(),
            )

            # Store using BaseStore interface
            self.put((namespace,), semantic_key, item.model_dump())

            if self.enable_versioning and hasattr(self.tree, "get_head"):
                item.version = self.tree.get_head()

            return item

    async def asearch(self, namespace: str, path_prefix: str) -> list[tuple[str, Any]]:
        """
        Async search for items with a given path prefix.
        Used by HierarchicalSearchEngine.

        Args:
            namespace: User namespace
            path_prefix: Path prefix to search for

        Returns:
            List of (key, data) tuples
        """
        # Use synchronous search with prefix
        results = []
        search_results = self.search((namespace,), limit=100)

        for _, key, data in search_results:
            if key.startswith(path_prefix):
                results.append((key, data))

        return results

    async def retrieve_memories_async(
        self, namespace: str, query: str, limit: int = 10
    ) -> list[MemoryItem]:
        """
        Retrieve memories using semantic search (async version).

        Args:
            namespace: User/agent namespace
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching memory items
        """
        # Use the hierarchical search engine to find relevant memories
        search_results = await self.search_engine.search(query, namespace)

        # Convert search results to memory items
        memories = []
        for result in search_results[:limit]:
            # Get the actual memory data from the store
            data = self.get((namespace,), result.key)
            if data and isinstance(data, dict):
                try:
                    memory = MemoryItem(**data)
                    memories.append(memory)
                except Exception as e:
                    logger.warning(f"Failed to parse memory item: {e}")

        return memories

    def retrieve_memories(
        self, namespace: str, query: str, limit: int = 10
    ) -> list[MemoryItem]:
        """
        Retrieve memories using semantic search (sync fallback).

        Note: This is a simple fallback. For proper semantic search,
        use retrieve_memories_async() which leverages the HierarchicalSearchEngine.

        Args:
            namespace: User/agent namespace
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching memory items
        """
        logger.warning(
            "Using fallback sync search. For better results, use retrieve_memories_async()"
        )

        # Simple fallback - just return all memories
        all_memories = []
        search_results = self.search((namespace,), limit=limit)

        for _, _key, data in search_results:
            if isinstance(data, dict):
                try:
                    memory = MemoryItem(**data)
                    all_memories.append(memory)
                except Exception as e:
                    logger.warning(f"Failed to parse memory item: {e}")

        return all_memories

    def get_statistics(self) -> dict[str, Any]:
        """Get store statistics."""
        stats = {
            "performance": self._stats.copy(),
            "taxonomy": self.taxonomy.get_statistics(),
            "classifier": self.classifier.get_statistics(),
        }

        if self.enable_versioning and hasattr(self.tree, "get_head"):
            try:
                stats["versioning"] = {
                    "current_commit": self.tree.get_head(),
                }
                if hasattr(self.tree, "log"):
                    commits = self.tree.log()
                    stats["versioning"]["total_commits"] = len(commits)
            except Exception:
                pass

        return stats

    def export_namespace(self, namespace: str, output_path: str) -> None:
        """
        Export all memories from a namespace to JSON.

        Args:
            namespace: Namespace to export
            output_path: Path to save JSON file
        """
        memories = {}
        search_results = self.search((namespace,), limit=1000)

        for _, key, data in search_results:
            memories[key] = data

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

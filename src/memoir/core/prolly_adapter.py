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

from memoir.search.hierarchical_search import HierarchicalSearchEngine
from memoir.taxonomy.semantic_classifier import SemanticClassifier
from memoir.taxonomy.semantic_taxonomy import get_taxonomy

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
            # Use memory mode for simplicity (can be changed to 'file' for persistence)
            self.tree = ProllyTree("memory")

        self.enable_versioning = enable_versioning
        self.taxonomy = get_taxonomy()
        if classifier is None:
            raise ValueError(
                "SemanticClassifier with LLM is required for production use"
            )
        self.classifier = classifier

        # Initialize search engine
        self.search_engine = HierarchicalSearchEngine(
            store=self, classifier=classifier, max_content_length=10000
        )

        # Performance tracking
        self._stats = {"reads": 0, "writes": 0, "searches": 0, "classifications": 0}

        # Key registry for memory mode (since ProllyTree doesn't have list_keys in memory mode)
        self._keys = set()

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
            # Use our key registry to find matching keys
            count = 0
            for full_key in self._keys:
                if count >= limit:
                    break

                if full_key.startswith(prefix):
                    key_bytes = full_key.encode("utf-8")
                    if self.enable_versioning:
                        value = self.tree.get(key_bytes)
                    else:
                        value = self.tree.find(key_bytes)
                    decoded_value = self._decode_value(value)

                    # Apply filter if provided
                    if filter and not all(
                        decoded_value.get(k) == v
                        for k, v in filter.items()
                        if isinstance(decoded_value, dict)
                    ):
                        continue

                    # Extract item key from full key
                    item_key = full_key[len(prefix) :]
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
            if self.enable_versioning:
                # VersionedKvStore API - check if key exists using get
                existing = self.tree.get(key_bytes)
                if existing:
                    self.tree.update(key_bytes, value_bytes)
                else:
                    self.tree.insert(key_bytes, value_bytes)
                # Commit the change
                self.tree.commit(f"Store {key} in {':'.join(namespace)}")
            else:
                # ProllyTree API - check if key exists using find
                existing = self.tree.find(key_bytes)
                if existing:
                    self.tree.update(key_bytes, value_bytes)
                else:
                    self.tree.insert(key_bytes, value_bytes)

            # Track the key in our registry
            self._keys.add(full_key)

        except Exception as e:
            logger.error(f"Error storing {full_key}: {e}")
            raise

    def get(self, namespace: tuple, key: str) -> Optional[dict]:
        """Retrieve a value from a namespace."""
        self._stats["reads"] += 1
        full_key = ":".join(namespace) + ":" + key
        key_bytes = full_key.encode("utf-8")

        try:
            if self.enable_versioning:
                # VersionedKvStore API
                data = self.tree.get(key_bytes)
            else:
                # ProllyTree API
                data = self.tree.find(key_bytes)
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
            # Remove from key registry
            self._keys.discard(full_key)
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

        # Create unique storage key while preserving semantic path
        import uuid

        unique_id = str(uuid.uuid4())[:8]  # Short unique ID
        storage_key = f"{semantic_key}#{unique_id}"

        # Create memory item
        item = MemoryItem(
            key=semantic_key,  # Keep semantic key for classification
            namespace=namespace,
            content=content,
            confidence=confidence,
            timestamp=time.time(),
        )

        # Store using BaseStore interface with unique key
        self.put((namespace,), storage_key, item.model_dump())

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

            # Create unique storage key while preserving semantic path
            import uuid

            unique_id = str(uuid.uuid4())[:8]  # Short unique ID
            storage_key = f"{semantic_key}#{unique_id}"

            # Create memory item
            item = MemoryItem(
                key=semantic_key,  # Keep semantic key for classification
                namespace=namespace,
                content=content,
                confidence=confidence,
                timestamp=time.time(),
            )

            # Store using BaseStore interface with unique key
            self.put((namespace,), storage_key, item.model_dump())

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
            List of (semantic_key, data) tuples
        """
        # Use synchronous search with prefix
        results = []
        seen_content = set()  # Avoid duplicates based on content
        # Convert string namespace to tuple format
        # "memory:general" -> ("memory", "general")
        namespace_parts = namespace.split(":")
        namespace_tuple = tuple(namespace_parts)

        search_results = self.search(namespace_tuple, limit=100)

        for _, storage_key, data in search_results:
            # Extract semantic path from storage key (format: semantic_path#unique_id)
            if "#" in storage_key:
                semantic_key = storage_key.split("#")[0]
            else:
                semantic_key = storage_key

            # Check if semantic path matches prefix
            if semantic_key.startswith(path_prefix):
                # Avoid duplicates by content
                content = (
                    data.get("content", "") if isinstance(data, dict) else str(data)
                )
                content_hash = hash(content)
                if content_hash not in seen_content:
                    seen_content.add(content_hash)
                    # Return semantic key (not storage key) for search engine
                    results.append((semantic_key, data))

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

        # Convert search results to memory items with deduplication
        memories = []
        seen_content = set()

        for result in search_results:
            # The search result contains combined content from multiple items
            if result.combined_content:
                try:
                    # Split combined content back into individual memories
                    individual_contents = result.combined_content.split(" | ")
                    for content_text in individual_contents:
                        if content_text.strip():
                            # Create a memory item from the content
                            memory = MemoryItem(
                                key=result.path,
                                namespace=result.namespace,
                                content=content_text.strip(),
                                confidence=1.0,  # Default confidence
                                timestamp=time.time(),
                            )
                            # Deduplicate by content
                            content_hash = hash(memory.content)
                            if content_hash not in seen_content:
                                seen_content.add(content_hash)
                                memories.append(memory)
                                # Stop when we have enough unique results
                                if len(memories) >= limit:
                                    break
                    if len(memories) >= limit:
                        break
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

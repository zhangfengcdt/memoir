# SPDX-License-Identifier: Apache-2.0
"""
ProllyTree adapter implementing LangGraph's BaseStore interface.
Provides high-performance semantic memory storage with versioning.
"""

import contextlib
import json
import logging
import time
from pathlib import Path
from typing import Any

from langgraph.store.base import BaseStore
from prollytree import ProllyTree, VersionedKvStore
from pydantic import BaseModel, Field

# Storage layer doesn't import classification or search modules
# These are handled by higher layers

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
    version: str | None = Field(default=None, description="Version/commit ID")
    confidence: float = Field(default=1.0, description="Classification confidence")


class _CwdLockedTree:
    """Proxy that chdir's into the store path before any tree method call,
    then restores the caller's cwd. Workaround for prollytree's Rust binding,
    which uses cwd (not the absolute path passed to its constructor) to
    locate the enclosing git repo on every operation — not just at
    construction. Without this wrapper, callers in non-git cwds hit
    "Not in a git repository" on `.put()`/`.insert()`/`.commit()` even when
    the tree was constructed successfully via the in-init chdir below.

    Wrapping once at __init__ is uniformly cheaper than annotating every
    public method that touches `self.tree` (28+ call sites).
    """

    def __init__(self, tree: Any, store_path: Path):
        # Underscore prefix on the inner attrs so __getattr__ never recurses
        # into them (it only fires for missing names).
        object.__setattr__(self, "_tree", tree)
        object.__setattr__(self, "_store_path", str(store_path))

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._tree, name)
        if not callable(attr):
            return attr
        store_path = self._store_path

        def _wrapped(*args, **kwargs):
            import os as _os

            saved = _os.getcwd()
            try:
                _os.chdir(store_path)
                return attr(*args, **kwargs)
            finally:
                _os.chdir(saved)

        return _wrapped


class AggregatedMemory(BaseModel):
    """Represents aggregated memories at a semantic path."""

    path: str = Field(description="Semantic taxonomy path")
    memories: list[dict[str, Any]] = Field(
        default_factory=list, description="List of memory entries at this path"
    )
    count: int = Field(default=0, description="Number of memories")
    first_timestamp: float = Field(
        default_factory=time.time, description="Timestamp of first memory"
    )
    last_timestamp: float = Field(
        default_factory=time.time, description="Timestamp of last memory"
    )
    last_updated: float = Field(
        default_factory=time.time, description="Last update timestamp"
    )


class ProllyTreeStore(BaseStore):
    """
    High-performance semantic memory store using ProllyTree.
    Implements LangGraph's BaseStore interface following the reference pattern.
    """

    def __init__(
        self,
        path: str,
        enable_versioning: bool = True,
        auto_commit: bool = True,
        cache_size: int = 10000,
        create_if_missing: bool = False,
    ):
        """
        Initialize ProllyTree store.

        Storage layer is responsible only for storing and retrieving data.
        Classification is handled by higher layers (memory manager).

        Args:
            path: Path to ProllyTree database
            enable_versioning: Whether to enable git-like versioning
            auto_commit: Whether to automatically commit on each put/delete operation
            cache_size: Size of internal caches
            create_if_missing: When True, init the path as a git store if it
                isn't one yet (write README, `git init`, initial commit). When
                False (default), refuse to operate on a path that isn't already
                a memoir store. Strict default protects users running
                `memoir remember` from a random cwd from accidentally turning
                that cwd into a half-baked store. Only `memoir new` and the
                opt-in SDK auto-create paths should pass True.
        """
        super().__init__()

        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

        # Initialize git repository if using versioning and not exists
        if enable_versioning:
            import os
            import subprocess

            def _git_step(args: list[str], op_label: str) -> None:
                """Run a git command, surfacing git's stderr in the exception
                message instead of dropping it. Without this wrap users see
                only `CalledProcessError ... non-zero exit status 128` — which
                is useless for diagnosing real problems like 'directory has a
                .git but no commit checked out'.
                """
                try:
                    subprocess.run(
                        ["git", *args],
                        cwd=self.path,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except subprocess.CalledProcessError as e:
                    stderr = (e.stderr or "").strip()
                    detail = stderr or f"exit {e.returncode}"
                    raise RuntimeError(
                        f"Failed to initialize Git store: Git object error: "
                        f"{op_label} failed: {detail}"
                    ) from e

            if not os.path.exists(os.path.join(self.path, ".git")):
                if not create_if_missing:
                    raise FileNotFoundError(
                        f"Not a memoir store: {self.path} (no .git directory). "
                        f"Create one with `memoir new <path>` first, or pass "
                        f"-s/--store / set MEMOIR_STORE / cd into an existing store."
                    )
                _git_step(["init", "--quiet"], "git init")

                # Create initial commit
                readme_path = os.path.join(self.path, "README.md")
                with open(readme_path, "w") as f:
                    f.write("# Memoir Store\n")
                _git_step(["add", "."], "git add")
                _git_step(
                    ["commit", "-m", "Initial Commit -- ProllyTree Store"],
                    "git commit",
                )

        # Initialize ProllyTree
        if enable_versioning:
            # Create data subdirectory for VersionedKvStore
            data_dir = self.path / "data"
            data_dir.mkdir(exist_ok=True)
            # VersionedKvStore (prollytree Rust binding) uses cwd to locate the
            # enclosing git repository even when handed an absolute path —
            # which means callers in non-git cwds (e.g. /tmp, ~/.memoir) get
            # "Not in a git repository" errors. Construction needs a chdir;
            # so do per-operation calls (`.insert`/`.update`/`.commit`/`.get`).
            # We chdir here for the constructor, then wrap the tree in
            # _CwdLockedTree so every later method call also chdir's first.
            import os as _os

            _saved_cwd = _os.getcwd()
            try:
                _os.chdir(str(self.path))
                _raw_tree = VersionedKvStore(str(data_dir))
            finally:
                _os.chdir(_saved_cwd)
            self.tree = _CwdLockedTree(_raw_tree, self.path)
        else:
            # Memory mode doesn't touch git, so no cwd wrapper needed.
            self.tree = ProllyTree("memory")

        self.enable_versioning = enable_versioning
        self.auto_commit = auto_commit
        # Storage layer doesn't need taxonomy, classifier, or search engine
        # These are handled by higher layers

        # Performance tracking
        self._stats = {"reads": 0, "writes": 0, "searches": 0, "classifications": 0}

        # Key registry for memory mode (since ProllyTree doesn't have list_keys in memory mode)
        self._keys = set()

        # Populate key registry from existing data
        self._populate_key_registry()

        # Track aggregated memories to avoid redundant updates
        self._aggregation_cache = {}

    def _populate_key_registry(self):
        """Populate the key registry from existing data in the store."""
        try:
            if hasattr(self.tree, "scan"):
                # Use scan if available to iterate through all keys
                for key_bytes, _ in self.tree.scan():
                    key_str = key_bytes.decode("utf-8")
                    self._keys.add(key_str)
            elif hasattr(self.tree, "list_keys"):
                # Use list_keys if available
                for key_bytes in self.tree.list_keys():
                    key_str = key_bytes.decode("utf-8")
                    self._keys.add(key_str)
            else:
                # No way to enumerate keys, registry will be empty initially
                # Keys will be added as they are accessed via put()
                pass

            logger.info(f"Populated key registry with {len(self._keys)} existing keys")
        except Exception as e:
            logger.warning(f"Could not populate key registry: {e}")
            # Continue without existing keys - they'll be added as accessed

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
        self, namespace: tuple, *, filter: dict | None = None, limit: int = 10
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
                # Commit the change if auto_commit is enabled
                if self.auto_commit:
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

    def get(self, namespace: tuple, key: str) -> dict | None:
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
            if self.enable_versioning and self.auto_commit:
                self.tree.commit(f"Delete {key} from {':'.join(namespace)}")
        except Exception as e:
            logger.error(f"Error deleting {full_key}: {e}")

    def commit(self, message: str = "Manual commit") -> str | None:
        """
        Manually commit pending changes to the versioned store.

        This is useful when auto_commit is disabled and you want to batch
        multiple operations before committing.

        Args:
            message: Commit message

        Returns:
            Commit hash if versioning is enabled, None otherwise
        """
        if not self.enable_versioning:
            logger.warning("Commit requested but versioning is not enabled")
            return None

        try:
            commit_hash = self.tree.commit(message)
            logger.debug(f"Manual commit successful: {message}")
            return commit_hash
        except Exception as e:
            logger.error(f"Error committing changes: {e}")
            raise

    def get_key_history(
        self, namespace: tuple, key: str, limit: int = 10
    ) -> list[dict]:
        """
        Get commit history for a specific key.

        Args:
            namespace: Namespace tuple
            key: Key to get history for
            limit: Maximum number of commits to return

        Returns:
            List of commit dictionaries with id, timestamp, message, author, committer
        """
        if not self.enable_versioning:
            return []

        full_key = ":".join(namespace) + ":" + key
        key_bytes = full_key.encode("utf-8")

        try:
            commits = self.tree.get_commits_for_key(key_bytes)
            # Limit results and return most recent first
            return commits[:limit]
        except Exception as e:
            logger.error(f"Error getting history for {full_key}: {e}")
            return []

    def get_key_at_commit(
        self, namespace: tuple, key: str, commit_id: str
    ) -> dict | None:
        """
        Get the value of a key at a specific commit.

        Note: Current implementation returns None since VersionedKvStore doesn't support
        direct commit checkout. This is a placeholder for future enhancement.

        Args:
            namespace: Namespace tuple
            key: Key to retrieve
            commit_id: Commit ID to retrieve from

        Returns:
            None (historical content retrieval not yet implemented)
        """
        if not self.enable_versioning:
            return None

        # TODO: Implement historical content retrieval when VersionedKvStore supports it
        # Current limitation: VersionedKvStore only supports branch checkout, not commit checkout
        logger.debug(
            f"Historical content retrieval not yet implemented for commit {commit_id[:8]}"
        )
        return None

    def create_time_snapshot(self, snapshot_name: str) -> bool:
        """
        Create a branch snapshot at the current point in time.

        When auto_commit=False, this will first commit any pending changes
        before creating the snapshot to ensure all recent changes are included.

        Args:
            snapshot_name: Name for the snapshot branch

        Returns:
            True if snapshot created successfully
        """
        if not self.enable_versioning:
            return False

        try:
            # If auto_commit is disabled, commit pending changes before snapshot
            if not self.auto_commit:
                commit_hash = self.commit(
                    f"Auto-commit before snapshot: {snapshot_name}"
                )
                if commit_hash:
                    logger.debug(
                        f"Auto-committed pending changes before snapshot: {commit_hash[:8]}"
                    )

            self.tree.create_branch(snapshot_name)
            logger.debug(f"Created time snapshot: {snapshot_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create snapshot {snapshot_name}: {e}")
            return False

    def get_state_at_snapshot(
        self, namespace: tuple, snapshot_name: str
    ) -> dict[str, Any]:
        """
        Get all keys in a namespace at a specific snapshot.

        Args:
            namespace: Namespace tuple
            snapshot_name: Name of the snapshot branch

        Returns:
            Dictionary of key -> value at that snapshot
        """
        if not self.enable_versioning:
            return {}

        try:
            # Save current branch
            current_branch = self.tree.current_branch()

            # Switch to snapshot
            self.tree.checkout(snapshot_name)

            # Get all keys in namespace
            state = {}
            namespace_prefix = ":".join(namespace) + ":"

            keys = self.tree.list_keys()
            for key in keys:
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                if key_str.startswith(namespace_prefix):
                    # Get value
                    value = self.tree.get(
                        key if isinstance(key, bytes) else key.encode("utf-8")
                    )
                    if value:
                        # Extract the key without namespace prefix
                        short_key = key_str[len(namespace_prefix) :]
                        state[short_key] = self._decode_value(value)

            # Return to original branch
            self.tree.checkout(current_branch)

            return state

        except Exception as e:
            logger.error(f"Failed to get state at snapshot {snapshot_name}: {e}")
            # Try to return to original branch
            with contextlib.suppress(Exception):
                self.tree.checkout(current_branch)
            return {}

    # Enhanced methods for semantic memory functionality
    async def store_memory_async(
        self, namespace: str, content: Any, key: str
    ) -> MemoryItem:
        """
        Store a memory at the given semantic key.

        Note: Classification must be done by the caller (memory manager).
        Storage layer is responsible only for storing, not classifying.

        Args:
            namespace: User/agent namespace
            content: Memory content to store
            key: Semantic key where to store (REQUIRED - no classification here)

        Returns:
            MemoryItem with storage results
        """
        # Storage layer: just use the provided semantic key (no classification)
        semantic_key = key
        confidence = 1.0  # Confidence is determined by the caller (memory manager)

        # Use semantic key for aggregation
        storage_key = semantic_key

        # Create memory entry (not the full item)
        memory_entry = {
            "content": content,
            "confidence": confidence,
            "timestamp": time.time(),
            "metadata": {},
        }

        # Convert namespace to tuple format
        if ":" in namespace:
            namespace_parts = namespace.split(":")
            namespace_tuple = tuple(namespace_parts)
        else:
            namespace_tuple = (namespace,)

        # Get existing aggregated memory or create new one
        existing = self.get(namespace_tuple, storage_key)

        if existing and isinstance(existing, dict) and "memories" in existing:
            # Append to existing aggregated memory
            aggregated = AggregatedMemory(**existing)
            aggregated.memories.append(memory_entry)
            aggregated.count += 1
            aggregated.last_timestamp = memory_entry["timestamp"]
            aggregated.last_updated = time.time()
        else:
            # Create new aggregated memory
            aggregated = AggregatedMemory(
                path=semantic_key,
                memories=[memory_entry],
                count=1,
                first_timestamp=memory_entry["timestamp"],
                last_timestamp=memory_entry["timestamp"],
            )

        # Store the aggregated memory
        self.put(namespace_tuple, storage_key, aggregated.model_dump())

        # Create MemoryItem for return value (for compatibility)
        item = MemoryItem(
            key=semantic_key,
            namespace=namespace,
            content=content,
            confidence=confidence,
            timestamp=memory_entry["timestamp"],
        )

        if self.enable_versioning and hasattr(self.tree, "get_head"):
            item.version = self.tree.get_head()

        return item

    # Sync store_memory method removed - use store_memory_async for all operations
    # This eliminates the async/sync mismatch and fallback issues

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
        # Convert string namespace to tuple format
        # "memory:general" -> ("memory", "general")
        namespace_parts = namespace.split(":")
        namespace_tuple = tuple(namespace_parts)

        search_results = self.search(namespace_tuple, limit=100)

        for _, storage_key, data in search_results:
            semantic_key = storage_key

            # Check if semantic path matches prefix
            if semantic_key.startswith(path_prefix):
                # For aggregated memories, we return them as-is
                # The search engine will handle expanding them
                if isinstance(data, dict) and "memories" in data:
                    # This is an aggregated memory - return it
                    results.append((semantic_key, data))
                else:
                    # Legacy single memory format
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
            "total_keys": len(self._keys),
            "total_namespaces": len({key.split(":")[0] for key in self._keys}),
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

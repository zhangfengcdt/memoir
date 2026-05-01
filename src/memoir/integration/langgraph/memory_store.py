# SPDX-License-Identifier: Apache-2.0
"""LangGraph memory store implementation using Memoir."""

import asyncio
import contextlib
import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from langgraph.store.base import BaseStore, Item, NamespacePath, Op, Result

from memoir.classifier.intelligent import IntelligentClassifier

# ProllyTreeMemoryStoreManager depends on the optional `langmem` extra.
# Imported lazily inside _init_search so `import memoir` works without langmem.
from memoir.integration.base import BaseIntegration
from memoir.search.intelligent import IntelligentSearchEngine
from memoir.store.prolly_adapter import ProllyTreeStore
from memoir.taxonomy.iterative import LLMIterativeTaxonomy
from memoir.taxonomy.loader import TaxonomyLoader
from memoir.taxonomy.semantic import SemanticTaxonomy

from .types import MemoryConfig, MemoryEntry

logger = logging.getLogger(__name__)


class LangGraphMemoryStore(BaseStore, BaseIntegration):
    """LangGraph-compatible memory store implementation using Memoir.

    This adapter allows LangGraph agents to use Memoir's Git-like versioned
    memory system as a drop-in replacement for the standard memory store.
    """

    def __init__(
        self,
        config: MemoryConfig | None = None,
        llm: Any | None = None,
    ):
        """Initialize the LangGraph memory store.

        Args:
            config: Memory configuration settings
            llm: Optional LLM instance for intelligent features
        """
        config = config or MemoryConfig()
        BaseIntegration.__init__(self, config.to_dict())

        self.memory_config = config
        self.llm = llm

        # Initialize components
        self._init_storage()
        self._init_taxonomy_loader()
        self._init_taxonomy()
        self._init_search()

        # Track namespaces and branches
        self._namespaces: dict[str, str] = {}  # namespace -> branch mapping
        self._current_namespace = config.namespace

    def _init_storage(self) -> None:
        """Initialize the storage layer."""
        self.store = ProllyTreeStore(
            path=self.memory_config.storage_path,
            enable_versioning=self.memory_config.enable_versioning,
        )

        # Memory manager will be initialized after search engine
        self.memory_manager = None

    def _init_taxonomy_loader(self) -> None:
        """Initialize the taxonomy loader and ensure taxonomy is in store."""
        self.taxonomy_loader = TaxonomyLoader(self.store)

        # Initialize taxonomy if not already present
        if not self.taxonomy_loader.has_taxonomy_in_store():
            logger.info("Initializing taxonomy in store...")
            self.taxonomy_loader.init_store(include_builtin=True)

    def _init_taxonomy(self) -> None:
        """Initialize the taxonomy system based on configuration."""
        taxonomy_type = self.memory_config.taxonomy_type

        if taxonomy_type == "fixed":
            self.taxonomy = SemanticTaxonomy()
            self.classifier = None
        elif taxonomy_type == "iterative" and self.llm:
            self.taxonomy = LLMIterativeTaxonomy(llm=self.llm)
            self.classifier = None
        elif taxonomy_type == "intelligent" and self.llm:
            # IntelligentClassifier manages its own taxonomy internally
            self.classifier = IntelligentClassifier(
                llm=self.llm,
                memory_store=None,  # Will be set later if needed
                taxonomy_loader=self.taxonomy_loader,
            )
            self.taxonomy = SemanticTaxonomy()  # Fallback for search
        else:
            # Fallback to fixed taxonomy
            self.taxonomy = SemanticTaxonomy()
            self.classifier = None

    def _init_search(self) -> None:
        """Initialize the search engine and complete memory manager setup."""
        if self.llm:
            self.search_engine = IntelligentSearchEngine(
                llm=self.llm,
                store=self.store,
                taxonomy_loader=self.taxonomy_loader,
            )
        else:
            # Fallback to a simple search if no LLM
            self.search_engine = None

        # Now initialize memory manager with all dependencies.
        # Lazy import: requires the `langmem` extra.
        try:
            from memoir.core.memory import ProllyTreeMemoryStoreManager
        except ImportError as e:
            raise ImportError(
                "LangGraphMemoryStore requires the 'langmem' extra. "
                "Install with: pip install 'memoir-ai[langmem]'"
            ) from e

        self.memory_manager = ProllyTreeMemoryStoreManager(
            prolly_store=self.store,
            classifier=getattr(self, "classifier", None),
            search_engine=self.search_engine,
        )

    async def initialize(self) -> None:
        """Initialize the store for async operations."""
        if not self._initialized:
            # Initialize async components if needed
            if hasattr(self.memory_manager, "initialize"):
                await self.memory_manager.initialize()
            self._initialized = True

    async def close(self) -> None:
        """Clean up resources."""
        if self._initialized:
            if hasattr(self.memory_manager, "close"):
                await self.memory_manager.close()
            self._initialized = False

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        # For sync context manager, just pass through
        pass

    # LangGraph BaseStore implementation

    async def abatch(self, ops: Sequence[Op]) -> list[Result]:
        """Execute a batch of operations.

        Args:
            ops: Sequence of operations to execute

        Returns:
            List of operation results
        """
        results = []

        for op in ops:
            try:
                if op.op == "put":
                    await self._put_items(op.namespace, op.items)
                    results.append(None)  # Successful put returns None
                elif op.op == "search":
                    items = await self._search_items(
                        op.namespace,
                        query=op.query,
                        limit=op.limit,
                    )
                    results.append(items)
                elif op.op == "delete":
                    await self._delete_items(op.namespace, op.keys)
                    results.append(None)  # Successful delete returns None
                else:
                    raise ValueError(f"Unknown operation: {op.op}")
            except Exception as e:
                logger.error(f"Operation failed: {e}")
                results.append(None)

        return results

    async def _put_items(
        self,
        namespace: NamespacePath,
        items: list[Item],
    ) -> None:
        """Store items in the memory system.

        Args:
            namespace: Namespace path for the items
            items: Items to store
        """
        # Ensure namespace branch exists
        self._get_or_create_branch(namespace)

        for item in items:
            # Convert Item to MemoryEntry
            memory_entry = self._item_to_memory_entry(item, namespace)

            # Store using memory manager
            # Combine namespace into a string for the memory manager
            namespace_str = ".".join(namespace)

            # Add thread_id and user_id to metadata
            full_metadata = memory_entry.metadata.copy()
            if memory_entry.thread_id:
                full_metadata["thread_id"] = memory_entry.thread_id
            if memory_entry.user_id:
                full_metadata["user_id"] = memory_entry.user_id

            memory_id = await self.memory_manager.store_memory(
                content=memory_entry.content,
                namespace=namespace_str,
                metadata=full_metadata,
            )

            # Store mapping of item key to memory ID only if memory_id is valid
            if item.key and memory_id:
                await self._store_key_mapping(namespace, item.key, memory_id)

    async def _search_items(
        self,
        namespace: NamespacePath,
        query: str | None = None,
        limit: int = 10,
    ) -> list[Item]:
        """Search for items in the memory system.

        Args:
            namespace: Namespace to search in
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching items
        """
        # Switch to namespace branch
        self._get_or_create_branch(namespace)
        # Note: ProllyTreeStore doesn't have checkout method
        # Branch management would need to be handled differently

        if query:
            # Perform semantic search
            namespace_str = ".".join(namespace)
            results = await self.memory_manager.search_memories(
                query=query,
                namespace=namespace_str,
                limit=limit,
            )

            # Convert results to Items
            # Check format of results (might be Memory objects)
            items = []
            for result in results:
                if hasattr(result, "content"):
                    # Memory object
                    content = result.content
                    metadata = result.metadata if hasattr(result, "metadata") else {}
                elif isinstance(result, dict):
                    # Dict format
                    content = result.get("content", "")
                    metadata = result.get("metadata", {})
                else:
                    content = str(result)
                    metadata = {}

                items.append(self._memory_to_item(content, metadata, namespace))
        else:
            # Return recent items from namespace
            items = await self._get_recent_items(namespace, limit)

        return items

    async def _delete_items(
        self,
        namespace: NamespacePath,
        keys: list[str],
    ) -> None:
        """Delete items from the memory system.

        Args:
            namespace: Namespace containing the items
            keys: Keys of items to delete
        """
        self._get_or_create_branch(namespace)
        # Branch operations would be handled by the underlying store if needed

        for key in keys:
            # Get memory ID from key mapping
            memory_id = await self._get_memory_id_from_key(namespace, key)
            if memory_id:
                # For now, just remove the mapping
                # Full deletion would require semantic path resolution
                pass

        # Commit if versioning is enabled
        if self.memory_config.enable_versioning:
            self.store.commit(f"Deleted {len(keys)} items from {namespace}")

    def batch(self, ops: Sequence[Op]) -> list[Result]:
        """Synchronous batch operations (delegates to async)."""
        return asyncio.run(self.abatch(ops))

    async def aget(
        self,
        namespace: NamespacePath,
        key: str,
    ) -> Item | None:
        """Get a single item by key.

        Args:
            namespace: Namespace containing the item
            key: Item key

        Returns:
            The item if found, None otherwise
        """
        try:
            # For now, try to get from mappings
            memory_id = await self._get_memory_id_from_key(namespace, key)
            if memory_id:
                # Try to retrieve from store using namespace + key
                # This is a simplified implementation
                data = self.store.get(namespace, key)
                if data:
                    return self._memory_to_item(
                        data.get("content", ""),
                        data.get("metadata", {}),
                        namespace,
                    )
            return None

        except Exception as e:
            logger.error(f"Failed to get item: {e}")
            return None

    def get(
        self,
        namespace: NamespacePath,
        key: str,
    ) -> Item | None:
        """Synchronous get (delegates to async)."""
        return asyncio.run(self.aget(namespace, key))

    async def asearch(
        self,
        namespace: NamespacePath,
        *,
        query: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Item]:
        """Async search for items.

        Args:
            namespace: Namespace to search in
            query: Optional search query
            limit: Maximum results
            offset: Result offset

        Returns:
            List of matching items
        """
        items = await self._search_items(namespace, query, limit + offset)
        # Apply offset
        return items[offset : offset + limit]

    def search(
        self,
        namespace: NamespacePath,
        *,
        query: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[Item]:
        """Synchronous search (delegates to async)."""
        return asyncio.run(
            self.asearch(namespace, query=query, limit=limit, offset=offset)
        )

    async def aput(
        self,
        namespace: NamespacePath,
        key: str,
        value: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a single item.

        Args:
            namespace: Namespace for the item
            key: Item key
            value: Item value
            metadata: Optional metadata
        """
        # Merge metadata into value for Item
        if isinstance(value, dict):
            value_with_metadata = {**value, "metadata": metadata or {}}
        else:
            value_with_metadata = {"content": value, "metadata": metadata or {}}

        item = Item(
            key=key,
            value=value_with_metadata,
            namespace=namespace,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        await self._put_items(namespace, [item])

    def put(
        self,
        namespace: NamespacePath,
        key: str,
        value: Any,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Synchronous put (delegates to async)."""
        asyncio.run(self.aput(namespace, key, value, metadata))

    async def adelete(
        self,
        namespace: NamespacePath,
        key: str,
    ) -> None:
        """Delete a single item.

        Args:
            namespace: Namespace containing the item
            key: Item key
        """
        await self._delete_items(namespace, [key])

    def delete(
        self,
        namespace: NamespacePath,
        key: str,
    ) -> None:
        """Synchronous delete (delegates to async)."""
        asyncio.run(self.adelete(namespace, key))

    # Helper methods

    def _get_or_create_branch(self, namespace: NamespacePath) -> str:
        """Get or create a branch for the namespace.

        Args:
            namespace: Namespace path

        Returns:
            Branch name
        """
        namespace_str = str(namespace)

        if namespace_str not in self._namespaces:
            # Create branch name from namespace
            branch_name = namespace_str.replace("/", "_").replace(".", "_")
            self._namespaces[namespace_str] = branch_name

            # Create branch if it doesn't exist
            with contextlib.suppress(Exception):
                asyncio.run(self.store.create_branch(branch_name))

        return self._namespaces[namespace_str]

    def _item_to_memory_entry(
        self,
        item: Item,
        namespace: NamespacePath,
    ) -> MemoryEntry:
        """Convert LangGraph Item to MemoryEntry.

        Args:
            item: LangGraph item
            namespace: Namespace path

        Returns:
            MemoryEntry
        """
        # Extract content and metadata from value
        if isinstance(item.value, dict):
            content = item.value.get("content", str(item.value))
            metadata = item.value.get("metadata", {})
        else:
            content = str(item.value)
            metadata = {}

        # Add namespace and key to metadata
        metadata["namespace"] = str(namespace)
        metadata["key"] = item.key

        return MemoryEntry(
            content=content,
            metadata=metadata,
            timestamp=item.created_at or datetime.now(),
            memory_id=item.key,
        )

    def _memory_to_item(
        self,
        content: str,
        metadata: dict[str, Any],
        namespace: NamespacePath | None = None,
    ) -> Item:
        """Convert memory data to LangGraph Item.

        Args:
            content: Memory content
            metadata: Memory metadata
            namespace: Optional namespace for the item

        Returns:
            LangGraph Item
        """
        return Item(
            key=metadata.get("key", ""),
            value={"content": content, "metadata": metadata},
            namespace=namespace or (),
            created_at=metadata.get("timestamp", datetime.now()),
            updated_at=metadata.get("updated_at", datetime.now()),
        )

    async def _store_key_mapping(
        self,
        namespace: NamespacePath,
        key: str,
        memory_id: str,
    ) -> None:
        """Store mapping between item key and memory ID.

        Args:
            namespace: Namespace path
            key: Item key
            memory_id: Memory ID
        """
        # Store in a special mappings namespace
        mapping_key = f"{'.'.join(namespace)}.{key}"
        self.store.put(
            namespace=("_mappings",), key=mapping_key, value={"memory_id": memory_id}
        )

    async def _get_memory_id_from_key(
        self,
        namespace: NamespacePath,
        key: str,
    ) -> str | None:
        """Get memory ID from item key.

        Args:
            namespace: Namespace path
            key: Item key

        Returns:
            Memory ID if found
        """
        mapping_key = f"{'.'.join(namespace)}.{key}"
        data = self.store.get(namespace=("_mappings",), key=mapping_key)
        return data.get("memory_id") if data else None

    async def _get_semantic_path(self, memory_id: str) -> str | None:
        """Get semantic path for a memory ID.

        Args:
            memory_id: Memory ID

        Returns:
            Semantic path if found
        """
        # Look up in index
        data = self.store.get(namespace=("_index", "memory_ids"), key=memory_id)
        return data.get("semantic_path") if data else None

    async def _get_recent_items(
        self,
        namespace: NamespacePath,
        limit: int,
    ) -> list[Item]:
        """Get recent items from a namespace.

        Args:
            namespace: Namespace path
            limit: Maximum number of items

        Returns:
            List of recent items
        """
        # Get all items from namespace using prefix search
        items = []

        # This is a simplified implementation
        # In production, you'd want to maintain a proper index
        return items[:limit]

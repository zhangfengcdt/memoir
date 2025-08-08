"""
Mock implementations for testing without full ProllyTree integration.
This allows tests to run while we develop the full integration.
"""

from datetime import datetime
from typing import Any, Optional

from langgraph.store.base import BaseStore, Item, SearchItem


class MockProllyTreeStore(BaseStore):
    """
    Mock implementation of ProllyTreeStore for testing.
    Uses in-memory storage instead of ProllyTree.
    """

    def __init__(self):
        self._data: dict[str, dict[str, Any]] = {}
        self._stats = {"reads": 0, "writes": 0, "searches": 0}

    def _namespace_key(self, namespace: tuple[str, ...], key: str) -> str:
        """Create a compound key from namespace and key."""
        return ".".join(namespace) + ":" + key

    async def aget(
        self,
        namespace: tuple[str, ...],
        key: str,
        *,
        refresh_ttl: Optional[bool] = None,
    ) -> Optional[Item]:
        """Get an item from the store."""
        self._stats["reads"] += 1

        full_key = self._namespace_key(namespace, key)
        if full_key in self._data:
            data = self._data[full_key]
            now = datetime.now()
            return Item(
                namespace=namespace,
                key=key,
                value=data["value"],
                created_at=data.get("created_at", now),
                updated_at=data.get("updated_at", now),
            )
        return None

    def get(
        self,
        namespace: tuple[str, ...],
        key: str,
        *,
        refresh_ttl: Optional[bool] = None,
    ) -> Optional[Item]:
        """Synchronous version of aget."""
        import asyncio

        return asyncio.run(self.aget(namespace, key, refresh_ttl=refresh_ttl))

    async def aput(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: dict[str, Any],
        index: Optional[list[str]] = None,
        *,
        ttl: Optional[float] = None,
    ) -> None:
        """Store an item in the store."""
        self._stats["writes"] += 1

        full_key = self._namespace_key(namespace, key)
        now = datetime.now()

        if full_key in self._data:
            # Update existing
            self._data[full_key]["value"] = value
            self._data[full_key]["updated_at"] = now
        else:
            # Create new
            self._data[full_key] = {
                "value": value,
                "created_at": now,
                "updated_at": now,
            }

    def put(
        self,
        namespace: tuple[str, ...],
        key: str,
        value: dict[str, Any],
        index: Optional[list[str]] = None,
        *,
        ttl: Optional[float] = None,
    ) -> None:
        """Synchronous version of aput."""
        import asyncio

        asyncio.run(self.aput(namespace, key, value, index, ttl=ttl))

    async def adelete(self, namespace: tuple[str, ...], key: str) -> None:
        """Delete an item from the store."""
        full_key = self._namespace_key(namespace, key)
        if full_key in self._data:
            del self._data[full_key]

    def delete(self, namespace: tuple[str, ...], key: str) -> None:
        """Synchronous version of adelete."""
        import asyncio

        asyncio.run(self.adelete(namespace, key))

    async def asearch(
        self,
        namespace_prefix: tuple[str, ...],
        /,
        *,
        query: Optional[str] = None,
        filter: Optional[dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
        refresh_ttl: Optional[bool] = None,
    ) -> list[SearchItem]:
        """Search for items in the store."""
        self._stats["searches"] += 1

        results = []
        prefix = ".".join(namespace_prefix)

        for full_key, data in list(self._data.items())[offset:]:
            if full_key.startswith(prefix):
                namespace_part, key_part = full_key.split(":", 1)
                namespace = tuple(namespace_part.split("."))

                # Simple query matching
                score = 1.0
                if query:
                    value_str = str(data["value"]).lower()
                    score = 1.0 if query.lower() in value_str else 0.5

                results.append(
                    SearchItem(
                        namespace=namespace,
                        key=key_part,
                        value=data["value"],
                        score=score,
                        created_at=data.get("created_at", datetime.now()),
                        updated_at=data.get("updated_at", datetime.now()),
                    )
                )

                if len(results) >= limit:
                    break

        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def search(
        self,
        namespace_prefix: tuple[str, ...],
        /,
        *,
        query: Optional[str] = None,
        filter: Optional[dict[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
        refresh_ttl: Optional[bool] = None,
    ) -> list[SearchItem]:
        """Synchronous version of asearch."""
        import asyncio

        return asyncio.run(
            self.asearch(
                namespace_prefix,
                query=query,
                filter=filter,
                limit=limit,
                offset=offset,
                refresh_ttl=refresh_ttl,
            )
        )

    async def alist_namespaces(
        self, prefix: tuple[str, ...] = ()
    ) -> list[tuple[str, ...]]:
        """List all namespaces with the given prefix."""
        prefixes = set()
        prefix_str = ".".join(prefix)

        for full_key in self._data:
            namespace_part = full_key.split(":", 1)[0]
            if not prefix_str or namespace_part.startswith(prefix_str):
                prefixes.add(tuple(namespace_part.split(".")))

        return list(prefixes)

    def list_namespaces(self, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
        """Synchronous version of alist_namespaces."""
        import asyncio

        return asyncio.run(self.alist_namespaces(prefix))

    async def abatch(self, ops):
        """Batch operations (not implemented)."""
        pass

    def batch(self, ops):
        """Synchronous batch operations (not implemented)."""
        pass

    def get_statistics(self) -> dict[str, Any]:
        """Get store statistics."""
        return {"total_items": len(self._data), "stats": self._stats.copy()}

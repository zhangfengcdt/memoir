# SPDX-License-Identifier: Apache-2.0
"""Vector top-k semantic search; resolves doc_ids back to memory items."""

import logging
import time
from pathlib import Path

from memoir.services.base import BaseService, StoreNotFoundError
from memoir.services.models import SearchHit, SearchResult
from memoir.services.vector_service import VectorService

logger = logging.getLogger(__name__)


class SearchService(BaseService):
    def __init__(self, store_path: str):
        super().__init__(store_path)
        self._vector_service: VectorService | None = None

    def _get_vector_service(self) -> VectorService:
        if self._vector_service is None:
            self._vector_service = VectorService(self.store_path)
        return self._vector_service

    def search(
        self, query: str, namespace: str = "default", k: int = 5
    ) -> SearchResult:
        """Top-k semantic search. Hits are ordered by ascending distance."""
        start = time.time()
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        if not VectorService.feature_available():
            return SearchResult(
                success=False,
                query=query,
                namespace=namespace,
                error=(
                    "Vector search is unavailable: prollytree was built "
                    "without the `proximity_text` feature."
                ),
            )

        store = self._get_store()
        ns_tuple = self.namespace_to_tuple(namespace)

        try:
            raw = self._get_vector_service().search(namespace, query, k=k)
        except Exception as e:
            logger.warning("vector search failed: %s", e)
            return SearchResult(
                success=False,
                query=query,
                namespace=namespace,
                timing_ms=(time.time() - start) * 1000.0,
                error=str(e),
            )
        hits: list[SearchHit] = []
        for doc_id_bytes, score in raw:
            try:
                key = doc_id_bytes.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning("non-utf8 doc_id in search results: %r", doc_id_bytes)
                continue
            try:
                value = store.get(ns_tuple, key)
            except Exception as e:
                logger.debug("resolve %s failed: %s", key, e)
                value = None
            if not isinstance(value, dict):
                # Orphan: vector index has the doc_id but primary store no
                # longer does. `purge_text_index_orphans` cleans these up.
                hits.append(
                    SearchHit(
                        key=key,
                        score=float(score),
                        content="(memory no longer present)",
                        namespace=namespace,
                        source=None,
                        related_keys=[],
                    )
                )
                continue
            hits.append(
                SearchHit(
                    key=key,
                    score=float(score),
                    content=value.get("content", ""),
                    namespace=namespace,
                    source=value.get("source"),
                    related_keys=list(value.get("related_keys") or []),
                )
            )

        return SearchResult(
            success=True,
            query=query,
            hits=hits,
            namespace=namespace,
            timing_ms=(time.time() - start) * 1000.0,
        )

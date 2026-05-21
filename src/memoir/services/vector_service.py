# SPDX-License-Identifier: Apache-2.0
"""Thin wrapper around prollytree's NamespacedKvStore text-index API."""

import logging
import os
from pathlib import Path

from memoir.services.base import BaseService, ServiceError
from memoir.store.cwd_locked import CwdLockedTree

logger = logging.getLogger(__name__)


# Prollytree persists the embedder's id+version on first open and rejects
# reopens with a mismatched embedder, so we hardcode one index per namespace.
INDEX_NAME = "watched"

# Test-only: swap in HashEmbedder to skip the MiniLm model download.
_TEST_EMBEDDER_ENV = "MEMOIR_TEST_USE_HASH_EMBEDDER"


class VectorIndexUnavailable(ServiceError):
    def __init__(self) -> None:
        super().__init__(
            "Vector search is unavailable: this prollytree wheel was built "
            "without the `proximity_text` feature. Reinstall with a wheel "
            "that includes it (the default PyPI wheel ships with it) or "
            "build from source with `--features proximity_text`.",
            code=6,
        )


class VectorService(BaseService):
    """Open, write, and search the vector index over a memoir store."""

    def __init__(self, store_path: str) -> None:
        super().__init__(store_path)
        self._ns_store = None
        self._embedder = None
        self._opened: set[tuple[str, str]] = set()

    @staticmethod
    def feature_available() -> bool:
        try:
            import prollytree
        except ImportError:
            return False
        return bool(getattr(prollytree, "proximity_text_available", False))

    def _get_ns_store(self):
        # CwdLockedTree wraps the handle because prollytree's Rust binding uses
        # cwd (not the constructor path) to locate the enclosing git repo on
        # every op.
        if self._ns_store is None:
            from prollytree.prollytree import NamespacedKvStore

            data_dir = Path(self.store_path) / "data"
            if not data_dir.exists():
                raise ServiceError(
                    f"Vector store not initialized at {data_dir}. Create the "
                    f"memoir store first with `memoir new <path>`.",
                    code=3,
                )
            saved = os.getcwd()
            try:
                os.chdir(self.store_path)
                raw = NamespacedKvStore(str(data_dir))
            finally:
                os.chdir(saved)
            self._ns_store = CwdLockedTree(raw, self.store_path)
        return self._ns_store

    def _get_embedder(self):
        if self._embedder is not None:
            return self._embedder
        if not self.feature_available():
            raise VectorIndexUnavailable()

        import prollytree

        if os.environ.get(_TEST_EMBEDDER_ENV) == "1":
            self._embedder = prollytree.HashEmbedder(dim=384, seed=0)
        else:
            cache_dir = (
                Path(os.environ.get("PROLLYTREE_EMBEDDER_CACHE", "~"))
                .expanduser()
                .joinpath(".cache", "prollytree", "embedders")
                if not os.environ.get("PROLLYTREE_EMBEDDER_CACHE")
                else Path(os.environ["PROLLYTREE_EMBEDDER_CACHE"]).expanduser()
            )
            if not cache_dir.exists():
                logger.info(
                    "First-run: downloading ~90 MB MiniLM embedder weights into %s",
                    cache_dir,
                )
            self._embedder = prollytree.MiniLmEmbedder()
        return self._embedder

    # -------- vector ops ----------------------------------------------------

    def open(self, namespace: str, idx_name: str = INDEX_NAME) -> None:
        """Open the text index for ``namespace`` (idempotent)."""
        ns_store = self._get_ns_store()
        embedder = self._get_embedder()
        ns_store.text_index_open(namespace, idx_name, embedder)
        self._opened.add((namespace, idx_name))

    def index(
        self,
        namespace: str,
        doc_id: bytes,
        text: str,
        idx_name: str = INDEX_NAME,
    ) -> None:
        """Embed ``text`` under ``doc_id`` (upsert)."""
        if (namespace, idx_name) not in self._opened:
            self.open(namespace, idx_name)
        ns_store = self._get_ns_store()
        ns_store.text_index_insert(namespace, idx_name, doc_id, text)

    def delete(
        self,
        namespace: str,
        doc_id: bytes,
        idx_name: str = INDEX_NAME,
    ) -> bool:
        """Remove ``doc_id`` from the index. Returns True if any chunks matched."""
        if (namespace, idx_name) not in self._opened:
            self.open(namespace, idx_name)
        ns_store = self._get_ns_store()
        return ns_store.text_index_delete(namespace, idx_name, doc_id)

    def search(
        self,
        namespace: str,
        query: str,
        k: int = 5,
        idx_name: str = INDEX_NAME,
    ) -> list[tuple[bytes, float]]:
        """Top-k semantic search, returns ``[(doc_id, distance), ...]``."""
        if (namespace, idx_name) not in self._opened:
            self.open(namespace, idx_name)
        ns_store = self._get_ns_store()
        return ns_store.text_index_search(namespace, idx_name, query, k)

    def commit(self, message: str = "vector index update") -> str | None:
        """Persist dirty index state. Returns the commit hash, or None on no-op."""
        ns_store = self._get_ns_store()
        try:
            return ns_store.commit(message)
        except Exception as e:
            if "no changes" in str(e).lower() or "empty" in str(e).lower():
                return None
            raise

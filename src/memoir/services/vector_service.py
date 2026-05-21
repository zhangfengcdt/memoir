# SPDX-License-Identifier: Apache-2.0
"""Thin wrapper around prollytree's NamespacedKvStore text-index API.

Memoir's primary adapter (``ProllyTreeStore`` in ``memoir.store.prolly_adapter``)
wraps a ``VersionedKvStore``. The text-index methods (``text_index_open``,
``text_index_insert``, ``text_index_search``, ``text_index_delete``) live on
the sibling ``NamespacedKvStore`` class. To use them without rewriting the
existing adapter, ``VectorService`` opens a second prollytree handle —
a ``NamespacedKvStore`` against the same ``data/`` directory — and exposes
only the vector ops through it.

As of prollytree's namespaced-config-file split, the two stores write to
separate config files (``prolly_config_tree_config`` for the versioned tree,
``prolly_config_namespaced_root`` for the namespace tree), so they no
longer clobber each other's root hash. ``versioned_config_preserved`` is
kept as a no-op context manager so call sites compiled against earlier
memoir versions don't need to change.
"""

import contextlib
import logging
import os
from pathlib import Path

from memoir.services.base import BaseService, ServiceError
from memoir.store.cwd_locked import CwdLockedTree

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def versioned_config_preserved(store_path: str):
    """No-op context manager kept for backward compatibility.

    Previously snapshotted ``data/prolly_config_tree_config`` around any
    ``NamespacedKvStore`` operation to work around a shared-filename
    collision. Prollytree now writes the namespace store's root hash to
    a separate file (``prolly_config_namespaced_root``), so the
    workaround is no longer needed. Yielding a no-op preserves the
    public API for any out-of-tree callers.
    """
    _ = store_path  # accepted for backward-compat
    yield


# Single text index per namespace in v1. Prollytree validates the embedder's
# id+version on reopen against the values persisted at first open, so a
# single-named index per namespace keeps that check meaningful. If we ever
# want to host multiple embedders in the same namespace, promote this to a
# constructor arg.
INDEX_NAME = "watched"

# When set, VectorService uses HashEmbedder (deterministic, no model download)
# instead of MiniLmEmbedder. Test-only knob; do not document publicly.
_TEST_EMBEDDER_ENV = "MEMOIR_TEST_USE_HASH_EMBEDDER"


class VectorIndexUnavailable(ServiceError):
    """Raised when prollytree was built without proximity_text (e.g. a sdist
    install on a machine that couldn't compile the Candle deps).
    """

    def __init__(self) -> None:
        super().__init__(
            "Vector search is unavailable: this prollytree wheel was built "
            "without the `proximity_text` feature. Reinstall with a wheel "
            "that includes it (the default PyPI wheel ships with it) or "
            "build from source with `--features proximity_text`.",
            code=6,
        )


class VectorService(BaseService):
    """Open, write, and search the vector index over a memoir store.

    Lazy-opens a single ``MiniLmEmbedder`` per process on the first call to
    ``open()``. Subsequent ``open()`` calls in different namespaces reuse the
    same embedder instance — the model download / load only happens once.
    """

    def __init__(self, store_path: str) -> None:
        super().__init__(store_path)
        self._ns_store = None
        self._embedder = None
        # Track which (ns, idx) pairs we've already opened in this process so
        # `index()` / `delete()` / `search()` can lazy-open just-in-time.
        self._opened: set[tuple[str, str]] = set()

    # -------- feature gate --------------------------------------------------

    @staticmethod
    def feature_available() -> bool:
        """True if this prollytree build includes proximity_text (the
        MiniLmEmbedder side). Cheap to call; safe to call before construction.
        """
        try:
            import prollytree
        except ImportError:
            return False
        return bool(getattr(prollytree, "proximity_text_available", False))

    # -------- lazy handles --------------------------------------------------

    def _get_ns_store(self):
        """Lazily open a NamespacedKvStore against ``<store>/data``.

        Prollytree's ``NamespacedKvStore(path)`` constructor is now
        idempotent — it detects an existing namespaced store and routes
        to ``open()`` internally, so we no longer need the
        try-open-fall-back-to-init dance memoir used to do here.

        Wraps the raw handle in ``CwdLockedTree`` so every method call
        chdir's into the store path first — required because prollytree's
        Rust binding uses cwd (not the path passed to the constructor)
        to locate the enclosing git repo on every op.
        """
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
        """Lazily construct the embedder. Returns a MiniLmEmbedder by default,
        or a HashEmbedder when ``MEMOIR_TEST_USE_HASH_EMBEDDER=1`` is set
        (tests use this to skip the 90 MB model download)."""
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
                    "First-run setup: downloading ~90 MB MiniLM embedder weights "
                    "into %s — this is a one-time cost.",
                    cache_dir,
                )
            self._embedder = prollytree.MiniLmEmbedder()
        return self._embedder

    # -------- vector ops ----------------------------------------------------

    def open(self, namespace: str, idx_name: str = INDEX_NAME) -> None:
        """Open the text index for ``namespace`` (idempotent).

        On the very first open against a fresh store, persists the embedder's
        id+version into the index metadata. Subsequent opens with a different
        embedder identity hard-fail inside prollytree with a clear error —
        we let that surface unchanged.
        """
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
        """Embed ``text`` under ``doc_id`` in the index. Auto-opens the index
        for this namespace if not already opened in this process.

        Upsert semantics: prollytree deletes any prior chunks for ``doc_id``
        before inserting new ones — no need for a separate delete call when
        re-indexing the same doc with updated content.
        """
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
        """Remove ``doc_id`` from the index. Returns True if any chunks were
        removed, False if nothing matched. Auto-opens the index for this
        namespace if not already opened.
        """
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
        """Top-k semantic search. Returns ``[(doc_id_bytes, distance), ...]``
        in ascending distance (smaller = closer). Resolution back to the
        primary memory item happens one level up (SearchService).
        """
        if (namespace, idx_name) not in self._opened:
            self.open(namespace, idx_name)
        ns_store = self._get_ns_store()
        return ns_store.text_index_search(namespace, idx_name, query, k)

    def commit(self, message: str = "vector index update") -> str | None:
        """Persist any dirty index state. Required before the search results
        will reflect any writes made through ``index()`` / ``delete()``.

        Returns the commit hash, or None if there were no changes to commit.
        """
        ns_store = self._get_ns_store()
        try:
            return ns_store.commit(message)
        except Exception as e:
            # Prollytree raises on empty-commit attempts; treat as no-op.
            if "no changes" in str(e).lower() or "empty" in str(e).lower():
                return None
            raise

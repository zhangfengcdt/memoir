# SPDX-License-Identifier: Apache-2.0
"""Thin wrapper around prollytree's NamespacedKvStore text-index API.

Memoir's primary adapter (``ProllyTreeStore`` in ``memoir.store.prolly_adapter``)
wraps a ``VersionedKvStore``. The text-index methods (``text_index_open``,
``text_index_insert``, ``text_index_search``, ``text_index_delete``) live on
the sibling ``NamespacedKvStore`` class. To use them without rewriting the
existing adapter, ``VectorService`` opens a second prollytree handle —
a ``NamespacedKvStore`` against the same ``data/`` directory — and exposes
only the vector ops through it.

Coexistence is verified by ``tests/test_proximity_smoke.py`` (P0 gate). Two
commits per scan reality: writes through ``VectorService`` are persisted by
``vector_service.commit(...)``, which is a separate git commit from
``ProllyTreeStore.commit(...)``. Callers that need both stores in sync should
commit data first, index second, and accept that a crash in between leaves
the index slightly behind (next scan re-detects unchanged files via hash and
re-indexes — no correctness loss, only wasted LLM tokens).
"""

import contextlib
import logging
import os
from pathlib import Path

from memoir.services.base import BaseService, ServiceError
from memoir.store.cwd_locked import CwdLockedTree

logger = logging.getLogger(__name__)

# Filename inside ``<store>/data`` that holds the active prolly tree's
# root hash. Shared between ``VersionedKvStore`` and ``NamespacedKvStore``
# in prollytree 0.3.x — both write it on commit, last writer wins on disk.
_TREE_CONFIG_FILENAME = "prolly_config_tree_config"


@contextlib.contextmanager
def versioned_config_preserved(store_path: str):
    """Preserve ``data/prolly_config_tree_config`` across a code block
    that may open or commit through ``NamespacedKvStore``.

    Why this exists: ``NamespacedKvStore.open()`` and ``.commit()`` both
    write the config file with the *namespace* tree's placeholder root
    hash, even though the actual data tree maintained by
    ``VersionedKvStore`` is unchanged. If we exit the process with the
    placeholder hash on disk, the next process's ``VersionedKvStore.open()``
    can't reconstruct its tree and every subsequent read returns None.

    The fix: snapshot the file bytes on entry, write them back on exit.
    Cheap (one file read + write, no git commit), matches the in-memory
    state both stores already cached, and leaves
    ``prolly_namespace_registry`` / ``prolly_hash_mappings`` untouched
    so the namespace store remains fully readable.

    Caveat: between snapshot/restore and the next data write, the
    working tree diverges from HEAD (HEAD's commit holds the placeholder;
    the file holds the data tree's root). The next data write through
    ``VersionedKvStore`` reconciles via its auto-commit. ``git status``
    would show this file as modified in the meantime — cosmetic.
    """
    config_path = Path(store_path) / "data" / _TREE_CONFIG_FILENAME
    snapshot: bytes | None = None
    if config_path.exists():
        try:
            snapshot = config_path.read_bytes()
        except OSError as e:
            logger.warning("config snapshot read failed: %s", e)
            snapshot = None
    try:
        yield
    finally:
        if snapshot is not None:
            try:
                current = config_path.read_bytes() if config_path.exists() else None
                if current != snapshot:
                    config_path.write_bytes(snapshot)
            except OSError as e:
                logger.warning("config restore write failed: %s", e)


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

        Prefers ``NamespacedKvStore.open(path)`` (the static method) over
        the constructor. The constructor (``NamespacedKvStore(path)``)
        unconditionally re-runs ``GitNamespacedKvStore::init``, which
        creates a new ``"Initial namespaced store"`` git commit every
        time it's called — even on already-initialized stores. That
        means every memoir process that ran ``memoir search`` would add
        a junk commit to history. ``.open`` skips the init step.

        On first creation of the store the file doesn't exist yet, so
        ``open`` raises — we fall back to the constructor in that case,
        which is the one and only legitimate use of ``init``.

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
                try:
                    raw = NamespacedKvStore.open(str(data_dir))
                except Exception as e:
                    # First-time open on a fresh store has no namespace
                    # metadata yet — fall back to the init constructor.
                    logger.debug("NamespacedKvStore.open failed (%s); init", e)
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

"""Smoke test: a memoir store can host both VersionedKvStore (the existing
adapter's primary handle) and NamespacedKvStore (where the new text-index
methods live) against the same ``data/`` directory.

This is the P0 gate for the ``memoir watch`` feature. If these two prollytree
handles fight over ``data/prolly_config_tree_config`` or the underlying root
hashes, the watch feature has to swap the whole adapter to NamespacedKvStore
before going further — a much larger refactor.
"""

import tempfile
from pathlib import Path

import prollytree
import pytest
from prollytree.prollytree import NamespacedKvStore

from memoir.services.store_service import StoreService

# Both vector indexing and the MiniLM embedder require prollytree's
# `proximity` / `proximity_text` Cargo features. Skip the whole module if the
# wheel was built without them.
if not getattr(prollytree, "proximity_text_available", False):
    pytest.skip(
        "prollytree built without proximity_text feature; skipping vector smoke",
        allow_module_level=True,
    )


@pytest.fixture
def memoir_store():
    """Create a real memoir store in a tempdir via StoreService.create_store.

    Returns the absolute store path. Mirrors what `memoir new <path>` does in
    production: git init, hardened gc config, data/ dir, initial commit.
    """
    with tempfile.TemporaryDirectory() as tmp:
        store_path = Path(tmp) / "store"
        result = StoreService(str(store_path)).create_store(str(store_path))
        assert result.success, result.error
        yield store_path


def test_prollytree_features_present():
    """Sanity: feature gate is on and required types are importable."""
    assert getattr(prollytree, "proximity_text_available", False) is True
    assert prollytree.NamespacedKvStore is not None
    assert prollytree.MiniLmEmbedder is not None
    assert prollytree.HashEmbedder is not None
    assert prollytree.VersionedKvStore is not None


def test_namespaced_store_coexists_with_versioned_store(memoir_store):
    """The new vector_service will open a NamespacedKvStore alongside the
    existing ProllyTreeStore (VersionedKvStore-backed). Confirm both can:

    1. open against the same data/ directory without exception,
    2. write through their respective APIs,
    3. read back what each wrote,
    4. exercise the text-index methods (open/insert/search/delete),
    5. commit independently without corrupting each other's state.
    """
    from memoir.store.prolly_adapter import ProllyTreeStore

    data_dir = memoir_store / "data"

    # Existing adapter (VersionedKvStore under the hood).
    primary = ProllyTreeStore(
        path=str(memoir_store), enable_versioning=True, auto_commit=True
    )
    primary.put(("default",), "knowledge.test.first", {"content": "from primary"})

    # NEW: NamespacedKvStore against the same data/ dir. cwd-locked dance to
    # match the constructor-time chdir the adapter does.
    import os as _os

    saved = _os.getcwd()
    try:
        _os.chdir(str(memoir_store))
        ns_store = NamespacedKvStore(str(data_dir))
    finally:
        _os.chdir(saved)

    # Use a deterministic embedder for the smoke test — no model download
    # required, fast, identical across machines.
    embedder = prollytree.HashEmbedder(dim=64, seed=0)

    # Open a text index in a fresh namespace (don't touch the namespace the
    # primary handle is writing into; ns_insert/ns_get use a different key
    # space from the VersionedKvStore composite keys anyway).
    def _ns(*args):
        # Same cwd-locked pattern the adapter uses, applied to ns calls.
        saved = _os.getcwd()
        try:
            _os.chdir(str(memoir_store))
            return args[0](*args[1:])
        finally:
            _os.chdir(saved)

    _ns(ns_store.text_index_open, "vector_smoke", "watched", embedder)

    docs = {
        b"doc:1": "the quick brown fox jumps over the lazy dog",
        b"doc:2": "rust is a systems programming language",
        b"doc:3": "merkle trees enable verifiable data structures",
    }
    for doc_id, text in docs.items():
        _ns(ns_store.text_index_insert, "vector_smoke", "watched", doc_id, text)

    # Commit on the namespaced handle — this is the moment of truth for
    # coexistence. If the two stores fight over the same config file or
    # root hash, this raises.
    commit_hash = _ns(ns_store.commit, "vector smoke seed")
    assert commit_hash is not None

    # Search through the index.
    hits = _ns(ns_store.text_index_search, "vector_smoke", "watched", "fox jumped", 2)
    assert len(hits) == 2
    assert hits[0][0] == b"doc:1"  # exact-ish match wins
    for doc_id, score in hits:
        assert isinstance(doc_id, bytes)
        assert isinstance(score, float)

    # Confirm primary handle's writes are still readable after the
    # namespaced commit — i.e. the two stores aren't clobbering each
    # other's state.
    primary_value = primary.get(("default",), "knowledge.test.first")
    assert primary_value is not None
    assert primary_value.get("content") == "from primary"

    # Delete one entry through the namespaced API and re-search; the
    # deleted doc should no longer appear.
    removed = _ns(ns_store.text_index_delete, "vector_smoke", "watched", b"doc:1")
    assert removed is True
    _ns(ns_store.commit, "vector smoke delete")

    hits = _ns(ns_store.text_index_search, "vector_smoke", "watched", "fox jumped", 3)
    returned_ids = {h[0] for h in hits}
    assert b"doc:1" not in returned_ids


def test_minilm_embedder_constructs():
    """MiniLmEmbedder() should at least *construct* without raising. We don't
    call embed() here to avoid the ~90 MB model download during normal CI;
    callers that need an end-to-end MiniLM test should do it in a slow/marked
    integration suite.
    """
    emb = prollytree.MiniLmEmbedder()
    assert emb.dim == 384
    # `id` and `version` are persisted by text_index_open for the
    # embedder-identity check on reopen — verify the strings are non-empty.
    assert isinstance(emb.id, str)
    assert emb.id
    assert isinstance(emb.version, str)
    assert emb.version

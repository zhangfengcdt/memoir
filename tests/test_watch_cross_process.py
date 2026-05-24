"""Cross-process regression tests for the watch + search code paths.

Each test drops every in-process handle between operations to simulate a
process boundary. Originally written to repro a config-file collision
between ``VersionedKvStore`` and ``NamespacedKvStore`` (both wrote
``prolly_config_tree_config``, last writer won, the next process's
``VersionedKvStore.open()`` fell back to an empty tree). Prollytree now
writes a separate ``prolly_config_namespaced_root`` for the namespace
store, so the collision is gone — these tests stay as guards against
future regressions in cross-process data visibility.
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import prollytree
import pytest

if not getattr(prollytree, "proximity_text_available", False):
    pytest.skip(
        "prollytree built without proximity_text; skip cross-process test",
        allow_module_level=True,
    )

from memoir.classifier.intelligent import SliceClassification
from memoir.services.store_service import StoreService
from memoir.services.watch_service import WatchService

os.environ.setdefault("MEMOIR_TEST_USE_HASH_EMBEDDER", "1")


@pytest.fixture
def memoir_store():
    with tempfile.TemporaryDirectory() as tmp:
        store_path = Path(tmp) / "store"
        res = StoreService(str(store_path)).create_store(str(store_path))
        assert res.success, res.error
        yield store_path


@pytest.fixture
def docs_dir(tmp_path):
    d = tmp_path / "docs"
    d.mkdir()
    (d / "async.md").write_text("# Async\nasyncio coroutines\n")
    (d / "rust.md").write_text("# Rust\nownership rules\n")
    return d


def _build_watch(store_path: Path, *, paths=("knowledge.test.demo",)):
    """WatchService wired with a mocked classifier and a mocked markitdown
    so each test runs deterministically and without an LLM key."""
    svc = WatchService(str(store_path))
    ms = svc._get_memory_service()

    async def _one_slice(text, *, max_slices=50, window_chars=100_000):
        return [
            SliceClassification(
                start=0,
                end=len(text),
                paths=list(paths),
                confidence=0.9,
                reasoning="mocked",
            )
        ]

    fake_cls = MagicMock()
    fake_cls.classify_slices_async = AsyncMock(side_effect=_one_slice)
    ms._classifier = fake_cls
    svc._classifier = fake_cls

    class _FakeMd:
        def convert(self, path):
            r = MagicMock()
            r.text_content = Path(path).read_text()
            return r

    svc._markitdown_factory = lambda: _FakeMd()
    return svc


def _read_data_fresh(store_path: Path, namespace: str, key: str):
    """Open a brand-new VersionedKvStore handle and read one key. Mimics
    what happens at the start of a new process."""
    from memoir.services.memory_service import MemoryService

    fresh_store = MemoryService(str(store_path))._get_store()
    return fresh_store.get((namespace,), key)


def _fresh_search(store_path: Path, query: str, k: int = 3):
    """Run search via a fresh SearchService — a new process boundary."""
    from memoir.services.search_service import SearchService

    return SearchService(str(store_path)).search(query, namespace="default", k=k)


def test_data_survives_in_fresh_process(memoir_store, docs_dir):
    """After watch.add, a brand-new MemoryService must still see the data."""
    svc = _build_watch(memoir_store)
    res = asyncio.run(svc.add(str(docs_dir), namespace="default"))
    assert res.success
    assert res.scan.files_indexed == 2
    del svc

    # Slice mode: a single-slice file's key is the bare classified path
    # (the `.N` collision suffix only kicks in for repeated paths within
    # one file).
    value = _read_data_fresh(memoir_store, "default", "knowledge.test.demo")
    assert value is not None
    assert value.get("content"), value
    assert value.get("source", {}).get("kind") == "watch"


def test_repeated_search_survives_fresh_handles(memoir_store, docs_dir):
    """Repeated searches across process boundaries keep returning content
    (not "(memory no longer present)" stubs)."""
    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(docs_dir), namespace="default"))
    del svc

    for attempt in (1, 2, 3):
        result = _fresh_search(memoir_store, "ownership", k=3)
        assert result.success, result.error
        assert result.hits, f"attempt {attempt}: no hits"
        top = result.hits[0]
        assert top.content, f"attempt {attempt}: empty content"
        assert (
            top.content != "(memory no longer present)"
        ), f"attempt {attempt}: orphan stub returned"


def test_rescan_then_fresh_search(memoir_store, docs_dir):
    """No-op rescan must not break a subsequent fresh search."""
    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(docs_dir), namespace="default"))
    del svc

    svc2 = _build_watch(memoir_store)
    rescans = asyncio.run(svc2.scan(path=str(docs_dir)))
    assert len(rescans) == 1
    assert rescans[0].success
    assert rescans[0].files_indexed == 0
    assert rescans[0].files_unchanged == 2
    del svc2

    result = _fresh_search(memoir_store, "ownership", k=2)
    assert result.success
    assert result.hits
    assert result.hits[0].content
    assert result.hits[0].content != "(memory no longer present)"


def test_search_then_rescan_then_fresh_search(memoir_store, docs_dir):
    """Interleave: watch add → search → rescan → search."""
    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(docs_dir), namespace="default"))
    del svc

    # First search.
    r1 = _fresh_search(memoir_store, "ownership", k=2)
    assert r1.success
    assert r1.hits[0].content != "(memory no longer present)"

    # Re-scan from fresh handles after a search.
    svc2 = _build_watch(memoir_store)
    rescans = asyncio.run(svc2.scan(path=str(docs_dir)))
    assert rescans[0].success
    del svc2

    # Second search in another fresh process.
    r2 = _fresh_search(memoir_store, "ownership", k=2)
    assert r2.success
    assert r2.hits, "second search returned no hits"
    assert r2.hits[0].content != "(memory no longer present)"


def test_purge_then_fresh_search(memoir_store, docs_dir):
    """watch add → drop handles → watch remove --purge → drop handles →
    search. Purge opens both stores and must end with a VersionedKvStore
    write so a subsequent fresh open still works (even though the
    purged data is gone)."""
    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(docs_dir), namespace="default"))
    del svc

    # Sanity: data is there before the purge.
    pre = _read_data_fresh(memoir_store, "default", "knowledge.test.demo")
    assert pre is not None

    svc2 = _build_watch(memoir_store)
    rm = svc2.remove(str(docs_dir), purge=True)
    assert rm.success
    assert rm.files_removed == 2
    del svc2

    # After purge, the memory key should be gone (not just unreadable).
    post = _read_data_fresh(memoir_store, "default", "knowledge.test.demo")
    assert post is None, "purge should have deleted the memory entry"

    # And we should still be able to read other parts of the store —
    # specifically the registry, which lives under the watch namespace.
    from memoir.services.memory_service import MemoryService

    store = MemoryService(str(memoir_store))._get_store()
    paths_meta = store.get(("watch",), "paths")
    assert paths_meta is not None, (
        "Post-purge fresh open cannot read watch:paths — purge "
        "left the config file pointing at the namespace tree. The "
        "remove(purge=True) code path must end with a VersionedKvStore "
        "write."
    )
    assert paths_meta.get("paths") == []


def test_search_skips_files_deleted_between_scans(memoir_store, docs_dir):
    """End-to-end: index files, delete one on disk, re-scan, then search.
    The deleted file's content must not surface as a "(memory no longer
    present)" stub — the scan should have cleaned both the data and the
    vector index."""
    svc = _build_watch(memoir_store, paths=("knowledge.test.demo",))
    asyncio.run(svc.add(str(docs_dir), namespace="default"))
    del svc

    deleted_path = docs_dir / "rust.md"
    deleted_path.unlink()

    svc2 = _build_watch(memoir_store, paths=("knowledge.test.demo",))
    rescan = asyncio.run(svc2.scan(path=str(docs_dir)))
    assert rescan[0].files_deleted == 1
    del svc2

    result = _fresh_search(memoir_store, "ownership", k=5)
    assert result.success
    for hit in result.hits:
        assert hit.content != "(memory no longer present)", (
            "deleted file surfaced as an orphan; scan cleanup did not "
            "remove its vector index entry"
        )
        if hit.source:
            assert hit.source.get("abs_path") != str(deleted_path), (
                "deleted file still surfacing in search; scan cleanup "
                "did not remove its memory entry"
            )


def test_search_with_no_matching_hits(memoir_store, docs_dir):
    """Edge case: a search that returns zero hits still touches the
    namespace store. The marker write must run on this path too,
    otherwise a follow-up search would see a corrupted config."""
    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(docs_dir), namespace="default"))
    del svc

    # First search: deliberately bizarre query. HashEmbedder returns
    # something, but content is fine either way — we care about the
    # follow-up read working.
    r1 = _fresh_search(memoir_store, "xyzzy_no_match_garbage", k=3)
    assert r1.success
    # Whatever hits we get, the data must still be readable in the next
    # fresh process.
    value = _read_data_fresh(memoir_store, "default", "knowledge.test.demo")
    assert value is not None, (
        "Post-search fresh data read failed even when the search "
        "returned no useful hits. The marker write must always run."
    )
    assert value.get("content")

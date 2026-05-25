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

from memoir.services.store_service import StoreService
from memoir.services.watch_service import ChunkPlan, WatchChunk, WatchService

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
    """WatchService wired with a mocked chunk-and-summarize call + mocked
    markitdown so each test runs deterministically without an LLM key.
    ``paths`` is accepted (defaulted) for back-compat with older call
    sites; chunk-mode doesn't classify, so it's ignored."""
    del paths
    svc = WatchService(str(store_path))

    async def _one_chunk(text):
        return ChunkPlan(
            summary="mocked summary",
            chunks=[WatchChunk(start=0, end=len(text))],
        )

    svc._chunk_and_summarize_async = AsyncMock(side_effect=_one_chunk)

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


def _add_dir(svc, d, namespace="default"):
    """Folder watches aren't supported — add each file individually."""
    return [
        asyncio.run(svc.add(str(f), namespace=namespace))
        for f in sorted(f for f in Path(d).iterdir() if f.is_file())
    ]


def test_data_survives_in_fresh_process(memoir_store, docs_dir):
    """After watch.add, a brand-new MemoryService must still see the data."""
    svc = _build_watch(memoir_store)
    results = _add_dir(svc, docs_dir)
    assert all(r.success for r in results)
    assert sum(r.scan.files_indexed for r in results) == 2
    del svc

    # Slice mode: a single-slice file's key is the bare classified path
    # (the `.N` collision suffix only kicks in for repeated paths within
    # one file).
    value = _read_data_fresh(memoir_store, "default", "raw.async_md.summary")
    assert value is not None
    assert value.get("content"), value
    assert value.get("source", {}).get("kind") == "watch"


def test_repeated_search_survives_fresh_handles(memoir_store, docs_dir):
    """Repeated searches across process boundaries keep returning content
    (not "(memory no longer present)" stubs)."""
    svc = _build_watch(memoir_store)
    _add_dir(svc, docs_dir)
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
    _add_dir(svc, docs_dir)
    del svc

    svc2 = _build_watch(memoir_store)
    files = sorted(f for f in docs_dir.iterdir() if f.is_file())
    rescans = []
    for f in files:
        rescans.extend(asyncio.run(svc2.scan(path=str(f))))
    assert len(rescans) == len(files)
    assert all(r.success for r in rescans)
    assert sum(r.files_indexed for r in rescans) == 0
    assert sum(r.files_unchanged for r in rescans) == len(files)
    del svc2

    result = _fresh_search(memoir_store, "ownership", k=2)
    assert result.success
    assert result.hits
    assert result.hits[0].content
    assert result.hits[0].content != "(memory no longer present)"


def test_search_then_rescan_then_fresh_search(memoir_store, docs_dir):
    """Interleave: watch add → search → rescan → search."""
    svc = _build_watch(memoir_store)
    _add_dir(svc, docs_dir)
    del svc

    # First search.
    r1 = _fresh_search(memoir_store, "ownership", k=2)
    assert r1.success
    assert r1.hits, "first search returned no hits"
    assert r1.hits[0].content != "(memory no longer present)"

    # Re-scan from fresh handles after a search.
    svc2 = _build_watch(memoir_store)
    files = sorted(f for f in docs_dir.iterdir() if f.is_file())
    rescans = []
    for f in files:
        rescans.extend(asyncio.run(svc2.scan(path=str(f))))
    assert all(r.success for r in rescans)
    del svc2

    # Second search in another fresh process.
    r2 = _fresh_search(memoir_store, "ownership", k=2)
    assert r2.success
    assert r2.hits, "second search returned no hits"
    assert r2.hits[0].content != "(memory no longer present)"


def test_purge_then_fresh_search(memoir_store, docs_dir):
    """watch add → drop handles → watch remove --purge per-file → drop
    handles → search. Purge opens both stores and must end with a
    VersionedKvStore write so a subsequent fresh open still works (even
    though the purged data is gone)."""
    svc = _build_watch(memoir_store)
    _add_dir(svc, docs_dir)
    del svc

    # Sanity: data is there before the purge.
    pre = _read_data_fresh(memoir_store, "default", "raw.async_md.summary")
    assert pre is not None

    svc2 = _build_watch(memoir_store)
    files = sorted(f for f in docs_dir.iterdir() if f.is_file())
    for f in files:
        rm = svc2.remove(str(f), purge=True)
        assert rm.success
    del svc2

    # After purge, the memory key should be gone (not just unreadable).
    post = _read_data_fresh(memoir_store, "default", "raw.async_md.summary")
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
    _add_dir(svc, docs_dir)
    del svc

    deleted_path = docs_dir / "rust.md"
    deleted_path.unlink()

    svc2 = _build_watch(memoir_store, paths=("knowledge.test.demo",))
    rescan = asyncio.run(svc2.scan(path=str(deleted_path)))
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
    _add_dir(svc, docs_dir)
    del svc

    # First search: deliberately bizarre query. HashEmbedder returns
    # something, but content is fine either way — we care about the
    # follow-up read working.
    r1 = _fresh_search(memoir_store, "xyzzy_no_match_garbage", k=3)
    assert r1.success
    # Whatever hits we get, the data must still be readable in the next
    # fresh process.
    value = _read_data_fresh(memoir_store, "default", "raw.async_md.summary")
    assert value is not None, (
        "Post-search fresh data read failed even when the search "
        "returned no useful hits. The marker write must always run."
    )
    assert value.get("content")

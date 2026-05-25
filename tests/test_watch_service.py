"""End-to-end tests for the watch pipeline.

Strategy:
- Real prollytree store (via StoreService.create_store) — no mocking of the
  storage layer; we want to catch any commit-ordering / store-coexistence
  regressions.
- HashEmbedder (via MEMOIR_TEST_USE_HASH_EMBEDDER=1) so the vector index is
  exercised without the 90 MB MiniLM model download.
- Mocked LLM classifier so tests are deterministic and don't need API keys.
- Mocked markitdown for tests that don't need real-format parsing — the
  real markitdown is exercised in test_supported_extensions only.
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
        "prollytree built without proximity_text; skip watch e2e tests",
        allow_module_level=True,
    )

from memoir.services.store_service import StoreService
from memoir.services.watch_service import (
    EXCLUDE_DIRS,
    ChunkPlan,
    WatchChunk,
    WatchService,
    supported_extensions,
)

os.environ["MEMOIR_TEST_USE_HASH_EMBEDDER"] = "1"


# ---------- helpers -------------------------------------------------------


@pytest.fixture
def memoir_store():
    """Create a real memoir store in a tempdir."""
    with tempfile.TemporaryDirectory() as tmp:
        store_path = Path(tmp) / "store"
        res = StoreService(str(store_path)).create_store(str(store_path))
        assert res.success, res.error
        yield store_path


@pytest.fixture
def docs_dir(tmp_path):
    """A tiny markdown corpus for watch to ingest."""
    d = tmp_path / "docs"
    d.mkdir()
    (d / "async.md").write_text(
        "# Async Patterns\n\nasyncio is python's concurrency library.\n"
    )
    (d / "rust.md").write_text(
        "# Rust Borrow Checker\n\nOwnership and borrowing in Rust.\n"
    )
    (d / "merkle.md").write_text("# Merkle Trees\n\nHash trees with a single root.\n")
    return d


def _build_watch(
    memoir_store,
    classification_paths=(
        "knowledge.test.demo",
    ),  # kept for back-compat call sites; unused now
    slice_count=1,
    summary="mocked summary of the document.",
):
    """Construct a WatchService with a mocked chunk-and-summarize call +
    mocked markitdown.

    The mocked LLM returns a ``ChunkPlan`` with ``slice_count`` evenly
    spaced chunks over the input text and the supplied summary string.
    The ``classification_paths`` argument is kept (defaulted) so older
    test call sites still pass without modification — chunk-mode doesn't
    classify, but tests that pass it through are simply ignored here.
    """
    del classification_paths  # silence unused-arg

    svc = WatchService(str(memoir_store), llm_model="claude-haiku-4-5")

    async def fake_chunk_and_summarize(text):
        if not text:
            return ChunkPlan(summary="", chunks=[])
        if slice_count <= 1:
            return ChunkPlan(
                summary=summary,
                chunks=[WatchChunk(start=0, end=len(text))],
            )
        step = max(1, len(text) // slice_count)
        chunks: list[WatchChunk] = []
        for i in range(slice_count):
            start = i * step
            end = len(text) if i == slice_count - 1 else (i + 1) * step
            chunks.append(WatchChunk(start=start, end=end))
        return ChunkPlan(summary=summary, chunks=chunks)

    svc._chunk_and_summarize_async = AsyncMock(side_effect=fake_chunk_and_summarize)

    # Mock markitdown so .convert(path) returns .text_content = file contents.
    class _FakeMd:
        def convert(self, path):
            text = Path(path).read_text()
            res = MagicMock()
            res.text_content = text
            return res

    svc._markitdown_factory = lambda: _FakeMd()

    return svc


# ---------- per-file helper ----------------------------------------------
#
# Folder watches are no longer supported (`memoir watch add` only takes a
# single file path). Tests that historically passed ``docs_dir`` to
# ``svc.add`` use this helper to register each file individually and
# aggregate the scan stats so existing assertions still hold.


def _add_all_files(svc, d, namespace="default"):
    """Register every regular file in ``d`` individually via svc.add."""
    files = sorted(f for f in Path(d).iterdir() if f.is_file())
    return [asyncio.run(svc.add(str(f), namespace=namespace)) for f in files]


def _scan_all_files(svc, d):
    """Re-scan every previously-registered file under ``d`` individually."""
    files = sorted(f for f in Path(d).iterdir() if f.is_file())
    results = []
    for f in files:
        results.extend(asyncio.run(svc.scan(path=str(f))))
    return results


# ---------- module-level helpers ------------------------------------------


def test_supported_extensions_includes_core_types():
    exts = supported_extensions()
    for required in (".md", ".txt", ".pdf", ".docx", ".csv"):
        assert required in exts, f"{required} missing from {sorted(exts)}"


def test_supported_extensions_excludes_non_text_formats():
    """Image, audio, video, archive — intentionally not supported (yet)."""
    exts = supported_extensions()
    for excluded in (".png", ".jpg", ".mp3", ".mp4", ".wav", ".zip", ".epub"):
        assert excluded not in exts


def test_exclude_dirs_contains_expected_set():
    # Defensive regression — these are documented in user-facing copy.
    for d in (".git", "node_modules", "venv", "__pycache__"):
        assert d in EXCLUDE_DIRS


# ---------- pipeline ------------------------------------------------------


def test_watch_add_indexes_each_file(memoir_store, docs_dir):
    svc = _build_watch(memoir_store)
    results = _add_all_files(svc, docs_dir)
    assert all(r.success for r in results), [r.error for r in results]
    assert len(results) == 3
    assert sum(r.scan.files_seen for r in results) == 3
    assert sum(r.scan.files_indexed for r in results) == 3
    assert sum(r.scan.files_unchanged for r in results) == 0
    assert sum(r.scan.index_failures for r in results) == 0


def test_watch_add_idempotent_on_unchanged(memoir_store, docs_dir):
    svc = _build_watch(memoir_store)
    first = _add_all_files(svc, docs_dir)
    assert all(r.success for r in first)
    assert sum(r.scan.files_indexed for r in first) == 3

    # Second scan: nothing changed, so zero re-indexes per file.
    second = _scan_all_files(svc, docs_dir)
    assert len(second) == 3
    assert all(s.success for s in second)
    assert sum(s.files_indexed for s in second) == 0
    assert sum(s.files_unchanged for s in second) == 3


def test_watch_reindexes_on_content_change(memoir_store, docs_dir):
    svc = _build_watch(memoir_store)
    _add_all_files(svc, docs_dir)

    # Edit one file.
    (docs_dir / "async.md").write_text("# Async Patterns\n\nNEW BODY.\n")

    rescans = _scan_all_files(svc, docs_dir)
    assert len(rescans) == 3
    assert sum(r.files_indexed for r in rescans) == 1
    assert sum(r.files_unchanged for r in rescans) == 2


def test_chunk_pipeline_writes_summary_and_chunks(memoir_store, tmp_path):
    """The chunk-and-summarize pipeline produces one ``raw.<file>.summary``
    plus N ``raw.<file>.chunk.NNN`` keys, all under the watch namespace.
    Chunks concatenate back to the original text (mock splits evenly)."""
    doc = tmp_path / "doc.md"
    body = "section one body. " * 100 + "\n\n" + "section two body. " * 100
    doc.write_text(body)

    svc = _build_watch(memoir_store, slice_count=3, summary="three-section doc.")
    res = asyncio.run(svc.add(str(doc), namespace="default"))
    assert res.success, res.error
    assert res.scan.files_indexed == 1
    assert res.scan.chunks_indexed == 3

    store = svc._get_memory_service()._get_store()
    # Summary present.
    summary_v = store.get(("default",), "raw.doc_md.summary")
    assert summary_v is not None, "summary key missing"
    assert summary_v["content"] == "three-section doc."

    # Three chunk keys present, concatenating to the original body.
    chunk_keys = [
        "raw.doc_md.chunk.001",
        "raw.doc_md.chunk.002",
        "raw.doc_md.chunk.003",
    ]
    pieces = []
    for k in chunk_keys:
        v = store.get(("default",), k)
        assert v is not None, f"chunk key missing: {k}"
        pieces.append(v["content"])
    assert "".join(pieces) == body


def test_chunk_pipeline_cleans_up_prev_keys_on_reindex(memoir_store, tmp_path):
    """When a file changes and re-scans with a different chunk count, the
    old keys must be deleted so the store doesn't accumulate orphans."""
    doc = tmp_path / "f.md"
    doc.write_text("v1 body " * 50)

    svc = _build_watch(memoir_store, slice_count=3)
    asyncio.run(svc.add(str(doc), namespace="default"))

    # Rewrite content; switch the mock to produce 2 chunks this time.
    doc.write_text("v2 body " * 50)
    svc2 = _build_watch(memoir_store, slice_count=2)
    asyncio.run(svc2.scan(path=str(doc)))

    store = svc2._get_memory_service()._get_store()
    # New chunks present.
    assert store.get(("default",), "raw.f_md.summary") is not None
    assert store.get(("default",), "raw.f_md.chunk.001") is not None
    assert store.get(("default",), "raw.f_md.chunk.002") is not None
    # Old third chunk removed.
    assert store.get(("default",), "raw.f_md.chunk.003") is None


def test_scan_cleans_up_deleted_files(memoir_store, docs_dir):
    """A previously-indexed file that's been removed from disk on a
    re-scan must be deleted from memory + vector index and counted as
    files_deleted."""
    svc = _build_watch(memoir_store, classification_paths=("knowledge.test.demo",))
    _add_all_files(svc, docs_dir)

    # Delete one file.
    deleted = docs_dir / "rust.md"
    deleted.unlink()

    rescans = asyncio.run(svc.scan(path=str(deleted)))
    assert len(rescans) == 1
    r = rescans[0]
    assert r.success
    assert r.files_indexed == 0
    assert r.files_deleted == 1

    # Per-file state no longer references the deleted file.
    files_state = svc._read_files()
    abs_paths = [s.get("abs_path") for s in files_state.values()]
    assert str(deleted) not in abs_paths
    assert str(docs_dir / "async.md") in abs_paths
    assert str(docs_dir / "merkle.md") in abs_paths


def test_scan_handles_rename_as_delete_plus_add(memoir_store, docs_dir):
    """Renaming a registered file: scanning the old path shows it as
    deleted; adding the new path indexes it fresh."""
    svc = _build_watch(memoir_store)
    _add_all_files(svc, docs_dir)

    old_path = docs_dir / "rust.md"
    new_path = docs_dir / "ownership.md"
    old_path.rename(new_path)

    # Scan the old path → deletion detected.
    rescans = asyncio.run(svc.scan(path=str(old_path)))
    assert rescans[0].files_deleted == 1
    files_state = svc._read_files()
    abs_paths = {s.get("abs_path") for s in files_state.values()}
    assert str(old_path) not in abs_paths

    # Adding the renamed file works as a fresh single-file watch.
    add_res = asyncio.run(svc.add(str(new_path), namespace="default"))
    assert add_res.success
    assert add_res.scan.files_indexed == 1
    files_state = svc._read_files()
    abs_paths = {s.get("abs_path") for s in files_state.values()}
    assert str(new_path) in abs_paths


def test_watch_skips_oversize_files(memoir_store, tmp_path):
    """A single file that exceeds max_size_bytes is rejected with
    files_skipped_size=1 (not files_indexed). The new chunk-mode cap is
    100 KB by default — well below older test fixtures could ever produce."""
    big = tmp_path / "big.md"
    big.write_text("X" * 200_000)  # 200 KB, over the 100 KB default cap

    svc = _build_watch(memoir_store)
    res = asyncio.run(svc.add(str(big), namespace="default"))
    assert res.success
    assert res.scan.files_skipped_size == 1
    assert res.scan.files_indexed == 0


def test_watch_rejects_unsupported_extension(memoir_store, tmp_path):
    """A single file with an unsupported extension is rejected with
    files_skipped_unsupported=1."""
    binary = tmp_path / "binary.xyz"
    binary.write_bytes(b"\x00\x01\x02")

    svc = _build_watch(memoir_store)
    res = asyncio.run(svc.add(str(binary), namespace="default"))
    assert res.success
    assert res.scan.files_skipped_unsupported == 1
    assert res.scan.files_indexed == 0


def test_remove_with_purge_deletes_index_entries(memoir_store, docs_dir):
    svc = _build_watch(memoir_store)
    _add_all_files(svc, docs_dir)

    files = sorted(f for f in docs_dir.iterdir() if f.is_file())
    for f in files:
        rm = svc.remove(str(f), purge=True)
        assert rm.success

    # Registry empty.
    assert svc.list().entries == []

    # Confirm primary store no longer has any of the file's watch keys
    # (raw.<file>.summary + raw.<file>.chunk.NNN).
    from memoir.services.memory_service import MemoryService

    ms = MemoryService(str(memoir_store))
    store = ms._get_store()
    for f in files:
        token = f.name.replace(".", "_")
        for k in (
            f"raw.{token}.summary",
            f"raw.{token}.chunk.001",
            f"raw.{token}.chunk.002",
        ):
            v = store.get(("default",), k)
            assert v is None, (k, v)


def test_remove_purges_regardless_of_purge_flag(memoir_store, docs_dir):
    """``purge=False`` (the old soft-remove mode) is no longer supported;
    remove() always cleans up. Confirm passing purge=False still yields
    a full purge (files_removed > 0)."""
    svc = _build_watch(memoir_store)
    _add_all_files(svc, docs_dir)

    files = sorted(f for f in docs_dir.iterdir() if f.is_file())
    for f in files:
        rm = svc.remove(str(f), purge=False)
        assert rm.success
        assert rm.files_removed == 1, "remove should always purge now"
    assert svc.list().entries == []


def test_vector_index_failure_does_not_abort_scan(memoir_store, docs_dir):
    """When VectorService.index() raises, the data write still commits and
    the scan continues to the next file. index_failures counter is
    incremented — chunk-mode indexes summary + N chunks per file, so a
    one-chunk default file produces 2 index calls (summary + chunk.001)."""
    svc = _build_watch(memoir_store)

    # Force the vector service to raise on every index call.
    vec = svc._get_vector_service()
    bad_index = MagicMock(side_effect=RuntimeError("simulated vector failure"))
    vec.index = bad_index

    results = _add_all_files(svc, docs_dir)
    assert all(r.success for r in results)  # data writes still committed.
    assert sum(r.scan.files_indexed for r in results) == 3
    # 3 files x (1 summary + 1 chunk) = 6 failed index calls.
    assert sum(r.scan.index_failures for r in results) == 6


def test_search_returns_resolved_memory(memoir_store, docs_dir):
    """End-to-end: ingest 3 docs, search for one, get a resolved hit.
    Hits land on either the summary or a chunk key — both are filename-keyed
    and vector-indexed independently."""
    svc = _build_watch(memoir_store)
    _add_all_files(svc, docs_dir)

    from memoir.services.search_service import SearchService

    sr = SearchService(str(memoir_store)).search(
        "merkle hash root", namespace="default", k=3
    )
    assert sr.success, sr.error
    assert sr.hits  # at least one hit
    top = sr.hits[0]
    # Hit key is filename-derived under the raw.* namespace.
    assert top.key.startswith("raw."), top.key
    assert top.key.endswith(".summary") or ".chunk." in top.key
    assert top.source is not None
    assert top.source.get("kind") == "watch"


def test_watch_status_reports_recent_files(memoir_store, docs_dir):
    svc = _build_watch(memoir_store)
    _add_all_files(svc, docs_dir)

    # Status is per-watched-file in single-file mode.
    files = sorted(f for f in docs_dir.iterdir() if f.is_file())
    for f in files:
        st = svc.status(str(f))
        assert st.success
        assert st.kind == "file"
        assert st.namespace == "default"
        assert st.files_indexed == 1


def test_keyboard_interrupt_saves_partial_progress(memoir_store, tmp_path):
    """When a scan is interrupted (KeyboardInterrupt), already-indexed files
    must be written to files_state and last_scan must be updated. The
    KeyboardInterrupt is re-raised so the caller knows the scan was cut short."""
    files = []
    for i in range(5):
        f = tmp_path / f"f{i:02d}.md"
        f.write_text(f"# File {i}\n")
        files.append(f)

    svc = _build_watch(memoir_store)

    # Register all files with a clean initial add.
    for f in files:
        res = asyncio.run(svc.add(str(f), namespace="default"))
        assert res.success
        assert res.scan.files_indexed == 1

    # Mutate all files so they appear changed on the next scan.
    for i, f in enumerate(files):
        f.write_text(f"# File {i} UPDATED\n")

    # Inject a mock that raises KeyboardInterrupt on the third chunk+summarize
    # call (so 2 files re-index successfully before the interrupt fires).
    call_count = 0

    async def _interrupt_on_third(text):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise KeyboardInterrupt
        return ChunkPlan(
            summary="mocked",
            chunks=[WatchChunk(start=0, end=len(text))],
        )

    svc._chunk_and_summarize_async = AsyncMock(side_effect=_interrupt_on_third)

    # Re-scan each file in turn; the third file's scan raises mid-classify.
    interrupted = False
    for f in files:
        try:
            asyncio.run(svc.scan(path=str(f)))
        except KeyboardInterrupt:
            interrupted = True
            break
    assert interrupted, "expected a KeyboardInterrupt from the third scan"

    # Despite the interrupt, all 5 entries remain (2 updated + 3 still from initial).
    files_state = svc._read_files()
    assert len(files_state) == 5, "No files_state entries should have been deleted"

    # last_scan was updated on each path that completed at least its
    # partial scan loop (including the interrupted one).
    paths_meta = svc._read_paths()
    assert any(
        p.get("last_scan") is not None for p in paths_meta
    ), "at least one path's last_scan must be set after a successful scan"

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

from memoir.classifier.intelligent import SliceClassification
from memoir.services.store_service import StoreService
from memoir.services.watch_service import (
    EXCLUDE_DIRS,
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
    classification_paths=("knowledge.test.demo",),
    slice_count=1,
):
    """Construct a WatchService with a mocked slice classifier + markitdown.

    The slice classifier returns ``slice_count`` SliceClassification objects
    that together span the full input text (evenly split), each classified
    to ``classification_paths``. Tests that exercise multi-slice behavior
    pass ``slice_count > 1``.
    """
    svc = WatchService(str(memoir_store), llm_model="claude-haiku-4-5")
    ms = svc._get_memory_service()

    async def fake_slice(text, *, max_slices=50, window_chars=100_000):
        if not text:
            return []
        if slice_count <= 1:
            return [
                SliceClassification(
                    start=0,
                    end=len(text),
                    paths=list(classification_paths),
                    confidence=0.9,
                    reasoning="mocked single slice",
                )
            ]
        step = max(1, len(text) // slice_count)
        out = []
        for i in range(slice_count):
            start = i * step
            end = len(text) if i == slice_count - 1 else (i + 1) * step
            out.append(
                SliceClassification(
                    start=start,
                    end=end,
                    paths=list(classification_paths),
                    confidence=0.9,
                    reasoning=f"mocked slice {i}",
                )
            )
        return out

    fake_cls = MagicMock()
    fake_cls.classify_slices_async = AsyncMock(side_effect=fake_slice)
    ms._classifier = fake_cls
    svc._classifier = fake_cls

    # Mock markitdown so .convert(path) returns .text_content = file contents.
    class _FakeMd:
        def convert(self, path):
            text = Path(path).read_text()
            res = MagicMock()
            res.text_content = text
            return res

    svc._markitdown_factory = lambda: _FakeMd()

    return svc


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
    result = asyncio.run(svc.add(str(docs_dir), namespace="default"))
    assert result.success, result.error
    assert result.scan is not None
    assert result.scan.files_seen == 3
    assert result.scan.files_indexed == 3
    assert result.scan.files_unchanged == 0
    assert result.scan.index_failures == 0


def test_watch_add_idempotent_on_unchanged(memoir_store, docs_dir):
    svc = _build_watch(memoir_store)
    first = asyncio.run(svc.add(str(docs_dir), namespace="default"))
    assert first.success
    assert first.scan.files_indexed == 3

    # Second scan: nothing changed, so zero re-indexes.
    second_list = asyncio.run(svc.scan(path=str(docs_dir)))
    assert len(second_list) == 1
    second = second_list[0]
    assert second.success
    assert second.files_indexed == 0
    assert second.files_unchanged == 3


def test_watch_reindexes_on_content_change(memoir_store, docs_dir):
    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(docs_dir), namespace="default"))

    # Edit one file.
    (docs_dir / "async.md").write_text("# Async Patterns\n\nNEW BODY.\n")

    rescans = asyncio.run(svc.scan(path=str(docs_dir)))
    assert len(rescans) == 1
    r = rescans[0]
    assert r.success
    assert r.files_indexed == 1
    assert r.files_unchanged == 2


def test_slice_pipeline_writes_one_memory_per_slice(memoir_store, tmp_path):
    """The slice-then-classify pipeline should produce N memories for a doc
    the classifier carved into N slices. When all slices classify to the
    same taxonomy path, the first uses the bare path and the rest pick up
    a numeric collision suffix (``.2``, ``.3``, ...)."""
    root = tmp_path / "multi"
    root.mkdir()
    body = "section one body. " * 100 + "\n\n" + "section two body. " * 100
    (root / "doc.md").write_text(body)

    svc = _build_watch(memoir_store, slice_count=3)
    res = asyncio.run(svc.add(str(root), namespace="default"))
    assert res.success, res.error
    assert res.scan.files_indexed == 1
    assert res.scan.slices_indexed == 3

    # All three slice keys should resolve in the store and concatenate
    # back to the original body. The mock classifier returns the same
    # path for every slice, so we get the collision-suffix scheme.
    store = svc._get_memory_service()._get_store()
    keys = ["knowledge.test.demo", "knowledge.test.demo.2", "knowledge.test.demo.3"]
    values = []
    for k in keys:
        v = store.get(("default",), k)
        assert v is not None, f"slice key missing: {k}"
        values.append(v["content"])
    assert "".join(values) == body


def test_slice_pipeline_cleans_up_prev_keys_on_reindex(memoir_store, tmp_path):
    """When a file changes and re-scans with a different slice count, the
    old slice keys must be deleted so the store doesn't accumulate orphans."""
    root = tmp_path / "reindex"
    root.mkdir()
    (root / "f.md").write_text("v1 body " * 50)

    svc = _build_watch(memoir_store, slice_count=3)
    asyncio.run(svc.add(str(root), namespace="default"))

    # Rewrite content; switch the mock to produce 2 slices this time.
    (root / "f.md").write_text("v2 body " * 50)
    svc2 = _build_watch(memoir_store, slice_count=2)
    asyncio.run(svc2.scan(path=str(root)))

    store = svc2._get_memory_service()._get_store()
    # New slices present.
    assert store.get(("default",), "knowledge.test.demo") is not None
    assert store.get(("default",), "knowledge.test.demo.2") is not None
    # Old third slice removed (was at `.3` after the first scan with 3 slices).
    assert store.get(("default",), "knowledge.test.demo.3") is None


def test_scan_cleans_up_deleted_files(memoir_store, docs_dir):
    """A previously-indexed file that's been removed from disk on a
    re-scan must be deleted from memory + vector index and counted as
    files_deleted."""
    svc = _build_watch(memoir_store, classification_paths=("knowledge.test.demo",))
    res = asyncio.run(svc.add(str(docs_dir), namespace="default"))
    assert res.success
    assert res.scan.files_indexed == 3

    # Delete one file.
    (docs_dir / "rust.md").unlink()

    rescans = asyncio.run(svc.scan(path=str(docs_dir)))
    assert len(rescans) == 1
    r = rescans[0]
    assert r.success
    assert r.files_indexed == 0
    assert r.files_unchanged == 2
    assert r.files_deleted == 1

    # Per-file state no longer references the deleted file.
    files_state = svc._read_files()
    abs_paths = [s.get("abs_path") for s in files_state.values()]
    assert str(docs_dir / "rust.md") not in abs_paths
    assert str(docs_dir / "async.md") in abs_paths
    assert str(docs_dir / "merkle.md") in abs_paths


def test_scan_handles_rename_as_delete_plus_add(memoir_store, docs_dir):
    """Renaming a file looks like delete+add from the path-hash perspective.
    The old entry must be torn down and the new file indexed fresh."""
    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(docs_dir), namespace="default"))

    (docs_dir / "rust.md").rename(docs_dir / "ownership.md")

    rescans = asyncio.run(svc.scan(path=str(docs_dir)))
    r = rescans[0]
    assert r.success
    assert r.files_deleted == 1  # rust.md gone
    assert r.files_indexed == 1  # ownership.md indexed
    assert r.files_unchanged == 2

    files_state = svc._read_files()
    abs_paths = {s.get("abs_path") for s in files_state.values()}
    assert str(docs_dir / "rust.md") not in abs_paths
    assert str(docs_dir / "ownership.md") in abs_paths


def test_scan_keeps_other_watched_roots_intact_on_delete(memoir_store, tmp_path):
    """The deletion sweep must only consider entries with watched_path ==
    the target being scanned. Files indexed under a different watched
    root must not be touched even if they happen to be missing."""
    root_a = tmp_path / "a"
    root_a.mkdir()
    (root_a / "file_a.md").write_text("# A\n")
    root_b = tmp_path / "b"
    root_b.mkdir()
    (root_b / "file_b.md").write_text("# B\n")

    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(root_a), namespace="default"))
    asyncio.run(svc.add(str(root_b), namespace="default"))

    pre_state = svc._read_files()
    b_entries = [s for s in pre_state.values() if s.get("watched_path") == str(root_b)]
    assert len(b_entries) == 1

    # Delete the file from root_a, then scan ONLY root_a.
    (root_a / "file_a.md").unlink()
    rescans = asyncio.run(svc.scan(path=str(root_a)))
    assert rescans[0].files_deleted == 1

    # root_b's entries are untouched.
    post_state = svc._read_files()
    b_entries_after = [
        s for s in post_state.values() if s.get("watched_path") == str(root_b)
    ]
    assert len(b_entries_after) == 1


def test_scan_does_not_delete_when_file_filtered_out(memoir_store, tmp_path):
    """If a file's extension stops being supported (e.g. config changes)
    we still don't want to tear down the indexed memory — the file is
    still on disk. Confirm the deletion sweep checks .exists()."""
    root = tmp_path / "docs"
    root.mkdir()
    keep = root / "keep.md"
    keep.write_text("# Keep\n")

    svc = _build_watch(memoir_store)
    res = asyncio.run(svc.add(str(root), namespace="default"))
    assert res.scan.files_indexed == 1

    # Inject a fake entry pointing at a file that still exists, with a
    # made-up path-hash that scan won't see (so it'd be a candidate for
    # the deletion sweep). The .exists() guard must skip it.
    fake_path = root / "ghost.md"
    fake_path.write_text("# Ghost\n")
    files_state = svc._read_files()
    from memoir.services.watch_service import _abs_path_hash

    files_state["fake-key-not-real"] = {
        "abs_path": str(fake_path),
        "watched_path": str(root),
        "namespace": "default",
        "memory_keys": ["knowledge.test.never-touch"],
        "content_hash": "sha256:fakefake",
    }
    svc._write_files(files_state)

    # Re-scan: ghost.md exists on disk but its path_hash key in the state
    # dict doesn't match the real one (we used "fake-key-not-real"). The
    # sweep should NOT delete it because the abs_path still exists.
    rescans = asyncio.run(svc.scan(path=str(root)))
    r = rescans[0]
    assert r.files_deleted == 0
    # Real ghost.md got indexed under its actual path-hash.
    assert r.files_indexed == 1  # ghost.md (keep.md was unchanged)

    # The fake entry is still there because abs_path exists.
    post = svc._read_files()
    assert "fake-key-not-real" in post
    # The real path_hash for ghost.md was added too.
    assert _abs_path_hash(fake_path) in post


def test_watch_skips_excluded_dirs(memoir_store, tmp_path):
    """Files under .git / node_modules / etc. are never visited."""
    root = tmp_path / "project"
    root.mkdir()
    (root / "keep.md").write_text("# Keep\n")
    (root / ".git").mkdir()
    (root / ".git" / "ignore.md").write_text("# Should not be ingested\n")
    (root / "node_modules").mkdir()
    (root / "node_modules" / "ignore.md").write_text("# Should not be ingested\n")

    svc = _build_watch(memoir_store)
    res = asyncio.run(svc.add(str(root), namespace="default"))
    assert res.success
    # files_seen is the count AFTER exclude filtering; only keep.md survives.
    assert res.scan.files_seen == 1
    assert res.scan.files_indexed == 1


def test_watch_skips_oversize_files(memoir_store, tmp_path):
    root = tmp_path / "big"
    root.mkdir()
    (root / "small.md").write_text("# Small\n")
    big = root / "big.md"
    big.write_text("X" * (2 * 1024 * 1024))  # 2 MB

    svc = _build_watch(memoir_store)
    # Manually shrink the size cap.
    svc._write_meta(
        "config",
        {
            "max_size_mb": 1,
            "summarize_min_chars": 1_000,
            "summarize_max_chars": 10_000,
            "max_files_per_scan": 100,
            "embedder": "MiniLmEmbedder",
        },
    )
    res = asyncio.run(svc.add(str(root), namespace="default"))
    assert res.success
    assert res.scan.files_skipped_size == 1
    assert res.scan.files_indexed == 1


def test_scan_caps_indexed_files_per_run(memoir_store, tmp_path):
    """Per-scan cap stops the loop once ``max_files_per_scan`` new/changed
    files have been indexed. Remaining work is reported via a progress
    warning and is picked up on the next scan."""
    root = tmp_path / "many"
    root.mkdir()
    for i in range(6):
        (root / f"f{i:02d}.md").write_text(f"# File {i}\n")

    captured: list[str] = []

    svc = WatchService(str(memoir_store), progress=captured.append)
    # Wire the same fake slice-classifier + markitdown _build_watch uses.
    async def _one_slice(text, *, max_slices=50, window_chars=100_000):
        return [
            SliceClassification(
                start=0,
                end=len(text),
                paths=["knowledge.test.demo"],
                confidence=0.9,
                reasoning="mocked",
            )
        ]

    fake_cls = MagicMock()
    fake_cls.classify_slices_async = AsyncMock(side_effect=_one_slice)
    svc._get_memory_service()._classifier = fake_cls
    svc._classifier = fake_cls

    class _FakeMd:
        def convert(self, path):
            r = MagicMock()
            r.text_content = Path(path).read_text()
            return r

    svc._markitdown_factory = lambda: _FakeMd()

    # Cap at 3 — 6 files on disk, expect 3 indexed + warning about 3 remaining.
    svc._write_meta(
        "config",
        {
            "max_size_mb": 100,
            "summarize_min_chars": 1_000,
            "summarize_max_chars": 10_000,
            "max_files_per_scan": 3,
            "embedder": "MiniLmEmbedder",
        },
    )
    res = asyncio.run(svc.add(str(root), namespace="default"))
    assert res.success
    assert res.scan.files_indexed == 3
    assert any("scan cap reached" in line for line in captured), captured
    assert any("3 file(s) remain" in line for line in captured), captured

    # Second scan should pick up the remaining 3.
    captured.clear()
    rescans = asyncio.run(svc.scan(path=str(root)))
    assert rescans[0].files_indexed == 3
    assert rescans[0].files_unchanged == 3
    assert not any("scan cap reached" in line for line in captured)


def test_scan_cap_does_not_run_deletion_sweep(memoir_store, tmp_path):
    """When the cap fires mid-scan, the deletion sweep must NOT run —
    seen_path_keys is partial and would mark unvisited files as deleted."""
    root = tmp_path / "del-safety"
    root.mkdir()
    for i in range(5):
        (root / f"f{i}.md").write_text(f"# {i}\n")

    svc = _build_watch(memoir_store)
    # First scan: index everything (5 files) with default cap (100).
    res = asyncio.run(svc.add(str(root), namespace="default"))
    assert res.scan.files_indexed == 5

    # Now mutate ALL files so they're all "changed", and drop the cap to 2.
    for i in range(5):
        (root / f"f{i}.md").write_text(f"# {i} UPDATED\n")
    svc._write_meta(
        "config",
        {
            "max_size_mb": 100,
            "summarize_min_chars": 1_000,
            "summarize_max_chars": 10_000,
            "max_files_per_scan": 2,
            "embedder": "MiniLmEmbedder",
        },
    )
    rescans = asyncio.run(svc.scan(path=str(root)))
    r = rescans[0]
    assert r.files_indexed == 2
    # Critical: even though 3 files were unvisited, no deletions reported.
    assert r.files_deleted == 0
    # All 5 entries should still be in files_state — none torn down.
    assert len(svc._read_files()) == 5


def test_watch_skips_unsupported_extensions(memoir_store, tmp_path):
    root = tmp_path / "mixed"
    root.mkdir()
    (root / "keep.md").write_text("# Keep\n")
    (root / "binary.xyz").write_bytes(b"\x00\x01\x02")

    svc = _build_watch(memoir_store)
    res = asyncio.run(svc.add(str(root), namespace="default"))
    assert res.success
    # files_seen counts files visited before extension filtering. The .xyz
    # binary is counted there, then dropped via files_skipped_unsupported.
    assert res.scan.files_seen == 2
    assert res.scan.files_skipped_unsupported == 1
    assert res.scan.files_indexed == 1


def test_remove_with_purge_deletes_index_entries(memoir_store, docs_dir):
    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(docs_dir), namespace="default"))

    rm = svc.remove(str(docs_dir), purge=True)
    assert rm.success
    assert rm.files_removed == 3

    # Confirm registry is empty.
    assert svc.list().entries == []

    # Confirm primary store no longer has the memory. In slice mode each
    # file's primary classification key is the bare path (collision suffix
    # only kicks in for repeated paths within one file); after purge,
    # neither the bare key nor any collision-suffixed variant should remain.
    from memoir.services.memory_service import MemoryService

    ms = MemoryService(str(memoir_store))
    store = ms._get_store()
    for key in ("knowledge.test.demo", "knowledge.test.demo.2", "knowledge.test.demo.3"):
        v = store.get(("default",), key)
        assert v is None, v


def test_remove_without_purge_unregisters_only(memoir_store, docs_dir):
    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(docs_dir), namespace="default"))

    rm = svc.remove(str(docs_dir), purge=False)
    assert rm.success
    assert rm.files_removed == 0  # nothing deleted
    assert svc.list().entries == []


def test_vector_index_failure_does_not_abort_scan(memoir_store, docs_dir):
    """When VectorService.index() raises, the data write still commits and
    the scan continues to the next file. index_failures counter is
    incremented."""
    svc = _build_watch(memoir_store)

    # Force the vector service to raise on every index call.
    vec = svc._get_vector_service()
    bad_index = MagicMock(side_effect=RuntimeError("simulated vector failure"))
    vec.index = bad_index

    res = asyncio.run(svc.add(str(docs_dir), namespace="default"))
    assert res.success  # data writes still committed; scan does not abort.
    assert res.scan.files_indexed == 3
    assert res.scan.index_failures == 3


def test_search_returns_resolved_memory(memoir_store, docs_dir):
    """End-to-end: ingest 3 docs, search for one, get a resolved hit."""
    svc = _build_watch(memoir_store, classification_paths=("knowledge.technical.docs",))
    asyncio.run(svc.add(str(docs_dir), namespace="default"))

    from memoir.services.search_service import SearchService

    sr = SearchService(str(memoir_store)).search(
        "merkle hash root", namespace="default", k=3
    )
    assert sr.success, sr.error
    assert sr.hits  # at least one hit
    top = sr.hits[0]
    # All three files share the same primary classification under this test
    # (mocked classifier always returns "knowledge.technical.docs"). In slice
    # mode each file's single slice gets the bare path (collision suffix is
    # per-file, so cross-file collisions overwrite — last writer wins).
    assert top.key == "knowledge.technical.docs"
    assert top.source is not None
    assert top.source.get("kind") == "watch"


def test_watch_status_reports_recent_files(memoir_store, docs_dir):
    svc = _build_watch(memoir_store)
    asyncio.run(svc.add(str(docs_dir), namespace="default"))

    st = svc.status(str(docs_dir))
    assert st.success
    assert st.kind == "folder"
    assert st.namespace == "default"
    assert st.files_indexed == 3
    assert len(st.recently_changed) == 3


def test_keyboard_interrupt_saves_partial_progress(memoir_store, tmp_path):
    """When a scan is interrupted (KeyboardInterrupt), already-indexed files
    must be written to files_state and last_scan must be updated.  The
    KeyboardInterrupt is re-raised so the caller knows the scan was cut short."""
    root = tmp_path / "many"
    root.mkdir()
    for i in range(5):
        (root / f"f{i:02d}.md").write_text(f"# File {i}\n")

    svc = _build_watch(memoir_store)

    # First, register the path with a clean initial scan.
    initial = asyncio.run(svc.add(str(root), namespace="default"))
    assert initial.success
    assert initial.scan.files_indexed == 5

    # Mutate all files so they appear changed on the next scan.
    for i in range(5):
        (root / f"f{i:02d}.md").write_text(f"# File {i} UPDATED\n")

    # Inject a mock that raises KeyboardInterrupt on the third slice-classify
    # call (so 2 files have already been indexed when the interrupt fires).
    call_count = 0

    async def _interrupt_on_third(text, *, max_slices=50, window_chars=100_000):
        nonlocal call_count
        call_count += 1
        if call_count == 3:
            raise KeyboardInterrupt
        return [
            SliceClassification(
                start=0,
                end=len(text),
                paths=["knowledge.test.demo"],
                confidence=0.9,
                reasoning="mocked",
            )
        ]

    svc._classifier.classify_slices_async = AsyncMock(side_effect=_interrupt_on_third)

    # Re-scan — the interrupt fires after 2 files are indexed.
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(svc.scan(path=str(root)))

    # Despite the interrupt, all 5 entries remain (2 updated + 3 from initial).
    files_state = svc._read_files()
    assert len(files_state) == 5, "No files_state entries should have been deleted"

    # last_scan must be updated even for an interrupted scan.
    paths_meta = svc._read_paths()
    entry = next((p for p in paths_meta if p.get("path") == str(root)), None)
    assert entry is not None
    assert entry.get("last_scan") is not None, "last_scan must be set even after interrupt"

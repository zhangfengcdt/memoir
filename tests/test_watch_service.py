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

from memoir.classifier.intelligent import (
    ClassificationAction,
    ClassificationConfidence,
    ClassificationResult,
)
from memoir.services.store_service import StoreService
from memoir.services.watch_service import (
    EXCLUDE_DIRS,
    WatchService,
    _deterministic_summary,
    _extract_titles,
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


def _build_watch(memoir_store, classification_paths=("knowledge.test.demo",)):
    """Construct a WatchService with a mocked classifier + mocked markitdown.

    The classifier returns a deterministic ClassificationResult so we can
    assert downstream behavior without an API key.
    """
    svc = WatchService(str(memoir_store), llm_model="claude-haiku-4-5")

    # Mock the classifier (warm up MemoryService first so its store handle
    # is shared).
    ms = svc._get_memory_service()

    fake_cls = MagicMock()
    fake_cls.classify_input = AsyncMock(
        return_value=ClassificationResult(
            is_memory=True,
            confidence=0.9,
            confidence_level=ClassificationConfidence.HIGH,
            reasoning="mocked",
            suggested_action=ClassificationAction.CLASSIFY,
            path=classification_paths[0],
            paths=list(classification_paths),
        )
    )
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
    for required in (".md", ".txt", ".pdf", ".docx", ".html"):
        assert required in exts, f"{required} missing from {sorted(exts)}"


def test_extract_titles_picks_markdown_headings():
    text = "# Top\n\nbody text\n\n## Sub\n\nmore\n\n### Deep\n"
    assert _extract_titles(text) == ["Top", "Sub", "Deep"]


def test_extract_titles_skips_prose():
    text = "This is a normal sentence with a capital start.\n"
    assert _extract_titles(text) == []


def test_deterministic_summary_layout():
    body = "head text " * 100 + "\n\n# Section A\n\n" + "tail text " * 100
    summary = _deterministic_summary(body, threshold=200, source_name="example.md")
    assert summary.startswith("# example.md")
    assert "Section A" in summary
    assert "## Beginning" in summary
    # tail is only included when text is long enough.
    assert "## End" in summary
    assert len(summary) <= 200


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
        "watch.config",
        {"max_size_mb": 1, "summarize_min_chars": 10_000, "embedder": "MiniLmEmbedder"},
    )
    res = asyncio.run(svc.add(str(root), namespace="default"))
    assert res.success
    assert res.scan.files_skipped_size == 1
    assert res.scan.files_indexed == 1


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

    # Confirm primary store no longer has the memory.
    from memoir.services.memory_service import MemoryService

    ms = MemoryService(str(memoir_store))
    store = ms._get_store()
    v = store.get(("default",), "knowledge.test.demo")
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
    # All three files share the same primary key under this test (mocked
    # classifier always returns "knowledge.technical.docs"), so the index
    # only has one document and the content is the last file written.
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

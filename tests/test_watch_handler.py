"""HTTP-handler-level tests for /api/watch/{list,stats,search}.

Uses a stub request handler that captures `wfile` so we don't need a real
HTTP server. Mocks the LLM classifier and uses HashEmbedder via
``MEMOIR_TEST_USE_HASH_EMBEDDER=1`` so no API key is required.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import urlparse

import prollytree
import pytest

if not getattr(prollytree, "proximity_text_available", False):
    pytest.skip(
        "prollytree built without proximity_text; skip watch UI handler tests",
        allow_module_level=True,
    )

from memoir.classifier.intelligent import SliceClassification
from memoir.services.store_service import StoreService
from memoir.services.watch_service import WatchService
from memoir.ui.handlers.watch_handler import WatchHandler

os.environ["MEMOIR_TEST_USE_HASH_EMBEDDER"] = "1"


class _StubRequest:
    """Minimal stand-in for ``http.server.BaseHTTPRequestHandler`` — captures
    the JSON the handler writes so the test can assert on it."""

    def __init__(self) -> None:
        self.status_code: int | None = None
        self.wfile = io.BytesIO()
        self.headers: dict[str, str] = {}

    def send_response(self, code: int) -> None:
        self.status_code = code

    def send_header(self, *_a) -> None:
        pass

    def end_headers(self) -> None:
        pass


def _seed_store(docs: dict[str, str]) -> Path:
    """Create a temp memoir store with `docs` watched and indexed via a
    mocked classifier + fake markitdown. Returns the absolute store path."""
    tmp = Path(tempfile.mkdtemp())
    store_path = tmp / "store"
    res = StoreService(str(store_path)).create_store(str(store_path))
    assert res.success, res.error

    docs_dir = tmp / "docs"
    docs_dir.mkdir()
    for name, body in docs.items():
        (docs_dir / name).write_text(body)

    svc = WatchService(str(store_path))
    ms = svc._get_memory_service()

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
    ms._classifier = fake_cls
    svc._classifier = fake_cls

    class _FakeMd:
        def convert(self, path):
            r = MagicMock()
            r.text_content = Path(path).read_text()
            return r

    svc._markitdown_factory = lambda: _FakeMd()
    # Folder watches are not supported; add each file individually.
    for f in sorted(p for p in docs_dir.iterdir() if p.is_file()):
        asyncio.run(svc.add(str(f), namespace="default"))
    return store_path


def _call(handler_method, query: str) -> tuple[int | None, dict]:
    req = _StubRequest()
    h = WatchHandler(req)
    parsed = urlparse(f"/api/watch/x?{query}")
    handler_method(h, parsed)
    body = req.wfile.getvalue().decode()
    return req.status_code, (json.loads(body) if body else {})


def test_watch_list_returns_registered_paths():
    store = _seed_store({"a.md": "# A\n", "b.md": "# B\n"})
    status, data = _call(WatchHandler.handle_list_api, f"path={store}")
    assert status == 200
    assert data["success"] is True
    # Each file is its own watched entry (folders aren't supported).
    assert data["count"] == 2
    for entry in data["entries"]:
        assert entry["kind"] == "file"
        assert entry["indexed_count"] == 1


def test_watch_stats_returns_proximity_index_counts():
    store = _seed_store({"a.md": "# A\n", "b.md": "# B\n"})
    status, data = _call(
        WatchHandler.handle_stats_api, f"path={store}&namespace=default"
    )
    assert status == 200
    assert data["available"] is True
    assert data["opened"] is True
    # All 2 files share the same classified path under the mocked
    # classifier, so 1 doc + 1 chunk under identity chunker.
    assert data["doc_count"] == 1
    assert data["chunk_count"] == 1


def test_watch_search_returns_top_k_hits():
    store = _seed_store(
        {"a.md": "rust ownership story\n", "b.md": "merkle hash tree\n"}
    )
    status, data = _call(
        WatchHandler.handle_search_api,
        f"path={store}&query=ownership&namespace=default&k=2",
    )
    assert status == 200
    assert data["success"] is True
    assert data["query"] == "ownership"
    assert len(data["hits"]) >= 1
    hit = data["hits"][0]
    assert "key" in hit
    assert "score" in hit
    assert "content" in hit


def test_watch_search_requires_query():
    store = _seed_store({"a.md": "x"})
    status, data = _call(WatchHandler.handle_search_api, f"path={store}&query=&k=5")
    assert status == 400
    assert "query" in data["error"].lower()


def test_watch_list_rejects_missing_store_path():
    status, data = _call(WatchHandler.handle_list_api, "")
    assert status == 400
    assert "path" in data["error"].lower()


def test_watch_stats_handles_uninitialized_index():
    """Brand-new store with no `watch add` yet — stats should return a
    note rather than 500."""
    tmp = Path(tempfile.mkdtemp())
    store_path = tmp / "store"
    StoreService(str(store_path)).create_store(str(store_path))

    status, data = _call(
        WatchHandler.handle_stats_api, f"path={store_path}&namespace=default"
    )
    assert status == 200
    assert data["available"] is True
    # Either the index opens with zero docs, or it reports the not-yet-
    # initialized note. Both are valid for an empty store; the contract
    # is "no 5xx".
    assert data.get("doc_count", 0) == 0

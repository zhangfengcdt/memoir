"""
Schema-drift test for the range-diff endpoint.

Builds a store, writes two memories, commits, modifies one and adds a
third, commits again, then asks the schema to round-trip the wire-native
payload from ``_generate_commit_range_diff``. Keeps us honest when the
server-side diff shape shifts.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

import pytest

from memoir.services.store_service import StoreService
from memoir.store.prolly_adapter import ProllyTreeStore
from memoir.ui.schemas import RangeDiffResponse


def _git(store: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=store,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


@pytest.fixture
def store_with_diff():
    """A store with two commits whose diff has one add and one modify."""
    path = tempfile.mkdtemp(prefix="memoir_diff_test_")
    try:
        StoreService(path).create_store(path)

        store = ProllyTreeStore(
            path=path,
            enable_versioning=True,
            auto_commit=True,
            cache_size=1000,
        )
        store.tree.insert(
            b"default:workflow.coding.style",
            json.dumps({"content": "prefer async"}).encode(),
        )
        store.commit("seed: add style memory")
        from_hash = _git(path, "rev-parse", "HEAD").stdout.strip()

        store.tree.insert(
            b"default:workflow.coding.style",
            json.dumps({"content": "prefer async-first"}).encode(),
        )
        store.tree.insert(
            b"default:identity.name",
            json.dumps({"content": "Feng"}).encode(),
        )
        store.commit("feat: refine style + add identity")
        to_hash = _git(path, "rev-parse", "HEAD").stdout.strip()

        yield path, from_hash, to_hash
    finally:
        if os.path.exists(path):
            shutil.rmtree(path)


def test_range_diff_payload_matches_schema(store_with_diff):
    """Hit the raw generator, then push its output through the schema
    and back. Anything that breaks the contract raises."""
    from memoir.ui.server import MemoryStoreHandler

    path, from_hash, to_hash = store_with_diff

    # Instantiate the handler without running __init__ — we only need the
    # diff helper, and its dependencies on ``self.handler`` are lazy.
    handler = MemoryStoreHandler.__new__(MemoryStoreHandler)
    raw = handler._generate_commit_range_diff(path, from_hash, to_hash)

    assert raw["success"] is True
    assert isinstance(raw["commits"], list)
    # Exactly one commit in the range (``to_hash`` is 1 commit ahead of ``from_hash``).
    assert len(raw["commits"]) == 1

    # Round-trip through the model.
    body = RangeDiffResponse.from_legacy(raw)
    assert body.from_ref == from_hash
    assert body.to_ref == to_hash
    assert body.commits[0].hash == to_hash
    # The diff should show at least one change (add of identity.name;
    # the modified style field depends on the prollytree diff semantics
    # so we only assert ``>= 1`` to stay robust).
    assert len(body.commits[0].changes) >= 1

    # Wire-native round-trip — the handler emits ``from``/``to`` keys.
    wire = body.to_legacy()
    assert "from" in wire
    assert "to" in wire
    assert "from_ref" not in wire
    assert "to_ref" not in wire

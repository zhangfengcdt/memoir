"""
Tests for the commit-snapshot endpoint (``/api/commit-snapshot`` ->
``_generate_commit_snapshot``).

Exists to cover a gap ``_generate_commit_range_diff`` structurally can't:
a ``git log --reverse from..to`` walk always excludes the true root commit
(no parent to diff against), so any state reconstruction built by
accumulating range-diffs is permanently missing whatever the root commit
itself introduced. ``_generate_commit_snapshot`` reads state directly via
prollytree's ``get_keys_at_ref`` instead, so it's exact at any commit,
root included.
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
def store_with_history():
    """``ProllyTreeStore(..., auto_commit=True)`` always lays down its own
    empty "Initial commit" as the true root before any caller write lands
    (verified empirically — the first ``insert`` + ``commit`` call always
    produces the *second* commit, never the root). So the root commit
    being unreconstructable via ``from..to`` range-diffing is a structural
    invariant here, not a hypothetical: `seed_hash` below is the first
    commit that actually carries data, and `root_hash` is its empty parent.
    """
    path = tempfile.mkdtemp(prefix="memoir_snapshot_test_")
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
        root_hash = _git(path, "rev-list", "--max-parents=0", "HEAD").stdout.strip()
        seed_hash = _git(path, "rev-parse", "HEAD").stdout.strip()
        assert root_hash != seed_hash, (
            "expected ProllyTreeStore's auto-created empty commit ahead of "
            "the first real write — if this fails, the store's init "
            "behavior changed and this fixture (and the bug this file "
            "guards against) needs re-checking"
        )

        store.tree.insert(
            b"default:workflow.coding.style",
            json.dumps({"content": "prefer async-first"}).encode(),
        )
        store.tree.insert(
            b"default:identity.name",
            json.dumps({"content": "Feng"}).encode(),
        )
        store.commit("feat: refine style + add identity")
        mid_hash = _git(path, "rev-parse", "HEAD").stdout.strip()

        store.tree.delete(b"default:identity.name")
        store.commit("chore: remove identity")
        tip_hash = _git(path, "rev-parse", "HEAD").stdout.strip()

        yield path, root_hash, seed_hash, mid_hash, tip_hash
    finally:
        if os.path.exists(path):
            shutil.rmtree(path)


def _handler():
    from memoir.ui.server import MemoryStoreHandler

    # Instantiate without running __init__ — the snapshot helper only
    # touches ``self.utility_handler``, initialized lazily on first use.
    return MemoryStoreHandler.__new__(MemoryStoreHandler)


def test_snapshot_at_root_commit_is_exact_not_falsely_empty(store_with_history):
    """The true root has no parent, so no `from..to` range diff can ever
    include it. It happens to carry no data here (see fixture docstring),
    but the point is `commit-snapshot` reports that state directly and
    correctly — not via an accumulation that would silently omit it while
    still being trusted as complete."""
    path, root_hash, _seed_hash, _mid_hash, _tip_hash = store_with_history
    result = _handler()._generate_commit_snapshot(path, root_hash)

    assert result["success"] is True
    assert result["ref"] == root_hash
    assert result["memories"] == []


def test_snapshot_at_seed_commit_captures_its_own_introduced_data(store_with_history):
    """`seed_hash` is the first commit that has a parent — the one a
    `from..to` diff *can* reach — but only when the caller's range
    actually starts at its parent (the empty root). `commit-snapshot`
    gets this right unconditionally, with no range to get wrong."""
    path, _root_hash, seed_hash, _mid_hash, _tip_hash = store_with_history
    result = _handler()._generate_commit_snapshot(path, seed_hash)

    assert result["success"] is True
    paths = {m["path"]: m["content"] for m in result["memories"]}
    assert paths == {"workflow.coding.style": "prefer async"}


def test_snapshot_at_mid_commit_reflects_all_paths_so_far(store_with_history):
    path, _root_hash, _seed_hash, mid_hash, _tip_hash = store_with_history
    result = _handler()._generate_commit_snapshot(path, mid_hash)

    assert result["success"] is True
    paths = {m["path"]: m["content"] for m in result["memories"]}
    assert paths == {
        "workflow.coding.style": "prefer async-first",
        "identity.name": "Feng",
    }


def test_snapshot_excludes_paths_deleted_by_that_commit(store_with_history):
    path, _root_hash, _seed_hash, _mid_hash, tip_hash = store_with_history
    result = _handler()._generate_commit_snapshot(path, tip_hash)

    assert result["success"] is True
    paths = {m["path"] for m in result["memories"]}
    assert paths == {"workflow.coding.style"}


def test_snapshot_filters_to_default_namespace(store_with_history):
    path, _root_hash, _seed_hash, _mid_hash, _tip_hash = store_with_history
    store = ProllyTreeStore(
        path=path, enable_versioning=True, auto_commit=True, cache_size=1000
    )
    store.tree.insert(
        b"taxonomy:some.internal.path",
        json.dumps({"content": "not user-facing"}).encode(),
    )
    store.commit("internal: taxonomy write")

    result = _handler()._generate_commit_snapshot(
        path, _git(path, "rev-parse", "HEAD").stdout.strip()
    )
    assert result["success"] is True
    namespaces = {m["namespace"] for m in result["memories"]}
    assert namespaces == {"default"}

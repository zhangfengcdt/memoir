# SPDX-License-Identifier: Apache-2.0
"""Regression tests for prollytree's 1024-key enumeration cap.

``list_keys()`` and ``get_keys_at_ref()`` stop at 1024 keys in the Python
binding, and the surviving subset changes between calls, so a store past the
cap answers the same query differently every time. These tests build 1500-key
stores and assert that every read path sees the complete key set, plus the
edge cases raised in review (empty branch, bad ref, removed key, staged write).
"""

from __future__ import annotations

import json
import subprocess

import pytest

from memoir.services.branch_service import BranchService
from memoir.services.store_service import StoreService
from memoir.store.prolly_adapter import ProllyTreeStore

# Comfortably past the cap, small enough to keep the suite fast.
KEY_COUNT = 1500


def _git(path: str, *args: str) -> str:
    """Run one git command in the store and return its trimmed output."""
    return subprocess.run(
        ["git", "-C", path, *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _seed(path, count: int, prefix: str = "context.project.k") -> None:
    """Write ``count`` memories and commit them once."""
    store = ProllyTreeStore(path, auto_commit=False)
    for i in range(count):
        store.put(
            ("default",),
            f"{prefix}{i:04d}",
            {"content": f"value {i}", "confidence": 1.0, "metadata": {}},
        )
    store.commit(f"seed {count} keys")


@pytest.fixture
def big_store(tmp_path):
    """A store holding ``KEY_COUNT`` memories."""
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)
    _seed(path, KEY_COUNT)
    return path


def test_all_keys_is_complete_and_deterministic(big_store):
    """all_keys() returns every key, and two calls agree."""
    store = ProllyTreeStore(big_store)

    first = store.all_keys()
    second = store.all_keys()

    assert len(first) == KEY_COUNT
    assert first == second
    assert first == sorted(first)
    # Both ends are present; the cap used to drop an arbitrary tail.
    assert "default:context.project.k0000" in first
    assert f"default:context.project.k{KEY_COUNT - 1:04d}" in first


def test_search_returns_every_key(big_store):
    """search() reads the same uncapped set, not the old key registry."""
    store = ProllyTreeStore(big_store)

    results = store.search(("default",), limit=KEY_COUNT * 2)

    assert len(results) == KEY_COUNT


def test_read_store_and_status_report_full_count(big_store):
    """UI read_store() and CLI status report the real count, not 1024."""
    service = StoreService(big_store)

    data = service.read_store()
    status = service.get_status()

    assert data["total_memories"] == KEY_COUNT
    assert len(data["namespaces"]["default"]) == KEY_COUNT
    assert status.memory_count == KEY_COUNT


def test_export_namespace_exports_every_key(big_store, tmp_path):
    """Export is not bounded by the old search(limit=1000)."""
    store = ProllyTreeStore(big_store)
    output = tmp_path / "export.json"

    store.export_namespace("default", str(output))

    memories = json.loads(output.read_text())["memories"]
    assert len(memories) == KEY_COUNT


def test_promote_branch_copies_every_key(tmp_path):
    """Promote copies all 100 new keys and loses none.

    The capped enumeration made promote report 84-86 of 100 additions, then
    silently drop keys while returning success=True.
    """
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)
    _seed(path, 1100)

    branch = BranchService(path)
    branch.checkout("feature/z", create_if_missing=True)
    _seed(path, 100, prefix="context.project.extra")
    branch.checkout("main")

    dry = branch.promote_branch("feature/z", "main", dry_run=True)
    assert len(dry.added_keys) == 100

    applied = branch.promote_branch("feature/z", "main", dry_run=False)
    assert applied.success
    assert len(applied.added_keys) == 100

    store = ProllyTreeStore(path)
    assert len(store.all_keys()) == 1200
    for i in range(100):
        assert store.get(("default",), f"context.project.extra{i:04d}") is not None


def test_ref_snapshot_sees_every_key(tmp_path):
    """A ref-scoped read sees its branch's full key set, without a checkout."""
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)
    _seed(path, 1100)

    branch = BranchService(path)
    branch.checkout("feature/z", create_if_missing=True)
    _seed(path, 100, prefix="context.project.extra")
    branch.checkout("main")

    snapshot = ProllyTreeStore(path, ref="feature/z")

    assert len(snapshot.all_keys()) == 1200
    assert snapshot.get(("default",), "context.project.extra0099") is not None
    # Reading the snapshot leaves the checked-out branch untouched.
    assert len(ProllyTreeStore(path).all_keys()) == 1100


def test_unknown_ref_still_raises(tmp_path):
    """An unknown ref keeps its clear error instead of becoming empty."""
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)
    _seed(path, 1)

    with pytest.raises(ValueError, match="does not exist"):
        ProllyTreeStore(path, ref="no-such-branch")


# ---------------------------------------------------------------------------
# Edge cases from review (#1, #2, #3, #4).
# ---------------------------------------------------------------------------


def test_empty_branch_does_not_show_the_checked_out_branch(tmp_path):
    """Review #1: an empty branch must not fall back to the checked-out one.

    Create ``emptyb`` at the empty initial commit, write two keys on main,
    then read ``ref='emptyb'``: it must be empty, not main's data.
    """
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)

    store = ProllyTreeStore(path)
    root = _git(path, "rev-list", "--max-parents=0", "HEAD")
    _seed(path, 2, prefix="a.b.")
    _git(path, "branch", "emptyb", root)

    assert store.all_keys() != []
    assert ProllyTreeStore(path, ref="emptyb").all_keys() == []


@pytest.mark.parametrize("ref", ["HEAD~1", "main~1", "abc1234"])
def test_revision_expressions_are_rejected(tmp_path, ref):
    """Review #2: git resolves these, prollytree does not.

    Before the fix they passed validation, the replay failed, and the code
    fell back to the current branch's data.
    """
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)
    _seed(path, 2)

    with pytest.raises(ValueError, match="does not exist"):
        ProllyTreeStore(path, ref=ref)


def test_deleted_key_does_not_reappear_from_the_root_commit(tmp_path):
    """Review #3: the root-commit fill-in must not revive a deleted key."""
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)
    _seed(path, 1, prefix="context.project.gone")

    ProllyTreeStore(path).delete(("default",), "context.project.gone0000")

    assert ProllyTreeStore(path).all_keys() == []


def test_staged_writes_are_visible_to_enumeration(tmp_path):
    """Review #4: with auto_commit=False, listing must match get().

    The replayed history only contains commits, while get() and list_keys()
    also see the staging area, so enumeration layers it on top.
    """
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)

    store = ProllyTreeStore(path, auto_commit=False)
    store.put(("default",), "committed.key", {"content": "c", "confidence": 1.0})
    store.commit("first")
    store.put(("default",), "staged.key", {"content": "s", "confidence": 1.0})

    assert sorted(store.all_keys()) == ["default:committed.key", "default:staged.key"]
    assert sorted(store.all_items()) == ["default:committed.key", "default:staged.key"]

    output = tmp_path / "export.json"
    store.export_namespace("default", str(output))
    assert sorted(json.loads(output.read_text())["memories"]) == [
        "committed.key",
        "staged.key",
    ]


def test_recall_is_reproducible_on_large_store(big_store):
    """The same query returns the same memories on every call.

    With the capped enumeration each call returned a different subset, so
    agent behaviour was not reproducible.
    """
    from memoir.mcp import server as S

    first = S.recall(big_store, "value 42", limit=10)
    second = S.recall(big_store, "value 42", limit=10)

    assert first["count"] == second["count"] > 0
    assert [m["key"] for m in first["memories"]] == [
        m["key"] for m in second["memories"]
    ]

    # The last key (always outside the old cap) is reachable too.
    everything = S.recall(big_store, f"value {KEY_COUNT - 1}", limit=5)
    assert any(
        m["key"] == f"context.project.k{KEY_COUNT - 1:04d}"
        for m in everything["memories"]
    )


# ---------------------------------------------------------------------------
# Round 2 review: staged deletes, cache staleness, ref resolution.
# ---------------------------------------------------------------------------


def test_staged_delete_is_removed_from_all_keys(tmp_path):
    """Review #1: ``keys | written - removed`` parsed as
    ``keys | (written - removed)``, so a staged delete stayed in the list."""
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)

    writer = ProllyTreeStore(path)
    writer.put(("default",), "a.b.c", {"content": "1", "confidence": 1.0})
    writer.put(("default",), "a.b.d", {"content": "2", "confidence": 1.0})

    store = ProllyTreeStore(path, auto_commit=False)
    store.delete(("default",), "a.b.c")

    assert store.all_keys() == ["default:a.b.d"]
    assert sorted(store.all_items()) == ["default:a.b.d"]
    assert store.get_statistics()["total_keys"] == 1


def test_checkout_through_branch_service_invalidates_the_cache(tmp_path):
    """Review #2: ``BranchService.checkout`` switches the tree directly, so
    a cached key set from the previous branch used to survive the switch."""
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)

    branch = BranchService(path)
    branch.checkout("feature/x", create_if_missing=True)
    store = branch._get_store()
    store.put(("default",), "b", {"content": "b", "confidence": 1.0})
    assert store.all_keys() == ["default:b"]

    branch.checkout("main")

    assert store.all_keys() == []
    assert store.get(("default",), "b") is None


def test_merge_invalidates_the_cache(tmp_path):
    """Review #3: ``BranchService.merge`` commits through the tree directly."""
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)

    branch = BranchService(path)
    store = branch._get_store()
    store.put(("default",), "a", {"content": "a", "confidence": 1.0})

    branch.checkout("feat", create_if_missing=True)
    ProllyTreeStore(path).put(
        ("default",), "x.y.z", {"content": "z", "confidence": 1.0}
    )
    branch.checkout("main")

    assert store.all_keys() == ["default:a"]
    assert branch.merge("feat").success
    assert store.all_keys() == ["default:a", "default:x.y.z"]


@pytest.mark.parametrize(
    "ref", ["refs/heads/nope", "refs/tags/nope", "refs/remotes/nope/main"]
)
def test_missing_full_ref_raises_the_friendly_error(tmp_path, ref):
    """Review #5: a refs/... path was accepted on its prefix alone, so the
    failure surfaced as a raw git error from rev-list."""
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)
    _seed(path, 1)

    with pytest.raises(ValueError, match="does not exist"):
        ProllyTreeStore(path, ref=ref)


def test_branch_wins_over_a_tag_with_the_same_name(tmp_path):
    """Review #6: git resolves ``v1`` to the tag first, so ``--branch v1``
    read the tag's memories while the user asked for the branch."""
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)

    store = ProllyTreeStore(path)
    store.put(("default",), "old", {"content": "o", "confidence": 1.0})
    _git(path, "branch", "v1")
    store.put(("default",), "new", {"content": "n", "confidence": 1.0})
    _git(path, "tag", "v1")

    # The branch points at the older commit, the tag at the newer one.
    assert ProllyTreeStore(path, ref="v1").all_keys() == ["default:old"]
    # An explicit tag ref still reads the tag.
    assert sorted(ProllyTreeStore(path, ref="refs/tags/v1").all_keys()) == [
        "default:new",
        "default:old",
    ]


def test_snapshot_error_path_does_not_leave_snapshot_keys_cached(tmp_path):
    """Review #4: if the snapshot read raised after the cache was filled, the
    original branch kept serving the snapshot's keys."""
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)

    store = ProllyTreeStore(path)
    store.put(("default",), "on.main", {"content": "m", "confidence": 1.0})
    _git(path, "branch", "snapshot_x")
    store.put(("default",), "after.snapshot", {"content": "a", "confidence": 1.0})

    snapshot = store.get_state_at_snapshot(("default",), "snapshot_x")
    assert sorted(snapshot) == ["on.main"]
    assert snapshot["on.main"]["content"] == "m"

    # Back on main: the cache must describe main, not the snapshot.
    assert sorted(store.all_keys()) == ["default:after.snapshot", "default:on.main"]


# ---------------------------------------------------------------------------
# Round 3 review: cache-key source, revision syntax on full refs, tree SHAs.
# ---------------------------------------------------------------------------


def test_cache_key_uses_the_handle_branch_not_the_disk_head(tmp_path):
    """Review #1: the cache key's commit must come from the handle's branch.

    Handle A is on main while another process moves on-disk HEAD to feat, so
    the old key was (main, feat's commit) and a later commit on main never
    invalidated it. Both values now come from refs/heads/<handle branch>.
    """
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)

    writer = ProllyTreeStore(path)
    writer.put(("default",), "a", {"content": "a", "confidence": 1.0})

    # Put a key on feat so main and feat have different commits.
    _git(path, "branch", "feat")
    _git(path, "checkout", "feat")
    ProllyTreeStore(path).put(
        ("default",), "onfeat_pre", {"content": "f", "confidence": 1.0}
    )
    _git(path, "checkout", "main")

    # Handle A stays on main while on-disk HEAD moves to feat.
    handle = ProllyTreeStore(path)
    _git(path, "symbolic-ref", "HEAD", "refs/heads/feat")

    assert handle.all_keys() == ["default:a"]  # first call builds the cache

    # Another process commits on main, then moves HEAD back to feat.
    _git(path, "checkout", "main")
    ProllyTreeStore(path).put(
        ("default",), "main2", {"content": "m", "confidence": 1.0}
    )
    _git(path, "symbolic-ref", "HEAD", "refs/heads/feat")

    # main moved on, so the cache must be rebuilt.
    assert handle.all_keys() == ["default:a", "default:main2"]


@pytest.mark.parametrize(
    "ref", ["refs/heads/main~1", "refs/heads/main^{tree}", "refs/tags/v1^{}"]
)
def test_revision_syntax_on_full_refs_is_rejected(tmp_path, ref):
    """Review #2: revision syntax must be filtered before full refs pass.

    Without that, refs/heads/main~1 was accepted on its prefix and failed
    inside diff with a raw git error instead of "Branch does not exist".
    """
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)
    _seed(path, 1)
    _git(path, "tag", "v1")

    with pytest.raises(ValueError, match="does not exist"):
        ProllyTreeStore(path, ref=ref)


def test_tree_sha_is_rejected(tmp_path):
    """Review #3: a 40-hex SHA must peel to a commit, not a tree or blob.

    A tree SHA passed validation, rev-list found no roots, and all_keys()
    returned [] — indistinguishable from a genuinely empty branch.
    """
    path = str(tmp_path / "store")
    StoreService(path).create_store(path)
    _seed(path, 2)

    tree_sha = _git(path, "rev-parse", "HEAD^{tree}")
    with pytest.raises(ValueError, match="does not exist"):
        ProllyTreeStore(path, ref=tree_sha)

    # A full commit SHA still reads normally.
    commit_sha = _git(path, "rev-parse", "HEAD")
    assert len(ProllyTreeStore(path, ref=commit_sha).all_keys()) == 2

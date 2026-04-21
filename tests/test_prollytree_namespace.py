"""
Tests for the NamespacedKvStore feature introduced in prollytree 0.3.2.

These tests exercise the native ProllyTree Python bindings directly to confirm
that the namespace subtree API behaves as advertised: each namespace is isolated,
carries its own O(1) root hash, and participates in shared git-style commits.

See prollytree release 0.3.2: "Add native namespace support to KvStore with
separate subtrees" (PR #152).
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

# NamespacedKvStore is not re-exported from prollytree's top-level __init__,
# so import it from the compiled submodule.
from prollytree.prollytree import NamespacedKvStore


def _init_git_dir(root: Path) -> Path:
    """Create a git repository with a data subdirectory for the store.

    NamespacedKvStore requires its path to live inside a git repository and needs
    an initial commit to resolve HEAD.
    """
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@memoir.local"], cwd=root, check=True
    )
    subprocess.run(["git", "config", "user.name", "memoir-test"], cwd=root, check=True)
    readme = root / "README.md"
    readme.write_text("# ns test\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "init", "--quiet"], cwd=root, check=True)
    data_dir = root / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def store_path():
    """Yield a ready-to-use data directory inside a fresh git repo."""
    with tempfile.TemporaryDirectory() as tmp:
        yield _init_git_dir(Path(tmp))


@pytest.fixture
def store(store_path):
    return NamespacedKvStore(str(store_path))


class TestNamespaceBasicOperations:
    """Namespace-scoped insert/get/delete/list_keys."""

    def test_insert_and_get(self, store):
        store.ns_insert("users", b"alice", b'{"age": 30}')
        assert store.ns_get("users", b"alice") == b'{"age": 30}'

    def test_get_missing_key_returns_none(self, store):
        assert store.ns_get("users", b"nonexistent") is None

    def test_get_from_missing_namespace_returns_none(self, store):
        # Reading from a namespace that was never written to should not error.
        assert store.ns_get("ghost", b"any") is None

    def test_list_keys_in_namespace(self, store):
        store.ns_insert("users", b"alice", b"1")
        store.ns_insert("users", b"bob", b"2")
        store.ns_insert("users", b"carol", b"3")
        keys = store.ns_list_keys("users")
        assert set(keys) == {b"alice", b"bob", b"carol"}

    def test_list_keys_empty_namespace(self, store):
        assert store.ns_list_keys("missing") == []

    def test_delete_key_returns_true_when_present(self, store):
        store.ns_insert("users", b"alice", b"1")
        assert store.ns_delete("users", b"alice") is True
        assert store.ns_get("users", b"alice") is None

    def test_delete_key_returns_false_when_absent(self, store):
        assert store.ns_delete("users", b"ghost") is False


class TestNamespaceIsolation:
    """Separate subtrees keep identical keys from colliding across namespaces."""

    def test_same_key_different_namespaces(self, store):
        store.ns_insert("users", b"id-1", b"alice")
        store.ns_insert("products", b"id-1", b"widget")
        assert store.ns_get("users", b"id-1") == b"alice"
        assert store.ns_get("products", b"id-1") == b"widget"

    def test_list_keys_is_namespace_scoped(self, store):
        store.ns_insert("users", b"u1", b"x")
        store.ns_insert("users", b"u2", b"x")
        store.ns_insert("products", b"p1", b"x")
        assert set(store.ns_list_keys("users")) == {b"u1", b"u2"}
        assert set(store.ns_list_keys("products")) == {b"p1"}

    def test_delete_in_one_namespace_leaves_others(self, store):
        store.ns_insert("users", b"k", b"u-val")
        store.ns_insert("products", b"k", b"p-val")
        store.ns_delete("users", b"k")
        assert store.ns_get("users", b"k") is None
        assert store.ns_get("products", b"k") == b"p-val"


class TestNamespaceRegistry:
    """list_namespaces / delete_namespace / default namespace behavior."""

    def test_list_namespaces_includes_default(self, store):
        # A fresh store already has the 'default' namespace available.
        assert "default" in store.list_namespaces()

    def test_list_namespaces_after_inserts(self, store):
        store.ns_insert("users", b"k", b"v")
        store.ns_insert("products", b"k", b"v")
        names = store.list_namespaces()
        assert "users" in names
        assert "products" in names

    def test_delete_staged_namespace(self, store):
        # Matches the Rust unit test for delete_namespace: delete operates on
        # the in-memory registry, so it removes a namespace whose changes have
        # not yet been committed.
        store.ns_insert("temp", b"key", b"value")
        assert "temp" in store.list_namespaces()
        assert store.delete_namespace("temp") is True
        assert "temp" not in store.list_namespaces()

    def test_delete_nonexistent_namespace_returns_false(self, store):
        assert store.delete_namespace("does-not-exist") is False

    def test_delete_namespace_is_idempotent(self, store):
        store.ns_insert("temp", b"k", b"v")
        assert store.delete_namespace("temp") is True
        # Second delete on the now-missing namespace reports False.
        assert store.delete_namespace("temp") is False

    def test_cannot_delete_default_namespace(self, store):
        # Rust layer explicitly refuses to delete the default namespace.
        with pytest.raises(ValueError, match="Cannot delete the default namespace"):
            store.delete_namespace("default")


class TestDefaultNamespaceFlatAPI:
    """The flat insert/get/delete/list_keys target the 'default' namespace."""

    def test_flat_api_round_trip(self, store):
        store.insert(b"flat-key", b"flat-value")
        assert store.get(b"flat-key") == b"flat-value"

    def test_flat_api_does_not_leak_into_named_namespace(self, store):
        store.insert(b"shared", b"from-flat")
        store.ns_insert("other", b"shared", b"from-named")
        assert store.get(b"shared") == b"from-flat"
        assert store.ns_get("other", b"shared") == b"from-named"

    def test_flat_list_keys_scoped_to_default(self, store):
        store.insert(b"x", b"1")
        store.ns_insert("other", b"y", b"1")
        assert set(store.list_keys()) == {b"x"}


class TestNamespaceRootHash:
    """get_namespace_root_hash provides an O(1) per-namespace fingerprint."""

    def test_root_hash_is_32_bytes_after_commit(self, store):
        store.ns_insert("users", b"a", b"1")
        store.commit("seed")
        h = store.get_namespace_root_hash("users")
        assert isinstance(h, bytes)
        assert len(h) == 32

    def test_root_hash_changes_on_content_change(self, store):
        store.ns_insert("users", b"a", b"1")
        store.commit("first")
        before = store.get_namespace_root_hash("users")
        store.ns_insert("users", b"b", b"2")
        store.commit("second")
        after = store.get_namespace_root_hash("users")
        assert before != after

    def test_root_hash_unchanged_when_other_namespace_mutates(self, store):
        store.ns_insert("users", b"a", b"1")
        store.ns_insert("products", b"p", b"1")
        store.commit("seed both")
        users_hash = store.get_namespace_root_hash("users")
        store.ns_insert("products", b"p2", b"2")
        store.commit("mutate products only")
        assert store.get_namespace_root_hash("users") == users_hash


class TestNamespaceChanged:
    """namespace_changed compares a namespace's root hash between two commits."""

    def test_unchanged_namespace_reports_false(self, store):
        store.ns_insert("users", b"a", b"1")
        store.ns_insert("products", b"p", b"1")
        c1 = store.commit("seed")

        store.ns_insert("products", b"p2", b"2")
        c2 = store.commit("touch products")

        assert store.namespace_changed("users", c1, c2) is False

    def test_changed_namespace_reports_true(self, store):
        store.ns_insert("users", b"a", b"1")
        c1 = store.commit("seed")
        store.ns_insert("users", b"b", b"2")
        c2 = store.commit("grow users")
        assert store.namespace_changed("users", c1, c2) is True


class TestCommitsAcrossNamespaces:
    """A single commit captures staged changes across every namespace."""

    def test_single_commit_covers_all_namespaces(self, store):
        store.ns_insert("users", b"u", b"1")
        store.ns_insert("products", b"p", b"1")
        commit_id = store.commit("cross-ns commit")
        assert isinstance(commit_id, str)
        assert len(commit_id) > 0
        assert store.ns_get("users", b"u") == b"1"
        assert store.ns_get("products", b"p") == b"1"

    def test_commit_returns_unique_ids(self, store):
        store.ns_insert("users", b"u", b"1")
        first = store.commit("first")
        store.ns_insert("users", b"v", b"2")
        second = store.commit("second")
        assert first != second


class TestPersistenceAndReopen:
    """NamespacedKvStore.open reconstructs state from disk."""

    def test_open_round_trip(self, store_path):
        store = NamespacedKvStore(str(store_path))
        store.ns_insert("users", b"alice", b"data")
        store.ns_insert("products", b"p1", b"widget")
        store.commit("seed")

        reopened = NamespacedKvStore.open(str(store_path))
        assert reopened.ns_get("users", b"alice") == b"data"
        assert reopened.ns_get("products", b"p1") == b"widget"
        names = reopened.list_namespaces()
        assert "users" in names
        assert "products" in names

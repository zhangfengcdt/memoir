"""
Tests for the pluggable StorageBackend options on ``VersionedKvStore``.

prollytree 0.3.2 exposes four storage backends:

- ``StorageBackend.Git``     — full git versioning (already covered by the
                                existing ``test_versioning.py`` via
                                ``ProllyTreeStore``)
- ``StorageBackend.File``    — content-addressed file storage under ``.git/``
- ``StorageBackend.InMemory``— volatile in-process storage
- ``StorageBackend.RocksDB`` — RocksDB-backed (only present when the
                                ``rocksdb_storage`` feature is compiled in;
                                the PyPI wheel does not ship with it, so that
                                test is skipped when the feature is absent)

All backends share the same ``VersionedKvStore`` Python surface. These tests
verify round-trip behavior and cross-backend agreement on core operations,
plus persistence semantics unique to each backend.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest
from prollytree import StorageBackend, VersionedKvStore


def _init_git_dir(root: Path) -> Path:
    """Create a git repo and return its ``data/`` subdirectory.

    Every backend requires the store's path to sit inside a git repository —
    the versioning metadata (HEAD, branches, commit history) lives in ``.git/``
    regardless of whether tree nodes are persisted to disk.
    """
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@memoir.local"], cwd=root, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "memoir-test"], cwd=root, check=True
    )
    (root / "README.md").write_text("# backend test\n")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init", "--quiet"], cwd=root, check=True
    )
    data_dir = root / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def store_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield _init_git_dir(Path(tmp))


def _rocksdb_available() -> bool:
    """Probe whether the running wheel includes the rocksdb_storage feature."""
    with tempfile.TemporaryDirectory() as tmp:
        data = _init_git_dir(Path(tmp))
        try:
            VersionedKvStore(str(data), StorageBackend.RocksDB)
        except ValueError as e:
            if "rocksdb_storage" in str(e):
                return False
            raise
        return True


ROCKSDB_AVAILABLE = _rocksdb_available()


@pytest.mark.parametrize(
    "backend",
    [
        StorageBackend.File,
        StorageBackend.InMemory,
        pytest.param(
            StorageBackend.RocksDB,
            marks=pytest.mark.skipif(
                not ROCKSDB_AVAILABLE,
                reason="wheel built without rocksdb_storage feature",
            ),
        ),
    ],
    ids=["File", "InMemory", "RocksDB"],
)
class TestBackendCoreOperations:
    """Every non-Git backend must pass the same basic contract."""

    def test_insert_and_get(self, store_path, backend):
        store = VersionedKvStore(str(store_path), backend)
        store.insert(b"alice", b"hello")
        assert store.get(b"alice") == b"hello"

    def test_get_missing_returns_none(self, store_path, backend):
        store = VersionedKvStore(str(store_path), backend)
        assert store.get(b"does-not-exist") is None

    def test_update_existing_key(self, store_path, backend):
        store = VersionedKvStore(str(store_path), backend)
        store.insert(b"k", b"v1")
        assert store.update(b"k", b"v2") is True
        assert store.get(b"k") == b"v2"

    def test_update_missing_returns_false(self, store_path, backend):
        store = VersionedKvStore(str(store_path), backend)
        assert store.update(b"missing", b"v") is False

    def test_delete_existing_returns_true(self, store_path, backend):
        store = VersionedKvStore(str(store_path), backend)
        store.insert(b"k", b"v")
        assert store.delete(b"k") is True
        assert store.get(b"k") is None

    def test_delete_missing_returns_false(self, store_path, backend):
        store = VersionedKvStore(str(store_path), backend)
        assert store.delete(b"nope") is False

    def test_list_keys_reflects_inserts(self, store_path, backend):
        store = VersionedKvStore(str(store_path), backend)
        store.insert(b"a", b"1")
        store.insert(b"b", b"2")
        store.insert(b"c", b"3")
        assert set(store.list_keys()) == {b"a", b"b", b"c"}

    def test_commit_returns_hex_id(self, store_path, backend):
        store = VersionedKvStore(str(store_path), backend)
        store.insert(b"k", b"v")
        commit_id = store.commit("seed")
        assert isinstance(commit_id, str)
        # Git object IDs are 40 hex chars.
        assert len(commit_id) == 40
        int(commit_id, 16)  # raises if not hex

    def test_storage_backend_getter_reports_chosen_backend(
        self, store_path, backend
    ):
        store = VersionedKvStore(str(store_path), backend)
        assert store.storage_backend() == backend


class TestFileBackendPersistence:
    """File backend is the practical "persistent without git-object plumbing"
    option — confirm values survive reopen via the node-storage on disk."""

    def test_values_survive_reopen(self, store_path):
        store = VersionedKvStore(str(store_path), StorageBackend.File)
        store.insert(b"persistent", b"yes")
        store.commit("persist")
        del store

        reopened = VersionedKvStore.open(str(store_path), StorageBackend.File)
        assert reopened.get(b"persistent") == b"yes"
        assert reopened.storage_backend() == StorageBackend.File

    def test_file_backend_writes_node_files(self, store_path):
        store = VersionedKvStore(str(store_path), StorageBackend.File)
        store.insert(b"k", b"v")
        store.commit("write nodes")

        # The File backend writes node blobs to <repo_root>/.git/prolly/nodes/files/.
        # ``store_path`` is the ``data/`` subdirectory; the git repo lives at
        # its parent.
        node_dir = store_path.parent / ".git" / "prolly" / "nodes" / "files"
        assert node_dir.is_dir()
        # At least one node file should exist after a commit.
        assert any(p.is_file() for p in node_dir.rglob("*"))


class TestInMemoryBackendVolatility:
    """InMemory backend documents that reopens see an empty state (no node
    persistence). Branch metadata still lives in .git/ but tree contents do
    not, so a reopen cannot resurrect the pre-drop values."""

    def test_values_do_not_survive_new_instance(self, store_path):
        store = VersionedKvStore(str(store_path), StorageBackend.InMemory)
        store.insert(b"ephemeral", b"yes")
        store.commit("seed")
        assert store.get(b"ephemeral") == b"yes"
        del store

        reopened = VersionedKvStore.open(str(store_path), StorageBackend.InMemory)
        # Nodes were never persisted to disk, so the value is unreachable.
        assert reopened.get(b"ephemeral") is None


class TestRocksDBAvailability:
    """If the wheel is built without the rocksdb_storage feature, the Python
    binding must raise a clear ValueError naming the feature."""

    @pytest.mark.skipif(
        ROCKSDB_AVAILABLE, reason="wheel ships with rocksdb_storage feature"
    )
    def test_rocksdb_backend_rejected_when_feature_disabled(self, store_path):
        with pytest.raises(ValueError, match="rocksdb_storage"):
            VersionedKvStore(str(store_path), StorageBackend.RocksDB)

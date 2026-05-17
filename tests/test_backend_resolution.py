"""Tests for ``memoir.store.backend`` — backend resolution + lock-file I/O.

Precedence rules (highest first):
1. Per-store lock at ``<store>/.git/memoir-backend``
2. Legacy on-disk detection. Requires a prollytree-specific marker
   (``data/prolly_config_tree_config`` or ``.git/prolly/``) — a plain
   ``data/`` directory is *not* enough. Within a recognized memoir
   store, presence of ``.git/prolly/nodes/files/`` ⇒ File; otherwise
   ⇒ Git (the historic default).
3. Env var ``MEMOIR_PROLLY_BACKEND``
4. Default: File
"""

import subprocess
from pathlib import Path

import pytest
from prollytree import StorageBackend

from memoir.store.backend import is_memoir_store, resolve_backend, write_backend_lock


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True)


# --- env var + default ---


def test_default_is_file_when_no_path(monkeypatch):
    monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)
    assert resolve_backend() == StorageBackend.File


def test_env_var_git(monkeypatch):
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "git")
    assert resolve_backend() == StorageBackend.Git


def test_env_var_file(monkeypatch):
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "file")
    assert resolve_backend() == StorageBackend.File


def test_env_var_rocksdb(monkeypatch):
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "rocksdb")
    assert resolve_backend() == StorageBackend.RocksDB


def test_env_var_memory_rejected_early(monkeypatch):
    """``memory`` (InMemory) is volatile and cannot be persisted in a
    backend lock. Reject at parse time rather than letting partial init
    run before ``write_backend_lock`` raises."""
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "memory")
    with pytest.raises(ValueError, match="MEMOIR_PROLLY_BACKEND"):
        resolve_backend()


def test_env_var_case_insensitive(monkeypatch):
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "GIT")
    assert resolve_backend() == StorageBackend.Git


def test_env_var_strips_whitespace(monkeypatch):
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "  file  ")
    assert resolve_backend() == StorageBackend.File


def test_env_var_invalid_raises(monkeypatch):
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "neon")
    with pytest.raises(ValueError, match="MEMOIR_PROLLY_BACKEND"):
        resolve_backend()


def test_brand_new_path_with_no_store_uses_default(monkeypatch, tmp_path):
    """Empty directory (no .git, no data) — treat as brand-new, use default."""
    monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)
    assert resolve_backend(tmp_path) == StorageBackend.File


# --- per-store lock (highest precedence) ---


def test_per_store_lock_overrides_env(monkeypatch, tmp_path):
    _init_repo(tmp_path)
    write_backend_lock(tmp_path, StorageBackend.Git)
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "file")
    assert resolve_backend(tmp_path) == StorageBackend.Git


def test_per_store_lock_file(tmp_path, monkeypatch):
    monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)
    _init_repo(tmp_path)
    write_backend_lock(tmp_path, StorageBackend.File)
    assert resolve_backend(tmp_path) == StorageBackend.File


def test_per_store_lock_overrides_legacy_detection(monkeypatch, tmp_path):
    """Lock wins even when on-disk state would point at a different backend."""
    _init_repo(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "prolly_config_tree_config").write_text("{}")
    # On-disk state looks Git-backed (no File node dir), but lock says File.
    write_backend_lock(tmp_path, StorageBackend.File)
    monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)
    assert resolve_backend(tmp_path) == StorageBackend.File


def test_per_store_lock_invalid_raises(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / ".git" / "memoir-backend").write_text("xenon\n")
    with pytest.raises(ValueError, match="memoir-backend"):
        resolve_backend(tmp_path)


# --- legacy on-disk detection ---


def test_legacy_store_with_file_node_dir_detects_file(monkeypatch, tmp_path):
    """Real legacy File-backed store: .git/, data/prolly_config_tree_config,
    and .git/prolly/nodes/files/ all present."""
    _init_repo(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "prolly_config_tree_config").write_text("{}")
    (tmp_path / ".git" / "prolly" / "nodes" / "files").mkdir(parents=True)
    monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)
    assert resolve_backend(tmp_path) == StorageBackend.File


def test_legacy_store_without_file_node_dir_detects_git(monkeypatch, tmp_path):
    """A store with .git/, data/prolly_config_tree_config, but no File-
    backend dir was created by an older memoir version with the Git
    backend. Preserve that on open."""
    _init_repo(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "prolly_config_tree_config").write_text("{}")
    monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)
    assert resolve_backend(tmp_path) == StorageBackend.Git


def test_legacy_detection_ignores_env(monkeypatch, tmp_path):
    """Once a store exists on disk, the legacy detector pins its backend so
    an accidentally-set env var can't break it."""
    _init_repo(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "prolly_config_tree_config").write_text("{}")
    # Legacy Git-backed store.
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "file")
    assert resolve_backend(tmp_path) == StorageBackend.Git


def test_legacy_detection_requires_memoir_marker(monkeypatch, tmp_path):
    """A repo with .git/ and a plain top-level data/ but no memoir-
    specific markers is NOT a memoir store. ``_detect_legacy_backend``
    must return None so resolution falls through to env/default rather
    than misclassifying a random project repo as a Git-backed memoir
    store (which would let the adapter materialize prolly state in it)."""
    _init_repo(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "some_project_file.txt").write_text("not memoir\n")
    monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)
    # No env, no lock, no prolly marker — falls through to File default.
    assert resolve_backend(tmp_path) == StorageBackend.File


# --- is_memoir_store helper ---


def test_is_memoir_store_recognizes_backend_lock(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / ".git" / "memoir-backend").write_text("file\n")
    assert is_memoir_store(tmp_path)


def test_is_memoir_store_recognizes_prolly_dir(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / ".git" / "prolly").mkdir()
    assert is_memoir_store(tmp_path)


def test_is_memoir_store_recognizes_prolly_config(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "prolly_config_tree_config").write_text("{}")
    assert is_memoir_store(tmp_path)


def test_is_memoir_store_rejects_plain_data_dir(tmp_path):
    """The whole point: ``data/`` alone is not a memoir marker. A random
    project repo with a top-level data/ directory must not be classified
    as a memoir store."""
    _init_repo(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "user_file.csv").write_text("not memoir\n")
    assert not is_memoir_store(tmp_path)


def test_is_memoir_store_rejects_empty_dir(tmp_path):
    assert not is_memoir_store(tmp_path)


def test_is_memoir_store_accepts_str_path(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / ".git" / "memoir-backend").write_text("file\n")
    assert is_memoir_store(str(tmp_path))


# --- write_backend_lock ---


def test_write_backend_lock_creates_file_with_lowercase_name(tmp_path):
    _init_repo(tmp_path)
    write_backend_lock(tmp_path, StorageBackend.File)
    lock = tmp_path / ".git" / "memoir-backend"
    assert lock.read_text().strip() == "file"


def test_write_backend_lock_overwrites_existing(tmp_path):
    _init_repo(tmp_path)
    write_backend_lock(tmp_path, StorageBackend.Git)
    write_backend_lock(tmp_path, StorageBackend.File)
    assert (tmp_path / ".git" / "memoir-backend").read_text().strip() == "file"


def test_write_backend_lock_refuses_inmemory(tmp_path):
    """Persisting a volatile backend would lose all data on the next reopen,
    which is incoherent. Refuse explicitly with a clear error."""
    _init_repo(tmp_path)
    with pytest.raises(ValueError, match="InMemory"):
        write_backend_lock(tmp_path, StorageBackend.InMemory)

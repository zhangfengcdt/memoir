"""Tests for ``memoir.store.backend`` — backend resolution + lock-file I/O.

Precedence rules (highest first):
1. Per-store lock at ``<store>/.git/memoir-backend``
2. Legacy on-disk detection (presence of ``.git/prolly/nodes/files/`` ⇒ File;
   else if ``.git`` and ``data/`` exist ⇒ Git, the historic default)
3. Env var ``MEMOIR_PROLLY_BACKEND``
4. Default: File
"""

import subprocess
from pathlib import Path

import pytest
from prollytree import StorageBackend

from memoir.store.backend import resolve_backend, write_backend_lock


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


def test_env_var_memory(monkeypatch):
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "memory")
    assert resolve_backend() == StorageBackend.InMemory


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
    _init_repo(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / ".git" / "prolly" / "nodes" / "files").mkdir(parents=True)
    monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)
    assert resolve_backend(tmp_path) == StorageBackend.File


def test_legacy_store_without_file_node_dir_detects_git(monkeypatch, tmp_path):
    """A store with .git and data/ but no File-backend dir was created by an
    older memoir version with the Git backend. Preserve that on open."""
    _init_repo(tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)
    assert resolve_backend(tmp_path) == StorageBackend.Git


def test_legacy_detection_ignores_env(monkeypatch, tmp_path):
    """Once a store exists on disk, the legacy detector pins its backend so
    an accidentally-set env var can't break it."""
    _init_repo(tmp_path)
    (tmp_path / "data").mkdir()
    # Legacy Git-backed store.
    monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "file")
    assert resolve_backend(tmp_path) == StorageBackend.Git


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

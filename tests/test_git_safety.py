"""Tests for ``src/memoir/store/git_safety.harden_git_config``.

Verify the two git-config flags are applied on a fresh repo, overwrite any
pre-existing unsafe values (the retrofit case for legacy stores), are
idempotent, and reject non-git directories.
"""

import subprocess
from pathlib import Path

import pytest

from memoir.store.git_safety import harden_git_config


def _init_repo(path: Path) -> None:
    """Create a bare-bones git repo at ``path`` with a usable user identity."""
    subprocess.run(["git", "init", "--quiet"], cwd=path, check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "test@memoir.local"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "memoir-test"], check=True
    )


def _get(path: Path, key: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(path), "config", "--get", key],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_harden_sets_configs_on_fresh_repo(tmp_path):
    _init_repo(tmp_path)
    harden_git_config(tmp_path)
    assert _get(tmp_path, "gc.auto") == "0"
    assert _get(tmp_path, "gc.pruneExpire") == "never"


def test_harden_overwrites_unsafe_configs(tmp_path):
    """Retrofit path: a legacy store with default-or-unsafe values is fixed."""
    _init_repo(tmp_path)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "gc.auto", "6700"], check=True
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "gc.pruneExpire", "2.weeks.ago"],
        check=True,
    )
    harden_git_config(tmp_path)
    assert _get(tmp_path, "gc.auto") == "0"
    assert _get(tmp_path, "gc.pruneExpire") == "never"


def test_harden_is_idempotent(tmp_path):
    _init_repo(tmp_path)
    harden_git_config(tmp_path)
    harden_git_config(tmp_path)
    harden_git_config(tmp_path)
    assert _get(tmp_path, "gc.auto") == "0"
    assert _get(tmp_path, "gc.pruneExpire") == "never"


def test_harden_accepts_str_path(tmp_path):
    _init_repo(tmp_path)
    harden_git_config(str(tmp_path))
    assert _get(tmp_path, "gc.auto") == "0"
    assert _get(tmp_path, "gc.pruneExpire") == "never"


def test_harden_raises_on_non_git_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        harden_git_config(tmp_path)


def test_file_backend_survives_aggressive_git_gc(tmp_path):
    """The File backend's reason-for-being: node files live at
    ``.git/prolly/nodes/files/<hex>``, *outside* ``.git/objects/``, so even
    the explicit-override case (``git gc --aggressive --prune=now``) leaves
    them untouched. Hardening alone (Decision #1) cannot protect against
    this; only the File backend does.
    """
    from memoir.services.store_service import StoreService
    from memoir.store.prolly_adapter import ProllyTreeStore

    namespace = ("gc_test",)
    key = "should-survive"

    result = StoreService().create_store(str(tmp_path), backend="file")
    assert result.success

    store = ProllyTreeStore(
        path=str(tmp_path), enable_versioning=True, auto_commit=True
    )
    store.put(namespace, key, {"content": "alive"})
    del store

    # The override case: even with --prune=now (which bypasses
    # gc.pruneExpire=never), data outside .git/objects/ stays.
    subprocess.run(
        ["git", "-C", str(tmp_path), "gc", "--aggressive", "--prune=now"],
        check=True,
        capture_output=True,
    )

    node_dir = tmp_path / ".git" / "prolly" / "nodes" / "files"
    assert node_dir.is_dir()
    assert any(p.is_file() for p in node_dir.rglob("*")), "node files were pruned"

    reopened = ProllyTreeStore(path=str(tmp_path), enable_versioning=True)
    value = reopened.get(namespace, key)
    assert value is not None, "data lost across aggressive git gc"
    assert value["content"] == "alive"


def test_prolly_adapter_writes_backend_lock_on_fresh_init(tmp_path, monkeypatch):
    """Direct callers of ProllyTreeStore (e.g. ``ui/initializer.py``) bypass
    StoreService.create_store and so don't write the per-store backend
    lock at create time. To prevent that path from leaving stores without
    a lock, the adapter writes the lock the first time it initializes a
    fresh prollytree.
    """
    from memoir.store.prolly_adapter import ProllyTreeStore

    # Pre-create the bare git scaffolding the way ui/initializer.py does.
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)

    lock = tmp_path / ".git" / "memoir-backend"
    assert not lock.exists()

    ProllyTreeStore(path=str(tmp_path), enable_versioning=True)

    assert lock.exists()
    assert lock.read_text().strip() == "file"


def test_prolly_adapter_refuses_non_memoir_git_repo_with_commits(tmp_path):
    """The defense-in-depth twin of StoreService.create_store's guardrail.
    Read-side callers (status / recall / ui server) can land on a path that
    is a git repo (has commits) but is NOT a memoir store. Without this
    guard, the adapter would happily initialize a fresh prolly tree there
    — exactly how this repo's source tree got accidentally turned into a
    File-backed memoir store during a leaky test run.
    """
    from memoir.store.prolly_adapter import ProllyTreeStore

    # Make a git repo with one real (non-memoir) commit.
    subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "x@y"], check=True
    )
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "x"], check=True)
    (tmp_path / "README.md").write_text("not a memoir store\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init", "--quiet"], check=True
    )

    with pytest.raises(FileNotFoundError, match="Not a memoir store"):
        ProllyTreeStore(path=str(tmp_path), enable_versioning=True)

    # Crucially: nothing was created in the repo as a side effect.
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / ".git" / "memoir-backend").exists()
    assert not (tmp_path / ".git" / "prolly").exists()


def test_prolly_adapter_retrofits_unhardened_store_on_open(tmp_path):
    """A legacy memoir store (one without the gc-safety configs) must be
    retrofitted on the next open through ProllyTreeStore — this is how the
    fix reaches the entire installed base without a migration step.
    """
    from memoir.services.store_service import StoreService
    from memoir.store.prolly_adapter import ProllyTreeStore

    StoreService().create_store(str(tmp_path))
    for key in ("gc.auto", "gc.pruneExpire"):
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "--unset", key], check=True
        )
    assert _get(tmp_path, "gc.auto") == ""
    assert _get(tmp_path, "gc.pruneExpire") == ""

    ProllyTreeStore(path=str(tmp_path), enable_versioning=True)

    assert _get(tmp_path, "gc.auto") == "0"
    assert _get(tmp_path, "gc.pruneExpire") == "never"

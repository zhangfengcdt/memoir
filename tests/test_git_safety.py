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

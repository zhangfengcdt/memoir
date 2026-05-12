# SPDX-License-Identifier: Apache-2.0
"""Tests for the best-effort code-repo branch enrichment on /api/store.

Exercises three things the handler now relies on:

* ``_resolve_code_repo_path`` decodes the store-slug convention into a real
  on-disk path when one exists and is a git repo, and otherwise returns
  ``None``.
* ``_git_head_info`` reads the live HEAD branch of a git repo (or returns
  ``None`` cleanly when the path isn't a repo).
* ``_code_repo_branch_for_store`` caches results for ``_CODE_REPO_CACHE_TTL_SEC``
  so /api/store polling doesn't spawn two subprocesses per poll.

The slug convention (mirrors ``plugins/claude-code/scripts/derive-store-path.sh``)
maps both ``/`` and ``.`` to ``-`` in the absolute project path. The reverse
``_resolve_code_repo_path`` is lossy when the path contains dots or dashes;
the fake repo is therefore created under ``/tmp/memoirtest<alnum>/`` whose
resolved form (``/private/tmp/...`` on macOS) contains neither.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from memoir.ui.handlers import store_handler
from memoir.ui.handlers.store_handler import (
    _code_repo_branch_cache,
    _code_repo_branch_for_store,
    _git_head_info,
    _resolve_code_repo_path,
)


def _slug_from_path(p: str) -> str:
    """Mirror ``tr '/.' '--'`` from derive-store-path.sh."""
    return p.translate(str.maketrans("/.", "--"))


@pytest.fixture
def isolated_home(monkeypatch, tmp_path):
    """Monkeypatch ``Path.home`` to a clean tmp dir so the tests never read
    or write the real ``~/.memoir/``. Also clears the module-level branch
    cache so prior tests don't bleed across cases."""
    home = tmp_path / "home"
    (home / ".memoir").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    _code_repo_branch_cache.clear()
    yield home
    _code_repo_branch_cache.clear()


@pytest.fixture
def fake_repo():
    """A real git repo at a slug-round-trippable path. ``mkdtemp`` uses
    alphanumeric-only suffixes; ``/tmp`` resolves to ``/private/tmp`` on
    macOS — neither contains dots or dashes, so the slug encoding round-trips."""
    parent = tempfile.mkdtemp(prefix="memoirtest", dir="/tmp")
    repo_path = str(Path(parent).resolve() / "repo")
    Path(repo_path).mkdir()
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
    }
    subprocess.run(
        ["git", "init", "-q", "-b", "main"],
        cwd=repo_path,
        check=True,
        env=env,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-q", "-m", "init"],
        cwd=repo_path,
        check=True,
        env=env,
    )
    yield repo_path
    shutil.rmtree(parent, ignore_errors=True)


def test_resolve_code_repo_path_decodes_slug_to_real_repo(isolated_home, fake_repo):
    slug = _slug_from_path(fake_repo)
    store_path = isolated_home / ".memoir" / slug
    store_path.mkdir()

    assert _resolve_code_repo_path(str(store_path), []) == fake_repo


def test_resolve_returns_none_when_store_not_under_memoir_home(isolated_home, tmp_path):
    other = tmp_path / "stray_store"
    other.mkdir()
    assert _resolve_code_repo_path(str(other), []) is None


def test_resolve_returns_none_when_decoded_path_is_not_a_repo(isolated_home):
    store_path = isolated_home / ".memoir" / "-nonexistent-path"
    store_path.mkdir()
    assert _resolve_code_repo_path(str(store_path), []) is None


def test_git_head_info_returns_branch_for_initialised_repo(fake_repo):
    sha, branch = _git_head_info(fake_repo)
    assert branch == "main"
    assert sha is not None
    assert len(sha) == 40


def test_git_head_info_returns_none_for_non_repo(tmp_path):
    sha, branch = _git_head_info(str(tmp_path))
    assert sha is None
    assert branch is None


def test_branch_for_store_populates_when_resolvable(isolated_home, fake_repo):
    slug = _slug_from_path(fake_repo)
    store_path = isolated_home / ".memoir" / slug
    store_path.mkdir()

    assert _code_repo_branch_for_store(str(store_path)) == "main"


def test_branch_for_store_returns_none_when_unresolvable(isolated_home):
    store_path = isolated_home / ".memoir" / "-no-such-thing"
    store_path.mkdir()

    assert _code_repo_branch_for_store(str(store_path)) is None


def test_branch_cache_skips_repeat_lookups_within_ttl(
    isolated_home, fake_repo, monkeypatch
):
    slug = _slug_from_path(fake_repo)
    store_path = isolated_home / ".memoir" / slug
    store_path.mkdir()

    calls = {"resolve": 0, "head": 0}
    real_resolve = store_handler._resolve_code_repo_path
    real_head = store_handler._git_head_info

    def counting_resolve(*args, **kwargs):
        calls["resolve"] += 1
        return real_resolve(*args, **kwargs)

    def counting_head(*args, **kwargs):
        calls["head"] += 1
        return real_head(*args, **kwargs)

    monkeypatch.setattr(store_handler, "_resolve_code_repo_path", counting_resolve)
    monkeypatch.setattr(store_handler, "_git_head_info", counting_head)

    # First call performs the real lookup.
    assert _code_repo_branch_for_store(str(store_path)) == "main"
    assert calls == {"resolve": 1, "head": 1}

    # Three more calls within the TTL window must hit the cache.
    for _ in range(3):
        assert _code_repo_branch_for_store(str(store_path)) == "main"
    assert calls == {"resolve": 1, "head": 1}


def test_branch_cache_refreshes_after_ttl_expires(
    isolated_home, fake_repo, monkeypatch
):
    slug = _slug_from_path(fake_repo)
    store_path = isolated_home / ".memoir" / slug
    store_path.mkdir()

    calls = {"resolve": 0}
    real_resolve = store_handler._resolve_code_repo_path

    def counting_resolve(*args, **kwargs):
        calls["resolve"] += 1
        return real_resolve(*args, **kwargs)

    monkeypatch.setattr(store_handler, "_resolve_code_repo_path", counting_resolve)
    # Force every call to be a cache miss.
    monkeypatch.setattr(store_handler, "_CODE_REPO_CACHE_TTL_SEC", 0.0)

    _code_repo_branch_for_store(str(store_path))
    _code_repo_branch_for_store(str(store_path))
    assert calls["resolve"] == 2

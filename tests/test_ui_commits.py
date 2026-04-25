"""
Tests for the rich commits endpoint annotation.

Verifies that ``BranchService.get_commits(annotate=True)`` populates
``tags`` and ``refs`` correctly from ``git show-ref`` output, without
regressing the un-annotated legacy path.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import pytest

from memoir.services.branch_service import BranchService
from memoir.services.store_service import StoreService
from memoir.ui.schemas import CommitsResponse


def _git(store: str, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=store,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


@pytest.fixture
def annotated_store():
    """Store with an explicit commit graph: initial → middle (tagged) → head.

    ``StoreService.create_store`` does not auto-commit, so the fixture lays
    down three explicit empty commits itself. That gives deterministic
    positions to assert about.
    """
    path = tempfile.mkdtemp(prefix="memoir_commits_test_")
    try:
        StoreService(path).create_store(path)
        _git(path, "commit", "--allow-empty", "-m", "initial")
        _git(path, "commit", "--allow-empty", "-m", "middle")
        _git(path, "tag", "v1.0")
        _git(path, "commit", "--allow-empty", "-m", "head")
        _git(path, "branch", "experiment")
        yield path
    finally:
        if os.path.exists(path):
            shutil.rmtree(path)


def test_legacy_get_commits_omits_annotations(annotated_store):
    """annotate=False (default) → no git show-ref call; tags/refs stay empty."""
    service = BranchService(annotated_store)
    commits = service.get_commits("HEAD", limit=10)
    assert len(commits) == 3
    for c in commits:
        assert c.tags == []
        assert c.refs == []


def test_annotated_commits_carry_tags_and_refs(annotated_store):
    service = BranchService(annotated_store)
    commits = service.get_commits("HEAD", limit=10, annotate=True)

    assert [c.message for c in commits] == ["head", "middle", "initial"]

    head, middle, initial = commits

    # HEAD: both branches point here (main + experiment was branched from head)
    assert set(head.refs) == {"main", "experiment"}
    assert head.tags == []

    # Middle commit carries the v1.0 tag
    assert middle.tags == ["v1.0"]
    assert middle.refs == []

    # Initial commit has no refs or tags pointing at it
    assert initial.tags == []
    assert initial.refs == []


def test_annotated_commits_round_trip_through_schema(annotated_store):
    """Handler-level: ``to_dict()`` → Pydantic validate → ``model_dump`` stable."""
    service = BranchService(annotated_store)
    commits = service.get_commits("HEAD", limit=10, annotate=True)

    body = CommitsResponse.model_validate(
        {
            "success": True,
            "commits": [c.to_dict() for c in commits],
            "branch": "HEAD",
        }
    )
    dumped = body.model_dump(mode="json")
    # Every commit in the dumped payload must have `tags` and `refs`
    # (possibly empty) as real arrays, not missing keys.
    for c in dumped["commits"]:
        assert isinstance(c["tags"], list)
        assert isinstance(c["refs"], list)

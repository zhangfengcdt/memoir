"""
Schema-drift tests for memoir UI response models.

These tests answer one question: **does the data the service layer
actually produces match the Pydantic model the UI handler will ship?**

The models in ``memoir.ui.schemas`` are validated against real
``BranchService`` / ``StoreService`` output. If a service field gets
renamed, added, or removed, Pydantic raises here — well before a
browser sees a 500.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from pydantic import ValidationError

from memoir.services.branch_service import BranchService
from memoir.services.store_service import StoreService
from memoir.ui.schemas import (
    BranchesResponse,
    CommitsResponse,
    CurrentBranchResponse,
    StoreResponse,
)


@pytest.fixture
def temp_store():
    """A fresh memoir store on disk."""
    path = tempfile.mkdtemp(prefix="memoir_schema_test_")
    try:
        StoreService(path).create_store(path)
        yield path
    finally:
        if os.path.exists(path):
            shutil.rmtree(path)


def test_branches_response_matches_service(temp_store):
    info = BranchService(temp_store).list_branches()

    body = BranchesResponse(
        success=True,
        branches=info.branches,
        current=info.current,
    )

    # Round-trip: model → dict → model → dict must be stable
    assert body.model_dump() == BranchesResponse(**body.model_dump()).model_dump()
    dumped = body.model_dump(mode="json")
    assert dumped["success"] is True
    assert isinstance(dumped["branches"], list)
    assert isinstance(dumped["current"], str)


def test_current_branch_response_matches_service(temp_store):
    branch, commit = BranchService(temp_store).get_current_branch()

    body = CurrentBranchResponse(success=True, branch=branch, commit=commit)

    dumped = body.model_dump(mode="json")
    assert dumped["branch"] == branch
    assert dumped["commit"] == commit


def test_commits_response_matches_service(temp_store):
    commits = BranchService(temp_store).get_commits("HEAD", limit=5)

    body = CommitsResponse.model_validate(
        {
            "success": True,
            "commits": [c.to_dict() for c in commits],
            "branch": "HEAD",
        }
    )

    # Every commit field declared in the schema must exist in the service
    # output (otherwise model_validate would have raised).
    for c in body.commits:
        assert c.hash
        assert len(c.hash) >= 7
        assert c.short_hash
        assert c.message
        assert c.author
        assert c.email
        assert isinstance(c.timestamp, int)


def test_store_response_matches_service(temp_store):
    data = StoreService(temp_store).read_store()

    # This is the real drift guard — if read_store() starts returning a
    # dict that's missing ``store_path`` or changes ``branches`` from
    # list[str] to list[dict], Pydantic will raise.
    body = StoreResponse.model_validate(data)

    # On macOS the tmp path is symlinked (/var → /private/var), so compare
    # by real paths rather than strings.
    assert os.path.realpath(body.store_path) == os.path.realpath(temp_store)
    assert isinstance(body.branches, list)
    assert isinstance(body.current_branch, str)
    assert body.total_memories == 0  # freshly created store
    # Legacy extras (``memories``, ``tree``) are preserved via extra='allow'.
    dumped = body.model_dump(mode="json")
    assert "store_path" in dumped


def test_store_response_with_memories_validates(temp_store):
    """Populated store drift guard.

    Insert memories with dotted taxonomy paths (the format the UI tree
    view depends on), run the reader, and make sure the Pydantic schema
    accepts the resulting payload. Catches changes in the reader that
    would otherwise surface as runtime JSON errors in the browser.
    """
    import json as _json

    from memoir.store.prolly_adapter import ProllyTreeStore

    store = ProllyTreeStore(
        path=temp_store,
        enable_versioning=True,
        auto_commit=True,
        cache_size=1000,
    )
    samples = [
        ("default:workflow.coding.style", "prefer async-first"),
        ("default:workflow.coding.naming", "snake_case for Python"),
        ("codebase:onboard:structure.cli", "Click-based CLI"),
    ]
    for key, content in samples:
        store.tree.insert(
            key.encode("utf-8"),
            _json.dumps({"content": content}).encode("utf-8"),
        )

    data = StoreService(temp_store).read_store()
    body = StoreResponse.model_validate(data)

    assert body.total_memories >= len(samples)
    paths = {m.path for m in body.memories}
    assert "workflow.coding.style" in paths
    assert "structure.cli" in paths
    # Namespaces must be preserved verbatim (the v2 tree splits on them).
    namespaces = {m.namespace for m in body.memories}
    assert "default" in namespaces
    assert "codebase:onboard" in namespaces


def test_branches_response_rejects_extra_fields():
    """Schema drift guard: ``extra='forbid'`` catches unexpected keys."""
    with pytest.raises(ValidationError, match="unexpected_field"):
        BranchesResponse.model_validate(
            {
                "success": True,
                "branches": ["main"],
                "current": "main",
                "unexpected_field": "oops",
            }
        )

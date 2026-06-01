# SPDX-License-Identifier: Apache-2.0
"""
Tests for the public ``memoir.sdk`` surface.

The SDK is the documented entry point (``from memoir.sdk import MemoryClient``)
but was previously exercised by no test, so an import-time regression (issue
#128: a ``list`` method shadowing the builtin in an eagerly-evaluated
annotation) went unnoticed. These tests pin both the import surface and the
delegating behavior of ``MemoryClient`` / ``BranchManager``.
"""

import os
import shutil
import tempfile
import typing

import pytest


class TestSdkImports:
    """Regression tests for issue #128 and the advertised import surface."""

    def test_import_memory_client(self):
        """The documented entry point must import without error."""
        from memoir.sdk import MemoryClient

        assert MemoryClient is not None

    def test_import_branch_manager(self):
        """BranchManager is exported and must import without error."""
        from memoir.sdk import BranchManager

        assert BranchManager is not None

    def test_all_exported_symbols_are_importable(self):
        """Every name in ``__all__`` must be importable from the package."""
        import memoir.sdk as sdk

        for name in sdk.__all__:
            assert hasattr(sdk, name), f"{name} listed in __all__ but missing"

    def test_branch_manager_commits_annotation_resolves_to_builtin_list(self):
        """``commits`` return annotation must resolve to the builtin ``list``.

        This is the root cause of #128: a ``list`` *method* on the class
        shadowed the builtin when the ``-> list[CommitInfo]`` annotation was
        evaluated. ``get_type_hints`` forces resolution and would resolve to
        the method (not the builtin) if the shadowing regressed. ``CommitInfo``
        is imported only under ``TYPE_CHECKING`` in the module, so it is passed
        in explicitly for resolution.
        """
        from memoir.sdk.client import BranchManager
        from memoir.services.models import CommitInfo

        hints = typing.get_type_hints(
            BranchManager.commits, localns={"CommitInfo": CommitInfo}
        )
        assert typing.get_origin(hints["return"]) is list


@pytest.fixture
def temp_dir():
    """Create a temporary directory for a store."""
    temp = tempfile.mkdtemp(prefix="memoir_sdk_test_")
    yield temp
    if os.path.exists(temp):
        shutil.rmtree(temp)


@pytest.fixture
def store_path(temp_dir):
    """Create an initialized store and return its path."""
    from memoir.services.store_service import StoreService

    store_service = StoreService(temp_dir)
    store_service.create_store(temp_dir)
    return temp_dir


@pytest.fixture
def client(store_path):
    """Create a MemoryClient pointed at an initialized store."""
    from memoir.sdk import MemoryClient

    return MemoryClient(store_path)


class TestMemoryClientConstruction:
    """Construction, properties, and context-manager behavior."""

    def test_store_path_is_resolved(self, store_path):
        from pathlib import Path

        from memoir.sdk import MemoryClient

        client = MemoryClient(store_path)
        assert client.store_path == str(Path(store_path).resolve())

    def test_accepts_path_object(self, store_path):
        from pathlib import Path

        from memoir.sdk import MemoryClient

        client = MemoryClient(Path(store_path))
        assert client.store_path == str(Path(store_path).resolve())

    def test_sync_context_manager_returns_self(self, client):
        with client as ctx:
            assert ctx is client

    @pytest.mark.asyncio
    async def test_async_context_manager_returns_self(self, client):
        async with client as ctx:
            assert ctx is client

    def test_branch_property_returns_branch_manager(self, client):
        from memoir.sdk import BranchManager

        assert isinstance(client.branch, BranchManager)

    def test_branch_property_is_cached(self, client):
        assert client.branch is client.branch


class TestBranchManager:
    """BranchManager delegates to BranchService over a real store."""

    def test_list_returns_branch_info(self, client):
        result = client.branch.list()

        assert hasattr(result, "branches")
        assert hasattr(result, "current")
        assert isinstance(result.branches, list)

    def test_current_returns_tuple(self, client):
        branch, commit = client.branch.current()

        assert isinstance(branch, str)
        assert commit is None or isinstance(commit, str)

    def test_commits_returns_list(self, client):
        result = client.branch.commits()

        assert isinstance(result, list)


class TestMemoryClientOperations:
    """remember / recall / forget / status against a real store."""

    @pytest.mark.asyncio
    async def test_recall_empty_store(self, client):
        result = await client.recall("anything")

        assert hasattr(result, "memories")
        assert isinstance(result.memories, list)
        assert result.memories == []

    def test_recall_sync(self, client):
        result = client.recall_sync("anything")

        assert hasattr(result, "memories")
        assert isinstance(result.memories, list)

    def test_status_returns_dict(self, client):
        status = client.status()

        assert isinstance(status, dict)

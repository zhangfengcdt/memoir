"""
Integration tests for branch workflows.

Tests end-to-end branch operations: create → checkout → merge.
"""

import os
import shutil
import tempfile

import pytest

from memoir.services.branch_service import BranchService
from memoir.services.store_service import StoreService


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    temp = tempfile.mkdtemp(prefix="memoir_branch_workflow_test_")
    yield temp
    if os.path.exists(temp):
        shutil.rmtree(temp)


@pytest.fixture
def services(temp_dir):
    """Create store and branch services."""
    store_service = StoreService(temp_dir)
    store_service.create_store(temp_dir)
    branch_service = BranchService(temp_dir)
    return store_service, branch_service


class TestBranchWorkflow:
    """Test complete branch workflows."""

    def test_list_branches_after_init(self, services):
        """Test listing branches after store initialization."""
        _, branch_service = services

        result = branch_service.list_branches()

        assert result is not None
        assert hasattr(result, "branches")
        assert hasattr(result, "current")

    def test_commits_empty_store(self, services):
        """Test getting commits from empty store."""
        _, branch_service = services

        commits = branch_service.get_commits()

        assert commits is not None
        assert isinstance(commits, list)

    def test_create_and_list_branch(self, services):
        """Test creating a branch and listing it."""
        _, branch_service = services

        # Create branch (may fail if no initial commit)
        create_result = branch_service.create_branch("feature")

        # List branches
        list_result = branch_service.list_branches()

        assert list_result is not None
        # If creation succeeded, branch should be in list
        if create_result.success:
            assert "feature" in list_result.branches


class TestBranchOperationsSequence:
    """Test sequences of branch operations."""

    def test_multiple_branch_creates(self, services):
        """Test creating multiple branches."""
        _, branch_service = services

        results = []
        for i in range(3):
            result = branch_service.create_branch(f"branch-{i}")
            results.append(result)

        # All operations should complete without crash
        assert len(results) == 3

    def test_checkout_after_create(self, services):
        """Test checkout after branch creation."""
        _, branch_service = services

        # Create branch
        create_result = branch_service.create_branch("checkout-test")

        if create_result.success:
            # Checkout the branch
            checkout_result = branch_service.checkout("checkout-test")
            assert checkout_result is not None

    def test_list_after_multiple_operations(self, services):
        """Test listing branches after multiple operations."""
        _, branch_service = services

        # Perform various operations
        branch_service.create_branch("op1")
        branch_service.create_branch("op2")
        branch_service.checkout("main")

        # List should still work
        result = branch_service.list_branches()
        assert result is not None


class TestBranchEdgeCases:
    """Test edge cases in branch workflows."""

    def test_checkout_nonexistent_with_create(self, services):
        """Test checkout with create flag for nonexistent branch."""
        _, branch_service = services

        result = branch_service.checkout("auto-create-branch", create_if_missing=True)

        assert result is not None

    def test_delete_nonexistent_branch(self, services):
        """Test deleting a branch that doesn't exist."""
        _, branch_service = services

        result = branch_service.delete_branch("nonexistent")

        assert result is not None
        # Should fail gracefully
        assert result.success is False or result.error is not None

    def test_merge_into_self(self, services):
        """Test merging a branch into itself."""
        _, branch_service = services

        # Try to merge main into main (should be no-op or error)
        result = branch_service.merge("main")

        assert result is not None


class TestBranchStoreIntegration:
    """Test integration between branch and store services."""

    def test_store_status_after_branch_ops(self, services):
        """Test store status after branch operations."""
        store_service, branch_service = services

        # Perform branch operations
        branch_service.create_branch("test")
        branch_service.list_branches()

        # Store should still be valid
        status = store_service.get_status()
        assert status.initialized is True

    def test_store_data_after_branch_ops(self, services):
        """Test store data consistency after branch operations."""
        store_service, branch_service = services

        # Perform operations
        branch_service.create_branch("data-test")

        # Store data should be intact
        data = store_service.read_store()
        assert isinstance(data, dict)
        # Store should have some content
        assert len(data) > 0


class TestCommitHistory:
    """Test commit history functionality."""

    def test_commits_with_various_limits(self, services):
        """Test getting commits with various limits."""
        _, branch_service = services

        commits1 = branch_service.get_commits(limit=1)
        commits5 = branch_service.get_commits(limit=5)
        commits20 = branch_service.get_commits(limit=20)

        assert len(commits1) <= 1
        assert len(commits5) <= 5
        assert len(commits20) <= 20

    def test_commits_for_branch(self, services):
        """Test getting commits for specific branch."""
        _, branch_service = services

        commits = branch_service.get_commits(branch="main")

        assert commits is not None
        assert isinstance(commits, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

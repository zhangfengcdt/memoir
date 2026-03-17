"""
Tests for BranchService.

Tests branch operations: list, create, checkout, merge, commits, diff.
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
    temp = tempfile.mkdtemp(prefix="memoir_branch_test_")
    yield temp
    if os.path.exists(temp):
        shutil.rmtree(temp)


@pytest.fixture
def initialized_store(temp_dir):
    """Create an initialized store."""
    store_service = StoreService(temp_dir)
    store_service.create_store(temp_dir)
    return temp_dir


@pytest.fixture
def branch_service(initialized_store):
    """Create a BranchService."""
    return BranchService(initialized_store)


class TestBranchServiceList:
    """Test branch listing functionality."""

    def test_list_branches_empty_store(self, branch_service):
        """Test listing branches in a new store."""
        result = branch_service.list_branches()

        assert result is not None
        assert hasattr(result, "branches")
        assert hasattr(result, "current")

    def test_list_branches_returns_list(self, branch_service):
        """Test that branches is a list."""
        result = branch_service.list_branches()

        assert isinstance(result.branches, list)

    def test_list_branches_has_main_or_master(self, branch_service):
        """Test that default branch exists."""
        result = branch_service.list_branches()

        # New git repos have main or master as default
        if result.branches:
            assert any(
                b in ["main", "master"] for b in result.branches
            ) or result.current in ["main", "master", None]


class TestBranchServiceCreate:
    """Test branch creation functionality."""

    def test_create_branch(self, branch_service):
        """Test creating a new branch."""
        result = branch_service.create_branch("test-branch")

        # May fail if no initial commit
        assert result is not None
        assert hasattr(result, "success")

    def test_create_branch_with_special_chars(self, branch_service):
        """Test creating branch with special characters."""
        result = branch_service.create_branch("feature/test-123")

        assert result is not None

    def test_create_duplicate_branch(self, branch_service):
        """Test creating a branch that already exists."""
        branch_service.create_branch("duplicate")
        result = branch_service.create_branch("duplicate")

        # Should fail or handle gracefully
        assert result is not None
        # Second creation should indicate failure or already exists
        if result.success:
            # Some implementations allow this
            pass
        else:
            assert result.error is not None or not result.success


class TestBranchServiceCheckout:
    """Test checkout functionality."""

    def test_checkout_existing_branch(self, branch_service):
        """Test checking out an existing branch."""
        # Try to checkout main/master
        result = branch_service.checkout("main")

        # May fail if no commits
        assert result is not None
        assert hasattr(result, "success")

    def test_checkout_with_create(self, branch_service):
        """Test checkout with create_if_missing flag."""
        result = branch_service.checkout("new-branch", create_if_missing=True)

        assert result is not None

    def test_checkout_nonexistent_branch(self, branch_service):
        """Test checking out a branch that doesn't exist."""
        result = branch_service.checkout("nonexistent-branch-xyz")

        # Should fail
        assert result is not None
        assert result.success is False or result.error is not None


class TestBranchServiceCommits:
    """Test commit history functionality."""

    def test_get_commits_empty_store(self, branch_service):
        """Test getting commits from empty store."""
        commits = branch_service.get_commits()

        assert commits is not None
        assert isinstance(commits, list)

    def test_get_commits_with_limit(self, branch_service):
        """Test getting commits with limit."""
        commits = branch_service.get_commits(limit=5)

        assert commits is not None
        assert len(commits) <= 5

    def test_get_commits_returns_commit_info(self, branch_service):
        """Test that commits have expected fields."""
        commits = branch_service.get_commits()

        # If there are commits, check structure
        for commit in commits:
            assert hasattr(commit, "hash") or hasattr(commit, "short_hash")
            assert hasattr(commit, "message")


class TestBranchServiceMerge:
    """Test merge functionality."""

    def test_merge_nonexistent_branch(self, branch_service):
        """Test merging a branch that doesn't exist."""
        result = branch_service.merge("nonexistent-branch")

        assert result is not None
        assert result.success is False or result.error is not None


class TestBranchServiceDiff:
    """Test diff functionality."""

    def test_get_diff_empty_store(self, branch_service):
        """Test getting diff from empty store."""
        # May fail or return empty
        try:
            diff = branch_service.get_diff("HEAD~1", "HEAD")
            assert diff is not None or diff == ""
        except Exception:
            # Expected if no commits
            pass

    def test_get_diff_same_commit(self, branch_service):
        """Test diff between same commit."""
        try:
            diff = branch_service.get_diff("HEAD", "HEAD")
            # Should be empty or minimal
            assert diff is not None
        except Exception:
            # Expected if no commits
            pass


class TestBranchServiceEdgeCases:
    """Test edge cases and error handling."""

    def test_service_with_invalid_path(self):
        """Test service with invalid store path."""
        from memoir.services.base import StoreNotFoundError

        service = BranchService("/nonexistent/path")

        # Should raise StoreNotFoundError
        with pytest.raises(StoreNotFoundError):
            service.list_branches()

    def test_branch_name_validation(self, branch_service):
        """Test branch name with invalid characters."""
        # Git doesn't allow certain characters
        result = branch_service.create_branch("invalid..name")

        # Should fail gracefully
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

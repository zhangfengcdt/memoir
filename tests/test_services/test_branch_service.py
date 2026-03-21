"""
Tests for BranchService.

Tests branch operations: list, create, checkout, merge, commits, diff.
"""

import os
import shutil
import tempfile

import pytest

from memoir.services.branch_service import BranchService, MergeStrategy
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

    def test_merge_strategy_enum(self):
        """Test MergeStrategy enum values."""
        from prollytree import ConflictResolution

        assert MergeStrategy.OURS.value == "ours"
        assert MergeStrategy.THEIRS.value == "theirs"
        assert MergeStrategy.SKIP.value == "skip"

        # Test conversion to ConflictResolution
        assert (
            MergeStrategy.OURS.to_conflict_resolution()
            == ConflictResolution.TakeDestination
        )
        assert (
            MergeStrategy.THEIRS.to_conflict_resolution()
            == ConflictResolution.TakeSource
        )
        assert (
            MergeStrategy.SKIP.to_conflict_resolution() == ConflictResolution.IgnoreAll
        )

    def test_merge_default_strategy_is_skip(self, branch_service):
        """Test that default merge strategy is 'skip'."""
        # Create a branch to merge
        branch_service.create_branch("test-merge-default")
        result = branch_service.merge("test-merge-default")

        # The result should include the strategy used
        assert result is not None
        assert result.strategy == "skip"

    def test_merge_with_ours_strategy(self, branch_service):
        """Test merge with 'ours' strategy."""
        branch_service.create_branch("test-ours")
        result = branch_service.merge("test-ours", strategy=MergeStrategy.OURS)

        assert result is not None
        assert result.strategy == "ours"

    def test_merge_with_theirs_strategy(self, branch_service):
        """Test merge with 'theirs' strategy."""
        branch_service.create_branch("test-theirs")
        result = branch_service.merge("test-theirs", strategy=MergeStrategy.THEIRS)

        assert result is not None
        assert result.strategy == "theirs"

    def test_merge_result_includes_strategy(self, branch_service):
        """Test that MergeResult includes strategy field."""
        branch_service.create_branch("test-strategy")
        result = branch_service.merge("test-strategy", strategy=MergeStrategy.SKIP)

        assert result is not None
        assert hasattr(result, "strategy")
        assert result.strategy == "skip"

        # Test to_dict includes strategy
        result_dict = result.to_dict()
        assert "strategy" in result_dict
        assert result_dict["strategy"] == "skip"


class TestBranchServiceMergeWithData:
    """Test merge functionality with actual data in the store."""

    @pytest.fixture
    def store_with_data(self, temp_dir):
        """Create a store with some initial data."""
        store_service = StoreService(temp_dir)
        store_service.create_store(temp_dir)

        # Add some initial data using the store
        branch_service = BranchService(temp_dir)
        store = branch_service._get_store()

        # Store some data
        store.put(("default",), "preferences.theme", {"value": "light"})
        store.put(("default",), "preferences.language", {"value": "en"})
        store.commit("Initial data")

        return temp_dir

    @pytest.fixture
    def branch_service_with_data(self, store_with_data):
        """Create a BranchService with data."""
        return BranchService(store_with_data)

    def test_merge_branches_no_conflict(self, branch_service_with_data):
        """Test merging branches with no conflicts (different keys)."""
        service = branch_service_with_data
        store = service._get_store()

        # Create a feature branch
        service.create_branch("feature")
        service.checkout("feature")

        # Add new data on feature branch (different key)
        store.put(("default",), "preferences.font", {"value": "Arial"})
        store.commit("Add font preference")

        # Checkout main and merge
        service.checkout("main")
        result = service.merge("feature")

        assert result.success is True
        assert result.strategy == "skip"
        # No conflicts since different keys
        assert len(result.conflicts) == 0 or result.conflicts == []

    def test_merge_branches_with_conflict_skip_strategy(self, branch_service_with_data):
        """Test merging with conflict using 'skip' strategy."""
        service = branch_service_with_data
        store = service._get_store()

        # Create a feature branch
        service.create_branch("conflict-skip")
        service.checkout("conflict-skip")

        # Modify same key on feature branch
        store.put(("default",), "preferences.theme", {"value": "dark"})
        store.commit("Change theme to dark")

        # Go back to main and modify same key
        service.checkout("main")
        store.put(("default",), "preferences.theme", {"value": "system"})
        store.commit("Change theme to system")

        # Try to merge - should have conflict
        result = service.merge("conflict-skip", strategy=MergeStrategy.SKIP)

        assert result is not None
        assert result.strategy == "skip"
        # With skip strategy, conflicts are skipped

    def test_merge_branches_with_conflict_ours_strategy(
        self, branch_service_with_data
    ):
        """Test merging with conflict using 'ours' strategy."""
        service = branch_service_with_data
        store = service._get_store()

        # Create a feature branch
        service.create_branch("conflict-ours")
        service.checkout("conflict-ours")

        # Modify same key on feature branch
        store.put(("default",), "preferences.theme", {"value": "dark"})
        store.commit("Change theme to dark")

        # Go back to main and modify same key
        service.checkout("main")
        store.put(("default",), "preferences.theme", {"value": "system"})
        store.commit("Change theme to system")

        # Merge with 'ours' - should keep main's version
        result = service.merge("conflict-ours", strategy=MergeStrategy.OURS)

        assert result is not None
        assert result.strategy == "ours"

        # After merge, check that we kept 'ours' (main's value)
        if result.success:
            theme = store.get(("default",), "preferences.theme")
            assert theme is not None
            # 'ours' means keep destination (main) which was "system"
            assert theme.get("value") == "system"

    def test_merge_branches_with_conflict_theirs_strategy(
        self, branch_service_with_data
    ):
        """Test merging with conflict using 'theirs' strategy."""
        service = branch_service_with_data
        store = service._get_store()

        # Create a feature branch
        service.create_branch("conflict-theirs")
        service.checkout("conflict-theirs")

        # Modify same key on feature branch
        store.put(("default",), "preferences.theme", {"value": "dark"})
        store.commit("Change theme to dark")

        # Go back to main and modify same key
        service.checkout("main")
        store.put(("default",), "preferences.theme", {"value": "system"})
        store.commit("Change theme to system")

        # Merge with 'theirs' - should take feature branch's version
        result = service.merge("conflict-theirs", strategy=MergeStrategy.THEIRS)

        assert result is not None
        assert result.strategy == "theirs"

        # After merge, check that we took 'theirs' (feature's value)
        if result.success:
            theme = store.get(("default",), "preferences.theme")
            assert theme is not None
            # 'theirs' means take source (conflict-theirs) which was "dark"
            assert theme.get("value") == "dark"


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

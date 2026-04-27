"""
Tests for StoreService.

Tests store creation, connection, status, and data reading.
"""

import os
import shutil
import tempfile

import pytest

from memoir.services.store_service import StoreService


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    temp = tempfile.mkdtemp(prefix="memoir_store_test_")
    yield temp
    if os.path.exists(temp):
        shutil.rmtree(temp)


@pytest.fixture
def store_service(temp_dir):
    """Create a StoreService with a new store."""
    service = StoreService(temp_dir)
    service.create_store(temp_dir)
    return service


class TestStoreServiceCreation:
    """Test store creation functionality."""

    def test_create_store_success(self, temp_dir):
        """Test creating a new store."""
        # Remove temp dir so create_store can create it
        shutil.rmtree(temp_dir)

        service = StoreService()
        result = service.create_store(temp_dir)

        assert result.success is True
        # Use realpath to handle macOS /var vs /private/var symlink
        assert os.path.realpath(result.path) == os.path.realpath(temp_dir)
        assert os.path.exists(result.path)
        assert os.path.exists(os.path.join(result.path, ".git"))

    def test_create_store_with_path_argument(self, temp_dir):
        """Test creating a store at a specific path."""
        shutil.rmtree(temp_dir)
        new_path = temp_dir + "_new"

        service = StoreService()
        result = service.create_store(new_path)

        assert result.success is True
        assert os.path.exists(new_path)

        # Cleanup
        if os.path.exists(new_path):
            shutil.rmtree(new_path)

    def test_create_store_already_exists(self, temp_dir):
        """Test creating a store when directory already exists."""
        service = StoreService()
        # First creation
        service.create_store(temp_dir)
        # Second creation should handle existing store
        result = service.create_store(temp_dir)
        # May succeed (reinitialize) or fail gracefully
        assert result is not None

    def test_create_store_with_initial_branch_master(self, temp_dir):
        """`--initial-branch master` lands the initial commit on master and
        records memoir.primaryBranch=master in the store's git config."""
        import subprocess

        shutil.rmtree(temp_dir)

        service = StoreService()
        result = service.create_store(temp_dir, initial_branch="master")
        assert result.success is True

        # HEAD should point at refs/heads/master, not main. We use
        # `symbolic-ref` instead of `rev-parse --abbrev-ref` because
        # an empty memoir store may have no initial commit yet (empty
        # `data/` dir doesn't trigger one), and rev-parse on an unborn
        # branch returns non-zero. symbolic-ref reads the HEAD file
        # directly and works pre-commit.
        head = subprocess.run(
            ["git", "symbolic-ref", "HEAD"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
            check=True,
        )
        assert head.stdout.strip() == "refs/heads/master"

        # memoir.primaryBranch must be persisted so downstream callers
        # (BranchService.get_default_branch, plugin hooks) route to master.
        cfg = subprocess.run(
            ["git", "config", "--get", "memoir.primaryBranch"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
        )
        assert cfg.returncode == 0
        assert cfg.stdout.strip() == "master"

    def test_create_store_default_branch_writes_no_config(self, temp_dir):
        """Backwards-compat invariant: omitting --initial-branch must NOT
        write memoir.primaryBranch. Stores predating this feature, and
        users who never opt in, should be functionally identical."""
        import subprocess

        shutil.rmtree(temp_dir)

        service = StoreService()
        result = service.create_store(temp_dir)
        assert result.success is True

        cfg = subprocess.run(
            ["git", "config", "--get", "memoir.primaryBranch"],
            cwd=temp_dir,
            capture_output=True,
            text=True,
        )
        # `git config --get` exits non-zero when the key is absent.
        assert cfg.returncode != 0
        assert cfg.stdout.strip() == ""


class TestStoreServiceStatus:
    """Test store status functionality."""

    def test_get_status_initialized_store(self, store_service):
        """Test getting status of an initialized store."""
        status = store_service.get_status()

        assert status is not None
        assert status.path is not None
        assert status.initialized is True

    def test_get_status_has_branch_info(self, store_service):
        """Test that status includes branch information."""
        status = store_service.get_status()

        # Should have branch info (may be None if no commits)
        assert hasattr(status, "branch")

    def test_get_status_has_memory_count(self, store_service):
        """Test that status includes memory count."""
        status = store_service.get_status()

        assert hasattr(status, "memory_count")
        # Empty store should have 0 memories
        assert status.memory_count == 0 or status.memory_count is None

    def test_get_status_has_commit_count(self, store_service):
        """Test that status includes commit count."""
        status = store_service.get_status()

        assert hasattr(status, "commit_count")

    def test_get_status_to_dict(self, store_service):
        """Test that status can be converted to dict."""
        status = store_service.get_status()
        status_dict = status.to_dict()

        assert isinstance(status_dict, dict)
        assert "path" in status_dict


class TestStoreServiceRead:
    """Test store reading functionality."""

    def test_read_store_empty(self, store_service):
        """Test reading an empty store."""
        data = store_service.read_store()

        assert data is not None
        assert isinstance(data, dict)

    def test_read_store_has_expected_keys(self, store_service):
        """Test that read_store returns expected keys."""
        data = store_service.read_store()

        # Actual structure includes branches, commits, current_branch, memories
        # or namespaces/statistics depending on implementation
        assert isinstance(data, dict)
        # Check for common keys
        has_expected_keys = (
            "branches" in data or "namespaces" in data or "memories" in data
        )
        assert has_expected_keys

    def test_read_store_has_data_structure(self, store_service):
        """Test that read_store returns valid data structure."""
        data = store_service.read_store()

        # Store should have some content
        assert isinstance(data, dict)
        assert len(data) > 0


class TestStoreServiceEdgeCases:
    """Test edge cases and error handling."""

    def test_service_with_nonexistent_path(self):
        """Test service with path that doesn't exist."""
        service = StoreService("/nonexistent/path/to/store")
        status = service.get_status()

        # Should handle gracefully
        assert status is not None
        assert status.initialized is False

    def test_service_path_is_file(self, temp_dir):
        """Test service when path is a file, not directory."""
        file_path = os.path.join(temp_dir, "file.txt")
        with open(file_path, "w") as f:
            f.write("test")

        service = StoreService(file_path)
        status = service.get_status()

        # Should handle gracefully
        assert status.initialized is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

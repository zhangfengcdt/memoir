"""
Tests for StoreService.

Tests store creation, connection, status, and data reading.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

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

    def test_create_store_default_backend_is_file(self, temp_dir, monkeypatch):
        """Without an explicit backend or env var, new stores get File."""
        shutil.rmtree(temp_dir)
        monkeypatch.delenv("MEMOIR_PROLLY_BACKEND", raising=False)

        result = StoreService().create_store(temp_dir)
        assert result.success is True

        lock = Path(temp_dir) / ".git" / "memoir-backend"
        assert lock.exists()
        assert lock.read_text().strip() == "file"

    def test_create_store_with_backend_git(self, temp_dir):
        """Explicit backend='git' is honored and recorded in the lock."""
        shutil.rmtree(temp_dir)

        result = StoreService().create_store(temp_dir, backend="git")
        assert result.success is True

        lock = Path(temp_dir) / ".git" / "memoir-backend"
        assert lock.read_text().strip() == "git"

    def test_create_store_with_backend_file(self, temp_dir):
        """Explicit backend='file' is honored."""
        shutil.rmtree(temp_dir)

        result = StoreService().create_store(temp_dir, backend="file")
        assert result.success is True

        lock = Path(temp_dir) / ".git" / "memoir-backend"
        assert lock.read_text().strip() == "file"

    def test_create_store_env_var_overrides_default(self, temp_dir, monkeypatch):
        """MEMOIR_PROLLY_BACKEND=git forces Git when no explicit arg."""
        shutil.rmtree(temp_dir)
        monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "git")

        result = StoreService().create_store(temp_dir)
        assert result.success is True

        lock = Path(temp_dir) / ".git" / "memoir-backend"
        assert lock.read_text().strip() == "git"

    def test_create_store_honors_existing_lock_on_retry(self, temp_dir, monkeypatch):
        """Partial-create retry: an existing .git/memoir-backend lock must win
        over env/default when the caller didn't pass an explicit backend.
        Simulates: first create wrote the lock then failed before HEAD was
        established; user re-runs `memoir new` with different env."""
        shutil.rmtree(temp_dir)
        Path(temp_dir).mkdir()
        # Pre-existing partial state: .git/ with no HEAD, but lock pinned to git.
        subprocess.run(["git", "init", "--quiet"], cwd=temp_dir, check=True)
        (Path(temp_dir) / ".git" / "memoir-backend").write_text("git\n")

        # Env says "file" — but the lock should win on retry.
        monkeypatch.setenv("MEMOIR_PROLLY_BACKEND", "file")
        result = StoreService().create_store(temp_dir)
        assert result.success is True
        lock = Path(temp_dir) / ".git" / "memoir-backend"
        assert lock.read_text().strip() == "git"

    def test_get_status_non_memoir_git_repo_reports_not_initialized(self, tmp_path):
        """status on a non-memoir git repo (e.g. the cwd-fallback hitting a
        random source checkout) must report not-initialized — NOT silently
        construct a fresh memoir store inside it."""
        subprocess.run(["git", "init", "--quiet"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.email", "x@y"], check=True
        )
        subprocess.run(
            ["git", "-C", str(tmp_path), "config", "user.name", "x"], check=True
        )
        (tmp_path / "README.md").write_text("not memoir\n")
        subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
        subprocess.run(
            ["git", "-C", str(tmp_path), "commit", "-m", "init", "--quiet"], check=True
        )

        info = StoreService(str(tmp_path)).get_status()
        assert info.initialized is False
        # And nothing got materialized as a side effect.
        assert not (tmp_path / "data").exists()
        assert not (tmp_path / ".git" / "memoir-backend").exists()
        assert not (tmp_path / ".git" / "prolly").exists()

    def test_create_store_explicit_backend_overrides_existing_lock(self, temp_dir):
        """When user passes --backend explicitly, that wins over a stale lock —
        otherwise recovering from a wrong choice would be impossible."""
        shutil.rmtree(temp_dir)
        Path(temp_dir).mkdir()
        subprocess.run(["git", "init", "--quiet"], cwd=temp_dir, check=True)
        (Path(temp_dir) / ".git" / "memoir-backend").write_text("git\n")

        result = StoreService().create_store(temp_dir, backend="file")
        assert result.success is True
        lock = Path(temp_dir) / ".git" / "memoir-backend"
        assert lock.read_text().strip() == "file"

    def test_create_store_applies_gc_safety_configs(self, temp_dir):
        """New stores should have gc.auto=0 and gc.pruneExpire=never so dangling
        prollytree blobs survive automatic / default-config git gc."""
        shutil.rmtree(temp_dir)

        service = StoreService()
        result = service.create_store(temp_dir)
        assert result.success is True

        def _get(key: str) -> str:
            return subprocess.run(
                ["git", "-C", temp_dir, "config", "--get", key],
                capture_output=True,
                text=True,
            ).stdout.strip()

        assert _get("gc.auto") == "0"
        assert _get("gc.pruneExpire") == "never"

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

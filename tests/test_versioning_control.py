"""
Tests for the new versioning control functionality.

Tests the new auto_commit flag and batch commit capabilities:
- auto_commit parameter in ProllyTreeStore
- put_without_commit() and delete_without_commit() methods
- manual commit() method
- store_memory_without_commit() and store_commit() in memory manager
"""

import tempfile
from pathlib import Path

from memoir.store.prolly_adapter import ProllyTreeStore


class TestVersioningControl:
    """Test versioning control functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.test_namespace = ("test_user",)

    def test_auto_commit_default_behavior(self):
        """Test that auto_commit=True provides backward compatible behavior."""
        store = ProllyTreeStore(
            path=str(Path(self.temp_dir) / "auto_commit_test"),
            enable_versioning=True,
            auto_commit=True,  # Default behavior
        )

        # Store a value - should commit automatically
        store.put(self.test_namespace, "test_key", {"content": "test value"})

        # Verify the value was stored
        result = store.get(self.test_namespace, "test_key")
        assert result is not None
        assert result["content"] == "test value"

    def test_manual_commit_control(self):
        """Test manual commit control with auto_commit=False."""
        store = ProllyTreeStore(
            path=str(Path(self.temp_dir) / "manual_commit_test"),
            enable_versioning=True,
            auto_commit=False,  # Manual control
        )

        # Store values without committing
        store.put_without_commit(self.test_namespace, "key1", {"content": "value1"})
        store.put_without_commit(self.test_namespace, "key2", {"content": "value2"})

        # Verify values are stored (in working directory)
        result1 = store.get(self.test_namespace, "key1")
        result2 = store.get(self.test_namespace, "key2")
        assert result1["content"] == "value1"
        assert result2["content"] == "value2"

        # Manually commit the batch
        commit_hash = store.commit("Test batch commit")
        assert commit_hash is not None

    def test_put_without_commit_method(self):
        """Test put_without_commit() method specifically."""
        store = ProllyTreeStore(
            path=str(Path(self.temp_dir) / "put_without_commit_test"),
            enable_versioning=True,
            auto_commit=False,
        )

        # Use put_without_commit directly
        store.put_without_commit(
            self.test_namespace, "batch_key", {"content": "batch value", "batch_id": 1}
        )

        # Verify data is accessible
        result = store.get(self.test_namespace, "batch_key")
        assert result["content"] == "batch value"
        assert result["batch_id"] == 1

        # Commit manually
        commit_hash = store.commit("Manual commit test")
        assert commit_hash is not None

    def test_delete_without_commit_method(self):
        """Test delete_without_commit() method."""
        store = ProllyTreeStore(
            path=str(Path(self.temp_dir) / "delete_without_commit_test"),
            enable_versioning=True,
            auto_commit=False,
        )

        # Store and commit a value first
        store.put_without_commit(
            self.test_namespace, "temp_key", {"content": "temp value"}
        )
        store.commit("Initial value")

        # Verify it exists
        assert store.get(self.test_namespace, "temp_key") is not None

        # Delete without committing
        store.delete_without_commit(self.test_namespace, "temp_key")

        # Verify it's gone from working directory
        assert store.get(self.test_namespace, "temp_key") is None

        # Commit the deletion
        commit_hash = store.commit("Deleted temp_key")
        assert commit_hash is not None

    def test_mixed_auto_commit_workflow(self):
        """Test dynamically toggling auto_commit."""
        store = ProllyTreeStore(
            path=str(Path(self.temp_dir) / "mixed_workflow_test"),
            enable_versioning=True,
            auto_commit=True,  # Start with auto-commit
        )

        # Store something with auto-commit
        store.put(self.test_namespace, "immediate", {"content": "immediate value"})

        # Switch to manual mode
        store.auto_commit = False

        # Store batch without committing
        store.put(self.test_namespace, "batch1", {"content": "batch value 1"})
        store.put(self.test_namespace, "batch2", {"content": "batch value 2"})

        # Verify all values are accessible
        assert (
            store.get(self.test_namespace, "immediate")["content"] == "immediate value"
        )
        assert store.get(self.test_namespace, "batch1")["content"] == "batch value 1"
        assert store.get(self.test_namespace, "batch2")["content"] == "batch value 2"

        # Commit the batch
        commit_hash = store.commit("Batch commit in mixed workflow")
        assert commit_hash is not None

        # Re-enable auto-commit
        store.auto_commit = True

        # Store another value (should auto-commit)
        store.put(self.test_namespace, "final", {"content": "final value"})

        # Verify final value is stored
        assert store.get(self.test_namespace, "final")["content"] == "final value"

    def test_commit_without_versioning(self):
        """Test that commit() handles non-versioned stores gracefully."""
        store = ProllyTreeStore(
            path=str(Path(self.temp_dir) / "no_versioning_test"),
            enable_versioning=False,  # No versioning
            auto_commit=False,
        )

        # Store a value
        store.put(self.test_namespace, "test_key", {"content": "test value"})

        # Try to commit (should return None and log warning)
        commit_hash = store.commit("Should not commit")
        assert commit_hash is None

        # Value should still be accessible
        result = store.get(self.test_namespace, "test_key")
        assert result["content"] == "test value"

    def test_backward_compatibility(self):
        """Test that existing code continues to work unchanged."""
        # Old style initialization (should work exactly as before)
        store = ProllyTreeStore(
            path=str(Path(self.temp_dir) / "backward_compat_test"),
            enable_versioning=True,
            # auto_commit defaults to True
        )

        # Old style usage (should auto-commit as before)
        store.put(self.test_namespace, "old_style", {"content": "old style value"})

        # Should work exactly as before
        result = store.get(self.test_namespace, "old_style")
        assert result["content"] == "old style value"

    def test_batch_performance_benefit(self):
        """Test that batching reduces the number of commits."""
        import time

        # Test auto-commit (many commits)
        auto_store = ProllyTreeStore(
            path=str(Path(self.temp_dir) / "auto_perf_test"),
            enable_versioning=True,
            auto_commit=True,
        )

        # Test manual commit (few commits)
        manual_store = ProllyTreeStore(
            path=str(Path(self.temp_dir) / "manual_perf_test"),
            enable_versioning=True,
            auto_commit=False,
        )

        # Store multiple values with auto-commit
        start_time = time.time()
        for i in range(5):
            auto_store.put(
                self.test_namespace, f"auto_key_{i}", {"content": f"auto value {i}"}
            )
        auto_time = time.time() - start_time

        # Store multiple values with batch commit
        start_time = time.time()
        for i in range(5):
            manual_store.put_without_commit(
                self.test_namespace, f"manual_key_{i}", {"content": f"manual value {i}"}
            )
        manual_store.commit("Batch of 5 values")
        manual_time = time.time() - start_time

        # Verify all values are stored correctly
        for i in range(5):
            auto_result = auto_store.get(self.test_namespace, f"auto_key_{i}")
            manual_result = manual_store.get(self.test_namespace, f"manual_key_{i}")
            assert auto_result["content"] == f"auto value {i}"
            assert manual_result["content"] == f"manual value {i}"

        # Note: We can't easily test commit count without more complex git inspection,
        # but the time comparison shows the batch approach can be faster
        print(f"Auto-commit time: {auto_time:.4f}s")
        print(f"Batch commit time: {manual_time:.4f}s")


if __name__ == "__main__":
    # Run tests manually
    test = TestVersioningControl()

    tests = [
        test.test_auto_commit_default_behavior,
        test.test_manual_commit_control,
        test.test_put_without_commit_method,
        test.test_delete_without_commit_method,
        test.test_mixed_auto_commit_workflow,
        test.test_commit_without_versioning,
        test.test_backward_compatibility,
        test.test_batch_performance_benefit,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test.setup_method()
            test_func()
            print(f"✅ {test_func.__name__}")
            passed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")

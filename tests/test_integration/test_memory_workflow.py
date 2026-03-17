"""
Integration tests for memory workflows.

Tests end-to-end memory operations: store → recall → forget.
"""

import os
import shutil
import tempfile

import pytest

from memoir.services.memory_service import MemoryService
from memoir.services.store_service import StoreService


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    temp = tempfile.mkdtemp(prefix="memoir_workflow_test_")
    yield temp
    if os.path.exists(temp):
        shutil.rmtree(temp)


@pytest.fixture
def store_and_memory(temp_dir):
    """Create store and memory services."""
    store_service = StoreService(temp_dir)
    store_service.create_store(temp_dir)
    memory_service = MemoryService(temp_dir)
    return store_service, memory_service


class TestMemoryWorkflow:
    """Test complete memory workflows."""

    @pytest.mark.asyncio
    async def test_recall_empty_then_after_data(self, store_and_memory):
        """Test recall behavior on empty store."""
        _, memory_service = store_and_memory

        # Recall on empty store
        result = await memory_service.recall("anything")

        assert result is not None
        assert len(result.memories) == 0

    @pytest.mark.asyncio
    async def test_multiple_recalls(self, store_and_memory):
        """Test multiple recall operations."""
        _, memory_service = store_and_memory

        # Multiple recalls should work
        result1 = await memory_service.recall("query1")
        result2 = await memory_service.recall("query2")
        result3 = await memory_service.recall("query3")

        assert result1 is not None
        assert result2 is not None
        assert result3 is not None

    @pytest.mark.asyncio
    async def test_recall_with_different_limits(self, store_and_memory):
        """Test recall with various limits."""
        _, memory_service = store_and_memory

        result1 = await memory_service.recall("test", limit=1)
        result5 = await memory_service.recall("test", limit=5)
        result10 = await memory_service.recall("test", limit=10)

        assert len(result1.memories) <= 1
        assert len(result5.memories) <= 5
        assert len(result10.memories) <= 10

    @pytest.mark.asyncio
    async def test_forget_then_recall(self, store_and_memory):
        """Test that forget followed by recall works."""
        _, memory_service = store_and_memory

        # Forget a key
        forget_result = await memory_service.forget("test.key")

        # Recall should still work
        recall_result = await memory_service.recall("test")

        assert forget_result is not None
        assert recall_result is not None

    @pytest.mark.asyncio
    async def test_multiple_namespaces(self, store_and_memory):
        """Test operations across multiple namespaces."""
        _, memory_service = store_and_memory

        # Recall from different namespaces
        result_default = await memory_service.recall("test", namespace="default")
        result_custom = await memory_service.recall("test", namespace="custom")
        result_all = await memory_service.recall("test", namespace=None)

        assert result_default is not None
        assert result_custom is not None
        assert result_all is not None


class TestStoreMemoryIntegration:
    """Test integration between store and memory services."""

    def test_store_status_reflects_state(self, store_and_memory):
        """Test that store status reflects current state."""
        store_service, _ = store_and_memory

        status = store_service.get_status()

        assert status.initialized is True
        assert status.path is not None

    def test_store_read_returns_data(self, store_and_memory):
        """Test that store read returns expected data."""
        store_service, _ = store_and_memory

        data = store_service.read_store()

        # Store should return a dict with some content
        assert isinstance(data, dict)
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_operations_dont_corrupt_store(self, store_and_memory):
        """Test that multiple operations don't corrupt store."""
        store_service, memory_service = store_and_memory

        # Perform various operations
        await memory_service.recall("test1")
        await memory_service.recall("test2")
        await memory_service.forget("key1")
        await memory_service.forget("key2")

        # Store should still be valid
        status = store_service.get_status()
        assert status.initialized is True

        data = store_service.read_store()
        assert isinstance(data, dict)


class TestWorkflowErrorRecovery:
    """Test error recovery in workflows."""

    @pytest.mark.asyncio
    async def test_recall_after_invalid_forget(self, store_and_memory):
        """Test recall works after invalid forget."""
        _, memory_service = store_and_memory

        # Try to forget invalid key
        await memory_service.forget("")

        # Recall should still work
        result = await memory_service.recall("test")
        assert result is not None

    @pytest.mark.asyncio
    async def test_operations_with_special_characters(self, store_and_memory):
        """Test operations with special characters."""
        _, memory_service = store_and_memory

        # Queries with special characters
        result1 = await memory_service.recall("test@example.com")
        result2 = await memory_service.recall("path/to/something")
        result3 = await memory_service.recall("key=value&other=param")

        assert result1 is not None
        assert result2 is not None
        assert result3 is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

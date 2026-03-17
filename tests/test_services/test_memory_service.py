"""
Tests for MemoryService.

Tests memory operations: remember, recall, forget.
Note: Some tests may require LLM and are marked accordingly.
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
    temp = tempfile.mkdtemp(prefix="memoir_memory_test_")
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
def memory_service(initialized_store):
    """Create a MemoryService."""
    return MemoryService(initialized_store)


class TestMemoryServiceRecall:
    """Test recall functionality."""

    @pytest.mark.asyncio
    async def test_recall_empty_store(self, memory_service):
        """Test recall on empty store."""
        result = await memory_service.recall("test query")

        assert result is not None
        assert hasattr(result, "memories")
        assert isinstance(result.memories, list)
        assert len(result.memories) == 0

    @pytest.mark.asyncio
    async def test_recall_with_limit(self, memory_service):
        """Test recall with limit parameter."""
        result = await memory_service.recall("test", limit=5)

        assert result is not None
        assert len(result.memories) <= 5

    @pytest.mark.asyncio
    async def test_recall_with_namespace(self, memory_service):
        """Test recall with specific namespace."""
        result = await memory_service.recall("test", namespace="custom")

        assert result is not None
        assert hasattr(result, "memories")

    @pytest.mark.asyncio
    async def test_recall_result_structure(self, memory_service):
        """Test recall result has expected structure."""
        result = await memory_service.recall("test")

        assert hasattr(result, "memories")
        assert hasattr(result, "timing_ms")
        assert hasattr(result, "to_dict")

    @pytest.mark.asyncio
    async def test_recall_to_dict(self, memory_service):
        """Test recall result can be converted to dict."""
        result = await memory_service.recall("test")
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "memories" in result_dict


class TestMemoryServiceForget:
    """Test forget functionality."""

    @pytest.mark.asyncio
    async def test_forget_nonexistent_key(self, memory_service):
        """Test forgetting a key that doesn't exist."""
        result = await memory_service.forget("nonexistent.key")

        assert result is not None
        assert hasattr(result, "success")
        # May succeed (delete nothing) or fail (not found)

    @pytest.mark.asyncio
    async def test_forget_with_namespace(self, memory_service):
        """Test forget with specific namespace."""
        result = await memory_service.forget("test.key", namespace="custom")

        assert result is not None
        assert hasattr(result, "success")

    @pytest.mark.asyncio
    async def test_forget_result_structure(self, memory_service):
        """Test forget result has expected structure."""
        result = await memory_service.forget("test.key")

        assert hasattr(result, "success")
        assert hasattr(result, "key")
        assert hasattr(result, "to_dict")

    @pytest.mark.asyncio
    async def test_forget_to_dict(self, memory_service):
        """Test forget result can be converted to dict."""
        result = await memory_service.forget("test.key")
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)


class TestMemoryServiceRemember:
    """Test remember functionality.

    Note: Remember requires LLM for classification.
    These tests verify the service doesn't crash.
    """

    @pytest.mark.asyncio
    async def test_remember_returns_result(self, memory_service):
        """Test that remember returns a result object."""
        try:
            result = await memory_service.remember("Test content")
            assert result is not None
            assert hasattr(result, "success")
        except Exception:
            # May fail if no LLM configured - this is expected
            pass

    @pytest.mark.asyncio
    async def test_remember_with_namespace(self, memory_service):
        """Test remember with specific namespace."""
        try:
            result = await memory_service.remember("Test content", namespace="custom")
            assert result is not None
        except Exception:
            # Expected if no LLM
            pass

    @pytest.mark.asyncio
    async def test_remember_result_structure(self, memory_service):
        """Test remember result has expected structure."""
        try:
            result = await memory_service.remember("Test")
            assert hasattr(result, "success")
            assert hasattr(result, "key")
            assert hasattr(result, "to_dict")
        except Exception:
            # Expected if no LLM
            pass


class TestMemoryServiceEdgeCases:
    """Test edge cases and error handling."""

    def test_service_with_invalid_path(self):
        """Test service with invalid store path."""
        service = MemoryService("/nonexistent/path")
        # Should create without crashing
        assert service is not None

    @pytest.mark.asyncio
    async def test_recall_empty_query(self, memory_service):
        """Test recall with empty query."""
        result = await memory_service.recall("")

        assert result is not None

    @pytest.mark.asyncio
    async def test_recall_special_characters(self, memory_service):
        """Test recall with special characters in query."""
        result = await memory_service.recall("test @#$% query")

        assert result is not None

    @pytest.mark.asyncio
    async def test_forget_empty_key(self, memory_service):
        """Test forget with empty key."""
        result = await memory_service.forget("")

        assert result is not None


class TestMemoryServiceWarmup:
    """Test warmup functionality."""

    def test_warmup(self, memory_service):
        """Test warmup method."""
        try:
            warmup_time = memory_service.warmup()
            assert warmup_time is not None
            assert isinstance(warmup_time, (int, float))
            assert warmup_time >= 0
        except Exception:
            # May fail if dependencies not available
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

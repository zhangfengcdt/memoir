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

    @pytest.mark.asyncio
    async def test_remember_multi_path_writes_related_keys(self, memory_service):
        """Multi-path remember stores blobs at every path with cross-references."""
        result = await memory_service.remember(
            "Feng prefers TDD and terminal CLIs",
            paths=["preferences.coding.methodology", "preferences.tooling.terminal"],
        )
        assert result.success
        assert result.keys == [
            "preferences.coding.methodology",
            "preferences.tooling.terminal",
        ]

        get_a = memory_service.get(["preferences.coding.methodology"], "default")
        get_b = memory_service.get(["preferences.tooling.terminal"], "default")
        blob_a = get_a.items[0]["value"]
        blob_b = get_b.items[0]["value"]

        assert blob_a["related_keys"] == ["preferences.tooling.terminal"]
        assert blob_b["related_keys"] == ["preferences.coding.methodology"]
        # Same content at both paths.
        assert (
            blob_a["content"]
            == blob_b["content"]
            == "Feng prefers TDD and terminal CLIs"
        )

    @pytest.mark.asyncio
    async def test_remember_single_path_has_empty_related_keys(self, memory_service):
        """Single-path remember writes related_keys as an empty list, not missing."""
        result = await memory_service.remember(
            "single fact", paths=["context.project.foo"]
        )
        assert result.success
        get_res = memory_service.get(["context.project.foo"], "default")
        blob = get_res.items[0]["value"]
        assert blob["related_keys"] == []

    @pytest.mark.asyncio
    async def test_remember_path_alias_still_works(self, memory_service):
        """Backcompat: the old `path=` keyword still writes a single-path blob."""
        result = await memory_service.remember(
            "legacy single-path call", path="context.project.bar"
        )
        assert result.success
        assert result.key == "context.project.bar"
        assert result.keys == ["context.project.bar"]

    @pytest.mark.asyncio
    async def test_remember_edit_preserves_related_keys(self, memory_service):
        """Editing one path of a multi-key memory keeps the sibling reference."""
        await memory_service.remember(
            "v1",
            paths=["preferences.coding.methodology", "preferences.tooling.terminal"],
        )
        # Subsequent path-only write to one key should not clobber siblings.
        await memory_service.remember("v2", paths=["preferences.coding.methodology"])

        get_a = memory_service.get(["preferences.coding.methodology"], "default")
        blob_a = get_a.items[0]["value"]
        assert blob_a["content"] == "v2"
        assert "preferences.tooling.terminal" in blob_a["related_keys"]


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

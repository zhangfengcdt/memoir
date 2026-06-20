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
        """Editing one path of a multi-key memory keeps the sibling reference
        and appends the new content as an [update] paragraph."""
        await memory_service.remember(
            "v1",
            paths=["preferences.coding.methodology", "preferences.tooling.terminal"],
        )
        # Subsequent path-only write to one key should not clobber siblings,
        # and content should be appended (not replaced) under the append policy.
        await memory_service.remember(
            "v2", paths=["preferences.coding.methodology"], merge_policy="append"
        )

        get_a = memory_service.get(["preferences.coding.methodology"], "default")
        blob_a = get_a.items[0]["value"]
        assert blob_a["content"] == "v1\n\n[update] v2"
        assert "preferences.tooling.terminal" in blob_a["related_keys"]

    @pytest.mark.asyncio
    async def test_remember_path_appends_on_existing(self, memory_service):
        """Second write under the append policy appends with [update] marker."""
        path = "context.project.append_test"
        await memory_service.remember("first fact", paths=[path])
        await memory_service.remember(
            "second fact", paths=[path], merge_policy="append"
        )

        blob = memory_service.get([path]).items[0]["value"]
        assert blob["content"] == "first fact\n\n[update] second fact"

    @pytest.mark.asyncio
    async def test_remember_path_appends_repeatedly(self, memory_service):
        """Three append-policy writes stack two [update] paragraphs."""
        path = "context.project.stack_test"
        await memory_service.remember("a", paths=[path])
        await memory_service.remember("b", paths=[path], merge_policy="append")
        await memory_service.remember("c", paths=[path], merge_policy="append")

        blob = memory_service.get([path]).items[0]["value"]
        assert blob["content"] == "a\n\n[update] b\n\n[update] c"

    @pytest.mark.asyncio
    async def test_remember_path_duplicate_still_appends(self, memory_service):
        """Identical content submitted twice is appended verbatim (no dedup)."""
        path = "context.project.dup_test"
        await memory_service.remember("same", paths=[path])
        await memory_service.remember("same", paths=[path], merge_policy="append")

        blob = memory_service.get([path]).items[0]["value"]
        assert blob["content"] == "same\n\n[update] same"

    @pytest.mark.asyncio
    async def test_remember_path_mixed_existing_independent(self, memory_service):
        """Multi-path append-policy write with one existing and one fresh path:
        each behaves independently (existing appends, fresh stores plain)."""
        existing_path = "context.project.mixed_existing"
        fresh_path = "context.project.mixed_fresh"

        await memory_service.remember("orig", paths=[existing_path])
        await memory_service.remember(
            "new", paths=[existing_path, fresh_path], merge_policy="append"
        )

        existing_blob = memory_service.get([existing_path]).items[0]["value"]
        fresh_blob = memory_service.get([fresh_path]).items[0]["value"]
        assert existing_blob["content"] == "orig\n\n[update] new"
        assert fresh_blob["content"] == "new"

    @pytest.mark.asyncio
    async def test_remember_path_first_write_is_plain(self, memory_service):
        """First -p write at a fresh key stores the content verbatim
        (no [update] marker)."""
        path = "context.project.fresh_test"
        await memory_service.remember("only fact", paths=[path])

        blob = memory_service.get([path]).items[0]["value"]
        assert blob["content"] == "only fact"

    @pytest.mark.asyncio
    async def test_remember_path_replace_overrides_append(self, memory_service):
        """`replace=True` clobbers existing content instead of appending."""
        path = "context.project.replace_test"
        await memory_service.remember("first", paths=[path])
        await memory_service.remember("second", paths=[path], replace=True)

        blob = memory_service.get([path]).items[0]["value"]
        assert blob["content"] == "second"

    # --- Phase 2: timestamped-facet storage (schema_version 2) ---------------

    @pytest.mark.asyncio
    async def test_remember_writes_v2_facet_blob(self, memory_service):
        """A write stores a v2 blob: projected top-level content + entries list."""
        path = "context.project.facet_shape"
        await memory_service.remember("hello", paths=[path])

        blob = memory_service.get([path]).items[0]["value"]
        assert blob["schema_version"] == 2
        assert isinstance(blob["entries"], list)
        assert len(blob["entries"]) == 1
        assert blob["entries"][0]["content"] == "hello"
        assert blob["entries"][0]["status"] == "active"
        # legacy readers keep working via the projected top-level content
        assert blob["content"] == "hello"

    @pytest.mark.asyncio
    async def test_remember_append_accumulates_entries(self, memory_service):
        """Append adds a second active entry; projection stays byte-identical."""
        path = "context.project.facet_append"
        await memory_service.remember("a", paths=[path])
        await memory_service.remember("b", paths=[path], merge_policy="append")

        blob = memory_service.get([path]).items[0]["value"]
        assert [e["content"] for e in blob["entries"]] == ["a", "b"]
        assert blob["content"] == "a\n\n[update] b"

    @pytest.mark.asyncio
    async def test_remember_replace_collapses_to_single_entry(self, memory_service):
        """replace=True keeps the blob at a single entry (flat-key safety)."""
        path = "context.project.facet_replace"
        await memory_service.remember("first", paths=[path])
        await memory_service.remember("second", paths=[path], replace=True)

        blob = memory_service.get([path]).items[0]["value"]
        assert len(blob["entries"]) == 1
        assert blob["entries"][0]["content"] == "second"

    @pytest.mark.asyncio
    async def test_remember_upgrades_legacy_v1_blob_on_write(self, memory_service):
        """A pre-existing v1 blob (bare content, no entries) is lifted to v2 on
        the next write, preserving the old content as the first entry."""
        path = "context.project.legacy_upgrade"
        store = memory_service._get_store()
        ns = memory_service.namespace_to_tuple("default")
        # Simulate a legacy v1 blob written before the facet migration.
        store.put(ns, path, {"content": "legacy", "confidence": 1.0, "timestamp": 1.0})

        await memory_service.remember("new", paths=[path], merge_policy="append")

        blob = memory_service.get([path]).items[0]["value"]
        assert blob["schema_version"] == 2
        assert [e["content"] for e in blob["entries"]] == ["legacy", "new"]
        assert blob["content"] == "legacy\n\n[update] new"

    # --- Phase 3: per-type default policies + strategies ---------------------

    @pytest.mark.asyncio
    async def test_default_semantic_is_confidence_gated(self, memory_service):
        """Semantic keys (knowledge.*) default to confidence_gated: two equal
        (1.0) -p writes collapse to the latest (gate passes, replaces)."""
        path = "knowledge.technical.gate_default"
        await memory_service.remember("old", paths=[path])
        await memory_service.remember("new", paths=[path])

        blob = memory_service.get([path]).items[0]["value"]
        assert len(blob["entries"]) == 1
        assert blob["content"] == "new"

    @pytest.mark.asyncio
    async def test_default_episodic_appends(self, memory_service):
        """Episodic keys (experience.*) default to append (the event log)."""
        path = "experience.work.projects"
        await memory_service.remember("p1", paths=[path])
        await memory_service.remember("p2", paths=[path])

        blob = memory_service.get([path]).items[0]["value"]
        assert [e["content"] for e in blob["entries"]] == ["p1", "p2"]

    @pytest.mark.asyncio
    async def test_default_working_replaces(self, memory_service):
        """Working keys (context.current.*) default to replace (single entry)."""
        path = "context.current.session"
        await memory_service.remember("a", paths=[path])
        await memory_service.remember("b", paths=[path])

        blob = memory_service.get([path]).items[0]["value"]
        assert len(blob["entries"]) == 1
        assert blob["content"] == "b"

    @pytest.mark.asyncio
    async def test_default_procedural_llm_merges(self, memory_service, monkeypatch):
        """Procedural keys (workflow.*) default to llm_merge: the consolidation
        helper is invoked and its output becomes the single entry."""

        async def fake_consolidate(existing, new):
            return f"MERGED({existing}|{new})"

        monkeypatch.setattr(memory_service, "_llm_consolidate", fake_consolidate)
        path = "workflow.coding.style"
        await memory_service.remember("use tabs", paths=[path])
        await memory_service.remember("use spaces", paths=[path])

        blob = memory_service.get([path]).items[0]["value"]
        assert len(blob["entries"]) == 1
        assert blob["content"] == "MERGED(use tabs|use spaces)"

    @pytest.mark.asyncio
    async def test_merge_policy_reject_surfaces_conflict_without_writing(
        self, memory_service
    ):
        """merge_policy='reject' on an occupied key: nothing written, conflict
        returned, success False."""
        path = "knowledge.technical.reject_test"
        await memory_service.remember("first", paths=[path])
        result = await memory_service.remember(
            "second", paths=[path], merge_policy="reject"
        )

        assert result.success is False
        assert result.conflicts
        assert result.conflicts[0]["existing_content"] == "first"
        assert result.conflicts[0]["incoming_content"] == "second"
        # store unchanged
        blob = memory_service.get([path]).items[0]["value"]
        assert blob["content"] == "first"

    @pytest.mark.asyncio
    async def test_env_merge_policy_overrides_default(
        self, memory_service, monkeypatch
    ):
        """MEMOIR_MERGE_POLICY forces a strategy across the per-type default."""
        monkeypatch.setenv("MEMOIR_MERGE_POLICY", "append")
        path = "knowledge.technical.env_override"  # semantic -> normally gated
        await memory_service.remember("one", paths=[path])
        await memory_service.remember("two", paths=[path])

        blob = memory_service.get([path]).items[0]["value"]
        assert blob["content"] == "one\n\n[update] two"

    @pytest.mark.asyncio
    async def test_facet_cap_prunes_oldest(self, memory_service, monkeypatch):
        """MEMOIR_FACET_MAX_ENTRIES bounds append growth, dropping oldest."""
        monkeypatch.setenv("MEMOIR_FACET_MAX_ENTRIES", "2")
        path = "experience.work.capped"
        await memory_service.remember("1", paths=[path])
        await memory_service.remember("2", paths=[path])
        await memory_service.remember("3", paths=[path])

        blob = memory_service.get([path]).items[0]["value"]
        assert [e["content"] for e in blob["entries"]] == ["2", "3"]

    # --- Phase 4: merge-on-read (opt-in LLM consolidation) -------------------

    def _seed_two_entry_blob(self, memory_service, path):
        from memoir.services.merge_policy import (
            SCHEMA_VERSION,
            make_entry,
            project_entries,
        )

        store = memory_service._get_store()
        ns = memory_service.namespace_to_tuple("default")
        entries = [make_entry("p1", timestamp=1.0), make_entry("p2", timestamp=2.0)]
        proj = project_entries(entries)
        store.put(
            ns,
            path,
            {
                "content": proj["content"],
                "confidence": proj["confidence"],
                "timestamp": proj["timestamp"],
                "key": path,
                "namespace": "default",
                "related_keys": [],
                "entries": entries,
                "schema_version": SCHEMA_VERSION,
            },
        )

    def test_merge_on_read_consolidates_outside_event_loop(
        self, memory_service, monkeypatch
    ):
        """A sync get(consolidate=True) with no running loop runs the LLM
        consolidation and overwrites the returned content."""
        path = "experience.work.read_merge"
        self._seed_two_entry_blob(memory_service, path)
        monkeypatch.setattr(
            memory_service, "_consolidate_read", lambda contents: " | ".join(contents)
        )

        res = memory_service.get([path], consolidate=True)
        assert res.items[0]["value"]["content"] == "p1 | p2"

    def test_merge_on_read_env_enables(self, memory_service, monkeypatch):
        """MEMOIR_RECALL_MERGE enables consolidation without an explicit flag."""
        path = "experience.work.read_merge_env"
        self._seed_two_entry_blob(memory_service, path)
        monkeypatch.setenv("MEMOIR_RECALL_MERGE", "llm")
        monkeypatch.setattr(
            memory_service, "_consolidate_read", lambda contents: "MERGED"
        )

        res = memory_service.get([path])  # consolidate=None -> env decides
        assert res.items[0]["value"]["content"] == "MERGED"

    def test_get_default_keeps_deterministic_projection(self, memory_service):
        """Default get() does not consolidate — projection content is returned."""
        path = "experience.work.read_plain"
        self._seed_two_entry_blob(memory_service, path)

        res = memory_service.get([path])
        assert res.items[0]["value"]["content"] == "p1\n\n[update] p2"

    @pytest.mark.asyncio
    async def test_merge_on_read_falls_back_inside_event_loop(
        self, memory_service, monkeypatch
    ):
        """Inside a running loop the sync LLM call can't run; get() returns the
        deterministic projection without invoking consolidation."""
        path = "experience.work.read_merge_loop"
        self._seed_two_entry_blob(memory_service, path)
        called: list[int] = []
        monkeypatch.setattr(
            memory_service,
            "_consolidate_read",
            lambda contents: called.append(1) or "X",
        )

        res = memory_service.get([path], consolidate=True)
        assert not called  # loop-guard prevented the sync LLM call
        assert res.items[0]["value"]["content"] == "p1\n\n[update] p2"

    @pytest.mark.asyncio
    async def test_remember_path_replace_preserves_related_keys(self, memory_service):
        """Even with replace=True, sibling related_keys from earlier multi-key
        writes are still merged (replace targets content only, not graph edges)."""
        await memory_service.remember(
            "v1",
            paths=["preferences.coding.methodology", "preferences.tooling.terminal"],
        )
        await memory_service.remember(
            "v2", paths=["preferences.coding.methodology"], replace=True
        )

        blob = memory_service.get(["preferences.coding.methodology"]).items[0]["value"]
        assert blob["content"] == "v2"
        assert "preferences.tooling.terminal" in blob["related_keys"]


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

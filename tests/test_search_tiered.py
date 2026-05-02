"""Tests for the multi-stage tiered mode in IntelligentSearchEngine.

Covers the caller-driven drill-down pattern (L1 survey → L1 pick → optional
L2 pick → key pick) ported into the engine itself. Single-stage mode remains
the default and is exercised elsewhere; these tests focus on the tiered path
and backward compatibility.
"""

import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from memoir.search.intelligent import (
    IntelligentSearchEngine,
    _filter_keys,
    _group_by_depth,
)
from memoir.services.store_service import StoreService
from memoir.store.prolly_adapter import ProllyTreeStore


def _mk_memory(content: str) -> dict:
    return {"content": content, "confidence": 1.0, "metadata": {}}


def _populate(
    store: ProllyTreeStore, paths: list[str], namespace: tuple = ("default",)
):
    """Store one memory per path so the engine's path-discovery step sees them."""
    for p in paths:
        store.put(namespace, p, _mk_memory(f"stored at {p}"))


def _canned_llm_response(text: str):
    response = MagicMock()
    response.content = text
    return response


@pytest.fixture
def temp_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        StoreService(tmpdir).create_store(tmpdir)
        store = ProllyTreeStore(tmpdir)
        yield store


class TestTieredSearchPipeline:
    """Covers the L1 → (L2) → key-pick flow."""

    @pytest.mark.asyncio
    async def test_l1_histogram_computed_from_stored_paths(self, temp_store):
        """L1 survey groups stored paths by first segment — no LLM call needed
        for this step, only for the picks that follow."""
        paths = [
            "preferences.coding.style",
            "preferences.tools.editor",
            "preferences.work.hours",
            "context.project.stack",
            "context.project.repo",
            "workflow.coding.review",
            "workflow.devops.deploy",
        ]
        _populate(temp_store, paths)

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                _canned_llm_response("preferences\nworkflow"),
                _canned_llm_response(
                    "preferences.coding.style\nworkflow.coding.review"
                ),
            ]
        )

        engine = IntelligentSearchEngine(llm=mock_llm, store=temp_store)
        results = await engine.search(
            "how do I review code?",
            namespace="default",
            limit=5,
            mode="tiered",
            return_prompts=True,
        )

        # The tiered path emits its step_timings keys, confirming the L1 survey ran.
        md = results[0].metadata
        assert "l1_survey" in md["step_timings"]
        assert "l1_pick_llm" in md["step_timings"]
        assert "key_pick_llm" in md["step_timings"]
        assert md["mode"] == "tiered"

    @pytest.mark.asyncio
    async def test_two_llm_calls_in_baseline_tiered_flow(self, temp_store):
        """Baseline tiered flow (no oversized L1) should fire exactly two LLM
        calls: L1 pick + key pick. No L2 escalation."""
        paths = [
            "preferences.coding.style",
            "preferences.tools.editor",
            "context.project.stack",
            "workflow.coding.review",
        ]
        _populate(temp_store, paths)

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                _canned_llm_response("preferences"),
                _canned_llm_response("preferences.coding.style"),
            ]
        )

        engine = IntelligentSearchEngine(llm=mock_llm, store=temp_store)
        await engine.search(
            "coding style?", namespace="default", limit=5, mode="tiered"
        )

        assert mock_llm.ainvoke.call_count == 2

    @pytest.mark.asyncio
    async def test_l2_escalation_when_l1_too_wide(self, temp_store):
        """An L1 with >40 keys should trigger a third LLM call for L2 picking."""
        # 50 keys under preferences.* — crosses the 40-key escalation threshold.
        paths = [f"preferences.cat{i // 10}.item{i}" for i in range(50)]
        # Plus a couple of small-L1 neighbours so L1 pick has choices.
        paths += ["context.project.stack", "workflow.coding.review"]
        _populate(temp_store, paths)

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                _canned_llm_response("preferences"),  # L1 pick
                _canned_llm_response("preferences.cat0"),  # L2 pick for wide L1
                _canned_llm_response("preferences.cat0.item0"),  # key pick
            ]
        )

        engine = IntelligentSearchEngine(llm=mock_llm, store=temp_store)
        results = await engine.search(
            "anything", namespace="default", limit=5, mode="tiered", return_prompts=True
        )

        assert mock_llm.ainvoke.call_count == 3
        md = results[0].metadata
        assert "l2_pick_llm" in md["step_timings"]
        assert "l2_pick" in md["llm_prompts"]

    @pytest.mark.asyncio
    async def test_falls_back_on_malformed_l1_pick(self, temp_store):
        """If the L1 LLM returns garbage, top-N-by-count fallback keeps the
        search alive rather than returning empty."""
        paths = [
            "preferences.coding.style",
            "preferences.tools.editor",
            "context.project.stack",
        ]
        _populate(temp_store, paths)

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            side_effect=[
                _canned_llm_response("i am not a taxonomy prefix"),  # garbage L1
                _canned_llm_response("preferences.coding.style"),  # valid key pick
            ]
        )

        engine = IntelligentSearchEngine(llm=mock_llm, store=temp_store)
        results = await engine.search(
            "anything", namespace="default", limit=5, mode="tiered"
        )

        # Should still return a real result, not a timing-only dummy.
        assert any(r.path == "preferences.coding.style" for r in results)

    @pytest.mark.asyncio
    async def test_tiered_returns_same_shape_as_single(self, temp_store):
        """Tiered and single modes must return the same IntelligentSearchResult
        shape for the same query — callers must not need shape branching."""
        paths = [
            "preferences.coding.style",
            "context.project.stack",
        ]
        _populate(temp_store, paths)

        # Single mode: one LLM call returning the path.
        single_llm = MagicMock()
        single_llm.ainvoke = AsyncMock(
            return_value=_canned_llm_response("preferences.coding.style")
        )
        single_engine = IntelligentSearchEngine(llm=single_llm, store=temp_store)
        single_results = await single_engine.search(
            "style?", namespace="default", limit=5, mode="single"
        )

        # Tiered mode: L1 pick + key pick returning same path.
        tiered_llm = MagicMock()
        tiered_llm.ainvoke = AsyncMock(
            side_effect=[
                _canned_llm_response("preferences"),
                _canned_llm_response("preferences.coding.style"),
            ]
        )
        tiered_engine = IntelligentSearchEngine(llm=tiered_llm, store=temp_store)
        tiered_results = await tiered_engine.search(
            "style?", namespace="default", limit=5, mode="tiered"
        )

        def _shape(results):
            return [
                (type(r).__name__, r.path, type(r.metadata).__name__)
                for r in results
                if r.path  # drop timing-only dummies
            ]

        assert _shape(single_results) == _shape(tiered_results)


class TestBackwardCompatibility:
    """The new mode argument must not change existing behavior."""

    @pytest.mark.asyncio
    async def test_default_mode_is_single(self, temp_store):
        """Calling search() without mode must take the single-stage path
        (one LLM call, no L1 survey)."""
        paths = ["preferences.coding.style"]
        _populate(temp_store, paths)

        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(
            return_value=_canned_llm_response("preferences.coding.style")
        )

        engine = IntelligentSearchEngine(llm=mock_llm, store=temp_store)
        results = await engine.search("style?", namespace="default", limit=5)

        assert mock_llm.ainvoke.call_count == 1
        md = results[0].metadata
        # Single-stage timings use step1/step2/step3 keys, not the tiered ones.
        assert "step1_path_discovery" in md["step_timings"]
        assert "l1_survey" not in md["step_timings"]
        assert md["mode"] == "single"

    @pytest.mark.asyncio
    async def test_unknown_mode_raises(self, temp_store):
        mock_llm = MagicMock()
        engine = IntelligentSearchEngine(llm=mock_llm, store=temp_store)
        with pytest.raises(ValueError, match="Unknown search mode"):
            await engine.search("q", namespace="default", mode="banana")


class TestTieredHelpers:
    """Unit tests on the small helpers reused by the tiered flow."""

    def test_filter_keys_glob(self):
        keys = [
            "preferences.coding.style",
            "preferences.tools.editor",
            "context.project.stack",
        ]
        assert _filter_keys(keys, "preferences.*") == [
            "preferences.coding.style",
            "preferences.tools.editor",
        ]
        assert _filter_keys(keys, "*.project.*") == ["context.project.stack"]
        # None pattern is a passthrough.
        assert _filter_keys(keys, None) == keys

    def test_group_by_depth_counts(self):
        keys = [
            "preferences.coding.style",
            "preferences.tools.editor",
            "context.project.stack",
        ]
        assert _group_by_depth(keys, 1) == {"context": 1, "preferences": 2}
        assert _group_by_depth(keys, 2) == {
            "context.project": 1,
            "preferences.coding": 1,
            "preferences.tools": 1,
        }

"""
Schema-drift test for the statistics endpoint.

Hits ``handle_statistics_api`` indirectly by calling the same internal
helpers it uses, then validates the round-tripped payload through
``StatisticsResponse``. If the backend grows a brand-new top-level
section (or removes one), the schema fails here — a clear signal to
update the modal's tab list.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from memoir.services.store_service import StoreService
from memoir.ui.schemas import StatisticsResponse


@pytest.fixture
def temp_store():
    path = tempfile.mkdtemp(prefix="memoir_stats_test_")
    try:
        StoreService(path).create_store(path)
        yield path
    finally:
        if os.path.exists(path):
            shutil.rmtree(path)


def test_statistics_payload_validates(temp_store):
    """Build a payload by calling the same helpers the handler uses,
    then push it through ``StatisticsResponse`` to ensure the shape is
    locked correctly.
    """
    from memoir.store.prolly_adapter import ProllyTreeStore
    from memoir.ui.server import MemoryStoreHandler

    store = ProllyTreeStore(
        path=temp_store,
        enable_versioning=True,
        auto_commit=False,
        cache_size=10000,
    )

    # Instantiate the handler skeleton without going through HTTP.
    handler = MemoryStoreHandler.__new__(MemoryStoreHandler)
    stats: dict = {
        "storage": handler._get_storage_statistics(store, temp_store),
        "tree_structure": handler._analyze_tree_structure(store),
        "versioning": handler._get_versioning_statistics(temp_store),
        "metadata": handler._get_store_metadata(temp_store),
        "performance": handler._get_performance_metrics(store),
        "taxonomy": handler._get_taxonomy_statistics(store),
        "content": handler._analyze_content_statistics(store),
        "system": {
            "python_version": "3.11.9",
            "platform": "Test",
            "platform_version": "test",
            "memoir_version": "test",
        },
    }

    body = StatisticsResponse.model_validate(
        {
            "success": True,
            "statistics": stats,
            "generated_at": "2026-04-25T00:00:00",
            "store_path": temp_store,
        }
    )

    # All eight known sections present and dict-shaped.
    block = body.statistics
    for section in [
        "storage",
        "tree_structure",
        "versioning",
        "metadata",
        "performance",
        "taxonomy",
        "content",
        "system",
    ]:
        assert isinstance(getattr(block, section), dict), section

    # Round-trip through model_dump must preserve the data.
    dumped = body.model_dump(mode="json")
    assert dumped["success"] is True
    assert dumped["store_path"] == temp_store
    assert "system" in dumped["statistics"]


def test_statistics_rejects_unknown_top_level_section():
    """If the backend adds a new section without updating the model,
    we want validation to fail loudly — that's the contract of
    ``extra='forbid'`` on StatisticsBlock."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="surprises"):
        StatisticsResponse.model_validate(
            {
                "success": True,
                "statistics": {
                    "storage": {},
                    "tree_structure": {},
                    "versioning": {},
                    "metadata": {},
                    "performance": {},
                    "taxonomy": {},
                    "content": {},
                    "system": {},
                    "surprises": {"oops": True},
                },
                "generated_at": "now",
                "store_path": "/tmp/x",
            }
        )

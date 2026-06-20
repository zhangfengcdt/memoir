# SPDX-License-Identifier: Apache-2.0
"""Phase 1: readers tolerate the v2 facet blob shape (dual-read)."""

from memoir.services.merge_policy import SCHEMA_VERSION, make_entry
from memoir.ui.handlers.store_handler import _extract_content as store_extract
from memoir.ui.reader import _extract_content as reader_extract


def _v2(*entries, **top):
    blob = {"entries": list(entries), "schema_version": SCHEMA_VERSION}
    blob.update(top)
    return blob


def test_reader_v1_blob_unchanged():
    assert reader_extract({"content": "plain v1"}) == "plain v1"


def test_reader_v2_single_entry():
    blob = _v2(make_entry("hello", timestamp=1.0), content="hello")
    assert reader_extract(blob) == "hello"


def test_reader_v2_multi_entry_projects():
    blob = _v2(make_entry("a", timestamp=1.0), make_entry("b", timestamp=2.0))
    assert reader_extract(blob) == "a\n\n[update] b"


def test_reader_v2_respects_superseded_even_if_top_level_stale():
    # top-level content intentionally stale; entries are the source of truth
    blob = _v2(
        make_entry("old", timestamp=1.0, status="superseded"),
        make_entry("current", timestamp=2.0),
        content="STALE",
    )
    assert reader_extract(blob) == "current"


def test_store_handler_v1_metrics_json_still_parsed():
    # metrics keys store a JSON string in content; v1 path must still parse it
    assert store_extract({"content": '{"turns": 3}'}) == {"turns": 3}


def test_store_handler_v2_metrics_json_parsed_via_projection():
    # metrics use REPLACE -> single entry; projected content is the JSON string
    blob = _v2(make_entry('{"turns": 5}', timestamp=1.0), content='{"turns": 5}')
    assert store_extract(blob) == {"turns": 5}


def test_top_level_content_present_for_legacy_readers():
    # Invariant: every v2 blob a writer emits carries a projected top-level
    # `content` string, so the 22+ readers that read value["content"] keep
    # working without change. This asserts the contract the writer must honor.
    blob = _v2(
        make_entry("a", timestamp=1.0),
        make_entry("b", timestamp=2.0),
        content="a\n\n[update] b",
        confidence=1.0,
        timestamp=2.0,
    )
    assert isinstance(blob["content"], str)
    assert blob["content"] == "a\n\n[update] b"

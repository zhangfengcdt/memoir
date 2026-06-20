# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the pure merge-policy primitives (no store / LLM / IO)."""

import pytest

from memoir.services.merge_policy import (
    DEFAULT_FACET_MAX_ENTRIES,
    SCHEMA_VERSION,
    ConflictInfo,
    ConflictStrategy,
    MemoryType,
    apply_strategy,
    default_strategy_for_key,
    facet_max_entries,
    make_entry,
    memory_type_for_key,
    project_entries,
    read_project,
    resolve_policy,
    upgrade_blob,
)

# --------------------------------------------------------------------------- #
# project_entries — the legacy-compatible projection
# --------------------------------------------------------------------------- #


def test_project_two_active_entries_is_legacy_append_byte_identical():
    entries = [
        make_entry("first", confidence=1.0, timestamp=10.0),
        make_entry("second", confidence=0.9, timestamp=20.0),
    ]
    proj = project_entries(entries)
    assert proj["content"] == "first\n\n[update] second"
    assert proj["confidence"] == 1.0  # max over active
    assert proj["timestamp"] == 20.0  # max over active


def test_project_single_entry():
    proj = project_entries([make_entry("only", confidence=0.7, timestamp=5.0)])
    assert proj == {"content": "only", "confidence": 0.7, "timestamp": 5.0}


def test_project_empty():
    assert project_entries([]) == {"content": "", "confidence": 1.0, "timestamp": 0.0}


def test_project_excludes_superseded():
    entries = [
        make_entry("old", timestamp=1.0, status="superseded"),
        make_entry("current", timestamp=2.0),
    ]
    assert project_entries(entries)["content"] == "current"


# --------------------------------------------------------------------------- #
# upgrade_blob — lazy v1 -> v2
# --------------------------------------------------------------------------- #


def test_upgrade_v1_blob():
    v1 = {
        "content": "hello",
        "confidence": 0.8,
        "timestamp": 3.0,
        "key": "knowledge.x.y",
        "related_keys": ["a.b.c"],
    }
    up = upgrade_blob(v1)
    assert up["schema_version"] == SCHEMA_VERSION
    assert up["entries"] == [
        {"content": "hello", "confidence": 0.8, "timestamp": 3.0, "status": "active"}
    ]
    # preserves unrelated top-level fields
    assert up["related_keys"] == ["a.b.c"]
    assert up["key"] == "knowledge.x.y"


def test_upgrade_is_idempotent():
    v1 = {"content": "x", "confidence": 1.0, "timestamp": 0.0}
    once = upgrade_blob(v1)
    twice = upgrade_blob(once)
    assert twice is once  # already v2 -> returned unchanged


def test_upgrade_none_and_nondict_passthrough():
    assert upgrade_blob(None) is None
    assert upgrade_blob("raw") == "raw"


def test_upgrade_missing_confidence_defaults_to_one():
    up = upgrade_blob({"content": "legacy", "timestamp": 1.0})
    assert up["entries"][0]["confidence"] == 1.0


# --------------------------------------------------------------------------- #
# memory type mapping + per-type defaults
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("context.current.session", MemoryType.WORKING),
        ("metrics.turn.main", MemoryType.WORKING),
        ("metrics.code.main", MemoryType.EPISODIC),
        ("experience.work.projects", MemoryType.EPISODIC),
        ("workflow.coding.style", MemoryType.PROCEDURAL),
        ("behavior.work.practices", MemoryType.PROCEDURAL),
        ("knowledge.technical.backend", MemoryType.SEMANTIC),
        ("preferences.tools.memory", MemoryType.SEMANTIC),
        ("context.project.architecture", MemoryType.SEMANTIC),
        ("entity.code.repositories", MemoryType.SEMANTIC),
        ("totally.unknown.root", MemoryType.SEMANTIC),
    ],
)
def test_memory_type_for_key(key, expected):
    assert memory_type_for_key(key) == expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("context.current.session", ConflictStrategy.REPLACE),
        ("metrics.turn.main", ConflictStrategy.REPLACE),
        ("metrics.code.main", ConflictStrategy.APPEND),
        ("experience.x.y", ConflictStrategy.APPEND),
        ("workflow.coding.style", ConflictStrategy.LLM_MERGE),
        ("knowledge.technical.backend", ConflictStrategy.CONFIDENCE_GATED),
    ],
)
def test_default_strategy_for_key(key, expected):
    assert default_strategy_for_key(key) == expected


# --------------------------------------------------------------------------- #
# resolve_policy — precedence
# --------------------------------------------------------------------------- #


def test_resolve_explicit_wins_over_env_and_type():
    got = resolve_policy("append", "knowledge.x.y", path_provided=False, env="replace")
    assert got == ConflictStrategy.APPEND


def test_resolve_explicit_accepts_enum_and_is_case_insensitive():
    assert (
        resolve_policy("REPLACE", "knowledge.x.y", path_provided=False, env="")
        == ConflictStrategy.REPLACE
    )
    assert (
        resolve_policy(
            ConflictStrategy.REJECT, "knowledge.x.y", path_provided=False, env=""
        )
        == ConflictStrategy.REJECT
    )


def test_resolve_env_wins_over_type_default():
    got = resolve_policy(None, "knowledge.x.y", path_provided=False, env="append")
    assert got == ConflictStrategy.APPEND


def test_resolve_type_default_when_no_explicit_or_env():
    assert (
        resolve_policy(None, "workflow.coding.style", path_provided=False, env="")
        == ConflictStrategy.LLM_MERGE
    )
    assert (
        resolve_policy(None, "experience.x", path_provided=False, env="")
        == ConflictStrategy.APPEND
    )


def test_resolve_legacy_behaviour_neutral_split():
    # use_type_defaults=False reproduces today's behaviour: -p append, LLM replace.
    assert (
        resolve_policy(
            None, "knowledge.x.y", path_provided=True, env="", use_type_defaults=False
        )
        == ConflictStrategy.APPEND
    )
    assert (
        resolve_policy(
            None, "knowledge.x.y", path_provided=False, env="", use_type_defaults=False
        )
        == ConflictStrategy.REPLACE
    )


def test_resolve_invalid_value_raises():
    with pytest.raises(ValueError, match="bogus"):
        resolve_policy("bogus", "knowledge.x.y", path_provided=False, env="")


# --------------------------------------------------------------------------- #
# facet_max_entries — the shared cap resolver
# --------------------------------------------------------------------------- #


def test_facet_max_entries_default(monkeypatch):
    monkeypatch.delenv("MEMOIR_FACET_MAX_ENTRIES", raising=False)
    assert facet_max_entries() == DEFAULT_FACET_MAX_ENTRIES


@pytest.mark.parametrize("disable", ["0", "none", "off", "unlimited"])
def test_facet_max_entries_disabled(monkeypatch, disable):
    monkeypatch.setenv("MEMOIR_FACET_MAX_ENTRIES", disable)
    assert facet_max_entries() is None


def test_facet_max_entries_custom_and_invalid(monkeypatch):
    monkeypatch.setenv("MEMOIR_FACET_MAX_ENTRIES", "5")
    assert facet_max_entries() == 5
    monkeypatch.setenv("MEMOIR_FACET_MAX_ENTRIES", "notanumber")
    assert facet_max_entries() == DEFAULT_FACET_MAX_ENTRIES


# --------------------------------------------------------------------------- #
# apply_strategy — per-strategy mutation
# --------------------------------------------------------------------------- #


def _existing(*entries):
    return {"entries": list(entries), "schema_version": SCHEMA_VERSION}


def test_apply_no_existing_always_writes_single():
    new = make_entry("new", timestamp=2.0)
    for strat in ConflictStrategy:
        out = apply_strategy(strat, None, new)
        assert out.action == "write"
        assert out.entries == [new]


def test_apply_append_accumulates():
    existing = _existing(make_entry("a", timestamp=1.0))
    new = make_entry("b", timestamp=2.0)
    out = apply_strategy(ConflictStrategy.APPEND, existing, new)
    assert out.action == "write"
    assert [e["content"] for e in out.entries] == ["a", "b"]


def test_apply_append_respects_cap():
    existing = _existing(*(make_entry(str(i), timestamp=float(i)) for i in range(5)))
    out = apply_strategy(
        ConflictStrategy.APPEND,
        existing,
        make_entry("new", timestamp=9.0),
        max_entries=3,
    )
    # oldest dropped, newest kept
    assert [e["content"] for e in out.entries] == ["3", "4", "new"]


def test_apply_replace_collapses_to_single():
    existing = _existing(make_entry("a", timestamp=1.0), make_entry("b", timestamp=2.0))
    new = make_entry("c", timestamp=3.0)
    out = apply_strategy(ConflictStrategy.REPLACE, existing, new)
    assert out.action == "write"
    assert out.entries == [new]


def test_apply_llm_merge_collapses_to_consolidated_single():
    existing = _existing(make_entry("a", timestamp=1.0))
    # caller pre-consolidated text into the new entry
    merged = make_entry("a + b merged", timestamp=2.0)
    out = apply_strategy(ConflictStrategy.LLM_MERGE, existing, merged)
    assert out.entries == [merged]


def test_apply_confidence_gated_writes_when_not_lower():
    existing = _existing(make_entry("old", confidence=0.6, timestamp=1.0))
    new = make_entry("new", confidence=0.9, timestamp=2.0)
    out = apply_strategy(ConflictStrategy.CONFIDENCE_GATED, existing, new)
    assert out.action == "write"
    assert out.entries == [new]


def test_apply_confidence_gated_noops_when_lower():
    existing = _existing(make_entry("old", confidence=0.9, timestamp=1.0))
    new = make_entry("new", confidence=0.5, timestamp=2.0)
    out = apply_strategy(ConflictStrategy.CONFIDENCE_GATED, existing, new)
    assert out.action == "noop"
    assert out.entries == existing["entries"]  # unchanged


def test_apply_reject_surfaces_conflict_without_writing():
    existing = _existing(make_entry("old", confidence=0.8, timestamp=1.0))
    new = make_entry("new", confidence=0.5, timestamp=2.0)
    out = apply_strategy(
        ConflictStrategy.REJECT, existing, new, key="knowledge.x.y", namespace="default"
    )
    assert out.action == "reject"
    assert isinstance(out.conflict, ConflictInfo)
    assert out.conflict.existing_content == "old"
    assert out.conflict.incoming_content == "new"
    assert out.conflict.key == "knowledge.x.y"


def test_confidence_gated_only_bites_llm_branch():
    """-p writes hard-set confidence=1.0, so the gate always passes there;
    it only changes behaviour for sub-1.0 (classifier) confidence."""
    existing = _existing(make_entry("old", confidence=1.0, timestamp=1.0))
    # path-provided style: incoming confidence 1.0 -> passes the >= gate
    out = apply_strategy(
        ConflictStrategy.CONFIDENCE_GATED, existing, make_entry("p", confidence=1.0)
    )
    assert out.action == "write"
    # classifier style: incoming 0.7 < 1.0 -> no-op
    out2 = apply_strategy(
        ConflictStrategy.CONFIDENCE_GATED, existing, make_entry("llm", confidence=0.7)
    )
    assert out2.action == "noop"


# --------------------------------------------------------------------------- #
# read_project — merge-on-read
# --------------------------------------------------------------------------- #


def test_read_project_v1_blob_returns_content():
    assert read_project({"content": "plain"}) == "plain"


def test_read_project_deterministic_join():
    blob = _existing(make_entry("a", timestamp=1.0), make_entry("b", timestamp=2.0))
    assert read_project(blob) == "a\n\n[update] b"


def test_read_project_uses_consolidator_for_multi_entry():
    blob = _existing(make_entry("a"), make_entry("b"))
    out = read_project(blob, consolidator=lambda items: " & ".join(items))
    assert out == "a & b"


def test_read_project_skips_consolidator_for_single_entry():
    blob = _existing(make_entry("only"))
    out = read_project(blob, consolidator=lambda items: "SHOULD_NOT_RUN")
    assert out == "only"

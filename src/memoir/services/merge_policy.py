# SPDX-License-Identifier: Apache-2.0
"""
Conflict-resolution / merge-policy primitives for memoir's ``remember`` flow.

A memory blob historically stored a single ``content`` string. This module
introduces a *timestamped-facet* model (``schema_version: 2``) where a key holds
a list of dated entries, plus a pluggable set of strategies deciding what to do
when a write lands on an already-occupied key.

Everything here is **pure** — no store, no I/O, no LLM — so it can be unit-tested
in isolation and reused by the CLI, MCP server, and UI. ``LLM_MERGE`` is the one
strategy that needs model output: the *caller* fires the (haiku) consolidation
call and passes the merged text in as the new entry's content before calling
:func:`apply_strategy`, keeping this module side-effect-free.

Invariants this module helps preserve:

* The stored blob always carries a projected top-level ``content``/``confidence``/
  ``timestamp`` (see :func:`project_entries`) so legacy readers keep working;
  ``entries`` is purely additive.
* A blob without ``schema_version``/``entries`` is a valid v1 doc (one implicit
  entry) — :func:`upgrade_blob` lifts it lazily, only on write.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from enum import Enum

SCHEMA_VERSION = 2

#: Separator between facets when projecting active entries into a single string.
#: Kept byte-identical to the legacy append behaviour so projecting two active
#: entries reproduces the old ``"first\n\n[update] second"`` output exactly.
_UPDATE_SEP = "\n\n[update] "

#: Env var selecting a global merge policy (overrides per-type defaults).
ENV_MERGE_POLICY = "MEMOIR_MERGE_POLICY"


class ConflictStrategy(str, Enum):
    """How a write resolves against an already-occupied key."""

    APPEND = "append"  # accumulate entries (episodic; subject to cap)
    REPLACE = "replace"  # last-write-wins; drop prior actives (working/flat)
    CONFIDENCE_GATED = "confidence_gated"  # write only if >= existing confidence
    LLM_MERGE = (
        "llm_merge"  # consolidate prior + new into one entry (caller-supplied text)
    )
    MERGE_ON_READ = "merge_on_read"  # store like APPEND; consolidate at read time
    REJECT = "reject"  # don't write; surface a ConflictInfo (interactive / RMW)


class MemoryType(str, Enum):
    """Classical memory type a taxonomy key belongs to."""

    WORKING = "working"  # transient scratchpad
    EPISODIC = "episodic"  # ordered event log
    SEMANTIC = "semantic"  # facts / preferences / knowledge
    PROCEDURAL = "procedural"  # skills / how-to / workflows


# Taxonomy-prefix -> memory type, most-specific first (first match wins).
# Anything unmatched is SEMANTIC (the catch-all for knowledge/preferences/etc.).
_TYPE_RULES: list[tuple[str, MemoryType]] = [
    ("context.current", MemoryType.WORKING),
    ("metrics.turn", MemoryType.WORKING),
    ("metrics.code", MemoryType.EPISODIC),
    ("experience", MemoryType.EPISODIC),
    ("workflow", MemoryType.PROCEDURAL),
    ("behavior", MemoryType.PROCEDURAL),
]

_TYPE_DEFAULT: dict[MemoryType, ConflictStrategy] = {
    MemoryType.WORKING: ConflictStrategy.REPLACE,
    MemoryType.EPISODIC: ConflictStrategy.APPEND,
    MemoryType.SEMANTIC: ConflictStrategy.CONFIDENCE_GATED,
    MemoryType.PROCEDURAL: ConflictStrategy.LLM_MERGE,
}


@dataclass
class ConflictInfo:
    """A machine-readable conflict surfaced by the REJECT strategy.

    Doubles as the signal an interactive CLI renders and as the payload a
    read-merge-write caller (MCP/plugin) inspects before re-issuing the write.
    """

    key: str
    namespace: str
    existing_content: str
    existing_confidence: float
    existing_timestamp: float
    incoming_content: str
    incoming_confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResolveOutcome:
    """Result of applying a strategy to a (existing, incoming) pair.

    ``action``:
      * ``"write"`` — persist ``entries`` (reproject top-level, then ``store.put``).
      * ``"noop"``  — keep existing as-is, skip the write (no commit).
      * ``"reject"`` — do not write; ``conflict`` describes the collision.
    """

    action: str
    entries: list[dict]
    conflict: ConflictInfo | None = None


def _coerce(value: str | ConflictStrategy) -> ConflictStrategy:
    """Coerce a string/enum into a :class:`ConflictStrategy` (case-insensitive)."""
    if isinstance(value, ConflictStrategy):
        return value
    return ConflictStrategy(str(value).strip().lower())


def make_entry(
    content: str,
    confidence: float = 1.0,
    timestamp: float = 0.0,
    source=None,
    status: str = "active",
) -> dict:
    """Build a single facet entry. ``source`` is omitted when None."""
    entry: dict = {
        "content": content,
        "confidence": confidence,
        "timestamp": timestamp,
        "status": status,
    }
    if source is not None:
        entry["source"] = source
    return entry


def _active(entries: list[dict]) -> list[dict]:
    """Active entries (fall back to all entries if none are explicitly active)."""
    act = [e for e in entries if e.get("status", "active") == "active"]
    return act or list(entries)


def project_entries(entries: list[dict]) -> dict:
    """Roll active entries up into the projected top-level fields.

    Returns ``{"content", "confidence", "timestamp"}``. The content join is
    byte-identical to the legacy ``"\\n\\n[update] "`` append for 2 entries.
    """
    if not entries:
        return {"content": "", "confidence": 1.0, "timestamp": 0.0}
    active = _active(entries)
    content = active[0].get("content", "")
    for e in active[1:]:
        content += f"{_UPDATE_SEP}{e.get('content', '')}"
    confidence = max((e.get("confidence", 1.0) for e in active), default=1.0)
    timestamp = max((e.get("timestamp", 0.0) for e in active), default=0.0)
    return {"content": content, "confidence": confidence, "timestamp": timestamp}


def upgrade_blob(existing: dict | None) -> dict | None:
    """Lazily lift a v1 blob (bare ``content``) to the v2 facet shape.

    Idempotent: a blob already at ``schema_version >= 2`` with an ``entries``
    list is returned unchanged. ``None`` stays ``None``. Non-dicts pass through
    defensively. Preserves ``related_keys`` and any extra metadata.
    """
    if not isinstance(existing, dict):
        return existing
    if existing.get("schema_version", 1) >= SCHEMA_VERSION and isinstance(
        existing.get("entries"), list
    ):
        return existing
    entry = make_entry(
        content=existing.get("content", ""),
        confidence=existing.get("confidence", 1.0),
        timestamp=existing.get("timestamp", 0.0),
        source=existing.get("source"),
    )
    upgraded = dict(existing)
    upgraded["entries"] = [entry]
    upgraded["schema_version"] = SCHEMA_VERSION
    return upgraded


def memory_type_for_key(key: str) -> MemoryType:
    """Map a taxonomy key to its memory type via the prefix rules."""
    k = (key or "").strip().lower()
    for prefix, mtype in _TYPE_RULES:
        if k == prefix or k.startswith(prefix + "."):
            return mtype
    return MemoryType.SEMANTIC


def default_strategy_for_key(key: str) -> ConflictStrategy:
    """The per-type default strategy for a key (the Phase-3 target default)."""
    return _TYPE_DEFAULT[memory_type_for_key(key)]


def resolve_policy(
    explicit: str | ConflictStrategy | None,
    key: str,
    *,
    path_provided: bool,
    env: str | None = None,
    use_type_defaults: bool = True,
) -> ConflictStrategy:
    """Resolve the effective strategy for a write.

    Precedence: explicit call arg > ``MEMOIR_MERGE_POLICY`` env > default.

    The default is the per-type table (:func:`default_strategy_for_key`) when
    ``use_type_defaults`` is True (the target behaviour). When False, the
    behaviour-neutral legacy split is used (``-p`` → APPEND, LLM branch →
    REPLACE) so the storage migration can land without changing behaviour.

    ``env`` overrides the process env var (mainly for tests). Pass ``""`` to
    force "no env value".
    """
    if explicit is not None:
        return _coerce(explicit)
    env_val = (os.environ.get(ENV_MERGE_POLICY, "") if env is None else env).strip()
    if env_val:
        return _coerce(env_val)
    if use_type_defaults:
        return default_strategy_for_key(key)
    return ConflictStrategy.APPEND if path_provided else ConflictStrategy.REPLACE


def _cap(entries: list[dict], max_entries: int | None) -> list[dict]:
    """Bound growth by keeping the most recent ``max_entries`` (drop oldest)."""
    if max_entries is None or max_entries <= 0 or len(entries) <= max_entries:
        return entries
    return entries[-max_entries:]


def _conflict_from(
    existing_v2: dict, new_entry: dict, key: str, namespace: str
) -> ConflictInfo:
    proj = project_entries(existing_v2.get("entries", []))
    return ConflictInfo(
        key=key,
        namespace=namespace,
        existing_content=proj["content"],
        existing_confidence=proj["confidence"],
        existing_timestamp=proj["timestamp"],
        incoming_content=new_entry.get("content", ""),
        incoming_confidence=new_entry.get("confidence", 1.0),
    )


def apply_strategy(
    strategy: ConflictStrategy,
    existing_v2: dict | None,
    new_entry: dict,
    *,
    key: str = "",
    namespace: str = "default",
    max_entries: int | None = None,
) -> ResolveOutcome:
    """Compute the resulting entries list for a write under ``strategy``.

    ``existing_v2`` must already be upgraded (via :func:`upgrade_blob`) or None.
    For ``LLM_MERGE`` the caller must have placed the consolidated text into
    ``new_entry["content"]`` *before* calling this (this module never calls an
    LLM). Detection is key-collision only: a non-empty ``existing_v2.entries``
    means a collision.
    """
    existing_entries = (existing_v2 or {}).get("entries") or []

    # No prior content at this key — nothing to resolve.
    if not existing_entries:
        return ResolveOutcome("write", [new_entry])

    if strategy == ConflictStrategy.REJECT:
        return ResolveOutcome(
            "reject",
            existing_entries,
            _conflict_from(existing_v2, new_entry, key, namespace),
        )

    if strategy in (ConflictStrategy.APPEND, ConflictStrategy.MERGE_ON_READ):
        return ResolveOutcome(
            "write", _cap([*existing_entries, new_entry], max_entries)
        )

    if strategy in (ConflictStrategy.REPLACE, ConflictStrategy.LLM_MERGE):
        # REPLACE: last-write-wins. LLM_MERGE: new_entry already holds the
        # consolidated text. Both collapse to a single entry; prior values
        # survive in git history. This keeps flat keys (metrics.*) length-1.
        return ResolveOutcome("write", [new_entry])

    if strategy == ConflictStrategy.CONFIDENCE_GATED:
        max_conf = max(
            (e.get("confidence", 1.0) for e in _active(existing_entries)), default=0.0
        )
        if new_entry.get("confidence", 1.0) >= max_conf:
            return ResolveOutcome("write", [new_entry])
        return ResolveOutcome("noop", existing_entries)

    raise ValueError(f"Unhandled merge strategy: {strategy!r}")


def read_project(blob, consolidator=None) -> str:
    """Resolve a stored blob to a single display string (merge-on-read).

    Deterministic by default (the projected content). When ``consolidator`` is
    supplied — a callable taking a list of active entry contents and returning a
    string, typically an LLM call wired by the caller — it is used only when
    there is more than one active entry. Pure: this module never calls it itself.
    """
    if not isinstance(blob, dict):
        return str(blob)
    entries = blob.get("entries")
    if not isinstance(entries, list) or not entries:
        return blob.get("content", "")
    active = _active(entries)
    if consolidator is not None and len(active) > 1:
        return consolidator([e.get("content", "") for e in active])
    return project_entries(entries)["content"]

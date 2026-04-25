"""Memory record shape used in the store snapshot and future memory APIs."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Memory(BaseModel):
    """A single memory as exposed by ``GET /api/store`` (and later
    ``GET /api/memory/<key>``).

    Built by the reader from the underlying Prolly-tree key/value; keeps
    the raw ``value`` dict so the UI can inspect metadata (e.g. author,
    timestamp) without another round-trip.
    """

    # Unknown fields accepted so the reader can add metadata without a
    # schema bump; tighten to ``extra='forbid'`` once it's fully typed.
    model_config = ConfigDict(extra="allow")

    # Full key as stored on the wire (``namespace:path``). Acts as the
    # stable identity for selection / drawer fetch.
    key: str
    # The namespace portion of the key (``default``, ``codebase:onboard``, …).
    namespace: str
    # The dotted semantic path within the namespace
    # (``workflow.coding.style``).
    path: str
    # Extracted textual content for display. ``None`` when the memory's
    # value is structured-only (timelines, locations).
    content: str | None = None
    # Raw JSON value from the store. Kept as arbitrary data so new value
    # shapes don't require a schema change.
    value: dict[str, Any] = Field(default_factory=dict)

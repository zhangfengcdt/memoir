"""Statistics endpoint response model.

The statistics payload is display-only and its inner shapes evolve as
the backend gains new metrics. We lock the top-level envelope and the
list of section names; inner section dicts use ``extra='allow'`` so a
new metric doesn't break the schema.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Section(BaseModel):
    """Permissive base — every stats section is a free-form dict."""

    model_config = ConfigDict(extra="allow")


class StatisticsBlock(BaseModel):
    """The eight known sections of the stats payload.

    ``extra="forbid"`` here means the Pydantic check fails if the
    backend ships a *new* top-level section without updating this model
    — that's intentional, so we notice and update the UI's tab list.
    """

    model_config = ConfigDict(extra="forbid")

    storage: dict[str, Any] = Field(default_factory=dict)
    tree_structure: dict[str, Any] = Field(default_factory=dict)
    versioning: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    performance: dict[str, Any] = Field(default_factory=dict)
    taxonomy: dict[str, Any] = Field(default_factory=dict)
    content: dict[str, Any] = Field(default_factory=dict)
    system: dict[str, Any] = Field(default_factory=dict)


class StatisticsResponse(BaseModel):
    """Response for ``GET /api/statistics``."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    statistics: StatisticsBlock
    generated_at: str
    store_path: str

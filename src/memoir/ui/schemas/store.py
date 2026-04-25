"""Store-read API response model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .memory import Memory  # noqa: TC001 — resolved at runtime by Pydantic


class StoreCommit(BaseModel):
    """A commit summary as embedded inside the ``/api/store`` response."""

    model_config = ConfigDict(extra="forbid")

    hash: str
    message: str


class StoreResponse(BaseModel):
    """Response for ``GET /api/store``.

    Unlike most other endpoints this one does not carry a top-level
    ``success`` flag for historical reasons; errors are signalled via HTTP
    status codes instead. That's intentional and not normalised here — the
    change would break the existing legacy UI.
    """

    # The legacy handler emits a transitional ``tree`` key (cross-namespace
    # prefix → count map) the reader builds for the old UI. We don't use it
    # in v2 but keep ``extra='allow'`` so the shape stays flexible.
    model_config = ConfigDict(extra="allow")

    store_path: str
    branches: list[str]
    current_branch: str
    commits: list[StoreCommit]
    # Flat map of namespace name → list of dotted paths. Useful for a
    # quick outline; the v2 Tree view builds a richer structure from
    # ``memories`` instead.
    namespaces: dict[str, Any] = Field(default_factory=dict)
    # Full memory list — keyed by ``{namespace}:{path}``. The v2 tree view
    # groups these by namespace and builds a hierarchy from the dotted paths.
    memories: list[Memory] = Field(default_factory=list)
    total_memories: int = 0

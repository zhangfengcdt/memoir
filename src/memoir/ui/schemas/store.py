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
    status codes instead.
    """

    # ``extra='allow'`` keeps the shape flexible — the reader still builds a
    # cross-namespace prefix → count tree that not every consumer needs.
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

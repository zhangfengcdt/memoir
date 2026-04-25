"""Store-read API response model."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


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

    # The legacy handler emits extra transitional keys (``tree``, ``memories``)
    # depending on which reader path it takes. Accept unknown fields so the
    # schema doesn't tighten the contract prematurely.
    model_config = ConfigDict(extra="allow")

    store_path: str
    branches: list[str]
    current_branch: str
    commits: list[StoreCommit]
    namespaces: dict[str, Any] = Field(default_factory=dict)
    total_memories: int = 0

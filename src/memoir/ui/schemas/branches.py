"""Branch-related API response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BranchesResponse(BaseModel):
    """Response for ``GET /api/branches``."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    branches: list[str]
    current: str


class CurrentBranchResponse(BaseModel):
    """Response for ``GET /api/current-branch``."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    branch: str
    commit: str

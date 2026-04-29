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


class BranchStatus(BaseModel):
    """Per-branch divergence info from ``BranchService.get_branches_status``."""

    model_config = ConfigDict(extra="forbid")

    name: str
    is_default: bool
    is_current: bool
    ahead: int
    behind: int
    # Number of default-namespace keys that would sync to the default branch
    # (additions + modifications, no deletions). This is what the UI's "N ahead"
    # pill should display — what would actually merge, not raw commit count.
    keys_ahead: int = 0
    # ``BranchService`` writes the date as ISO 8601 when available; ``None``
    # for empty branches.
    last_commit_date: str | None = None
    # ``True`` when an explicit sync marker has been written after the
    # branch tip — distinguishes a clean "merged into main" state from
    # a coincidence where a branch happens to be at the same commit.
    synced: bool = False


class BranchesStatusResponse(BaseModel):
    """Response for ``GET /api/branches-status``."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    default: str
    current: str
    branches: list[BranchStatus]

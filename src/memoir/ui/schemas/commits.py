"""Commit-related API response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Commit(BaseModel):
    """A single commit as returned by ``BranchService.get_commits``."""

    model_config = ConfigDict(extra="forbid")

    hash: str
    short_hash: str
    message: str
    author: str
    email: str
    # Unix seconds. Kept as int (not datetime) for wire stability; the UI
    # converts via new Date(timestamp * 1000).
    timestamp: int
    # Tag names pointing at this commit (no ``refs/tags/`` prefix).
    tags: list[str] = Field(default_factory=list)
    # Branch-head names pointing at this commit (no ``refs/heads/`` prefix).
    refs: list[str] = Field(default_factory=list)


class CommitsResponse(BaseModel):
    """Response for ``GET /api/commits``."""

    model_config = ConfigDict(extra="forbid")

    success: bool
    commits: list[Commit]
    branch: str

# SPDX-License-Identifier: Apache-2.0
"""
Pydantic response models for the memoir HTTP API.

These models are the single source of truth for the response shape of every
``/api/*`` endpoint consumed by ``src/memoir/ui/webapp`` (the React UI).
Handlers build a model instance and ship ``model.model_dump(mode='json')`` on
the wire — that way every field name, type, and optionality is enforced at
runtime, and frontend types in ``webapp/src/api/types.ts`` can be kept in
sync by inspection or (later) codegen.

Phase 1 covers the four endpoints the v2 command bar needs:
store, branches, commits, current-branch. Remaining endpoints will be
ported as the views that consume them land.
"""

from __future__ import annotations

from .branches import (
    BranchesResponse,
    BranchesStatusResponse,
    BranchStatus,
    CurrentBranchResponse,
)
from .commits import Commit, CommitsResponse
from .diff import Change, ChangeStats, CommitDiff, RangeDiffResponse
from .memory import Memory
from .statistics import StatisticsBlock, StatisticsResponse
from .store import StoreCommit, StoreResponse
from .timeline import LocationResponse, Place, TimelineResponse

__all__ = [
    "BranchStatus",
    "BranchesResponse",
    "BranchesStatusResponse",
    "Change",
    "ChangeStats",
    "Commit",
    "CommitDiff",
    "CommitsResponse",
    "CurrentBranchResponse",
    "LocationResponse",
    "Memory",
    "Place",
    "RangeDiffResponse",
    "StatisticsBlock",
    "StatisticsResponse",
    "StoreCommit",
    "StoreResponse",
    "TimelineResponse",
]

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

from .branches import BranchesResponse, CurrentBranchResponse
from .commits import Commit, CommitsResponse
from .memory import Memory
from .store import StoreCommit, StoreResponse

__all__ = [
    "BranchesResponse",
    "Commit",
    "CommitsResponse",
    "CurrentBranchResponse",
    "Memory",
    "StoreCommit",
    "StoreResponse",
]

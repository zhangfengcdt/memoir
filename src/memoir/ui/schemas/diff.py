"""Diff-related API response models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Change(BaseModel):
    """A single key-level change inside a commit.

    Matches the shape the server emits in ``_kv_diffs_to_changes``:
    every change has a ``path`` (namespace-stripped key) and a ``type``
    of added / deleted / modified. Content fields are populated
    asymmetrically depending on the type.
    """

    model_config = ConfigDict(extra="forbid")

    path: str
    type: Literal["added", "deleted", "modified"]
    old_content: str | None = None
    new_content: str | None = None


class ChangeStats(BaseModel):
    """Aggregate counts across ``Change`` entries for a single commit."""

    model_config = ConfigDict(extra="forbid")

    added: int = 0
    modified: int = 0
    deleted: int = 0


class CommitDiff(BaseModel):
    """One commit plus the changes it introduces against its first parent."""

    model_config = ConfigDict(extra="forbid")

    hash: str
    short_hash: str
    message: str
    author: str
    email: str
    timestamp: int
    changes: list[Change]
    stats: ChangeStats


class RangeDiffResponse(BaseModel):
    """Response for ``GET /api/commit-range-diff``.

    ``from`` and ``to`` are the commit refs the client requested; they
    may be short hashes, full hashes, or branch names — echoed back
    verbatim so the UI can display them without needing to resolve.
    """

    model_config = ConfigDict(extra="forbid")

    success: bool
    # ``from`` is a Python keyword — aliased at the schema level.
    from_ref: str
    to_ref: str
    commits: list[CommitDiff]

    @classmethod
    def from_legacy(cls, payload: dict) -> RangeDiffResponse:
        """Translate the wire-native keys (``from``/``to``) to the model."""
        return cls.model_validate(
            {
                "success": payload.get("success", False),
                "from_ref": payload.get("from", ""),
                "to_ref": payload.get("to", ""),
                "commits": payload.get("commits", []),
            }
        )

    def to_legacy(self) -> dict:
        """Emit the wire-native shape (``from``/``to`` rather than ``from_ref``)."""
        data = self.model_dump(mode="json")
        data["from"] = data.pop("from_ref")
        data["to"] = data.pop("to_ref")
        return data

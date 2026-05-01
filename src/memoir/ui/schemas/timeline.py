# SPDX-License-Identifier: Apache-2.0
"""Timeline + location response models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class TimelineResponse(BaseModel):
    """Response for ``GET /api/timeline``.

    ``timeline_data`` keys are ``YYYYMMDD`` strings; values are the
    rendered event text for that day. ``summary`` is a free-form
    LLM-or-fallback overview.
    """

    model_config = ConfigDict(extra="forbid")

    success: bool
    summary: str | None = None
    timeline_data: dict[str, str]
    start_date: str | None = None
    end_date: str | None = None


class Place(BaseModel):
    """One place memento."""

    model_config = ConfigDict(extra="forbid")

    name: str
    content: str


class LocationResponse(BaseModel):
    """Response for ``GET /api/location``.

    ``location_data`` keys are normalised slugs (e.g. ``san_francisco``);
    values carry both a display name and rendered content.
    """

    model_config = ConfigDict(extra="forbid")

    success: bool
    summary: str | None = None
    location_data: dict[str, Place]

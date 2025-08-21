"""
Memento module for specialized memory collections.

This module contains memento classes that manage specific types of memories:
- Location: Spatial and geographical memories
- Timeline: Temporal and chronological memories
- Profile: Personal and identity-related memories

These classes represent collections of memories organized around specific themes,
rather than traditional "managers" - they are memory repositories.
"""

# Also provide direct access to the full class names
from .location import LocationMemento
from .location import LocationMemento as Location
from .profile import ProfileMemento
from .profile import ProfileMemento as Profile
from .timeline import TimelineMemento
from .timeline import TimelineMemento as Timeline

__all__ = [
    "Location",
    "LocationMemento",
    "Profile",
    "ProfileMemento",
    "Timeline",
    "TimelineMemento",
]

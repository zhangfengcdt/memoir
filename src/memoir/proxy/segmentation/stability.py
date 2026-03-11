"""
Sliding Window Stability Check.

Stage 3 of the block segmentation pipeline. Compares current request to
previous requests to identify frozen vs liquid blocks.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StabilityResult:
    """Result of stability analysis for a text segment."""

    start: int
    end: int
    is_frozen: bool
    stability_score: float  # 0.0 (liquid) to 1.0 (frozen)
    hash: str
    consecutive_matches: int


@dataclass
class SessionHistory:
    """Tracks prompt history for a session."""

    session_id: str
    prompts: list[str] = field(default_factory=list)
    segment_hashes: list[dict[str, str]] = field(default_factory=list)
    max_history: int = 10


class StabilityAnalyzer:
    """
    Analyzes text stability across requests.

    Compares current request to previous session requests to identify:
    - Frozen blocks: Text identical across requests (promote to Tier 1/2)
    - Liquid blocks: Text that changes (shift to Dynamic Suffix)
    """

    # Minimum segment size for analysis
    MIN_SEGMENT_SIZE = 100

    # Window size for sliding comparison
    WINDOW_SIZE = 500

    # Threshold for considering a block "frozen"
    FROZEN_THRESHOLD = 0.95

    def __init__(self) -> None:
        """Initialize the stability analyzer."""
        self._sessions: dict[str, SessionHistory] = {}

    def get_or_create_session(self, session_id: str) -> SessionHistory:
        """
        Get or create a session history.

        Args:
            session_id: Unique identifier for the session.

        Returns:
            SessionHistory object for the session.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionHistory(session_id=session_id)
        return self._sessions[session_id]

    def analyze(
        self,
        text: str,
        session_id: str,
        segment_boundaries: Optional[list[tuple[int, int]]] = None,
    ) -> list[StabilityResult]:
        """
        Analyze text stability for the given session.

        Args:
            text: The current prompt text.
            session_id: Session identifier for history tracking.
            segment_boundaries: Optional pre-defined segment boundaries.

        Returns:
            List of StabilityResult objects for each segment.
        """
        session = self.get_or_create_session(session_id)
        results: list[StabilityResult] = []

        # Generate segment boundaries if not provided
        if segment_boundaries is None:
            segment_boundaries = self._generate_boundaries(text)

        # Analyze each segment
        current_hashes: dict[str, str] = {}
        for start, end in segment_boundaries:
            segment = text[start:end]
            segment_hash = self._hash_segment(segment)
            current_hashes[f"{start}:{end}"] = segment_hash

            # Count consecutive matches in history
            consecutive = 0
            for prev_hashes in reversed(session.segment_hashes):
                # Check if any previous segment had the same hash
                if segment_hash in prev_hashes.values():
                    consecutive += 1
                else:
                    break

            # Calculate stability score
            stability_score = min(1.0, consecutive / max(1, len(session.prompts)))
            is_frozen = stability_score >= self.FROZEN_THRESHOLD

            results.append(
                StabilityResult(
                    start=start,
                    end=end,
                    is_frozen=is_frozen,
                    stability_score=stability_score,
                    hash=segment_hash,
                    consecutive_matches=consecutive,
                )
            )

        # Update session history
        session.prompts.append(text)
        session.segment_hashes.append(current_hashes)

        # Trim history if needed
        if len(session.prompts) > session.max_history:
            session.prompts = session.prompts[-session.max_history :]
            session.segment_hashes = session.segment_hashes[-session.max_history :]

        return results

    def _generate_boundaries(self, text: str) -> list[tuple[int, int]]:
        """
        Generate segment boundaries using sliding window.

        Args:
            text: The text to segment.

        Returns:
            List of (start, end) tuples.
        """
        boundaries: list[tuple[int, int]] = []
        pos = 0

        while pos < len(text):
            end = min(pos + self.WINDOW_SIZE, len(text))
            if end - pos >= self.MIN_SEGMENT_SIZE:
                boundaries.append((pos, end))
            pos = end

        return boundaries

    def _hash_segment(self, segment: str) -> str:
        """
        Generate a hash for a text segment.

        Args:
            segment: The text segment to hash.

        Returns:
            Hash string.
        """
        # Normalize whitespace before hashing for better matching
        normalized = " ".join(segment.split())
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]

    def clear_session(self, session_id: str) -> None:
        """
        Clear history for a session.

        Args:
            session_id: Session identifier to clear.
        """
        if session_id in self._sessions:
            del self._sessions[session_id]

    def get_frozen_ranges(
        self, results: list[StabilityResult]
    ) -> list[tuple[int, int]]:
        """
        Extract frozen ranges from stability results.

        Args:
            results: List of StabilityResult objects.

        Returns:
            List of (start, end) tuples for frozen segments.
        """
        return [(r.start, r.end) for r in results if r.is_frozen]

    def get_liquid_ranges(
        self, results: list[StabilityResult]
    ) -> list[tuple[int, int]]:
        """
        Extract liquid ranges from stability results.

        Args:
            results: List of StabilityResult objects.

        Returns:
            List of (start, end) tuples for liquid segments.
        """
        return [(r.start, r.end) for r in results if not r.is_frozen]

"""
Semantic Anchor Extraction.

Stage 2 (fallback) of the block segmentation pipeline. Used when explicit
delimiters are absent. Employs heuristic analysis to identify content tiers.
"""

import hashlib
from dataclasses import dataclass
from typing import ClassVar, Optional


@dataclass
class SemanticAnchor:
    """A semantically identified anchor point in the prompt."""

    start: int
    end: int
    tier: int
    confidence: float  # 0.0 to 1.0
    anchor_type: str  # "boilerplate", "instruction_boundary", "pattern"


class SemanticAnchorExtractor:
    """
    Extracts semantic anchors from unstructured prompts.

    When explicit delimiters are absent, uses heuristic analysis:
    - Boilerplate hashing against known identity database
    - Instruction boundary detection via common phrases
    """

    # Known instruction boundary phrases
    INSTRUCTION_PHRASES: ClassVar[list[str]] = [
        "You are an assistant",
        "You are a helpful",
        "Your task is to",
        "Your role is to",
        "As an AI assistant",
        "I want you to act as",
        "You will be",
        "Your job is to",
    ]

    # Boilerplate check window size
    BOILERPLATE_WINDOW: ClassVar[int] = 2000

    # Minimum similarity threshold for boilerplate matching
    BOILERPLATE_THRESHOLD: ClassVar[float] = 0.90

    def __init__(self) -> None:
        """Initialize the semantic anchor extractor."""
        self._known_identities: dict[str, str] = {}  # hash -> identity name
        self._instruction_phrases_lower = [p.lower() for p in self.INSTRUCTION_PHRASES]

    def register_identity(self, name: str, boilerplate: str) -> str:
        """
        Register a known identity boilerplate for matching.

        Args:
            name: Name/identifier for this boilerplate.
            boilerplate: The boilerplate text (first ~2000 chars of identity).

        Returns:
            The hash of the registered boilerplate.
        """
        text_hash = self._hash_text(boilerplate[: self.BOILERPLATE_WINDOW])
        self._known_identities[text_hash] = name
        return text_hash

    def extract(self, text: str) -> list[SemanticAnchor]:
        """
        Extract semantic anchors from the given text.

        Args:
            text: The prompt text to analyze.

        Returns:
            List of SemanticAnchor objects sorted by position.
        """
        anchors: list[SemanticAnchor] = []

        # Check for boilerplate match (Tier 1)
        boilerplate_anchor = self._check_boilerplate(text)
        if boilerplate_anchor:
            anchors.append(boilerplate_anchor)

        # Find instruction boundaries
        instruction_anchors = self._find_instruction_boundaries(text)
        anchors.extend(instruction_anchors)

        # Sort by position
        anchors.sort(key=lambda a: a.start)
        return anchors

    def _hash_text(self, text: str) -> str:
        """Generate a hash for the given text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _check_boilerplate(self, text: str) -> Optional[SemanticAnchor]:
        """
        Check if the text starts with known boilerplate.

        Args:
            text: The prompt text to analyze.

        Returns:
            SemanticAnchor if boilerplate match found, None otherwise.
        """
        window = text[: self.BOILERPLATE_WINDOW]
        window_hash = self._hash_text(window)

        if window_hash in self._known_identities:
            return SemanticAnchor(
                start=0,
                end=len(window),
                tier=1,
                confidence=1.0,
                anchor_type="boilerplate",
            )

        # Check for substring similarity with registered identities
        # This is a simplified check - production would use more sophisticated matching
        for _known_hash in self._known_identities:
            # For now, just check exact hash match
            # TODO: Implement fuzzy substring matching for >90% similarity
            pass

        return None

    def _find_instruction_boundaries(self, text: str) -> list[SemanticAnchor]:
        """
        Find instruction boundary phrases in the text.

        Args:
            text: The prompt text to analyze.

        Returns:
            List of SemanticAnchor objects for instruction boundaries.
        """
        anchors: list[SemanticAnchor] = []
        text_lower = text.lower()

        for phrase in self._instruction_phrases_lower:
            idx = text_lower.find(phrase)
            if idx != -1:
                # Find the end of the sentence/paragraph
                end_idx = idx + len(phrase)
                for end_char in [".", "\n\n", "\n"]:
                    next_end = text.find(end_char, end_idx)
                    if next_end != -1:
                        end_idx = next_end + len(end_char)
                        break

                anchors.append(
                    SemanticAnchor(
                        start=idx,
                        end=end_idx,
                        tier=1,
                        confidence=0.8,
                        anchor_type="instruction_boundary",
                    )
                )

        return anchors

    def estimate_tier(self, text: str, start: int, end: int) -> tuple[int, float]:
        """
        Estimate the tier for a given text segment.

        Args:
            text: The full prompt text.
            start: Start index of the segment.
            end: End index of the segment.

        Returns:
            Tuple of (tier, confidence).
        """
        segment = text[start:end].lower()

        # Check for Tier 1 indicators
        tier1_indicators = ["you are", "your role", "system", "assistant"]
        for indicator in tier1_indicators:
            if indicator in segment[:500]:
                return (1, 0.7)

        # Check for Tier 3 indicators
        tier3_indicators = ["current time", "timestamp", "user:", "human:"]
        for indicator in tier3_indicators:
            if indicator in segment:
                return (3, 0.8)

        # Default to Tier 2
        return (2, 0.5)

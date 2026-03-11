"""
Structural Delimiter Detection.

Stage 1 of the block segmentation pipeline. Scans for common agentic markers
that separate instructions from memory.
"""

import re
from dataclasses import dataclass
from typing import ClassVar, Optional


@dataclass
class DelimiterMatch:
    """A detected delimiter in the prompt."""

    pattern: str
    start: int
    end: int
    tier: int  # 1, 2, or 3
    label: str


class DelimiterDetector:
    """
    Detects structural delimiters in prompts.

    Scans for common agentic markers used to separate different sections
    of agent prompts (system, policy, context, tools, memory, etc.).
    """

    # Tier 1 patterns - Identity/permanent content
    TIER1_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"\[SYSTEM\]", "SYSTEM"),
        (r"\[POLICY\]", "POLICY"),
        (r"#\s*SOUL", "SOUL"),
        (r"#\s*AGENTS", "AGENTS"),
        (r"\[TOOLS\]", "TOOLS"),
        (r"<tools>", "TOOLS_XML"),
        (r'"tools"\s*:\s*\[', "TOOLS_JSON"),
    ]

    # Tier 2 patterns - Context/semi-stable content
    TIER2_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"\[CONTEXT\]", "CONTEXT"),
        (r"\[MEMORY\]", "MEMORY"),
        (r"#\s*WORKSPACE", "WORKSPACE"),
        (r"\[PROJECT\]", "PROJECT"),
        (r"<context>", "CONTEXT_XML"),
    ]

    # Tier 3 patterns - Dynamic content
    TIER3_PATTERNS: ClassVar[list[tuple[str, str]]] = [
        (r"\[MESSAGES\]", "MESSAGES"),
        (r"\[HISTORY\]", "HISTORY"),
        (r"\[OUTPUT\]", "OUTPUT"),
        (r"Current Time:", "TIMESTAMP"),
        (r"<user>", "USER_MESSAGE"),
        (r"<assistant>", "ASSISTANT_MESSAGE"),
    ]

    def __init__(self) -> None:
        """Initialize the delimiter detector with compiled regex patterns."""
        self._tier1_compiled = [
            (re.compile(p, re.IGNORECASE), label) for p, label in self.TIER1_PATTERNS
        ]
        self._tier2_compiled = [
            (re.compile(p, re.IGNORECASE), label) for p, label in self.TIER2_PATTERNS
        ]
        self._tier3_compiled = [
            (re.compile(p, re.IGNORECASE), label) for p, label in self.TIER3_PATTERNS
        ]

    def detect(self, text: str) -> list[DelimiterMatch]:
        """
        Detect all structural delimiters in the given text.

        Args:
            text: The prompt text to analyze.

        Returns:
            List of DelimiterMatch objects sorted by position.
        """
        matches: list[DelimiterMatch] = []

        # Check all tier patterns
        for pattern, label in self._tier1_compiled:
            for match in pattern.finditer(text):
                matches.append(
                    DelimiterMatch(
                        pattern=pattern.pattern,
                        start=match.start(),
                        end=match.end(),
                        tier=1,
                        label=label,
                    )
                )

        for pattern, label in self._tier2_compiled:
            for match in pattern.finditer(text):
                matches.append(
                    DelimiterMatch(
                        pattern=pattern.pattern,
                        start=match.start(),
                        end=match.end(),
                        tier=2,
                        label=label,
                    )
                )

        for pattern, label in self._tier3_compiled:
            for match in pattern.finditer(text):
                matches.append(
                    DelimiterMatch(
                        pattern=pattern.pattern,
                        start=match.start(),
                        end=match.end(),
                        tier=3,
                        label=label,
                    )
                )

        # Sort by position
        matches.sort(key=lambda m: m.start)
        return matches

    def detect_first(
        self, text: str, tier: Optional[int] = None
    ) -> Optional[DelimiterMatch]:
        """
        Detect the first delimiter, optionally filtered by tier.

        Args:
            text: The prompt text to analyze.
            tier: Optional tier to filter by (1, 2, or 3).

        Returns:
            The first matching delimiter or None.
        """
        matches = self.detect(text)
        if tier is not None:
            matches = [m for m in matches if m.tier == tier]
        return matches[0] if matches else None

    def has_structure(self, text: str) -> bool:
        """
        Check if the text has recognizable structural delimiters.

        Args:
            text: The prompt text to analyze.

        Returns:
            True if any delimiters were found.
        """
        return len(self.detect(text)) > 0

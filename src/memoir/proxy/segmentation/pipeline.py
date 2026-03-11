"""
Segmentation Pipeline.

Orchestrates the three-stage block segmentation process to transform
unstructured prompts into tiered ProllyTree-compatible blocks.
"""

from dataclasses import dataclass, field
from typing import Optional

from memoir.proxy.segmentation.delimiter import DelimiterDetector, DelimiterMatch
from memoir.proxy.segmentation.semantic import SemanticAnchor, SemanticAnchorExtractor
from memoir.proxy.segmentation.stability import StabilityAnalyzer, StabilityResult


@dataclass
class PromptBlock:
    """A segmented block of the prompt."""

    content: str
    start: int
    end: int
    tier: int  # 1, 2, or 3
    label: str
    confidence: float
    is_frozen: bool
    hash: Optional[str] = None


@dataclass
class SegmentedPrompt:
    """Result of prompt segmentation."""

    original: str
    blocks: list[PromptBlock] = field(default_factory=list)
    tier1_content: str = ""  # Identity prefix
    tier2_content: str = ""  # Context branch
    tier3_content: str = ""  # Dynamic suffix

    @property
    def stable_prefix(self) -> str:
        """Return the combined stable prefix (Tier 1 + Tier 2)."""
        return self.tier1_content + self.tier2_content

    @property
    def cache_key_content(self) -> str:
        """Return content used for cache key generation."""
        return self.tier1_content + self.tier2_content

    def get_blocks_by_tier(self, tier: int) -> list[PromptBlock]:
        """Get all blocks for a specific tier."""
        return [b for b in self.blocks if b.tier == tier]


class SegmentationPipeline:
    """
    Three-stage segmentation pipeline.

    Stages:
        1. Structural Delimiter Detection
        2. Semantic Anchor Extraction (fallback)
        3. Sliding Window Stability Check
    """

    def __init__(
        self,
        delimiter_detector: Optional[DelimiterDetector] = None,
        semantic_extractor: Optional[SemanticAnchorExtractor] = None,
        stability_analyzer: Optional[StabilityAnalyzer] = None,
    ) -> None:
        """
        Initialize the segmentation pipeline.

        Args:
            delimiter_detector: Optional custom delimiter detector.
            semantic_extractor: Optional custom semantic extractor.
            stability_analyzer: Optional custom stability analyzer.
        """
        self.delimiter_detector = delimiter_detector or DelimiterDetector()
        self.semantic_extractor = semantic_extractor or SemanticAnchorExtractor()
        self.stability_analyzer = stability_analyzer or StabilityAnalyzer()

    def segment(
        self,
        text: str,
        session_id: Optional[str] = None,
    ) -> SegmentedPrompt:
        """
        Segment a prompt into tiered blocks.

        Args:
            text: The prompt text to segment.
            session_id: Optional session ID for stability tracking.

        Returns:
            SegmentedPrompt with categorized blocks.
        """
        result = SegmentedPrompt(original=text)

        # Stage 1: Structural delimiter detection
        delimiters = self.delimiter_detector.detect(text)

        if delimiters:
            # Use delimiter-based segmentation
            blocks = self._segment_by_delimiters(text, delimiters)
        else:
            # Stage 2: Fallback to semantic anchor extraction
            anchors = self.semantic_extractor.extract(text)
            if anchors:
                blocks = self._segment_by_anchors(text, anchors)
            else:
                # No structure found - treat as single block
                blocks = [
                    PromptBlock(
                        content=text,
                        start=0,
                        end=len(text),
                        tier=2,  # Default to Tier 2
                        label="UNSTRUCTURED",
                        confidence=0.3,
                        is_frozen=False,
                    )
                ]

        # Stage 3: Stability analysis (if session tracking enabled)
        if session_id:
            boundaries = [(b.start, b.end) for b in blocks]
            stability_results = self.stability_analyzer.analyze(
                text, session_id, boundaries
            )
            blocks = self._apply_stability(blocks, stability_results)

        # Populate result
        result.blocks = blocks
        result.tier1_content = "".join(b.content for b in blocks if b.tier == 1)
        result.tier2_content = "".join(b.content for b in blocks if b.tier == 2)
        result.tier3_content = "".join(b.content for b in blocks if b.tier == 3)

        return result

    def _segment_by_delimiters(
        self, text: str, delimiters: list[DelimiterMatch]
    ) -> list[PromptBlock]:
        """
        Create blocks based on detected delimiters.

        Args:
            text: The original text.
            delimiters: Detected delimiter matches.

        Returns:
            List of PromptBlock objects.
        """
        blocks: list[PromptBlock] = []
        last_end = 0

        for i, delimiter in enumerate(delimiters):
            # Handle text before this delimiter
            if delimiter.start > last_end:
                # Determine tier for gap content
                prev_tier = delimiters[i - 1].tier if i > 0 else 1
                blocks.append(
                    PromptBlock(
                        content=text[last_end : delimiter.start],
                        start=last_end,
                        end=delimiter.start,
                        tier=prev_tier,
                        label=f"CONTENT_{prev_tier}",
                        confidence=0.9,
                        is_frozen=False,
                    )
                )

            # Find the end of this section (next delimiter or end of text)
            if i + 1 < len(delimiters):
                section_end = delimiters[i + 1].start
            else:
                section_end = len(text)

            blocks.append(
                PromptBlock(
                    content=text[delimiter.start : section_end],
                    start=delimiter.start,
                    end=section_end,
                    tier=delimiter.tier,
                    label=delimiter.label,
                    confidence=1.0,
                    is_frozen=False,
                )
            )
            last_end = section_end

        return blocks

    def _segment_by_anchors(
        self, text: str, anchors: list[SemanticAnchor]
    ) -> list[PromptBlock]:
        """
        Create blocks based on semantic anchors.

        Args:
            text: The original text.
            anchors: Detected semantic anchors.

        Returns:
            List of PromptBlock objects.
        """
        blocks: list[PromptBlock] = []
        last_end = 0

        for anchor in anchors:
            # Handle text before this anchor
            if anchor.start > last_end:
                tier, conf = self.semantic_extractor.estimate_tier(
                    text, last_end, anchor.start
                )
                blocks.append(
                    PromptBlock(
                        content=text[last_end : anchor.start],
                        start=last_end,
                        end=anchor.start,
                        tier=tier,
                        label=f"INFERRED_{tier}",
                        confidence=conf,
                        is_frozen=False,
                    )
                )

            # Add the anchor block
            blocks.append(
                PromptBlock(
                    content=text[anchor.start : anchor.end],
                    start=anchor.start,
                    end=anchor.end,
                    tier=anchor.tier,
                    label=anchor.anchor_type.upper(),
                    confidence=anchor.confidence,
                    is_frozen=False,
                )
            )
            last_end = anchor.end

        # Handle remaining text
        if last_end < len(text):
            blocks.append(
                PromptBlock(
                    content=text[last_end:],
                    start=last_end,
                    end=len(text),
                    tier=3,  # Trailing content is usually dynamic
                    label="TRAILING",
                    confidence=0.6,
                    is_frozen=False,
                )
            )

        return blocks

    def _apply_stability(
        self, blocks: list[PromptBlock], stability_results: list[StabilityResult]
    ) -> list[PromptBlock]:
        """
        Apply stability analysis results to blocks.

        Args:
            blocks: The segmented blocks.
            stability_results: Stability analysis results.

        Returns:
            Updated blocks with stability information.
        """
        # Create a map of stability results by position
        stability_map = {(r.start, r.end): r for r in stability_results}

        for block in blocks:
            key = (block.start, block.end)
            if key in stability_map:
                result = stability_map[key]
                block.is_frozen = result.is_frozen
                block.hash = result.hash

                # Promote frozen blocks to higher tiers
                # Frozen Tier 3 -> Tier 2, Frozen Tier 2 stays
                if result.is_frozen and block.tier == 3:
                    block.tier = 2

        return blocks

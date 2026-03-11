"""
Block Segmentation Pipeline.

Transforms unstructured prompts into tiered ProllyTree-compatible blocks:
    - Tier 1 (Identity): Permanent prefix (SOUL, AGENTS, tools)
    - Tier 2 (Context): Semi-stable branch (project files, heartbeat)
    - Tier 3 (Dynamic): Unstable suffix (timestamps, messages)
"""

from memoir.proxy.segmentation.delimiter import DelimiterDetector
from memoir.proxy.segmentation.pipeline import SegmentationPipeline, SegmentedPrompt
from memoir.proxy.segmentation.semantic import SemanticAnchorExtractor
from memoir.proxy.segmentation.stability import StabilityAnalyzer

__all__ = [
    "DelimiterDetector",
    "SegmentationPipeline",
    "SegmentedPrompt",
    "SemanticAnchorExtractor",
    "StabilityAnalyzer",
]

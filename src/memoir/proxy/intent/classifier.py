"""
Intent Classification.

Analyzes request intent signatures for optimal model routing.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Optional


class IntentCategory(Enum):
    """Categories of request intent."""

    HIGH_REASONING = "high_reasoning"  # Complex coding, analysis
    MEDIUM_REASONING = "medium_reasoning"  # General assistance
    LOW_REASONING = "low_reasoning"  # Simple extraction, formatting
    HEARTBEAT = "heartbeat"  # Status checks, keep-alive
    TOOL_CALL = "tool_call"  # Tool/function execution


@dataclass
class Intent:
    """Classified intent for a request."""

    category: IntentCategory
    confidence: float  # 0.0 to 1.0
    signals: list[str]  # Detected signal phrases/patterns
    estimated_complexity: int  # 1-10 scale
    requires_tools: bool


class IntentClassifier:
    """
    Classifies request intent for model routing optimization.

    Uses pattern matching and heuristics to determine the computational
    complexity of a request, enabling cost-optimized model selection.
    """

    # High reasoning indicators
    HIGH_REASONING_PATTERNS: ClassVar[list[str]] = [
        r"implement\s+(?:a|the|this)",
        r"write\s+(?:a|the|this)\s+\w+\s+(?:function|class|module)",
        r"design\s+(?:a|the|this)",
        r"architect",
        r"refactor",
        r"optimize\s+(?:the|this)",
        r"debug\s+(?:the|this|why)",
        r"analyze\s+(?:the|this)",
        r"explain\s+(?:how|why|the)",
        r"create\s+(?:a|the)\s+(?:complex|detailed)",
    ]

    # Medium reasoning indicators
    MEDIUM_REASONING_PATTERNS: ClassVar[list[str]] = [
        r"help\s+(?:me|with)",
        r"can\s+you",
        r"how\s+(?:do|can|should)\s+I",
        r"what\s+(?:is|are|should)",
        r"summarize",
        r"describe",
        r"compare",
        r"list\s+(?:the|all)",
    ]

    # Low reasoning / extraction indicators
    LOW_REASONING_PATTERNS: ClassVar[list[str]] = [
        r"extract\s+(?:the|all)",
        r"parse\s+(?:the|this)",
        r"format\s+(?:the|this)",
        r"convert\s+(?:the|this)",
        r"translate\s+(?:the|this)",
        r"count\s+(?:the|how)",
        r"find\s+(?:the|all)",
    ]

    # Heartbeat / status check indicators
    HEARTBEAT_PATTERNS: ClassVar[list[str]] = [
        r"check\s+(?:for|if)",
        r"any\s+(?:new|updates|messages)",
        r"status\s+(?:of|check|update)",
        r"ping",
        r"heartbeat",
        r"keep\s*alive",
        r"are\s+you\s+(?:there|available|ready)",
    ]

    # Tool call indicators
    TOOL_PATTERNS: ClassVar[list[str]] = [
        r"use\s+(?:the|a)\s+\w+\s+tool",
        r"call\s+(?:the|a)\s+function",
        r"run\s+(?:the|a)\s+command",
        r"execute",
        r"invoke",
    ]

    def __init__(self) -> None:
        """Initialize the intent classifier."""
        self._high_compiled = [
            re.compile(p, re.IGNORECASE) for p in self.HIGH_REASONING_PATTERNS
        ]
        self._medium_compiled = [
            re.compile(p, re.IGNORECASE) for p in self.MEDIUM_REASONING_PATTERNS
        ]
        self._low_compiled = [
            re.compile(p, re.IGNORECASE) for p in self.LOW_REASONING_PATTERNS
        ]
        self._heartbeat_compiled = [
            re.compile(p, re.IGNORECASE) for p in self.HEARTBEAT_PATTERNS
        ]
        self._tool_compiled = [re.compile(p, re.IGNORECASE) for p in self.TOOL_PATTERNS]

    def classify(self, text: str, context: Optional[dict] = None) -> Intent:
        """
        Classify the intent of a request.

        Args:
            text: The request text to classify.
            context: Optional context dict with additional signals.

        Returns:
            Intent with category, confidence, and metadata.
        """
        signals: list[str] = []
        scores: dict[IntentCategory, float] = {
            IntentCategory.HIGH_REASONING: 0.0,
            IntentCategory.MEDIUM_REASONING: 0.0,
            IntentCategory.LOW_REASONING: 0.0,
            IntentCategory.HEARTBEAT: 0.0,
            IntentCategory.TOOL_CALL: 0.0,
        }

        # Check for heartbeat patterns first (short-circuit)
        for pattern in self._heartbeat_compiled:
            if pattern.search(text):
                signals.append(f"heartbeat:{pattern.pattern}")
                scores[IntentCategory.HEARTBEAT] += 2.0

        # Check for high reasoning
        for pattern in self._high_compiled:
            if pattern.search(text):
                signals.append(f"high:{pattern.pattern}")
                scores[IntentCategory.HIGH_REASONING] += 1.5

        # Check for medium reasoning
        for pattern in self._medium_compiled:
            if pattern.search(text):
                signals.append(f"medium:{pattern.pattern}")
                scores[IntentCategory.MEDIUM_REASONING] += 1.0

        # Check for low reasoning
        for pattern in self._low_compiled:
            if pattern.search(text):
                signals.append(f"low:{pattern.pattern}")
                scores[IntentCategory.LOW_REASONING] += 1.0

        # Check for tool usage
        requires_tools = False
        for pattern in self._tool_compiled:
            if pattern.search(text):
                signals.append(f"tool:{pattern.pattern}")
                scores[IntentCategory.TOOL_CALL] += 1.0
                requires_tools = True

        # Additional heuristics based on text length
        text_length = len(text)
        if text_length < 50:
            scores[IntentCategory.HEARTBEAT] += 0.5
            scores[IntentCategory.LOW_REASONING] += 0.3
        elif text_length > 500:
            scores[IntentCategory.HIGH_REASONING] += 0.5

        # Context-based adjustments
        if context:
            if context.get("has_code_block"):
                scores[IntentCategory.HIGH_REASONING] += 1.0
            if context.get("has_tool_output"):
                scores[IntentCategory.MEDIUM_REASONING] += 0.5

        # Find the winning category
        max_score = max(scores.values())
        if max_score == 0:
            # Default to medium reasoning
            category = IntentCategory.MEDIUM_REASONING
            confidence = 0.3
        else:
            category = max(scores, key=lambda k: scores[k])
            # Normalize confidence
            total_score = sum(scores.values())
            confidence = max_score / total_score if total_score > 0 else 0.5

        # Estimate complexity (1-10)
        complexity = self._estimate_complexity(text, category, signals)

        return Intent(
            category=category,
            confidence=min(1.0, confidence),
            signals=signals[:10],  # Limit stored signals
            estimated_complexity=complexity,
            requires_tools=requires_tools,
        )

    def _estimate_complexity(
        self, text: str, category: IntentCategory, signals: list[str]
    ) -> int:
        """
        Estimate task complexity on a 1-10 scale.

        Args:
            text: The request text.
            category: Classified category.
            signals: Detected signals.

        Returns:
            Complexity score 1-10.
        """
        base_complexity = {
            IntentCategory.HIGH_REASONING: 7,
            IntentCategory.MEDIUM_REASONING: 5,
            IntentCategory.LOW_REASONING: 3,
            IntentCategory.HEARTBEAT: 1,
            IntentCategory.TOOL_CALL: 4,
        }

        complexity = base_complexity.get(category, 5)

        # Adjust based on text length
        if len(text) > 1000:
            complexity += 1
        if len(text) > 2000:
            complexity += 1

        # Adjust based on signal count
        if len(signals) > 5:
            complexity += 1

        return min(10, max(1, complexity))

    def is_cacheable(self, intent: Intent) -> bool:
        """
        Determine if a request is a good candidate for caching.

        Args:
            intent: The classified intent.

        Returns:
            True if the request benefits from caching.
        """
        # Heartbeats and low-reasoning tasks benefit most from caching
        return intent.category in [
            IntentCategory.HEARTBEAT,
            IntentCategory.LOW_REASONING,
        ]

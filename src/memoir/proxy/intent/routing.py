"""
Model Routing.

Routes requests to cost-appropriate models based on intent classification.
"""

from dataclasses import dataclass
from typing import ClassVar, Optional

from memoir.proxy.intent.classifier import Intent, IntentCategory


@dataclass
class ModelSpec:
    """Specification for an LLM model."""

    provider: str  # "anthropic", "google", "openai"
    model_id: str  # e.g., "claude-3-5-sonnet-20241022"
    display_name: str
    cost_per_1k_input: float  # USD
    cost_per_1k_output: float  # USD
    max_tokens: int
    supports_caching: bool = True
    reasoning_tier: int = 5  # 1-10, higher = more capable


@dataclass
class RoutingDecision:
    """Result of model routing decision."""

    selected_model: ModelSpec
    fallback_model: Optional[ModelSpec]
    reason: str
    estimated_cost: float  # Estimated cost in USD
    confidence: float


class ModelRouter:
    """
    Routes requests to optimal models based on intent and cost.

    Implements intent-based model arbitrage to minimize costs while
    maintaining quality for complex tasks.
    """

    # Default model configurations
    DEFAULT_MODELS: ClassVar[dict[str, ModelSpec]] = {
        # Anthropic models
        "claude-sonnet": ModelSpec(
            provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            display_name="Claude Sonnet 4",
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
            max_tokens=200000,
            supports_caching=True,
            reasoning_tier=8,
        ),
        "claude-haiku": ModelSpec(
            provider="anthropic",
            model_id="claude-3-5-haiku-20241022",
            display_name="Claude 3.5 Haiku",
            cost_per_1k_input=0.0008,
            cost_per_1k_output=0.004,
            max_tokens=200000,
            supports_caching=True,
            reasoning_tier=5,
        ),
        # Google models
        "gemini-pro": ModelSpec(
            provider="google",
            model_id="gemini-1.5-pro",
            display_name="Gemini 1.5 Pro",
            cost_per_1k_input=0.00125,
            cost_per_1k_output=0.005,
            max_tokens=2000000,
            supports_caching=True,
            reasoning_tier=7,
        ),
        "gemini-flash": ModelSpec(
            provider="google",
            model_id="gemini-1.5-flash",
            display_name="Gemini 1.5 Flash",
            cost_per_1k_input=0.000075,
            cost_per_1k_output=0.0003,
            max_tokens=1000000,
            supports_caching=True,
            reasoning_tier=4,
        ),
        # OpenAI models
        "gpt-4o": ModelSpec(
            provider="openai",
            model_id="gpt-4o",
            display_name="GPT-4o",
            cost_per_1k_input=0.0025,
            cost_per_1k_output=0.01,
            max_tokens=128000,
            supports_caching=True,
            reasoning_tier=8,
        ),
        "gpt-4o-mini": ModelSpec(
            provider="openai",
            model_id="gpt-4o-mini",
            display_name="GPT-4o Mini",
            cost_per_1k_input=0.00015,
            cost_per_1k_output=0.0006,
            max_tokens=128000,
            supports_caching=True,
            reasoning_tier=5,
        ),
    }

    # Intent to model mapping
    INTENT_MODEL_MAP: ClassVar[dict[IntentCategory, list[str]]] = {
        IntentCategory.HIGH_REASONING: ["claude-sonnet", "gpt-4o", "gemini-pro"],
        IntentCategory.MEDIUM_REASONING: ["claude-haiku", "gpt-4o-mini", "gemini-pro"],
        IntentCategory.LOW_REASONING: ["gemini-flash", "gpt-4o-mini", "claude-haiku"],
        IntentCategory.HEARTBEAT: ["gemini-flash", "gpt-4o-mini"],
        IntentCategory.TOOL_CALL: ["claude-sonnet", "gpt-4o", "claude-haiku"],
    }

    def __init__(
        self,
        models: Optional[dict[str, ModelSpec]] = None,
        default_provider: str = "anthropic",
    ) -> None:
        """
        Initialize the model router.

        Args:
            models: Optional custom model specifications.
            default_provider: Preferred provider when multiple options exist.
        """
        self.models = models or self.DEFAULT_MODELS.copy()
        self.default_provider = default_provider

    def route(
        self,
        intent: Intent,
        input_tokens: int = 1000,
        expected_output_tokens: int = 500,
        require_caching: bool = True,
        preferred_provider: Optional[str] = None,
    ) -> RoutingDecision:
        """
        Route a request to the optimal model.

        Args:
            intent: Classified intent of the request.
            input_tokens: Estimated input token count.
            expected_output_tokens: Expected output token count.
            require_caching: Whether caching support is required.
            preferred_provider: Optional provider preference override.

        Returns:
            RoutingDecision with selected model and reasoning.
        """
        provider = preferred_provider or self.default_provider

        # Get candidate models for this intent
        candidates = self.INTENT_MODEL_MAP.get(
            intent.category,
            ["claude-haiku"],  # Default fallback
        )

        # Filter by requirements
        valid_candidates: list[ModelSpec] = []
        for model_key in candidates:
            if model_key not in self.models:
                continue
            model = self.models[model_key]

            # Check caching requirement
            if require_caching and not model.supports_caching:
                continue

            # Check token capacity
            if model.max_tokens < input_tokens + expected_output_tokens:
                continue

            valid_candidates.append(model)

        if not valid_candidates:
            # Fallback to any available model
            valid_candidates = list(self.models.values())

        # Sort by provider preference, then by cost
        def sort_key(m: ModelSpec) -> tuple:
            provider_match = 0 if m.provider == provider else 1
            cost = self._estimate_cost(m, input_tokens, expected_output_tokens)
            return (provider_match, cost)

        valid_candidates.sort(key=sort_key)

        selected = valid_candidates[0]
        fallback = valid_candidates[1] if len(valid_candidates) > 1 else None

        estimated_cost = self._estimate_cost(
            selected, input_tokens, expected_output_tokens
        )

        return RoutingDecision(
            selected_model=selected,
            fallback_model=fallback,
            reason=self._generate_reason(intent, selected),
            estimated_cost=estimated_cost,
            confidence=intent.confidence,
        )

    def _estimate_cost(
        self,
        model: ModelSpec,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Estimate the cost of a request.

        Args:
            model: The model specification.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.

        Returns:
            Estimated cost in USD.
        """
        input_cost = (input_tokens / 1000) * model.cost_per_1k_input
        output_cost = (output_tokens / 1000) * model.cost_per_1k_output
        return input_cost + output_cost

    def _generate_reason(self, intent: Intent, model: ModelSpec) -> str:
        """
        Generate a human-readable routing reason.

        Args:
            intent: The classified intent.
            model: The selected model.

        Returns:
            Explanation string.
        """
        category_names = {
            IntentCategory.HIGH_REASONING: "high-reasoning task",
            IntentCategory.MEDIUM_REASONING: "general assistance",
            IntentCategory.LOW_REASONING: "simple extraction/formatting",
            IntentCategory.HEARTBEAT: "status check/heartbeat",
            IntentCategory.TOOL_CALL: "tool execution",
        }

        task_type = category_names.get(intent.category, "request")
        return (
            f"Routed {task_type} to {model.display_name} (tier {model.reasoning_tier})"
        )

    def add_model(self, key: str, model: ModelSpec) -> None:
        """
        Add or update a model specification.

        Args:
            key: Unique key for the model.
            model: ModelSpec to add.
        """
        self.models[key] = model

    def get_cheapest_model(
        self,
        input_tokens: int = 1000,
        output_tokens: int = 500,
        min_reasoning_tier: int = 1,
    ) -> Optional[ModelSpec]:
        """
        Get the cheapest model meeting minimum requirements.

        Args:
            input_tokens: Estimated input tokens.
            output_tokens: Estimated output tokens.
            min_reasoning_tier: Minimum reasoning capability.

        Returns:
            Cheapest qualifying model or None.
        """
        candidates = [
            m for m in self.models.values() if m.reasoning_tier >= min_reasoning_tier
        ]

        if not candidates:
            return None

        return min(
            candidates,
            key=lambda m: self._estimate_cost(m, input_tokens, output_tokens),
        )

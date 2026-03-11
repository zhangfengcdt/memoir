"""
LLM Proxy Server.

Main entry point for the Memoir Universal LLM Proxy.
Acts as a stateful, cost-optimizing layer between agentic systems and LLM providers.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from memoir.proxy.cache.anchor import AnchorGenerator, CacheAnchor
from memoir.proxy.cache.warming import CacheWarmer
from memoir.proxy.intent.classifier import Intent, IntentClassifier
from memoir.proxy.intent.routing import ModelRouter, RoutingDecision
from memoir.proxy.providers.anthropic import AnthropicProvider
from memoir.proxy.providers.base import BaseProvider, ProviderRequest, ProviderResponse
from memoir.proxy.providers.google import GoogleProvider
from memoir.proxy.providers.openai import OpenAIProvider
from memoir.proxy.segmentation.pipeline import SegmentationPipeline, SegmentedPrompt

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Configuration for the LLM Proxy."""

    # Provider settings
    default_provider: str = "anthropic"
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Caching settings
    enable_caching: bool = True
    enable_cache_warming: bool = True
    cache_warming_threshold: float = 0.85

    # Routing settings
    enable_intent_routing: bool = True
    min_reasoning_tier: int = 1

    # Segmentation settings
    enable_segmentation: bool = True
    track_stability: bool = True

    # Performance settings
    max_concurrent_requests: int = 10
    request_timeout: float = 120.0

    # Metrics
    enable_metrics: bool = True


@dataclass
class ProxyMetrics:
    """Metrics collected by the proxy."""

    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_tokens: int = 0
    total_latency_ms: float = 0.0
    requests_by_provider: dict[str, int] = field(default_factory=dict)
    requests_by_intent: dict[str, int] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average latency."""
        return (
            self.total_latency_ms / self.total_requests
            if self.total_requests > 0
            else 0.0
        )

    @property
    def token_savings_ratio(self) -> float:
        """Calculate token savings from caching."""
        total = self.total_input_tokens
        return self.total_cached_tokens / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        """Convert metrics to dictionary."""
        return {
            "total_requests": self.total_requests,
            "cache_hit_rate": self.cache_hit_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "token_savings_ratio": self.token_savings_ratio,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "requests_by_provider": self.requests_by_provider,
            "requests_by_intent": self.requests_by_intent,
            "uptime_seconds": (datetime.utcnow() - self.started_at).total_seconds(),
        }


@dataclass
class ProxyRequest:
    """Request to the LLM Proxy."""

    messages: list[dict[str, Any]]
    system: Optional[str] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    max_tokens: int = 4096
    temperature: float = 0.7
    tools: Optional[list[dict]] = None
    session_id: Optional[str] = None
    namespace: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class ProxyResponse:
    """Response from the LLM Proxy."""

    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cache_hit: bool
    cache_anchor: Optional[CacheAnchor]
    intent: Optional[Intent]
    routing_decision: Optional[RoutingDecision]
    segmented_prompt: Optional[SegmentedPrompt]
    latency_ms: float
    metadata: dict = field(default_factory=dict)


class LLMProxy:
    """
    Memoir Universal LLM Proxy.

    A stateful, cost-optimizing layer between agentic systems and LLM providers.
    Leverages ProllyTree architecture for bit-perfect prefix stability to
    maximize KV cache utilization.
    """

    def __init__(self, config: Optional[ProxyConfig] = None) -> None:
        """
        Initialize the LLM Proxy.

        Args:
            config: Optional proxy configuration.
        """
        self.config = config or ProxyConfig()
        self._providers: dict[str, BaseProvider] = {}
        self._segmentation = SegmentationPipeline()
        self._anchor_generator = AnchorGenerator()
        self._intent_classifier = IntentClassifier()
        self._model_router = ModelRouter(default_provider=self.config.default_provider)
        self._cache_warmer = CacheWarmer()
        self._metrics = ProxyMetrics()
        self._initialized = False
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)

    async def initialize(self) -> None:
        """Initialize the proxy and providers."""
        if self._initialized:
            return

        # Initialize providers based on available keys
        if self.config.anthropic_api_key:
            self._providers["anthropic"] = AnthropicProvider(
                api_key=self.config.anthropic_api_key,
                timeout=self.config.request_timeout,
            )

        if self.config.google_api_key:
            self._providers["google"] = GoogleProvider(
                api_key=self.config.google_api_key,
                timeout=self.config.request_timeout,
            )

        if self.config.openai_api_key:
            self._providers["openai"] = OpenAIProvider(
                api_key=self.config.openai_api_key,
                timeout=self.config.request_timeout,
            )

        # Initialize at least one provider
        if not self._providers:
            # Try to initialize with environment variables
            self._providers["anthropic"] = AnthropicProvider(
                timeout=self.config.request_timeout
            )

        # Initialize all providers
        for provider in self._providers.values():
            await provider.initialize()

        # Start cache warmer if enabled
        if self.config.enable_cache_warming:
            await self._cache_warmer.start()

        self._initialized = True
        logger.info(
            f"LLM Proxy initialized with providers: {list(self._providers.keys())}"
        )

    async def complete(self, request: ProxyRequest) -> ProxyResponse:
        """
        Process a completion request through the proxy.

        This is the main entry point for requests. The proxy will:
        1. Segment the prompt into tiered blocks
        2. Generate a cache anchor
        3. Classify intent and route to optimal model
        4. Send optimized request to provider
        5. Return response with metadata

        Args:
            request: The proxy request.

        Returns:
            ProxyResponse with completion and optimization metadata.
        """
        if not self._initialized:
            await self.initialize()

        async with self._semaphore:
            start_time = datetime.utcnow()

            # Step 1: Segment the prompt
            segmented: Optional[SegmentedPrompt] = None
            cache_anchor: Optional[CacheAnchor] = None

            if self.config.enable_segmentation and request.system:
                segmented = self._segmentation.segment(
                    request.system,
                    session_id=(
                        request.session_id if self.config.track_stability else None
                    ),
                )

                # Step 2: Generate cache anchor
                if self.config.enable_caching:
                    cache_anchor = self._anchor_generator.generate(
                        segmented,
                        namespace=request.namespace,
                    )

            # Step 3: Classify intent and route
            intent: Optional[Intent] = None
            routing: Optional[RoutingDecision] = None

            if self.config.enable_intent_routing:
                # Combine system and user messages for intent classification
                user_content = " ".join(
                    msg.get("content", "")
                    for msg in request.messages
                    if msg.get("role") == "user"
                )
                intent = self._intent_classifier.classify(user_content)

                # Route to optimal model
                estimated_input = len(request.system or "") + len(user_content)
                routing = self._model_router.route(
                    intent,
                    input_tokens=estimated_input // 4,
                    require_caching=self.config.enable_caching,
                    preferred_provider=request.provider,
                )

            # Determine provider and model
            provider_name = request.provider or self.config.default_provider
            if routing:
                provider_name = routing.selected_model.provider
                model = request.model or routing.selected_model.model_id
            else:
                model = request.model

            # Get provider
            if provider_name not in self._providers:
                provider_name = self.config.default_provider
            provider = self._providers.get(provider_name)

            if not provider:
                raise ValueError(f"No provider available: {provider_name}")

            # Step 4: Build optimized request
            cache_control = None
            if self.config.enable_caching and cache_anchor:
                cache_control = {"type": "ephemeral"}

            provider_request = ProviderRequest(
                messages=request.messages,
                model=model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=request.system,
                tools=request.tools,
                cache_control=cache_control,
                metadata=request.metadata,
            )

            # Step 5: Send request
            provider_response = await provider.complete(provider_request)

            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Update metrics
            if self.config.enable_metrics:
                self._update_metrics(provider_response, intent, provider_name)

            return ProxyResponse(
                content=provider_response.content,
                model=provider_response.model,
                provider=provider_response.provider,
                input_tokens=provider_response.input_tokens,
                output_tokens=provider_response.output_tokens,
                cache_hit=provider_response.cache_hit,
                cache_anchor=cache_anchor,
                intent=intent,
                routing_decision=routing,
                segmented_prompt=segmented,
                latency_ms=latency,
                metadata={
                    "provider_latency_ms": provider_response.latency_ms,
                    "cache_creation_tokens": provider_response.cache_creation_tokens,
                    **provider_response.metadata,
                },
            )

    async def stream(self, request: ProxyRequest) -> AsyncIterator[str]:
        """
        Stream a completion response through the proxy.

        Args:
            request: The proxy request.

        Yields:
            Content chunks as they arrive.
        """
        if not self._initialized:
            await self.initialize()

        # Determine provider
        provider_name = request.provider or self.config.default_provider
        provider = self._providers.get(provider_name)

        if not provider:
            raise ValueError(f"No provider available: {provider_name}")

        # Build request
        cache_control = {"type": "ephemeral"} if self.config.enable_caching else None

        provider_request = ProviderRequest(
            messages=request.messages,
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=request.system,
            tools=request.tools,
            cache_control=cache_control,
        )

        async for chunk in provider.stream(provider_request):
            yield chunk

    def _update_metrics(
        self,
        response: ProviderResponse,
        intent: Optional[Intent],
        provider: str,
    ) -> None:
        """Update proxy metrics."""
        self._metrics.total_requests += 1
        self._metrics.total_input_tokens += response.input_tokens
        self._metrics.total_output_tokens += response.output_tokens
        self._metrics.total_latency_ms += response.latency_ms

        if response.cache_hit:
            self._metrics.cache_hits += 1
            self._metrics.total_cached_tokens += response.cache_creation_tokens
        else:
            self._metrics.cache_misses += 1

        # Track by provider
        self._metrics.requests_by_provider[provider] = (
            self._metrics.requests_by_provider.get(provider, 0) + 1
        )

        # Track by intent
        if intent:
            intent_name = intent.category.value
            self._metrics.requests_by_intent[intent_name] = (
                self._metrics.requests_by_intent.get(intent_name, 0) + 1
            )

    def get_metrics(self) -> dict:
        """
        Get current proxy metrics.

        Returns:
            Dict with all metrics.
        """
        return self._metrics.to_dict()

    async def health_check(self) -> dict[str, bool]:
        """
        Check health of all providers.

        Returns:
            Dict mapping provider names to health status.
        """
        results = {}
        for name, provider in self._providers.items():
            results[name] = await provider.health_check()
        return results

    async def shutdown(self) -> None:
        """Shutdown the proxy and cleanup resources."""
        if self.config.enable_cache_warming:
            await self._cache_warmer.stop()

        self._initialized = False
        logger.info("LLM Proxy shutdown complete")

    def register_provider(self, name: str, provider: BaseProvider) -> None:
        """
        Register a custom provider.

        Args:
            name: Provider name.
            provider: BaseProvider implementation.
        """
        self._providers[name] = provider

    @property
    def providers(self) -> list[str]:
        """List of registered provider names."""
        return list(self._providers.keys())

"""
Base Provider Interface.

Abstract base class for LLM provider adapters.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ProviderResponse:
    """Response from an LLM provider."""

    content: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    cache_hit: bool
    cache_creation_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: str = "stop"
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def total_tokens(self) -> int:
        """Total tokens used in the request."""
        return self.input_tokens + self.output_tokens

    @property
    def cache_savings_ratio(self) -> float:
        """Ratio of tokens served from cache."""
        if self.input_tokens == 0:
            return 0.0
        return self.cache_creation_tokens / self.input_tokens if self.cache_hit else 0.0


@dataclass
class ProviderRequest:
    """Request to an LLM provider."""

    messages: list[dict[str, Any]]
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7
    system: Optional[str] = None
    tools: Optional[list[dict]] = None
    cache_control: Optional[dict] = None
    metadata: dict = field(default_factory=dict)


class BaseProvider(ABC):
    """
    Abstract base class for LLM provider adapters.

    Provides a unified interface for communicating with different
    LLM providers while leveraging their specific caching capabilities.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        """
        Initialize the provider.

        Args:
            api_key: API key for authentication.
            base_url: Optional custom base URL.
            timeout: Request timeout in seconds.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self._initialized = False

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name."""
        ...

    @property
    @abstractmethod
    def supports_caching(self) -> bool:
        """Whether this provider supports prompt caching."""
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the provider client.

        Called lazily on first request.
        """
        ...

    @abstractmethod
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """
        Send a completion request to the provider.

        Args:
            request: The completion request.

        Returns:
            ProviderResponse with completion and metadata.
        """
        ...

    @abstractmethod
    async def stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        """
        Stream a completion response.

        Args:
            request: The completion request.

        Yields:
            Content chunks as they arrive.
        """
        ...

    async def warm_cache(self, prefix: str) -> dict:
        """
        Send a cache warming request.

        Default implementation sends a minimal completion request
        with the prefix to populate the provider's cache.

        Args:
            prefix: The prefix content to warm.

        Returns:
            Dict with warming result metadata.
        """
        # Default warming implementation
        request = ProviderRequest(
            messages=[{"role": "user", "content": "Acknowledge."}],
            model=self.get_default_model(),
            max_tokens=1,
            system=prefix,
            cache_control={"type": "ephemeral"},
        )

        response = await self.complete(request)
        return {
            "warmed": True,
            "tokens_cached": response.cache_creation_tokens,
            "latency_ms": response.latency_ms,
        }

    @abstractmethod
    def get_default_model(self) -> str:
        """Return the default model for this provider."""
        ...

    @abstractmethod
    def format_cache_control(
        self,
        content: str,
        cache_type: str = "ephemeral",
    ) -> dict:
        """
        Format content with provider-specific cache control.

        Args:
            content: The content to cache.
            cache_type: Cache type (ephemeral, persistent, etc.).

        Returns:
            Provider-formatted content with cache control.
        """
        ...

    async def health_check(self) -> bool:
        """
        Check if the provider is healthy and responding.

        Returns:
            True if provider is available.
        """
        try:
            if not self._initialized:
                await self.initialize()

            # Send minimal request
            request = ProviderRequest(
                messages=[{"role": "user", "content": "Hi"}],
                model=self.get_default_model(),
                max_tokens=1,
            )
            await self.complete(request)
            return True
        except Exception:
            return False

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Default implementation uses character-based estimation.
        Subclasses should override with provider-specific tokenizers.

        Args:
            text: Text to estimate.

        Returns:
            Estimated token count.
        """
        # Rough estimate: ~4 characters per token
        return len(text) // 4

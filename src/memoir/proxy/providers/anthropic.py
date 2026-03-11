"""
Anthropic Provider Adapter.

Integration with Claude models and Anthropic's prompt caching.
"""

import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Optional

from memoir.proxy.providers.base import BaseProvider, ProviderRequest, ProviderResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseProvider):
    """
    Anthropic Claude provider adapter.

    Leverages Anthropic's prompt caching for cost optimization.
    See: https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
    """

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    DEFAULT_BASE_URL = "https://api.anthropic.com"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
        default_model: Optional[str] = None,
    ) -> None:
        """
        Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.
            base_url: Optional custom base URL.
            timeout: Request timeout in seconds.
            default_model: Default model to use.
        """
        super().__init__(
            api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"),
            base_url=base_url or self.DEFAULT_BASE_URL,
            timeout=timeout,
        )
        self._default_model = default_model or self.DEFAULT_MODEL
        self._client: Any = None

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "anthropic"

    @property
    def supports_caching(self) -> bool:
        """Whether this provider supports prompt caching."""
        return True

    async def initialize(self) -> None:
        """Initialize the Anthropic client."""
        if self._initialized:
            return

        try:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
            )
            self._initialized = True
            logger.info("Anthropic provider initialized")
        except ImportError:
            raise ImportError(
                "anthropic package required. Install with: pip install anthropic"
            )

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """
        Send a completion request to Claude.

        Args:
            request: The completion request.

        Returns:
            ProviderResponse with completion and cache metadata.
        """
        if not self._initialized:
            await self.initialize()

        start_time = datetime.utcnow()

        # Build the request
        kwargs: dict[str, Any] = {
            "model": request.model or self._default_model,
            "max_tokens": request.max_tokens,
            "messages": self._format_messages(request.messages),
        }

        # Add system prompt with cache control if specified
        if request.system:
            if request.cache_control:
                kwargs["system"] = [
                    {
                        "type": "text",
                        "text": request.system,
                        "cache_control": request.cache_control,
                    }
                ]
            else:
                kwargs["system"] = request.system

        # Add tools if specified
        if request.tools:
            kwargs["tools"] = request.tools

        # Add temperature
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature

        # Make the request
        response = await self._client.messages.create(**kwargs)

        latency = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Extract content
        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        # Check for cache usage
        cache_hit = False
        cache_creation_tokens = 0
        if hasattr(response, "usage"):
            cache_creation_tokens = getattr(
                response.usage, "cache_creation_input_tokens", 0
            )
            cache_read_tokens = getattr(response.usage, "cache_read_input_tokens", 0)
            cache_hit = cache_read_tokens > 0

        return ProviderResponse(
            content=content,
            model=response.model,
            provider=self.provider_name,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_hit=cache_hit,
            cache_creation_tokens=cache_creation_tokens,
            latency_ms=latency,
            finish_reason=response.stop_reason or "stop",
            metadata={
                "id": response.id,
                "cache_read_tokens": getattr(
                    response.usage, "cache_read_input_tokens", 0
                ),
            },
        )

    async def stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        """
        Stream a completion response from Claude.

        Args:
            request: The completion request.

        Yields:
            Content chunks as they arrive.
        """
        if not self._initialized:
            await self.initialize()

        kwargs: dict[str, Any] = {
            "model": request.model or self._default_model,
            "max_tokens": request.max_tokens,
            "messages": self._format_messages(request.messages),
        }

        if request.system:
            if request.cache_control:
                kwargs["system"] = [
                    {
                        "type": "text",
                        "text": request.system,
                        "cache_control": request.cache_control,
                    }
                ]
            else:
                kwargs["system"] = request.system

        if request.tools:
            kwargs["tools"] = request.tools

        if request.temperature is not None:
            kwargs["temperature"] = request.temperature

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    def get_default_model(self) -> str:
        """Return the default Claude model."""
        return self._default_model

    def format_cache_control(
        self,
        content: str,
        cache_type: str = "ephemeral",
    ) -> dict:
        """
        Format content with Anthropic cache control.

        Args:
            content: The content to cache.
            cache_type: Cache type (ephemeral supported).

        Returns:
            Formatted content block with cache control.
        """
        return {
            "type": "text",
            "text": content,
            "cache_control": {"type": cache_type},
        }

    def _format_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Format messages for Anthropic API.

        Args:
            messages: Input messages.

        Returns:
            Formatted messages.
        """
        formatted = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            # Handle cache control on messages
            if "cache_control" in msg:
                formatted.append(
                    {
                        "role": role,
                        "content": [
                            {
                                "type": "text",
                                "text": content,
                                "cache_control": msg["cache_control"],
                            }
                        ],
                    }
                )
            else:
                formatted.append({"role": role, "content": content})

        return formatted

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count using Claude's tokenizer.

        Args:
            text: Text to estimate.

        Returns:
            Estimated token count.
        """
        # Claude uses roughly 3.5-4 characters per token
        # This is a rough estimate; for precise counting use the tokenizer
        return len(text) // 4

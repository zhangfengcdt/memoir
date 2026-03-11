"""
OpenAI Provider Adapter.

Integration with GPT models and OpenAI's API.
"""

import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Optional

from memoir.proxy.providers.base import BaseProvider, ProviderRequest, ProviderResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseProvider):
    """
    OpenAI GPT provider adapter.

    Provides integration with OpenAI's API. Note that OpenAI's
    caching behavior is automatic and not directly controllable.
    """

    DEFAULT_MODEL = "gpt-4o"
    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 120.0,
        default_model: Optional[str] = None,
        organization: Optional[str] = None,
    ) -> None:
        """
        Initialize the OpenAI provider.

        Args:
            api_key: OpenAI API key. Falls back to OPENAI_API_KEY env var.
            base_url: Optional custom base URL.
            timeout: Request timeout in seconds.
            default_model: Default model to use.
            organization: Optional organization ID.
        """
        super().__init__(
            api_key=api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=base_url or self.DEFAULT_BASE_URL,
            timeout=timeout,
        )
        self._default_model = default_model or self.DEFAULT_MODEL
        self._organization = organization
        self._client: Any = None

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "openai"

    @property
    def supports_caching(self) -> bool:
        """
        Whether this provider supports prompt caching.

        OpenAI has automatic prompt caching but it's not
        directly controllable via the API.
        """
        return True

    async def initialize(self) -> None:
        """Initialize the OpenAI client."""
        if self._initialized:
            return

        try:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                organization=self._organization,
            )
            self._initialized = True
            logger.info("OpenAI provider initialized")
        except ImportError:
            raise ImportError(
                "openai package required. Install with: pip install openai"
            )

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """
        Send a completion request to OpenAI.

        Args:
            request: The completion request.

        Returns:
            ProviderResponse with completion and metadata.
        """
        if not self._initialized:
            await self.initialize()

        start_time = datetime.utcnow()

        # Build messages list
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})

        for msg in request.messages:
            messages.append(
                {
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                }
            )

        # Build request kwargs
        kwargs: dict[str, Any] = {
            "model": request.model or self._default_model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        # Add tools if specified
        if request.tools:
            kwargs["tools"] = request.tools

        # Make the request
        response = await self._client.chat.completions.create(**kwargs)

        latency = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Extract content
        content = ""
        if response.choices:
            choice = response.choices[0]
            if choice.message and choice.message.content:
                content = choice.message.content

        # Get token usage
        input_tokens = 0
        output_tokens = 0
        cache_hit = False
        cached_tokens = 0

        if response.usage:
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            # Check for cached tokens (OpenAI returns this for some models)
            if hasattr(response.usage, "prompt_tokens_details"):
                details = response.usage.prompt_tokens_details
                if details and hasattr(details, "cached_tokens"):
                    cached_tokens = details.cached_tokens
                    cache_hit = cached_tokens > 0

        finish_reason = "stop"
        if response.choices:
            finish_reason = response.choices[0].finish_reason or "stop"

        return ProviderResponse(
            content=content,
            model=response.model,
            provider=self.provider_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit=cache_hit,
            cache_creation_tokens=cached_tokens,
            latency_ms=latency,
            finish_reason=finish_reason,
            metadata={
                "id": response.id,
                "system_fingerprint": getattr(response, "system_fingerprint", None),
            },
        )

    async def stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        """
        Stream a completion response from OpenAI.

        Args:
            request: The completion request.

        Yields:
            Content chunks as they arrive.
        """
        if not self._initialized:
            await self.initialize()

        # Build messages list
        messages = []
        if request.system:
            messages.append({"role": "system", "content": request.system})

        for msg in request.messages:
            messages.append(
                {
                    "role": msg.get("role", "user"),
                    "content": msg.get("content", ""),
                }
            )

        kwargs: dict[str, Any] = {
            "model": request.model or self._default_model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": True,
        }

        if request.tools:
            kwargs["tools"] = request.tools

        stream = await self._client.chat.completions.create(**kwargs)

        async for chunk in stream:
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content

    def get_default_model(self) -> str:
        """Return the default GPT model."""
        return self._default_model

    def format_cache_control(
        self,
        content: str,
        cache_type: str = "ephemeral",
    ) -> dict:
        """
        Format content for OpenAI.

        Note: OpenAI doesn't have explicit cache control like Anthropic.
        This returns a standard message format.

        Args:
            content: The content.
            cache_type: Cache type (not used by OpenAI).

        Returns:
            Standard message format.
        """
        return {
            "role": "system",
            "content": content,
        }

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for GPT models.

        For accurate counting, use tiktoken library.

        Args:
            text: Text to estimate.

        Returns:
            Estimated token count.
        """
        # GPT models use roughly 4 characters per token
        # For precise counting, use tiktoken
        return len(text) // 4

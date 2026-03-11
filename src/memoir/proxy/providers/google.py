"""
Google Provider Adapter.

Integration with Gemini models and Google's context caching.
"""

import logging
import os
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Optional

from memoir.proxy.providers.base import BaseProvider, ProviderRequest, ProviderResponse

logger = logging.getLogger(__name__)


class GoogleProvider(BaseProvider):
    """
    Google Gemini provider adapter.

    Leverages Google's context caching for cost optimization.
    See: https://ai.google.dev/gemini-api/docs/caching
    """

    DEFAULT_MODEL = "gemini-1.5-flash"

    def __init__(
        self,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
        default_model: Optional[str] = None,
    ) -> None:
        """
        Initialize the Google provider.

        Args:
            api_key: Google API key. Falls back to GOOGLE_API_KEY env var.
            timeout: Request timeout in seconds.
            default_model: Default model to use.
        """
        super().__init__(
            api_key=api_key or os.environ.get("GOOGLE_API_KEY"),
            timeout=timeout,
        )
        self._default_model = default_model or self.DEFAULT_MODEL
        self._client: Any = None
        self._cached_content: dict[str, Any] = {}  # hash -> cached content handle

    @property
    def provider_name(self) -> str:
        """Return the provider name."""
        return "google"

    @property
    def supports_caching(self) -> bool:
        """Whether this provider supports prompt caching."""
        return True

    async def initialize(self) -> None:
        """Initialize the Google AI client."""
        if self._initialized:
            return

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            self._genai = genai
            self._initialized = True
            logger.info("Google provider initialized")
        except ImportError:
            raise ImportError(
                "google-generativeai package required. "
                "Install with: pip install google-generativeai"
            )

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """
        Send a completion request to Gemini.

        Args:
            request: The completion request.

        Returns:
            ProviderResponse with completion and cache metadata.
        """
        if not self._initialized:
            await self.initialize()

        start_time = datetime.utcnow()

        model_name = request.model or self._default_model
        model = self._genai.GenerativeModel(model_name)

        # Build the prompt
        prompt_parts = []
        if request.system:
            prompt_parts.append(request.system)

        for msg in request.messages:
            content = msg.get("content", "")
            role = msg.get("role", "user")
            if role == "user":
                prompt_parts.append(f"User: {content}")
            else:
                prompt_parts.append(f"Assistant: {content}")

        prompt = "\n\n".join(prompt_parts)

        # Generate response
        generation_config = self._genai.GenerationConfig(
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        response = await model.generate_content_async(
            prompt,
            generation_config=generation_config,
        )

        latency = (datetime.utcnow() - start_time).total_seconds() * 1000

        # Extract content
        content = response.text if response.text else ""

        # Get token counts
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, "usage_metadata"):
            input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0)
            output_tokens = getattr(
                response.usage_metadata, "candidates_token_count", 0
            )

        return ProviderResponse(
            content=content,
            model=model_name,
            provider=self.provider_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit=False,  # Would need cached content handle to determine
            latency_ms=latency,
            finish_reason="stop",
            metadata={},
        )

    async def stream(self, request: ProviderRequest) -> AsyncIterator[str]:
        """
        Stream a completion response from Gemini.

        Args:
            request: The completion request.

        Yields:
            Content chunks as they arrive.
        """
        if not self._initialized:
            await self.initialize()

        model_name = request.model or self._default_model
        model = self._genai.GenerativeModel(model_name)

        # Build the prompt
        prompt_parts = []
        if request.system:
            prompt_parts.append(request.system)

        for msg in request.messages:
            content = msg.get("content", "")
            role = msg.get("role", "user")
            if role == "user":
                prompt_parts.append(f"User: {content}")
            else:
                prompt_parts.append(f"Assistant: {content}")

        prompt = "\n\n".join(prompt_parts)

        generation_config = self._genai.GenerationConfig(
            max_output_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        response = await model.generate_content_async(
            prompt,
            generation_config=generation_config,
            stream=True,
        )

        async for chunk in response:
            if chunk.text:
                yield chunk.text

    def get_default_model(self) -> str:
        """Return the default Gemini model."""
        return self._default_model

    def format_cache_control(
        self,
        content: str,
        cache_type: str = "ephemeral",
    ) -> dict:
        """
        Format content for Google's context caching.

        Note: Google's caching requires explicit cache creation via
        the caching API, not inline cache_control like Anthropic.

        Args:
            content: The content to cache.
            cache_type: Cache type (not directly used by Google).

        Returns:
            Dict representing cacheable content.
        """
        return {
            "content": content,
            "cache_type": cache_type,
            "provider": "google",
        }

    async def create_cached_content(
        self,
        content: str,
        model: Optional[str] = None,
        display_name: Optional[str] = None,
        ttl_seconds: int = 3600,
    ) -> str:
        """
        Create a cached content object for reuse.

        Args:
            content: Content to cache.
            model: Model to use with this cache.
            display_name: Optional display name.
            ttl_seconds: Cache TTL in seconds.

        Returns:
            Cache handle/ID for reference.
        """
        if not self._initialized:
            await self.initialize()

        # Note: This is a simplified implementation
        # Full implementation would use genai.caching.CachedContent.create()
        import hashlib

        cache_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

        # Store locally for reference
        self._cached_content[cache_hash] = {
            "content": content,
            "model": model or self._default_model,
            "display_name": display_name,
            "ttl_seconds": ttl_seconds,
            "created_at": datetime.utcnow(),
        }

        logger.info(f"Created cached content: {cache_hash}")
        return cache_hash

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for Gemini.

        Args:
            text: Text to estimate.

        Returns:
            Estimated token count.
        """
        # Gemini uses roughly 4 characters per token
        return len(text) // 4

"""
LiteLLM wrapper providing a LangChain-compatible interface.

This module provides:
- LiteLLMWrapper: A wrapper class with invoke/ainvoke methods
- get_llm: Factory function to create LLM instances
- Automatic prompt caching for Anthropic models (up to 90% cost savings)

Supported providers include OpenAI, Anthropic, Google, Ollama, vLLM, Azure, and 100+ more.
See https://docs.litellm.ai/docs/providers for the full list.
"""

import logging
import os
from typing import Any, ClassVar

logger = logging.getLogger(__name__)


class LiteLLMResponse:
    """Response object that mimics LangChain's response format."""

    def __init__(self, content: str, usage: dict | None = None):
        self.content = content
        self.usage = usage or {}


class LiteLLMWrapper:
    """
    Wrapper around LiteLLM that provides a LangChain-compatible interface.

    This allows using LiteLLM with code that expects .invoke() and .ainvoke() methods.
    Supports 100+ LLM providers including OpenAI, Anthropic, Google, Ollama, vLLM, etc.

    Features:
    - Prompt caching for Anthropic models (reduces cost by up to 90% on cached tokens)
    - Automatic detection of cacheable content based on prompt structure
    """

    # Models that support prompt caching (with or without anthropic/ prefix)
    CACHE_SUPPORTED_MODELS: ClassVar[list[str]] = [
        # Current models (2025)
        "claude-opus-4",
        "claude-sonnet-4",
        "claude-haiku-4",
        # Legacy models
        "claude-3-5-sonnet",
        "claude-3-5-haiku",
        "claude-3-opus",
        "claude-3-haiku",
        "claude-3-sonnet",
        "anthropic/claude",  # Catch-all for anthropic/ prefixed models
    ]

    # Minimum tokens for caching (Anthropic requirements)
    # claude-3-5-sonnet/opus: 1024 tokens, claude-3-haiku: 2048 tokens
    MIN_CACHE_TOKENS = 1024

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0,
        max_tokens: int = 500,
        base_url: str | None = None,
        api_key: str | None = None,
        enable_prompt_cache: bool = True,
        debug_cache: bool = False,
    ):
        """
        Initialize the LiteLLM wrapper.

        Args:
            model: Model identifier (e.g., "gpt-4o-mini", "claude-haiku-4-5", "ollama/llama3.2")
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens in response
            base_url: Optional base URL for custom endpoints (e.g., vLLM, local servers)
            api_key: Optional API key (usually set via environment variables)
            enable_prompt_cache: Enable Anthropic prompt caching (default: True)
            debug_cache: Print cache debugging information (default: False)
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.base_url = base_url
        self.api_key = api_key
        self.enable_prompt_cache = enable_prompt_cache
        self._debug_cache = debug_cache

        # Cache statistics
        self.cache_stats = {
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "total_requests": 0,
            "cached_requests": 0,
        }

        # Import litellm here to fail fast if not installed
        try:
            import litellm

            self._litellm = litellm
            # Suppress litellm's verbose logging
            litellm.suppress_debug_info = True
        except ImportError as e:
            raise ImportError(
                "litellm is required for LLM-backed classification and search. "
                "Install with: pip install 'memoir-ai[litellm]'"
            ) from e

    def _supports_prompt_cache(self) -> bool:
        """Check if the current model supports prompt caching."""
        if not self.enable_prompt_cache:
            return False
        model_lower = self.model.lower()
        return any(
            supported in model_lower for supported in self.CACHE_SUPPORTED_MODELS
        )

    def _build_kwargs(self) -> dict:
        """Build kwargs for litellm calls."""
        kwargs = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.base_url:
            kwargs["base_url"] = self.base_url
            kwargs["api_base"] = self.base_url  # Some providers use api_base
        if self.api_key:
            kwargs["api_key"] = self.api_key
        return kwargs

    def _extract_cacheable_content(self, prompt: str) -> tuple[str, str]:
        """
        Extract the cacheable (static) and dynamic parts of a classification prompt.

        The IntelligentClassifier structures prompts as:
        1. [STATIC_SECTION_START] ... taxonomy + guidelines ... [STATIC_SECTION_END]
        2. [DYNAMIC_SECTION_START] ... user content + context ...

        Returns:
            Tuple of (static_content, dynamic_content) or (None, None) if no markers found
        """
        static_end_marker = "[STATIC_SECTION_END]"

        if static_end_marker in prompt:
            static_end_pos = prompt.find(static_end_marker) + len(static_end_marker)
            static_part = prompt[:static_end_pos]
            dynamic_part = prompt[static_end_pos:]

            if self._debug_cache:
                logger.debug(
                    f"[Cache] Static: {len(static_part)} chars (~{len(static_part)//4} tokens)"
                )
                logger.debug(
                    f"[Cache] Dynamic: {len(dynamic_part)} chars (~{len(dynamic_part)//4} tokens)"
                )
            return static_part, dynamic_part

        # No markers found - return None to indicate no caching
        if self._debug_cache:
            logger.debug("[Cache] No markers found, caching disabled for this prompt")
        return None, None

    def _format_cached_messages(self, prompt: str) -> list[dict]:
        """
        Format messages with Anthropic prompt caching structure.

        Splits prompt at [STATIC_SECTION_END] marker and adds cache_control
        to the static part (taxonomy + guidelines).
        """
        static_content, dynamic_content = self._extract_cacheable_content(prompt)

        # No markers found - send as regular message without caching
        if static_content is None:
            return [{"role": "user", "content": prompt}]

        # Check minimum token requirement
        estimated_static_tokens = len(static_content) // 4
        min_tokens = 2048 if "haiku" in self.model.lower() else 1024

        if estimated_static_tokens < min_tokens:
            if self._debug_cache:
                logger.debug(
                    f"[Cache] Static too short: ~{estimated_static_tokens} tokens < {min_tokens} required"
                )
            return [{"role": "user", "content": prompt}]

        if self._debug_cache:
            logger.debug(f"[Cache] Caching ~{estimated_static_tokens} static tokens")

        # Format with cache_control for Anthropic
        return [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": static_content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
            },
            {"role": "user", "content": dynamic_content.strip()},
        ]

    def _update_cache_stats(self, usage):
        """Update cache statistics from response usage.

        LiteLLM returns cache stats in prompt_tokens_details:
        - cache_creation_tokens: tokens written to cache
        - cached_tokens: tokens read from cache
        """
        self.cache_stats["total_requests"] += 1

        cache_creation = 0
        cache_read = 0

        # Try direct attributes first (Anthropic native format)
        if hasattr(usage, "cache_creation_input_tokens"):
            cache_creation = usage.cache_creation_input_tokens or 0
        if hasattr(usage, "cache_read_input_tokens"):
            cache_read = usage.cache_read_input_tokens or 0

        # Try LiteLLM's prompt_tokens_details format
        if cache_creation == 0 and cache_read == 0:
            prompt_details = getattr(usage, "prompt_tokens_details", None)
            if prompt_details:
                cache_creation = (
                    getattr(prompt_details, "cache_creation_tokens", 0) or 0
                )
                cache_read = getattr(prompt_details, "cached_tokens", 0) or 0

        # Try dict format
        if cache_creation == 0 and cache_read == 0 and isinstance(usage, dict):
            cache_creation = usage.get("cache_creation_input_tokens", 0)
            cache_read = usage.get("cache_read_input_tokens", 0)
            # Also check nested prompt_tokens_details
            prompt_details = usage.get("prompt_tokens_details", {})
            if isinstance(prompt_details, dict):
                cache_creation = cache_creation or prompt_details.get(
                    "cache_creation_tokens", 0
                )
                cache_read = cache_read or prompt_details.get("cached_tokens", 0)

        self.cache_stats["cache_creation_input_tokens"] += cache_creation
        self.cache_stats["cache_read_input_tokens"] += cache_read

        if cache_read > 0:
            self.cache_stats["cached_requests"] += 1

        if self._debug_cache:
            if cache_creation > 0:
                logger.debug(
                    f"[Cache] Cache CREATED: {cache_creation} tokens written to cache"
                )
            if cache_read > 0:
                logger.debug(f"[Cache] Cache HIT: {cache_read} tokens read from cache")
            if cache_creation == 0 and cache_read == 0:
                logger.debug(
                    "[Cache] Cache MISS: No cache activity (prompt may be too short)"
                )

    def get_cache_stats(self) -> dict:
        """Get prompt caching statistics."""
        stats = self.cache_stats.copy()
        if stats["total_requests"] > 0:
            stats["cache_hit_rate"] = stats["cached_requests"] / stats["total_requests"]
        else:
            stats["cache_hit_rate"] = 0.0

        # Estimate savings (cached tokens cost 90% less)
        if stats["cache_read_input_tokens"] > 0:
            stats["estimated_token_savings"] = int(
                stats["cache_read_input_tokens"] * 0.9
            )
        else:
            stats["estimated_token_savings"] = 0

        return stats

    def invoke(self, prompt: Any) -> LiteLLMResponse:
        """Synchronous invoke method compatible with LangChain interface."""
        import asyncio

        return asyncio.run(self.ainvoke(prompt))

    async def ainvoke(self, prompt: Any) -> LiteLLMResponse:
        """Async invoke method compatible with LangChain interface."""
        # Handle different prompt formats
        if isinstance(prompt, str):
            if self._supports_prompt_cache():
                # Use cached message format for Anthropic models
                messages = self._format_cached_messages(prompt)
            else:
                messages = [{"role": "user", "content": prompt}]
        elif isinstance(prompt, list):
            # Assume it's already a list of message dicts
            messages = prompt
        else:
            # Try to convert to string
            prompt_str = str(prompt)
            if self._supports_prompt_cache():
                messages = self._format_cached_messages(prompt_str)
            else:
                messages = [{"role": "user", "content": prompt_str}]

        kwargs = self._build_kwargs()
        kwargs["messages"] = messages

        response = await self._litellm.acompletion(**kwargs)

        # Extract content and usage from response
        content = response.choices[0].message.content
        usage = getattr(response, "usage", {})

        # Update cache statistics
        if self._supports_prompt_cache():
            self._update_cache_stats(usage)

        return LiteLLMResponse(content=content, usage=usage)


def get_llm(
    model: str = "gpt-4o-mini",
    temperature: float = 0,
    max_tokens: int = 500,
    base_url: str | None = None,
    api_key: str | None = None,
    enable_prompt_cache: bool = True,
    debug_cache: bool = False,
) -> Any:
    """
    Get LLM instance using LiteLLM for multi-provider support.

    This is the recommended way to create LLM instances in memoir.
    It supports 100+ providers and automatically handles prompt caching
    for supported Anthropic models.

    Args:
        model: Model identifier. Examples:
            - OpenAI: "gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"
            - Anthropic: "claude-haiku-4-5", "claude-sonnet-4-6", "claude-3-haiku-20240307"
            - Google: "gemini/gemini-1.5-flash", "gemini/gemini-1.5-pro"
            - Ollama: "ollama/llama3.2", "ollama/mistral"
            - vLLM: Use any model name with base_url parameter
            - Azure: "azure/deployment-name"
        temperature: Sampling temperature (0-1). Default: 0
        max_tokens: Maximum tokens in response. Default: 500
        base_url: Optional base URL for custom endpoints
        api_key: Optional API key (usually set via environment variables)
        enable_prompt_cache: Enable Anthropic prompt caching. Default: True
        debug_cache: Print cache debugging information. Default: False

    Returns:
        LiteLLMWrapper instance with invoke/ainvoke methods

    Environment Variables:
        - OPENAI_API_KEY: Required for OpenAI models
        - ANTHROPIC_API_KEY: Required for Claude models
        - GEMINI_API_KEY: Required for Gemini models
        - OLLAMA_HOST: Optional for non-default Ollama server

    Backend selection (MEMOIR_LLM_BACKEND env var):
        - unset / "litellm" (default): this LiteLLM path — direct provider APIs,
          needs OPENAI_API_KEY / ANTHROPIC_API_KEY / etc.
        - "claude-cli": shell out to `claude -p` instead — no API key needed,
          inherits Claude Code's auth (subscription OAuth or API key).
          Only Claude models supported. See claude_cli_client.py.

    Example:
        >>> from memoir.llm import get_llm
        >>> llm = get_llm(model="claude-haiku-4-5")
        >>> response = llm.invoke("What is the capital of France?")
        >>> print(response.content)
        Paris
    """
    # Route to the claude-cli backend if requested. This is the zero-API-key
    # path for running memoir under Claude Code; see ClaudeCLIWrapper docstring.
    backend = os.getenv("MEMOIR_LLM_BACKEND", "").strip().lower()
    if backend in ("claude-cli", "claude_cli", "cli"):
        from memoir.llm.claude_cli_client import ClaudeCLIWrapper

        # Coerce the default OpenAI model to a Claude model; claude-cli can't run gpt-*.
        cli_model = model
        if model.lower().startswith("gpt-") or "gpt-" in model.lower():
            cli_model = os.getenv("MEMOIR_LLM_MODEL", "claude-haiku-4-5")
        return ClaudeCLIWrapper(
            model=cli_model,
            temperature=temperature,
            max_tokens=max_tokens,
            base_url=base_url,
            api_key=api_key,
            enable_prompt_cache=enable_prompt_cache,
            debug_cache=debug_cache,
        )

    # Auto-add provider prefix for Claude models (LiteLLM requirement)
    model_lower = model.lower()
    if model_lower.startswith("claude") and not model_lower.startswith("anthropic/"):
        model = f"anthropic/{model}"
        model_lower = model.lower()

    # Validate API keys for known providers
    if model_lower.startswith("anthropic/") or "claude" in model_lower:
        if not os.getenv("ANTHROPIC_API_KEY") and not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY environment variable is required for Claude models. "
                "Set it with: export ANTHROPIC_API_KEY=your-api-key-here"
            )
    elif model_lower.startswith("gemini/"):
        if not os.getenv("GEMINI_API_KEY") and not api_key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is required for Gemini models. "
                "Set it with: export GEMINI_API_KEY=your-api-key-here"
            )
    elif (
        not model_lower.startswith("ollama/")
        and not base_url
        and not os.getenv("OPENAI_API_KEY")
        and not api_key
    ):
        # OpenAI or similar cloud providers
        raise ValueError(
            "OPENAI_API_KEY environment variable is required for OpenAI models. "
            "Set it with: export OPENAI_API_KEY=your-api-key-here"
        )

    return LiteLLMWrapper(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=base_url,
        api_key=api_key,
        enable_prompt_cache=enable_prompt_cache,
        debug_cache=debug_cache,
    )

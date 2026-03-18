"""
LLM utilities for memoir using LiteLLM.

This module provides a unified LLM interface that supports 100+ providers
including OpenAI, Anthropic, Google, Ollama, vLLM, and more.

Usage:
    from memoir.llm import get_llm

    # OpenAI (default)
    llm = get_llm()

    # Anthropic Claude with prompt caching
    llm = get_llm(model="claude-haiku-4-5")

    # Ollama (local)
    llm = get_llm(model="ollama/llama3.2")

    # Use with classifiers and search engines
    response = llm.invoke("Hello, world!")
    print(response.content)
"""

from memoir.llm.litellm_client import LiteLLMResponse, LiteLLMWrapper, get_llm

__all__ = [
    "LiteLLMResponse",
    "LiteLLMWrapper",
    "get_llm",
]

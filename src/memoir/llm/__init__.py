# SPDX-License-Identifier: Apache-2.0
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

import os

from memoir.llm.claude_cli_client import ClaudeCLIError, ClaudeCLIWrapper
from memoir.llm.litellm_client import LiteLLMResponse, LiteLLMWrapper, get_llm


def default_ui_model() -> str:
    """Default LLM for UI handlers.

    Claude by default so users with only ANTHROPIC_API_KEY (or the claude-cli
    backend) work out of the box. Override via the MEMOIR_LLM_MODEL env var —
    e.g. set it to "gpt-4o-mini" to restore the old OpenAI default.
    """
    override = os.getenv("MEMOIR_LLM_MODEL", "").strip()
    return override or "claude-haiku-4-5"


__all__ = [
    "ClaudeCLIError",
    "ClaudeCLIWrapper",
    "LiteLLMResponse",
    "LiteLLMWrapper",
    "default_ui_model",
    "get_llm",
]

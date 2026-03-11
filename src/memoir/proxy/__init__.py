"""
Memoir Universal LLM Proxy.

A stateful, cost-optimizing layer between agentic systems and LLM providers.
Leverages ProllyTree architecture for bit-perfect prefix stability to maximize
KV cache utilization.

Components:
    - segmentation: Block segmentation pipeline for prompt normalization
    - cache: Cache anchor generation and predictive warming
    - intent: Intent classification and model routing
    - providers: LLM provider adapters (Anthropic, Google, OpenAI)
"""

from memoir.proxy.server import LLMProxy, ProxyConfig

__all__ = [
    "LLMProxy",
    "ProxyConfig",
]

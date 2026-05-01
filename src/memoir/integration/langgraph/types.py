# SPDX-License-Identifier: Apache-2.0
"""Type definitions for LangGraph integration."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class MemoryEntry:
    """Represents a single memory entry in the system."""

    content: str
    metadata: dict[str, Any]
    timestamp: datetime
    memory_id: str | None = None
    thread_id: str | None = None
    user_id: str | None = None
    semantic_path: str | None = None
    commit_hash: str | None = None


@dataclass
class SearchResult:
    """Represents a search result from memory retrieval."""

    memory: MemoryEntry
    score: float
    relevance_context: str | None = None


@dataclass
class MemoryConfig:
    """Configuration for LangGraph memory integration."""

    # Memoir-specific settings
    storage_path: str = "./memoir_storage"
    taxonomy_type: str = "intelligent"  # "fixed", "iterative", or "intelligent"
    enable_versioning: bool = True
    enable_search_cache: bool = True

    # LangGraph compatibility settings
    namespace: str = "default"
    max_search_results: int = 10
    similarity_threshold: float = 0.7

    # LLM settings for intelligent features
    llm_provider: str | None = None  # "openai", "anthropic", etc.
    llm_model: str | None = None
    api_key: str | None = None

    # Performance settings
    batch_size: int = 100
    async_operations: bool = True
    compression_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "storage_path": self.storage_path,
            "taxonomy_type": self.taxonomy_type,
            "enable_versioning": self.enable_versioning,
            "enable_search_cache": self.enable_search_cache,
            "namespace": self.namespace,
            "max_search_results": self.max_search_results,
            "similarity_threshold": self.similarity_threshold,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "batch_size": self.batch_size,
            "async_operations": self.async_operations,
            "compression_enabled": self.compression_enabled,
        }

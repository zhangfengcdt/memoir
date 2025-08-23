"""Base integration interface for framework adapters."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TypeVar

T = TypeVar("T")


class BaseIntegration(ABC):
    """Abstract base class for framework integrations."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the integration with optional configuration.

        Args:
            config: Optional configuration dictionary for the integration
        """
        self.config = config or {}
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the integration (async setup)."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources used by the integration."""
        pass

    @property
    def is_initialized(self) -> bool:
        """Check if the integration is initialized."""
        return self._initialized

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

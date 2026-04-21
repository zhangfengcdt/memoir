"""
Base interfaces and protocols for taxonomy systems.
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TaxonomyInterface(Protocol):
    """
    Protocol defining the interface that all taxonomy implementations must support.

    This allows SemanticClassifier to work with any taxonomy type without
    using hasattr() checks or duck typing.
    """

    def is_valid_path(self, path: str) -> bool:
        """Check if a taxonomy path is valid."""
        ...

    def get_all_paths(self) -> list[str]:
        """Get all available taxonomy paths."""
        ...


@runtime_checkable
class AdvancedTaxonomyInterface(TaxonomyInterface, Protocol):
    """
    Extended interface for advanced taxonomy implementations like DynamicTaxonomy.

    Includes features like fallback logic, expansion tracking, and confidence-based
    path selection.
    """

    def select_path_with_fallback(
        self,
        classification_result: Any,
        memory_content: str,
        metadata: dict | None = None,
    ) -> tuple[str, float]:
        """
        Select taxonomy path with intelligent fallback logic.

        Args:
            classification_result: Result from classification
            memory_content: Original memory content
            metadata: Optional metadata

        Returns:
            Tuple of (selected_path, final_confidence)
        """
        ...


class BaseTaxonomy(ABC):
    """
    Abstract base class for taxonomy implementations.
    Provides common functionality and enforces the interface.
    """

    @abstractmethod
    def is_valid_path(self, path: str) -> bool:
        """Check if a taxonomy path is valid."""
        pass

    @abstractmethod
    def get_all_paths(self) -> list[str]:
        """Get all available taxonomy paths."""
        pass

    def get_statistics(self) -> dict[str, Any]:
        """Get taxonomy statistics. Override in subclasses for specific stats."""
        return {
            "total_paths": len(self.get_all_paths()),
            "type": self.__class__.__name__,
        }

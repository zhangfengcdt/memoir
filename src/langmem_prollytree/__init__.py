"""
LangMem-ProllyTree Integration
High-performance semantic memory system for AI agents.
"""

__version__ = "0.1.0"

try:
    from .core.memory_manager import ProllyTreeMemoryStoreManager
    from .core.prolly_adapter import MemoryItem, ProllyTreeStore
except ImportError:
    # Fall back to simplified version for testing
    import time
    from typing import Any, Optional

    # Mock MemoryItem
    from pydantic import BaseModel, Field

    from .core.mock_store import MockProllyTreeStore as ProllyTreeStore
    from .core.simple_memory_manager import (
        SimpleMemoryManager as ProllyTreeMemoryStoreManager,
    )

    class MemoryItem(BaseModel):
        key: str
        namespace: str
        content: Any
        metadata: dict[str, Any] = Field(default_factory=dict)
        timestamp: float = Field(default_factory=time.time)
        version: Optional[str] = None
        confidence: float = 1.0


from .search.hierarchical_search import (
    HierarchicalSearchEngine,
    SearchResult,
    SearchStrategy,
)
from .taxonomy.semantic_classifier import (
    ClassificationResult,
    OptimizedClassifier,
    SemanticClassifier,
)
from .taxonomy.semantic_taxonomy import SemanticTaxonomy, TaxonomyCategory, get_taxonomy

__all__ = [
    "ClassificationResult",
    # Search
    "HierarchicalSearchEngine",
    "MemoryItem",
    "OptimizedClassifier",
    # Core
    "ProllyTreeMemoryStoreManager",
    "ProllyTreeStore",
    "SearchResult",
    "SearchStrategy",
    # Classification
    "SemanticClassifier",
    # Taxonomy
    "SemanticTaxonomy",
    "TaxonomyCategory",
    "get_taxonomy",
]

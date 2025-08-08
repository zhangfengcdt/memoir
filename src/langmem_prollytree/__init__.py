"""
LangMem-ProllyTree Integration
High-performance semantic memory system for AI agents.
"""

__version__ = "0.1.0"

from .core.memory_manager import ProllyTreeMemoryStoreManager
from .core.prolly_adapter import MemoryItem, ProllyTreeStore
from .search.hierarchical_search import (
    HierarchicalSearchEngine,
    SearchResult,
    SearchStrategy,
)
from .taxonomy.semantic_classifier import (
    ClassificationResult,
    SemanticClassifier,
)
from .taxonomy.semantic_taxonomy import SemanticTaxonomy, TaxonomyCategory, get_taxonomy

__all__ = [
    "ClassificationResult",
    # Search
    "HierarchicalSearchEngine",
    "MemoryItem",
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

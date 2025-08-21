"""
LangMem-ProllyTree Integration
High-performance semantic memory system for AI agents.
"""

__version__ = "0.1.0"

from .classifier.semantic import (
    ClassificationResult,
    SemanticClassifier,
)
from .core.memory import ProllyTreeMemoryStoreManager
from .memento import LocationMemento, ProfileMemento, TimelineMemento
from .search.semantic import (
    SearchResult,
    SemanticSearchEngine,
)
from .store.prolly_adapter import MemoryItem, ProllyTreeStore
from .taxonomy.semantic import SemanticTaxonomy, TaxonomyCategory, get_taxonomy

__all__ = [
    "ClassificationResult",
    "LocationMemento",
    "MemoryItem",
    "ProfileMemento",
    "ProllyTreeMemoryStoreManager",
    "ProllyTreeStore",
    "SearchResult",
    "SemanticClassifier",
    "SemanticSearchEngine",
    "SemanticTaxonomy",
    "TaxonomyCategory",
    "TimelineMemento",
    "get_taxonomy",
]

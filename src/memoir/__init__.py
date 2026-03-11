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

# Integration components
from .integration.langgraph import LangGraphMemoryStore, MemoryConfig
from .memento import LocationMemento, ProfileMemento, TimelineMemento

# Proxy components
from .proxy import LLMProxy, ProxyConfig
from .search.semantic import (
    SearchResult,
    SemanticSearchEngine,
)
from .store.prolly_adapter import MemoryItem, ProllyTreeStore
from .taxonomy.semantic import SemanticTaxonomy, TaxonomyCategory, get_taxonomy

__all__ = [
    "ClassificationResult",
    "LLMProxy",
    "LangGraphMemoryStore",
    "LocationMemento",
    "MemoryConfig",
    "MemoryItem",
    "ProfileMemento",
    "ProllyTreeMemoryStoreManager",
    "ProllyTreeStore",
    "ProxyConfig",
    "SearchResult",
    "SemanticClassifier",
    "SemanticSearchEngine",
    "SemanticTaxonomy",
    "TaxonomyCategory",
    "TimelineMemento",
    "get_taxonomy",
]

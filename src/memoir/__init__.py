# SPDX-License-Identifier: Apache-2.0
"""
Memoir
High-performance semantic memory system for AI agents.
"""

__version__ = "0.1.8"  # Single source of truth; read by hatch + release workflow (keep on one line)

from .classifier.semantic import (
    ClassificationResult,
    SemanticClassifier,
)

# Integration components
from .integration.langgraph import LangGraphMemoryStore, MemoryConfig
from .memento import LocationMemento, ProfileMemento, TimelineMemento
from .search.intelligent import (
    IntelligentSearchEngine,
    IntelligentSearchResult,
)
from .store.prolly_adapter import MemoryItem, ProllyTreeStore
from .taxonomy.semantic import SemanticTaxonomy, TaxonomyCategory, get_taxonomy

__all__ = [
    "ClassificationResult",
    "IntelligentSearchEngine",
    "IntelligentSearchResult",
    "LangGraphMemoryStore",
    "LocationMemento",
    "MemoryConfig",
    "MemoryItem",
    "ProfileMemento",
    "ProllyTreeStore",
    "SemanticClassifier",
    "SemanticTaxonomy",
    "TaxonomyCategory",
    "TimelineMemento",
    "get_taxonomy",
]

# Optional: ProllyTreeMemoryStoreManager requires the `langmem` extra.
# Install via `pip install memoir-ai[langmem]` to enable it.
try:
    from .core.memory import ProllyTreeMemoryStoreManager  # noqa: F401

    __all__.append("ProllyTreeMemoryStoreManager")
except ImportError:  # langmem not installed
    pass

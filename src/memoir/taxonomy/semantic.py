"""
Comprehensive semantic taxonomy for AI memory classification.
Defines ~800 hierarchical paths for deterministic memory organization.
"""

import threading
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from memoir.classifier.base import BaseTaxonomy

from .data_sources import TaxonomyDataSourceManager, TaxonomyLoadError


class TaxonomyCategory(Enum):
    """Top-level taxonomy categories."""

    PROFILE = "profile"
    PREFERENCES = "preferences"
    EXPERIENCE = "experience"
    CONTEXT = "context"
    KNOWLEDGE = "knowledge"
    RELATIONSHIPS = "relationships"
    GOALS = "goals"
    BEHAVIOR = "behavior"


@dataclass
class TaxonomyNode:
    """Represents a node in the taxonomy tree."""

    path: str
    category: TaxonomyCategory
    depth: int
    is_leaf: bool
    description: str
    examples: list[str]


class SemanticTaxonomy(BaseTaxonomy):
    """
    Fixed semantic taxonomy with approximately 800 predefined paths.
    Provides hierarchical organization for AI memory classification.
    Implements TaxonomyInterface for standardized access.
    """

    def __init__(self, data_source_manager: Optional[TaxonomyDataSourceManager] = None):
        """
        Initialize semantic taxonomy with flexible data loading.

        Args:
            data_source_manager: Optional data source manager for loading taxonomy.
                                If None, uses default data sources (JSON file, then hardcoded fallback).
        """
        self.data_source_manager = data_source_manager or TaxonomyDataSourceManager()
        self._taxonomy = self._load_taxonomy_data()
        self._all_paths = self._generate_all_paths()
        self._path_index = self._build_path_index()

    def _load_taxonomy_data(self) -> dict:
        """
        Load taxonomy data using the data source manager.

        Returns:
            Dictionary containing the taxonomy structure

        Raises:
            RuntimeError: If taxonomy data cannot be loaded from any source
        """
        try:
            return self.data_source_manager.load_taxonomy_data()
        except TaxonomyLoadError as e:
            raise RuntimeError(f"Failed to load taxonomy data: {e}")

    def get_data_source_info(self) -> dict:
        """
        Get information about the data sources used to load taxonomy.

        Returns:
            Dictionary with data source status and metadata
        """
        return self.data_source_manager.get_source_status()

    def _generate_all_paths(self) -> set[str]:
        """Generate all valid paths from the taxonomy."""
        paths = set()

        def traverse(obj, prefix=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_prefix = f"{prefix}.{key}" if prefix else key
                    paths.add(new_prefix)
                    traverse(value, new_prefix)
            elif isinstance(obj, list):
                for item in obj:
                    new_path = f"{prefix}.{item}" if prefix else item
                    paths.add(new_path)

        traverse(self._taxonomy)
        return paths

    def _build_path_index(self) -> dict[str, list[str]]:
        """Build an index for efficient path lookups."""
        index = {}
        for path in self._all_paths:
            parts = path.split(".")
            for i in range(len(parts)):
                prefix = ".".join(parts[: i + 1])
                if prefix not in index:
                    index[prefix] = []
                if path != prefix:
                    index[prefix].append(path)
        return index

    def get_all_paths(self) -> list[str]:
        """Return all valid taxonomy paths."""
        return sorted(self._all_paths)

    def get_children(self, path: str) -> list[str]:
        """Get immediate children of a path."""
        if path not in self._path_index:
            return []

        children = []
        path_depth = len(path.split("."))
        for child in self._path_index[path]:
            if len(child.split(".")) == path_depth + 1:
                children.append(child)
        return sorted(children)

    def get_descendants(self, path: str) -> list[str]:
        """Get all descendants of a path."""
        if path not in self._path_index:
            return []
        return sorted(self._path_index[path])

    def is_valid_path(self, path: str) -> bool:
        """Check if a path exists in the taxonomy."""
        return path in self._all_paths

    def get_path_depth(self, path: str) -> int:
        """Get the depth of a path in the hierarchy."""
        return len(path.split("."))

    def get_category(self, path: str) -> TaxonomyCategory:
        """Get the top-level category for a path."""
        if not path:
            return None
        root = path.split(".")[0]
        try:
            return TaxonomyCategory(root)
        except ValueError:
            return None

    def get_related_paths(self, path: str, max_distance: int = 2) -> list[str]:
        """Get paths related to the given path within a certain distance."""
        if not self.is_valid_path(path):
            return []

        related = set()
        parts = path.split(".")

        # Get siblings
        if len(parts) > 1:
            parent = ".".join(parts[:-1])
            related.update(self.get_children(parent))

        # Get ancestors up to max_distance
        for i in range(1, min(max_distance + 1, len(parts))):
            ancestor = ".".join(parts[:-i])
            related.add(ancestor)

        # Get descendants up to max_distance
        if max_distance > 0:
            descendants = self.get_descendants(path)
            for desc in descendants:
                if (
                    self.get_path_depth(desc) - self.get_path_depth(path)
                    <= max_distance
                ):
                    related.add(desc)

        related.discard(path)  # Remove the path itself
        return sorted(related)

    def get_statistics(self) -> dict:
        """Get statistics about the taxonomy."""
        category_counts = {}
        depth_counts = {}

        for path in self._all_paths:
            category = self.get_category(path)
            if category:
                cat_name = category.value
                category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

            depth = self.get_path_depth(path)
            depth_counts[depth] = depth_counts.get(depth, 0) + 1

        return {
            "total_paths": len(self._all_paths),
            "categories": len(list(TaxonomyCategory)),
            "max_depth": max(depth_counts.keys()),
            "paths_by_category": category_counts,
            "paths_by_depth": depth_counts,
        }


# Thread-safe singleton instance
_taxonomy_instance = None
_taxonomy_lock = threading.Lock()


def get_taxonomy() -> SemanticTaxonomy:
    """Get the thread-safe singleton taxonomy instance."""
    global _taxonomy_instance
    if _taxonomy_instance is None:
        with _taxonomy_lock:
            # Double-check locking pattern
            if _taxonomy_instance is None:
                _taxonomy_instance = SemanticTaxonomy()
    return _taxonomy_instance

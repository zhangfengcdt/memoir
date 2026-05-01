# SPDX-License-Identifier: Apache-2.0
"""Central registry for taxonomy data management.

Handles loading from builtin and external markdown files,
and provides access to combined taxonomy data.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from .markdown_source import MarkdownTaxonomySource, TaxonomyData, TaxonomyParseError

logger = logging.getLogger(__name__)


@dataclass
class TaxonomyEntry:
    """Entry in the taxonomy registry."""

    data: TaxonomyData
    source_path: Path | None = None
    is_builtin: bool = True


class TaxonomyRegistry:
    """
    Central registry for managing taxonomy data from multiple sources.

    Provides:
    - Loading from built-in markdown files
    - Loading from external/user-provided files
    - Domain-based filtering
    - Type-based lookup (examples, descriptions, presets)
    - Merging/combining taxonomy data
    """

    def __init__(self):
        """Initialize an empty registry."""
        self._entries: dict[str, TaxonomyEntry] = {}
        self._by_type: dict[str, list[str]] = {
            "examples": [],
            "descriptions": [],
            "preset": [],
        }
        self._by_domain: dict[str, list[str]] = {}
        self._parser = MarkdownTaxonomySource()
        self._builtin_path = Path(__file__).parent / "data"

    def load_builtin(self) -> list[str]:
        """Load all built-in taxonomy markdown files.

        Returns:
            List of loaded taxonomy IDs.
        """
        loaded_ids = []

        if not self._builtin_path.exists():
            logger.warning(f"Built-in taxonomy path not found: {self._builtin_path}")
            return loaded_ids

        for md_file in self._builtin_path.rglob("*.md"):
            if md_file.name == "README.md":
                continue
            try:
                taxonomy_id = self._load_file(md_file, is_builtin=True)
                loaded_ids.append(taxonomy_id)
                logger.debug(f"Loaded builtin taxonomy: {taxonomy_id} from {md_file}")
            except (TaxonomyParseError, FileNotFoundError) as e:
                logger.error(f"Failed to load {md_file}: {e}")

        return loaded_ids

    def load_external(self, path: Path | str) -> str:
        """Load an external taxonomy file.

        Args:
            path: Path to markdown file.

        Returns:
            ID of the loaded taxonomy.

        Raises:
            TaxonomyParseError: If the file cannot be parsed.
            FileNotFoundError: If the file doesn't exist.
        """
        path = Path(path)
        return self._load_file(path, is_builtin=False)

    def _load_file(self, path: Path, is_builtin: bool) -> str:
        """Load a single taxonomy file.

        Args:
            path: Path to the markdown file.
            is_builtin: Whether this is a builtin file.

        Returns:
            ID of the loaded taxonomy.
        """
        data = self._parser.load(path)

        entry = TaxonomyEntry(data=data, source_path=path, is_builtin=is_builtin)

        taxonomy_id = data.metadata.id
        self._entries[taxonomy_id] = entry

        # Update type index
        taxonomy_type = data.metadata.type
        if taxonomy_type not in self._by_type:
            self._by_type[taxonomy_type] = []
        if taxonomy_id not in self._by_type[taxonomy_type]:
            self._by_type[taxonomy_type].append(taxonomy_id)

        # Update domain index
        domain = data.metadata.domain
        if domain not in self._by_domain:
            self._by_domain[domain] = []
        if taxonomy_id not in self._by_domain[domain]:
            self._by_domain[domain].append(taxonomy_id)

        return taxonomy_id

    def get(self, taxonomy_id: str) -> TaxonomyData | None:
        """Get taxonomy data by ID.

        Args:
            taxonomy_id: The taxonomy ID to look up.

        Returns:
            TaxonomyData if found, None otherwise.
        """
        entry = self._entries.get(taxonomy_id)
        return entry.data if entry else None

    def get_entry(self, taxonomy_id: str) -> TaxonomyEntry | None:
        """Get full taxonomy entry by ID.

        Args:
            taxonomy_id: The taxonomy ID to look up.

        Returns:
            TaxonomyEntry if found, None otherwise.
        """
        return self._entries.get(taxonomy_id)

    def get_by_type(
        self, taxonomy_type: str, domain: str | None = None
    ) -> list[TaxonomyData]:
        """Get all taxonomy data of a specific type.

        Args:
            taxonomy_type: Type to filter by (examples, descriptions, preset).
            domain: Optional domain to filter by.

        Returns:
            List of matching TaxonomyData.
        """
        ids = self._by_type.get(taxonomy_type, [])
        if domain:
            domain_ids = set(self._by_domain.get(domain, []))
            ids = [tid for tid in ids if tid in domain_ids]
        return [self._entries[tid].data for tid in ids if tid in self._entries]

    def get_combined_examples(
        self, domain: str | None = None
    ) -> list[tuple[str, str, str]]:
        """Get all examples combined, optionally filtered by domain.

        Args:
            domain: Optional domain to filter by. If None, uses "general".

        Returns:
            List of (input_text, path, reasoning) tuples.
        """
        examples: list[tuple[str, str, str]] = []

        # Load general first if no specific domain or if domain is different
        if domain is None or domain == "general":
            for data in self.get_by_type("examples", "general"):
                if data.examples:
                    examples.extend(data.examples)
        elif domain != "general":
            # Load general first, then domain-specific
            for data in self.get_by_type("examples", "general"):
                if data.examples:
                    examples.extend(data.examples)
            for data in self.get_by_type("examples", domain):
                if data.examples:
                    examples.extend(data.examples)

        return examples

    def get_combined_descriptions(self, domain: str | None = None) -> dict[str, str]:
        """Get all descriptions merged, domain-specific overriding general.

        Args:
            domain: Optional domain to filter by. If None, uses "general".

        Returns:
            Dict mapping category to description.
        """
        descriptions: dict[str, str] = {}

        # Load general first
        for data in self.get_by_type("descriptions", "general"):
            if data.descriptions:
                descriptions.update(data.descriptions)

        # Then domain-specific (if different from general)
        if domain and domain != "general":
            for data in self.get_by_type("descriptions", domain):
                if data.descriptions:
                    descriptions.update(data.descriptions)

        return descriptions

    def get_combined_paths(
        self, preset_id: str | None = None, domain: str | None = None
    ) -> dict[str, list[str]]:
        """Get preset paths, optionally filtered by preset ID or domain.

        Args:
            preset_id: Specific preset ID to load.
            domain: Domain to filter by.

        Returns:
            Dict mapping category to list of paths.
        """
        if preset_id:
            data = self.get(preset_id)
            if data and data.paths:
                return data.paths
            return {}

        # Combine all presets for domain
        paths: dict[str, list[str]] = {}
        presets = self.get_by_type("preset", domain or "general")
        for data in presets:
            if data.paths:
                for category, category_paths in data.paths.items():
                    if category not in paths:
                        paths[category] = []
                    paths[category].extend(category_paths)

        return paths

    def list_ids(self) -> list[str]:
        """List all registered taxonomy IDs.

        Returns:
            List of taxonomy IDs.
        """
        return list(self._entries.keys())

    def list_domains(self) -> list[str]:
        """List all available domains.

        Returns:
            List of domain names.
        """
        return list(self._by_domain.keys())

    def list_by_type(self, taxonomy_type: str) -> list[str]:
        """List taxonomy IDs by type.

        Args:
            taxonomy_type: The type to list (examples, descriptions, preset).

        Returns:
            List of taxonomy IDs of that type.
        """
        return list(self._by_type.get(taxonomy_type, []))

    def remove(self, taxonomy_id: str) -> bool:
        """Remove a taxonomy entry from the registry.

        Args:
            taxonomy_id: The taxonomy ID to remove.

        Returns:
            True if removed, False if not found.
        """
        if taxonomy_id not in self._entries:
            return False

        entry = self._entries[taxonomy_id]
        taxonomy_type = entry.data.metadata.type
        domain = entry.data.metadata.domain

        # Remove from type index
        if taxonomy_type in self._by_type:
            self._by_type[taxonomy_type] = [
                tid for tid in self._by_type[taxonomy_type] if tid != taxonomy_id
            ]

        # Remove from domain index
        if domain in self._by_domain:
            self._by_domain[domain] = [
                tid for tid in self._by_domain[domain] if tid != taxonomy_id
            ]

        # Remove entry
        del self._entries[taxonomy_id]
        return True

    def clear(self) -> None:
        """Clear all entries from the registry."""
        self._entries.clear()
        self._by_type = {"examples": [], "descriptions": [], "preset": []}
        self._by_domain = {}

    def __len__(self) -> int:
        """Return the number of entries in the registry."""
        return len(self._entries)

    def __contains__(self, taxonomy_id: str) -> bool:
        """Check if a taxonomy ID is in the registry."""
        return taxonomy_id in self._entries

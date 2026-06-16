# SPDX-License-Identifier: Apache-2.0
"""Unified taxonomy loader for services and applications.

Provides high-level API for loading taxonomy data from markdown files
into the store, and reading from store for classifier/search operations.
"""

import logging
from pathlib import Path
from typing import Any

from .markdown_source import MarkdownTaxonomySource, TaxonomyData
from .registry import TaxonomyRegistry

logger = logging.getLogger(__name__)

# Default namespace for taxonomy data in the store
TAXONOMY_NAMESPACE = ("taxonomy", "v1")


class TaxonomyLoader:
    """
    High-level loader for consuming taxonomy data in services/apps.

    Provides convenient methods for:
    - Loading taxonomy from markdown files (builtin or external)
    - Saving taxonomy data to the memoir store
    - Reading taxonomy from store (for classifier/search)
    - Formatting data for LLM prompts
    """

    def __init__(self, store: Any = None):
        """Initialize the taxonomy loader.

        Args:
            store: ProllyTreeStore instance for persistence.
                   If None, store operations will raise errors.
        """
        self.store = store
        self.registry = TaxonomyRegistry()
        self.namespace = TAXONOMY_NAMESPACE
        self._parser = MarkdownTaxonomySource()

    # -------------------------------------------------------------------------
    # Loading from files to registry
    # -------------------------------------------------------------------------

    def load_builtin(self) -> list[str]:
        """Load all built-in taxonomy files into the registry.

        Returns:
            List of loaded taxonomy IDs.
        """
        return self.registry.load_builtin()

    def load_external(self, path: Path | str) -> str:
        """Load an external taxonomy file into the registry.

        Args:
            path: Path to the markdown file.

        Returns:
            ID of the loaded taxonomy.
        """
        return self.registry.load_external(path)

    # -------------------------------------------------------------------------
    # Saving to store
    # -------------------------------------------------------------------------

    def _ensure_store(self) -> None:
        """Ensure store is available."""
        if self.store is None:
            raise RuntimeError("Store not initialized. Pass store to TaxonomyLoader.")

    def save_to_store(self, taxonomy_id: str) -> bool:
        """Save a single taxonomy entry to the store.

        Args:
            taxonomy_id: ID of the taxonomy to save.

        Returns:
            True if saved successfully, False if not found.
        """
        self._ensure_store()

        data = self.registry.get(taxonomy_id)
        if not data:
            logger.warning(f"Taxonomy not found in registry: {taxonomy_id}")
            return False

        # Save metadata
        meta_key = f"meta:{taxonomy_id}"
        meta_value = {
            "type": data.metadata.type,
            "id": data.metadata.id,
            "name": data.metadata.name,
            "domain": data.metadata.domain,
            "version": data.metadata.version,
            "author": data.metadata.author,
            "description": data.metadata.description,
        }
        if data.metadata.created:
            meta_value["created"] = data.metadata.created
        if data.metadata.updated:
            meta_value["updated"] = data.metadata.updated
        if data.metadata.taxonomy_version:
            meta_value["taxonomy_version"] = data.metadata.taxonomy_version

        self.store.put(self.namespace, meta_key, {"value": meta_value})

        # Save type-specific data
        if data.metadata.type == "examples" and data.examples:
            examples_key = f"examples:{taxonomy_id}"
            examples_value = [
                {"input": inp, "path": path, "reasoning": reason}
                for inp, path, reason in data.examples
            ]
            self.store.put(self.namespace, examples_key, {"value": examples_value})

        elif data.metadata.type == "descriptions" and data.descriptions:
            desc_key = f"descriptions:{taxonomy_id}"
            self.store.put(self.namespace, desc_key, {"value": data.descriptions})

        elif data.metadata.type == "preset" and data.paths:
            preset_key = f"preset:{taxonomy_id}"
            self.store.put(self.namespace, preset_key, {"value": data.paths})

        # Update indexes
        self._update_indexes(data)

        logger.debug(f"Saved taxonomy to store: {taxonomy_id}")
        return True

    def save_all_to_store(self) -> int:
        """Save all taxonomies in the registry to the store.

        Returns:
            Number of taxonomies saved.
        """
        self._ensure_store()

        saved_count = 0
        for taxonomy_id in self.registry.list_ids():
            if self.save_to_store(taxonomy_id):
                saved_count += 1

        return saved_count

    def _update_indexes(self, data: TaxonomyData) -> None:
        """Update the type and domain indexes in the store.

        Args:
            data: The taxonomy data to index.
        """
        taxonomy_id = data.metadata.id
        taxonomy_type = data.metadata.type
        domain = data.metadata.domain

        # Update type index
        type_index_key = "index:by-type"
        type_index = self._get_from_store(type_index_key, {})
        if taxonomy_type not in type_index:
            type_index[taxonomy_type] = []
        if taxonomy_id not in type_index[taxonomy_type]:
            type_index[taxonomy_type].append(taxonomy_id)
        self.store.put(self.namespace, type_index_key, {"value": type_index})

        # Update domain index
        domain_index_key = "index:by-domain"
        domain_index = self._get_from_store(domain_index_key, {})
        if domain not in domain_index:
            domain_index[domain] = []
        if taxonomy_id not in domain_index[domain]:
            domain_index[domain].append(taxonomy_id)
        self.store.put(self.namespace, domain_index_key, {"value": domain_index})

    def _get_from_store(self, key: str, default: Any = None) -> Any:
        """Get a value from the store with default.

        Args:
            key: Store key.
            default: Default value if not found.

        Returns:
            Value from store or default.
        """
        result = self.store.get(self.namespace, key)
        if result is None:
            return default
        # Handle the Item wrapper if present
        if hasattr(result, "value"):
            return result.value.get("value", default)
        if isinstance(result, dict):
            return result.get("value", default)
        return default

    # -------------------------------------------------------------------------
    # Loading from store (for classifier/search)
    # -------------------------------------------------------------------------

    def get_examples_from_store(
        self, limit: int | None = None, domain: str | None = None
    ) -> list[tuple[str, str, str]]:
        """Get classification examples from the store.

        Args:
            limit: Maximum number of examples to return.
            domain: Domain to filter by (default: general).

        Returns:
            List of (input_text, path, reasoning) tuples.
        """
        self._ensure_store()

        # Get type index
        type_index = self._get_from_store("index:by-type", {})
        example_ids = type_index.get("examples", [])
        logger.debug(
            f"[TaxonomyLoader] Loading examples from store, found IDs: {example_ids}"
        )

        # Filter by domain if specified
        if domain:
            domain_index = self._get_from_store("index:by-domain", {})
            domain_ids = set(domain_index.get(domain, []))
            example_ids = [eid for eid in example_ids if eid in domain_ids]

        # Collect all examples
        examples: list[tuple[str, str, str]] = []
        for taxonomy_id in example_ids:
            key = f"examples:{taxonomy_id}"
            example_data = self._get_from_store(key, [])
            for item in example_data:
                examples.append((item["input"], item["path"], item["reasoning"]))
                if limit and len(examples) >= limit:
                    logger.debug(
                        f"[TaxonomyLoader] Loaded {len(examples)} examples from store (limit reached)"
                    )
                    return examples

        logger.debug(f"[TaxonomyLoader] Loaded {len(examples)} examples from store")
        return examples[:limit] if limit else examples

    def get_descriptions_from_store(self, domain: str | None = None) -> dict[str, str]:
        """Get category descriptions from the store.

        Args:
            domain: Domain to filter by (default: general).

        Returns:
            Dict mapping category to description.
        """
        self._ensure_store()

        # Get type index
        type_index = self._get_from_store("index:by-type", {})
        desc_ids = type_index.get("descriptions", [])

        # Filter by domain if specified
        if domain:
            domain_index = self._get_from_store("index:by-domain", {})
            domain_ids = set(domain_index.get(domain, []))
            # Include both general and domain-specific
            general_ids = set(domain_index.get("general", []))
            desc_ids = [
                did for did in desc_ids if did in domain_ids or did in general_ids
            ]

        # Merge descriptions (later entries override earlier)
        descriptions: dict[str, str] = {}
        for taxonomy_id in desc_ids:
            key = f"descriptions:{taxonomy_id}"
            desc_data = self._get_from_store(key, {})
            descriptions.update(desc_data)

        logger.debug(
            f"[TaxonomyLoader] Loaded {len(descriptions)} category descriptions from store"
        )
        return descriptions

    def get_preset_paths_from_store(
        self, preset_id: str | None = None
    ) -> dict[str, list[str]]:
        """Get preset taxonomy paths from the store.

        Args:
            preset_id: Specific preset ID to load, or None for all.

        Returns:
            Dict mapping category to list of paths.
        """
        self._ensure_store()

        if preset_id:
            key = f"preset:{preset_id}"
            paths = self._get_from_store(key, {})
            logger.debug(
                f"[TaxonomyLoader] Loaded preset '{preset_id}' from store: {len(paths)} categories"
            )
            return paths

        # Get all presets
        type_index = self._get_from_store("index:by-type", {})
        preset_ids = type_index.get("preset", [])

        paths: dict[str, list[str]] = {}
        for pid in preset_ids:
            key = f"preset:{pid}"
            preset_data = self._get_from_store(key, {})
            for category, category_paths in preset_data.items():
                if category not in paths:
                    paths[category] = []
                paths[category].extend(category_paths)

        return paths

    # -------------------------------------------------------------------------
    # Convenience: Initialize store from files
    # -------------------------------------------------------------------------

    def init_store(
        self,
        include_builtin: bool = True,
        external_paths: list[Path | str] | None = None,
        merge_strategy: str = "extend",
    ) -> dict[str, Any]:
        """Initialize the store with taxonomy data from files.

        Args:
            include_builtin: Whether to load builtin taxonomy files.
            external_paths: List of external markdown file paths.
            merge_strategy: How to handle existing data:
                - "extend": Add new entries, keep existing (default)
                - "override": External entries replace same-id entries
                - "replace": Clear store, load only specified sources

        Returns:
            Dict with counts of loaded taxonomies by type.
        """
        self._ensure_store()

        # Clear if replace strategy
        if merge_strategy == "replace":
            self._clear_taxonomy_from_store()
            self.registry.clear()

        loaded: dict[str, int] = {"examples": 0, "descriptions": 0, "preset": 0}

        # Load builtin
        if include_builtin:
            builtin_ids = self.load_builtin()
            for tid in builtin_ids:
                data = self.registry.get(tid)
                if data:
                    loaded[data.metadata.type] = loaded.get(data.metadata.type, 0) + 1

        # Load external
        if external_paths:
            for path in external_paths:
                try:
                    tid = self.load_external(path)
                    data = self.registry.get(tid)
                    if data:
                        loaded[data.metadata.type] = (
                            loaded.get(data.metadata.type, 0) + 1
                        )
                except Exception as e:
                    logger.error(f"Failed to load external taxonomy {path}: {e}")

        # Save to store
        saved_count = self.save_all_to_store()
        logger.info(f"Initialized store with {saved_count} taxonomy entries")

        return {
            "loaded": loaded,
            "saved": saved_count,
        }

    def _clear_taxonomy_from_store(self) -> None:
        """Clear all taxonomy data from the store."""
        # Get all keys and remove them
        type_index = self._get_from_store("index:by-type", {})

        for taxonomy_type, ids in type_index.items():
            for tid in ids:
                if taxonomy_type == "examples":
                    self.store.delete(self.namespace, f"examples:{tid}")
                elif taxonomy_type == "descriptions":
                    self.store.delete(self.namespace, f"descriptions:{tid}")
                elif taxonomy_type == "preset":
                    self.store.delete(self.namespace, f"preset:{tid}")
                self.store.delete(self.namespace, f"meta:{tid}")

        # Clear indexes
        self.store.delete(self.namespace, "index:by-type")
        self.store.delete(self.namespace, "index:by-domain")

    # -------------------------------------------------------------------------
    # Prompt formatting (reads from store)
    # -------------------------------------------------------------------------

    def format_for_prompt(
        self,
        include_examples: bool = True,
        include_descriptions: bool = True,
        example_limit: int = 8,
        domain: str | None = None,
    ) -> str:
        """Format taxonomy data for LLM prompt insertion.

        Reads from the store (not registry) to ensure consistency
        with what's persisted.

        Args:
            include_examples: Whether to include classification examples.
            include_descriptions: Whether to include category descriptions.
            example_limit: Maximum number of examples to include.
            domain: Domain to filter by.

        Returns:
            Formatted string ready for prompt inclusion.
        """
        parts = []

        if include_descriptions:
            descriptions = self.get_descriptions_from_store(domain)
            if descriptions:
                parts.append("TAXONOMY CATEGORIES:")
                for cat, desc in sorted(descriptions.items()):
                    parts.append(f"  {cat}: {desc}")
                parts.append("")

        if include_examples:
            examples = self.get_examples_from_store(limit=example_limit, domain=domain)
            if examples:
                parts.append(
                    "CLASSIFICATION EXAMPLES (3-level paths: category.subcategory.type):"
                )
                for input_text, path, _reasoning in examples:
                    parts.append(f'  "{input_text}" -> {path}')
                parts.append("")

        return "\n".join(parts)

    def render_prompt_snippet(self, max_examples: int = 500) -> str:
        """Render the persisted taxonomy as a CATEGORIES / EXAMPLES block.

        Output mirrors the structure used by memoir's own classifier
        (``_build_fast_classification_prompt``), so out-of-process
        extractors — the Claude Code Stop hook and ``memoir capture`` —
        classify against the same taxonomy grounding as ``memoir
        remember``. Returns an empty string when the store has no
        taxonomy; callers fall back to their own hardcoded default.

        This is the single source of truth for both the ``taxonomy
        prompt-snippet`` CLI command and the ``capture`` extraction
        prompt — keep them sharing it so they cannot drift.
        """
        if not self.has_taxonomy_in_store():
            return ""

        descriptions = self.get_descriptions_from_store() or {}
        examples = self.get_examples_from_store() or []
        if not descriptions and not examples:
            return ""

        # Deterministic ordering (path, then input text) — matches
        # _build_fast_classification_prompt's limit=500 behavior.
        selected = sorted(examples, key=lambda e: (e[1], e[0]))[:max_examples]

        lines: list[str] = []
        if descriptions:
            lines.append("CATEGORIES:")
            for cat, desc in sorted(descriptions.items()):
                lines.append(f"  {cat}: {desc}")
            lines.append("")

        if selected:
            lines.append(
                "EXAMPLES (paths MUST be exactly 3 levels: "
                "category.subcategory.type):"
            )
            for input_text, path, _reason in selected:
                lines.append(f'  "{input_text}" → {path}')
            lines.append("")

        return "\n".join(lines).rstrip()

    # -------------------------------------------------------------------------
    # Utility methods
    # -------------------------------------------------------------------------

    def list_stored_taxonomies(self) -> dict[str, list[str]]:
        """List all taxonomies stored in the store, grouped by type.

        Returns:
            Dict mapping type to list of taxonomy IDs.
        """
        self._ensure_store()
        return self._get_from_store("index:by-type", {})

    def get_taxonomy_metadata(self, taxonomy_id: str) -> dict[str, Any] | None:
        """Get metadata for a specific taxonomy from the store.

        Args:
            taxonomy_id: The taxonomy ID.

        Returns:
            Metadata dict or None if not found.
        """
        self._ensure_store()
        return self._get_from_store(f"meta:{taxonomy_id}")

    def has_taxonomy_in_store(self) -> bool:
        """Check if any taxonomy data exists in the store.

        Returns:
            True if taxonomy data exists.
        """
        self._ensure_store()
        type_index = self._get_from_store("index:by-type", {})
        return bool(type_index)

"""Integration tests for TaxonomyLoader and store-based taxonomy."""

import tempfile

import pytest

from memoir.store.prolly_adapter import ProllyTreeStore
from memoir.taxonomy import TaxonomyLoader


class TestTaxonomyLoaderIntegration:
    """Integration tests for TaxonomyLoader with actual store."""

    @pytest.fixture
    def temp_store(self):
        """Create a temporary store for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ProllyTreeStore(tmpdir)
            yield store

    def test_init_store_with_builtin(self, temp_store):
        """Test initializing store with builtin taxonomy."""
        loader = TaxonomyLoader(temp_store)

        result = loader.init_store(include_builtin=True)

        assert result["saved"] == 3
        assert result["loaded"]["examples"] == 1
        assert result["loaded"]["descriptions"] == 1
        assert result["loaded"]["preset"] == 1

    def test_get_examples_from_store(self, temp_store):
        """Test retrieving examples from store."""
        loader = TaxonomyLoader(temp_store)
        loader.init_store(include_builtin=True)

        examples = loader.get_examples_from_store()

        assert len(examples) > 100  # Should have 215 examples
        assert all(len(ex) == 3 for ex in examples)  # (input, path, reasoning)

    def test_get_examples_with_limit(self, temp_store):
        """Test retrieving limited examples from store."""
        loader = TaxonomyLoader(temp_store)
        loader.init_store(include_builtin=True)

        examples = loader.get_examples_from_store(limit=10)

        assert len(examples) == 10

    def test_get_descriptions_from_store(self, temp_store):
        """Test retrieving descriptions from store."""
        loader = TaxonomyLoader(temp_store)
        loader.init_store(include_builtin=True)

        descriptions = loader.get_descriptions_from_store()

        assert len(descriptions) == 16  # 16 categories
        assert "profile" in descriptions
        assert "preferences" in descriptions

    def test_get_preset_paths_from_store(self, temp_store):
        """Test retrieving preset paths from store."""
        loader = TaxonomyLoader(temp_store)
        loader.init_store(include_builtin=True)

        paths = loader.get_preset_paths_from_store("simplified-preset")

        assert len(paths) >= 9  # At least 9 categories
        assert "profile" in paths
        assert len(paths["profile"]) > 0

    def test_format_for_prompt(self, temp_store):
        """Test formatting taxonomy for LLM prompt."""
        loader = TaxonomyLoader(temp_store)
        loader.init_store(include_builtin=True)

        prompt = loader.format_for_prompt(
            include_examples=True,
            include_descriptions=True,
            example_limit=8,
        )

        assert "TAXONOMY CATEGORIES:" in prompt
        assert "CLASSIFICATION EXAMPLES" in prompt
        assert "profile:" in prompt  # Category description

    def test_list_stored_taxonomies(self, temp_store):
        """Test listing taxonomies in store."""
        loader = TaxonomyLoader(temp_store)
        loader.init_store(include_builtin=True)

        taxonomies = loader.list_stored_taxonomies()

        assert "examples" in taxonomies
        assert "descriptions" in taxonomies
        assert "preset" in taxonomies
        assert "general-examples" in taxonomies["examples"]

    def test_has_taxonomy_in_store(self, temp_store):
        """Test checking if taxonomy exists in store."""
        loader = TaxonomyLoader(temp_store)

        # Before initialization
        assert not loader.has_taxonomy_in_store()

        # After initialization
        loader.init_store(include_builtin=True)
        assert loader.has_taxonomy_in_store()

    def test_get_taxonomy_metadata(self, temp_store):
        """Test retrieving taxonomy metadata."""
        loader = TaxonomyLoader(temp_store)
        loader.init_store(include_builtin=True)

        meta = loader.get_taxonomy_metadata("general-examples")

        assert meta is not None
        assert meta["type"] == "examples"
        assert meta["id"] == "general-examples"
        assert meta["domain"] == "general"


class TestTaxonomyLoaderWithExternalFiles:
    """Tests for loading external taxonomy files."""

    @pytest.fixture
    def temp_store(self):
        """Create a temporary store for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ProllyTreeStore(tmpdir)
            yield store

    def test_load_external_file(self, temp_store):
        """Test loading an external taxonomy file."""
        # Create a temporary markdown file
        content = """---
type: examples
id: custom-examples
name: Custom Examples
domain: custom
version: 1.0.0
---

# Custom Examples

## profile

| Input | Path | Reasoning |
|-------|------|-----------|
| Custom input | profile.custom.test | test |
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()

            loader = TaxonomyLoader(temp_store)
            tid = loader.load_external(f.name)
            loader.save_to_store(tid)

            # Verify it's in the store
            meta = loader.get_taxonomy_metadata("custom-examples")
            assert meta is not None
            assert meta["domain"] == "custom"

    def test_init_with_builtin_and_external(self, temp_store):
        """Test initializing with both builtin and external files."""
        # Create a temporary markdown file
        content = """---
type: descriptions
id: custom-descriptions
name: Custom Descriptions
domain: custom
version: 1.0.0
---

# Custom Descriptions

| Category | Description |
|----------|-------------|
| custom | A custom category |
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()

            loader = TaxonomyLoader(temp_store)
            result = loader.init_store(
                include_builtin=True,
                external_paths=[f.name],
            )

            # Should have loaded builtin + 1 external
            assert result["saved"] == 4  # 3 builtin + 1 external

            taxonomies = loader.list_stored_taxonomies()
            assert "custom-descriptions" in taxonomies["descriptions"]


class TestClassifierWithTaxonomyLoader:
    """Tests for IntelligentClassifier with TaxonomyLoader."""

    @pytest.fixture
    def temp_store(self):
        """Create a temporary store with taxonomy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ProllyTreeStore(tmpdir)
            loader = TaxonomyLoader(store)
            loader.init_store(include_builtin=True)
            yield store

    def test_classifier_uses_taxonomy_loader(self, temp_store):
        """Test that classifier can use TaxonomyLoader."""
        from unittest.mock import MagicMock

        from memoir.classifier.intelligent import IntelligentClassifier
        from memoir.taxonomy import TaxonomyLoader

        # Create a mock LLM
        mock_llm = MagicMock()

        # Create loader with store
        loader = TaxonomyLoader(temp_store)

        # Create classifier with loader
        classifier = IntelligentClassifier(
            llm=mock_llm,
            taxonomy_loader=loader,
        )

        # Verify the classifier loaded paths from store
        all_paths = classifier.taxonomy.get_all_paths()
        assert len(all_paths) > 100  # Should have many paths

    def test_classifier_fallback_without_loader(self):
        """Test that classifier falls back to presets without loader."""
        from unittest.mock import MagicMock

        from memoir.classifier.intelligent import IntelligentClassifier

        mock_llm = MagicMock()

        # Create classifier without loader
        classifier = IntelligentClassifier(
            llm=mock_llm,
            taxonomy_loader=None,
        )

        # Should still have paths (from TaxonomyPresets fallback)
        # Fallback is minimal (~40-70 paths), full taxonomy has ~200+
        all_paths = classifier.taxonomy.get_all_paths()
        assert len(all_paths) > 20


class TestSearchEngineWithTaxonomyLoader:
    """Tests for IntelligentSearchEngine with TaxonomyLoader."""

    @pytest.fixture
    def temp_store(self):
        """Create a temporary store with taxonomy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ProllyTreeStore(tmpdir)
            loader = TaxonomyLoader(store)
            loader.init_store(include_builtin=True)
            yield store

    def test_search_engine_uses_taxonomy_loader(self, temp_store):
        """Test that search engine can use TaxonomyLoader."""
        from unittest.mock import MagicMock

        from memoir.search.intelligent import IntelligentSearchEngine
        from memoir.taxonomy import TaxonomyLoader

        mock_llm = MagicMock()
        loader = TaxonomyLoader(temp_store)

        engine = IntelligentSearchEngine(
            llm=mock_llm,
            store=temp_store,
            taxonomy_loader=loader,
        )

        # Build static prompt should use store data
        prompt = engine._build_static_prompt()
        assert "profile:" in prompt  # Category from store
        assert "TAXONOMY CATEGORIES" in prompt

    def test_search_engine_fallback_without_loader(self):
        """Test that search engine falls back to presets without loader."""
        from unittest.mock import MagicMock

        from memoir.search.intelligent import IntelligentSearchEngine

        mock_llm = MagicMock()
        mock_store = MagicMock()

        engine = IntelligentSearchEngine(
            llm=mock_llm,
            store=mock_store,
            taxonomy_loader=None,
        )

        # Build static prompt should work with fallback
        prompt = engine._build_static_prompt()
        assert "TAXONOMY CATEGORIES" in prompt

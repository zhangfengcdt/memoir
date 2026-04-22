"""Tests for markdown-based taxonomy loading."""

import tempfile
from pathlib import Path

import pytest

from memoir.taxonomy import (
    MarkdownTaxonomySource,
    TaxonomyParseError,
    TaxonomyRegistry,
)


class TestMarkdownTaxonomySource:
    """Tests for MarkdownTaxonomySource parser."""

    def test_parse_examples(self):
        """Test parsing examples markdown."""
        content = """---
type: examples
id: test-examples
name: Test Examples
domain: general
version: 1.0.0
---

# Examples

## profile

| Input | Path | Reasoning |
|-------|------|-----------|
| My name is John | profile.personal.identity | identity |
| I am 30 years old | profile.personal.demographics | demographics |

## preferences

| Input | Path | Reasoning |
|-------|------|-----------|
| I love Python | preferences.coding.languages | language pref |
"""
        parser = MarkdownTaxonomySource()
        data = parser.parse(content)

        assert data.metadata.type == "examples"
        assert data.metadata.id == "test-examples"
        assert data.metadata.name == "Test Examples"
        assert data.metadata.domain == "general"
        assert len(data.examples) == 3
        assert data.examples[0] == (
            "My name is John",
            "profile.personal.identity",
            "identity",
        )

    def test_parse_descriptions(self):
        """Test parsing descriptions markdown."""
        content = """---
type: descriptions
id: test-descriptions
name: Test Descriptions
domain: general
version: 1.0.0
---

# Category Descriptions

| Category | Description |
|----------|-------------|
| profile | Personal information |
| preferences | User preferences |
"""
        parser = MarkdownTaxonomySource()
        data = parser.parse(content)

        assert data.metadata.type == "descriptions"
        assert data.metadata.id == "test-descriptions"
        assert len(data.descriptions) == 2
        assert data.descriptions["profile"] == "Personal information"
        assert data.descriptions["preferences"] == "User preferences"

    def test_parse_preset(self):
        """Test parsing preset markdown."""
        content = """---
type: preset
id: test-preset
name: Test Preset
domain: general
version: 1.0.0
taxonomy_version: simplified
---

# Preset

## profile

- personal.identity
- personal.demographics
- professional.occupation

## preferences

- coding.languages
- coding.frameworks
"""
        parser = MarkdownTaxonomySource()
        data = parser.parse(content)

        assert data.metadata.type == "preset"
        assert data.metadata.id == "test-preset"
        assert data.metadata.taxonomy_version == "simplified"
        assert len(data.paths) == 2
        assert len(data.paths["profile"]) == 3
        assert len(data.paths["preferences"]) == 2
        assert "personal.identity" in data.paths["profile"]

    def test_parse_missing_frontmatter(self):
        """Test error on missing frontmatter."""
        content = """# No frontmatter here
Some content.
"""
        parser = MarkdownTaxonomySource()
        with pytest.raises(TaxonomyParseError, match="missing YAML frontmatter"):
            parser.parse(content)

    def test_parse_missing_required_field(self):
        """Test error on missing required field."""
        content = """---
type: examples
name: Missing ID
---

# Content
"""
        parser = MarkdownTaxonomySource()
        with pytest.raises(TaxonomyParseError, match=r"Missing required field.*id"):
            parser.parse(content)

    def test_parse_unknown_type(self):
        """Test error on unknown type."""
        content = """---
type: unknown
id: test
name: Test
---

# Content
"""
        parser = MarkdownTaxonomySource()
        with pytest.raises(TaxonomyParseError, match="Unknown taxonomy type"):
            parser.parse(content)

    def test_to_dict_and_from_dict(self):
        """Test round-trip serialization."""
        content = """---
type: examples
id: test-examples
name: Test Examples
domain: general
version: 1.0.0
---

# Examples

## profile

| Input | Path | Reasoning |
|-------|------|-----------|
| My name is John | profile.personal.identity | identity |
"""
        parser = MarkdownTaxonomySource()
        data = parser.parse(content)

        # Convert to dict and back
        data_dict = parser.to_dict(data)
        restored = parser.from_dict(data_dict)

        assert restored.metadata.id == data.metadata.id
        assert restored.metadata.type == data.metadata.type
        assert restored.examples == data.examples

    def test_load_file(self):
        """Test loading from file."""
        content = """---
type: descriptions
id: file-test
name: File Test
domain: general
version: 1.0.0
---

# Descriptions

| Category | Description |
|----------|-------------|
| test | Test category |
"""
        parser = MarkdownTaxonomySource()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()

            data = parser.load(Path(f.name))
            assert data.metadata.id == "file-test"
            assert data.descriptions["test"] == "Test category"

    def test_load_nonexistent_file(self):
        """Test error on nonexistent file."""
        parser = MarkdownTaxonomySource()
        with pytest.raises(FileNotFoundError):
            parser.load(Path("/nonexistent/file.md"))


class TestTaxonomyRegistry:
    """Tests for TaxonomyRegistry."""

    def test_load_builtin(self):
        """Test loading builtin taxonomy files."""
        registry = TaxonomyRegistry()
        ids = registry.load_builtin()

        # Should load at least the general examples, descriptions, and preset
        assert len(ids) >= 3
        assert "general-examples" in ids
        assert "general-categories" in ids
        assert "simplified-preset" in ids

    def test_get_by_id(self):
        """Test getting taxonomy by ID."""
        registry = TaxonomyRegistry()
        registry.load_builtin()

        data = registry.get("general-examples")
        assert data is not None
        assert data.metadata.type == "examples"

        # Non-existent ID
        assert registry.get("nonexistent") is None

    def test_get_by_type(self):
        """Test getting taxonomies by type."""
        registry = TaxonomyRegistry()
        registry.load_builtin()

        examples = registry.get_by_type("examples")
        assert len(examples) >= 1
        assert all(d.metadata.type == "examples" for d in examples)

        descriptions = registry.get_by_type("descriptions")
        assert len(descriptions) >= 1
        assert all(d.metadata.type == "descriptions" for d in descriptions)

    def test_get_combined_examples(self):
        """Test getting combined examples."""
        registry = TaxonomyRegistry()
        registry.load_builtin()

        examples = registry.get_combined_examples()
        assert len(examples) > 100  # Should have many examples

        # Each example should be a tuple of 3
        for ex in examples:
            assert len(ex) == 3
            assert isinstance(ex[0], str)  # input
            assert isinstance(ex[1], str)  # path
            assert isinstance(ex[2], str)  # reasoning

    def test_get_combined_descriptions(self):
        """Test getting combined descriptions."""
        registry = TaxonomyRegistry()
        registry.load_builtin()

        descriptions = registry.get_combined_descriptions()
        assert len(descriptions) == 17  # 17 categories (v1.1.0 taxonomy)
        assert "profile" in descriptions
        assert "preferences" in descriptions

    def test_get_combined_paths(self):
        """Test getting combined paths."""
        registry = TaxonomyRegistry()
        registry.load_builtin()

        paths = registry.get_combined_paths()
        assert len(paths) >= 9  # At least 9 non-empty categories

        # Check structure
        assert "profile" in paths
        assert len(paths["profile"]) > 0

    def test_load_external(self):
        """Test loading external file."""
        content = """---
type: descriptions
id: external-test
name: External Test
domain: custom
version: 1.0.0
---

# Descriptions

| Category | Description |
|----------|-------------|
| custom | Custom category |
"""
        registry = TaxonomyRegistry()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(content)
            f.flush()

            tid = registry.load_external(f.name)
            assert tid == "external-test"
            assert "external-test" in registry

            data = registry.get("external-test")
            assert data.metadata.domain == "custom"

    def test_list_domains(self):
        """Test listing domains."""
        registry = TaxonomyRegistry()
        registry.load_builtin()

        domains = registry.list_domains()
        assert "general" in domains

    def test_remove(self):
        """Test removing taxonomy."""
        registry = TaxonomyRegistry()
        registry.load_builtin()

        assert "general-examples" in registry
        result = registry.remove("general-examples")
        assert result is True
        assert "general-examples" not in registry

        # Remove non-existent
        result = registry.remove("nonexistent")
        assert result is False

    def test_clear(self):
        """Test clearing registry."""
        registry = TaxonomyRegistry()
        registry.load_builtin()

        assert len(registry) > 0
        registry.clear()
        assert len(registry) == 0

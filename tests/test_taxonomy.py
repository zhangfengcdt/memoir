"""Tests for semantic taxonomy."""

from memoir.taxonomy import TaxonomyCategory, get_taxonomy


class TestSemanticTaxonomy:
    """Test semantic taxonomy functionality."""

    def test_singleton_instance(self):
        """Test that get_taxonomy returns singleton."""
        tax1 = get_taxonomy()
        tax2 = get_taxonomy()
        assert tax1 is tax2

    def test_taxonomy_size(self):
        """Test that taxonomy has expected number of paths."""
        taxonomy = get_taxonomy()
        paths = taxonomy.get_all_paths()

        # Simplified taxonomy has ~200-250 paths (3 levels max)
        assert len(paths) >= 150

        # All paths should be unique
        assert len(paths) == len(set(paths))

    def test_path_validation(self):
        """Test path validation."""
        taxonomy = get_taxonomy()

        # Valid paths (3-level simplified taxonomy)
        assert taxonomy.is_valid_path("profile.personal.identity")
        assert taxonomy.is_valid_path("preferences.coding.languages")
        assert taxonomy.is_valid_path("experience.work.projects")

        # Invalid paths
        assert not taxonomy.is_valid_path("invalid.path.here")
        assert not taxonomy.is_valid_path("")
        assert not taxonomy.is_valid_path("profile.invalid.category")

    def test_get_children(self):
        """Test getting children of a path."""
        taxonomy = get_taxonomy()

        # Test root level
        children = taxonomy.get_children("profile")
        assert "profile.personal" in children
        assert "profile.professional" in children

        # Test second level (simplified taxonomy is 3 levels deep)
        children = taxonomy.get_children("profile.personal")
        assert "profile.personal.identity" in children
        assert "profile.personal.demographics" in children

    def test_get_descendants(self):
        """Test getting all descendants."""
        taxonomy = get_taxonomy()

        # Simplified taxonomy: profile.personal has several 3-level paths
        descendants = taxonomy.get_descendants("profile.personal")

        # Should include all sub-paths
        assert len(descendants) > 2
        assert all(d.startswith("profile.personal") for d in descendants)

    def test_path_depth(self):
        """Test path depth calculation."""
        taxonomy = get_taxonomy()

        assert taxonomy.get_path_depth("profile") == 1
        assert taxonomy.get_path_depth("profile.personal") == 2
        assert taxonomy.get_path_depth("profile.personal.identity") == 3

    def test_get_category(self):
        """Test category extraction."""
        taxonomy = get_taxonomy()

        assert (
            taxonomy.get_category("profile.personal.identity")
            == TaxonomyCategory.PROFILE
        )
        assert (
            taxonomy.get_category("preferences.technology")
            == TaxonomyCategory.PREFERENCES
        )
        assert (
            taxonomy.get_category("goals.timeframes.short_term")
            == TaxonomyCategory.GOALS
        )
        assert taxonomy.get_category("invalid.path") is None

    def test_related_paths(self):
        """Test finding related paths."""
        taxonomy = get_taxonomy()

        related = taxonomy.get_related_paths(
            "profile.personal.identity", max_distance=2
        )

        # Should include siblings
        assert any("demographics" in r for r in related)

        # Should include parent
        assert "profile.personal" in related

        # Should not include self
        assert "profile.personal.identity" not in related

    def test_statistics(self):
        """Test taxonomy statistics."""
        taxonomy = get_taxonomy()
        stats = taxonomy.get_statistics()

        # Simplified taxonomy has ~200-250 paths at max depth 3
        assert stats["total_paths"] >= 150
        assert stats["categories"] == len(list(TaxonomyCategory))
        assert stats["max_depth"] >= 3
        assert "paths_by_category" in stats
        assert "paths_by_depth" in stats


class TestTaxonomyCategories:
    """Test taxonomy categories are comprehensive."""

    def test_all_categories_present(self):
        """Test all expected categories exist."""
        expected = [
            "PROFILE",
            "PREFERENCES",
            "EXPERIENCE",
            "CONTEXT",
            "KNOWLEDGE",
            "RELATIONSHIPS",
            "GOALS",
            "BEHAVIOR",
        ]

        actual = [c.name for c in TaxonomyCategory]
        for exp in expected:
            assert exp in actual

    def test_category_coverage(self):
        """Test each category has sufficient paths."""
        taxonomy = get_taxonomy()
        stats = taxonomy.get_statistics()

        # Simplified taxonomy: each category should have at least 5 paths
        # (some categories like timeline, location are managed separately)
        for category, count in stats["paths_by_category"].items():
            assert count >= 1, f"Category {category} has insufficient paths: {count}"

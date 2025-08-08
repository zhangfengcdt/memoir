"""Tests for semantic classifier."""


import pytest

from langmem_prollytree.taxonomy import ClassificationResult, OptimizedClassifier


class TestOptimizedClassifier:
    """Test optimized classifier functionality."""

    @pytest.fixture
    def classifier(self):
        """Create classifier instance."""
        return OptimizedClassifier()

    def test_fast_classify_name(self, classifier):
        """Test classification of name-related content."""
        result = classifier.fast_classify("My name is John Smith")

        assert isinstance(result, ClassificationResult)
        assert "profile.personal.identity.name" in result.primary_path
        assert result.confidence > 0.5
        assert result.reasoning is not None

    def test_fast_classify_work(self, classifier):
        """Test classification of work-related content."""
        result = classifier.fast_classify("I work at Google as a software engineer")

        assert "profile.professional" in result.primary_path
        assert result.confidence > 0.5

    def test_fast_classify_preferences(self, classifier):
        """Test classification of preferences."""
        result = classifier.fast_classify("I prefer dark mode in my IDE")

        assert "preferences" in result.primary_path
        assert result.confidence > 0.5

    def test_fast_classify_programming(self, classifier):
        """Test classification of programming skills."""
        result = classifier.fast_classify("I have 5 years of Python experience")

        assert "programming" in result.primary_path or "skills" in result.primary_path
        assert result.confidence > 0.5

    def test_fast_classify_project(self, classifier):
        """Test classification of project information."""
        result = classifier.fast_classify("Working on a machine learning project")

        assert "project" in result.primary_path or "experience" in result.primary_path
        assert result.confidence > 0.5

    def test_fast_classify_goals(self, classifier):
        """Test classification of goals."""
        result = classifier.fast_classify("My goal is to become a senior engineer")

        assert "goal" in result.primary_path
        assert result.confidence > 0.5

    def test_fast_classify_relationships(self, classifier):
        """Test classification of relationships."""
        result = classifier.fast_classify(
            "My colleague Sarah helped with the code review"
        )

        assert (
            "colleague" in result.primary_path or "relationships" in result.primary_path
        )
        assert result.confidence > 0.5

    def test_fast_classify_no_match(self, classifier):
        """Test classification with no clear match."""
        result = classifier.fast_classify("Random text without clear category")

        assert result.primary_path == "context.current.session.topic.main"
        assert result.confidence == 0.5

    def test_batch_classify(self, classifier):
        """Test batch classification."""
        memories = [
            "My name is Alice",
            "I work at Microsoft",
            "I prefer Python over Java",
            "My goal is to learn Rust",
        ]

        results = classifier.batch_classify(memories)

        assert len(results) == 4
        assert all(isinstance(r, ClassificationResult) for r in results)
        assert "name" in results[0].primary_path
        assert (
            "work" in results[1].primary_path
            or "professional" in results[1].primary_path
        )
        assert (
            "prefer" in results[2].primary_path
            or "preferences" in results[2].primary_path
        )
        assert "goal" in results[3].primary_path

    @pytest.mark.asyncio
    async def test_async_classification(self, classifier):
        """Test async classification (mock mode)."""
        result = await classifier.classify_async(
            "I'm learning machine learning", context={"user_id": "test_user"}
        )

        assert isinstance(result, ClassificationResult)
        assert result.primary_path is not None
        assert result.confidence > 0

    def test_cache_functionality(self, classifier):
        """Test that caching works."""
        memory = "Test memory content for caching"

        # First call
        result1 = classifier.classify(memory)

        # Second call (should hit cache)
        result2 = classifier.classify(memory)

        assert result1.primary_path == result2.primary_path
        assert result1.confidence == result2.confidence

        # Check cache statistics
        stats = classifier.get_statistics()
        assert stats["cache_size"] > 0

    def test_statistics(self, classifier):
        """Test classifier statistics."""
        # Classify some memories to populate stats
        classifier.fast_classify("Test memory 1")
        classifier.fast_classify("Test memory 2")

        stats = classifier.get_statistics()

        assert "cache_size" in stats
        assert "taxonomy_paths" in stats
        assert "categories" in stats
        assert stats["taxonomy_paths"] > 0
        assert stats["categories"] > 0


class TestClassificationAccuracy:
    """Test classification accuracy for various inputs."""

    @pytest.fixture
    def classifier(self):
        return OptimizedClassifier()

    def test_identity_classification(self, classifier):
        """Test identity-related classifications."""
        test_cases = [
            ("My name is Bob", "identity"),
            ("I'm 30 years old", "age"),
            ("I'm from San Francisco", "location"),
            ("My pronouns are they/them", "gender"),
        ]

        for text, expected_keyword in test_cases:
            result = classifier.fast_classify(text)
            assert (
                expected_keyword in result.primary_path.lower()
                or expected_keyword in result.reasoning.lower()
            ), f"Failed for: {text}"

    def test_professional_classification(self, classifier):
        """Test professional-related classifications."""
        test_cases = [
            ("I work at a startup", "professional"),
            ("My salary is 150k", "compensation"),
            ("I manage a team of 5", "team"),
            ("I have a PhD in Computer Science", "education"),
        ]

        for text, expected_keyword in test_cases:
            result = classifier.fast_classify(text)
            path_lower = result.primary_path.lower()
            # More flexible matching for professional content
            assert (
                "professional" in path_lower
                or "work" in path_lower
                or expected_keyword in path_lower
            ), f"Failed for: {text}, got: {result.primary_path}"

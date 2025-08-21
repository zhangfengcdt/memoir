"""Tests for semantic classifier with LLM-based classification."""

import pytest

from memoir.classifier.semantic import (
    ClassificationResult,
    SemanticClassifier,
)


class MockLLMResponse:
    """Mock LLM response for testing."""

    def __init__(self, content: str):
        self.content = content


class MockLLM:
    """Mock LLM for testing purposes."""

    def __init__(self, responses: dict | None = None):
        """Initialize with predefined responses."""
        self.responses = responses or {}
        self.call_count = 0
        self.last_prompt = None

    async def ainvoke(self, prompt: str) -> MockLLMResponse:
        """Mock LLM invocation."""
        self.call_count += 1
        self.last_prompt = prompt

        # Check for predefined responses - prioritize by order (most specific first)
        prompt_lower = prompt.lower()

        # Order matters - check most specific patterns first
        ordered_keys = sorted(self.responses.keys(), key=len, reverse=True)
        for key in ordered_keys:
            if key.lower() in prompt_lower:
                return MockLLMResponse(self.responses[key])

        # Default response for testing
        return MockLLMResponse(
            """{
            "primary_path": "context.current.session.topic.main",
            "confidence": 0.5,
            "alternative_paths": ["context.current.session"],
            "reasoning": "Default test classification"
        }"""
        )


class TestSemanticClassifier:
    """Test LLM-based semantic classifier functionality."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM with test responses."""
        responses = {
            "I work at Google as a software engineer": """{
                "primary_path": "profile.professional.current.role",
                "confidence": 0.85,
                "alternative_paths": ["profile.professional.current"],
                "reasoning": "Professional work information"
            }""",
            "I prefer dark mode in my IDE": """{
                "primary_path": "preferences.personal.lifestyle.daily",
                "confidence": 0.80,
                "alternative_paths": ["preferences.personal"],
                "reasoning": "Personal preferences"
            }""",
            "Python programming experience": """{
                "primary_path": "profile.professional.skills.technical.programming",
                "confidence": 0.85,
                "alternative_paths": ["profile.professional.skills"],
                "reasoning": "Programming skills"
            }""",
            "My goal is to become a senior engineer": """{
                "primary_path": "goals.long_term.career.progression",
                "confidence": 0.85,
                "alternative_paths": ["goals.long_term"],
                "reasoning": "Career goals"
            }""",
            "My name is John Smith": """{
                "primary_path": "profile.personal.identity.name",
                "confidence": 0.90,
                "alternative_paths": ["profile.personal.identity"],
                "reasoning": "Personal name information"
            }""",
        }
        return MockLLM(responses)

    @pytest.fixture
    def classifier(self, mock_llm):
        """Create classifier instance with mock LLM."""
        return SemanticClassifier(llm=mock_llm)

    @pytest.mark.asyncio
    async def test_classifier_requires_llm_for_classification(self):
        """Test that classifier requires LLM for actual classification."""
        classifier = SemanticClassifier(llm=None)

        # Should create classifier but fail when trying to classify
        result = await classifier.classify_async("test content")

        # Should return fallback classification when no LLM
        assert isinstance(result, ClassificationResult)
        # Fallback classification should have default values
        assert result.primary_path == "context.current.session.topic.main"
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_classify_name(self, classifier):
        """Test classification of name-related content."""
        result = await classifier.classify_async("My name is John Smith")

        assert isinstance(result, ClassificationResult)
        assert "profile.personal.identity.name" in result.primary_path
        assert result.confidence > 0.5
        assert result.reasoning is not None

    @pytest.mark.asyncio
    async def test_classify_work(self, classifier):
        """Test classification of work-related content."""
        result = await classifier.classify_async(
            "I work at Google as a software engineer"
        )

        assert "profile.professional" in result.primary_path
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_classify_preferences(self, classifier):
        """Test classification of preferences."""
        result = await classifier.classify_async("I prefer dark mode in my IDE")

        assert "preferences" in result.primary_path
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_classify_programming(self, classifier):
        """Test classification of programming skills."""
        result = await classifier.classify_async(
            "I have 5 years of Python programming experience"
        )

        assert "programming" in result.primary_path or "skills" in result.primary_path
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_classify_goals(self, classifier):
        """Test classification of goals."""
        result = await classifier.classify_async(
            "My goal is to become a senior engineer"
        )

        assert "goal" in result.primary_path
        assert result.confidence > 0.5

    @pytest.mark.asyncio
    async def test_classify_with_context(self, classifier):
        """Test classification with context."""
        context = {"user_id": "test_user", "session_id": "session_123"}
        result = await classifier.classify_async(
            "I'm learning machine learning", context=context
        )

        assert isinstance(result, ClassificationResult)
        assert result.primary_path is not None
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_cache_functionality(self, classifier):
        """Test that caching works."""
        memory = "Test memory content for caching"

        # First call
        result1 = await classifier.classify_async(memory)

        # Second call (should hit cache)
        result2 = await classifier.classify_async(memory)

        assert result1.primary_path == result2.primary_path
        assert result1.confidence == result2.confidence

        # Check that LLM was only called once (cache hit)
        assert classifier.llm.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_disabled(self, classifier):
        """Test classification with cache disabled."""
        memory = "Test memory for cache disabled"

        # First call
        result1 = await classifier.classify_async(memory, use_cache=True)

        # Second call with cache disabled
        result2 = await classifier.classify_async(memory, use_cache=False)

        # Results should be the same but LLM called twice
        assert result1.primary_path == result2.primary_path
        assert classifier.llm.call_count == 2

    def test_cache_key_generation(self, classifier):
        """Test cache key generation."""
        content = "test content"
        context1 = {"user": "alice"}
        context2 = {"user": "bob"}

        key1 = classifier._compute_cache_key(content, context1)
        key2 = classifier._compute_cache_key(content, context1)
        key3 = classifier._compute_cache_key(content, context2)

        # Same content and context should generate same key
        assert key1 == key2

        # Different context should generate different key
        assert key1 != key3

    @pytest.mark.asyncio
    async def test_invalid_llm_response(self, classifier):
        """Test handling of invalid LLM response."""
        # Set up mock to return invalid JSON
        classifier.llm.responses = {"invalid": "invalid json response"}

        # Should not raise exception but return fallback classification
        result = await classifier.classify_async("invalid response test")

        assert isinstance(result, ClassificationResult)
        # Should get fallback classification
        assert result.primary_path == "context.current.session.topic.main"
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_path_validation(self, classifier, mock_llm):
        """Test that invalid paths are corrected."""
        # Mock LLM returns invalid path
        mock_llm.responses = {
            "test": """{
                "primary_path": "invalid.path.that.does.not.exist",
                "confidence": 0.80,
                "alternative_paths": [],
                "reasoning": "Test invalid path"
            }"""
        }

        result = await classifier.classify_async("test invalid path")

        # Should get a valid fallback path
        assert result.primary_path != "invalid.path.that.does.not.exist"
        # Should be corrected to a valid path
        assert classifier.taxonomy.is_valid_path(result.primary_path)

    def test_context_info_generation(self, classifier):
        """Test context info generation."""
        context = {
            "user_id": "user123",
            "session_id": "session456",
            "timestamp": "2023-01-01T00:00:00Z",
        }

        context_info = classifier._get_context_info(context)

        assert "user123" in context_info
        assert "session456" in context_info
        assert "2023-01-01" in context_info

    def test_context_info_none(self, classifier):
        """Test context info with None context."""
        context_info = classifier._get_context_info(None)
        assert context_info == ""

    def test_examples_generation(self, classifier):
        """Test classification examples generation."""
        # Test with examples enabled
        examples = classifier._get_classification_examples()
        assert len(examples) > 0
        assert "John Smith" in examples  # Should contain example names

        # Test with examples disabled
        classifier_no_examples = SemanticClassifier(
            llm=classifier.llm, use_examples=False
        )
        examples_disabled = classifier_no_examples._get_classification_examples()
        assert examples_disabled == ""


class TestClassificationAccuracy:
    """Test classification accuracy for various inputs."""

    @pytest.fixture
    def mock_llm(self):
        """Create mock LLM with realistic responses."""
        return MockLLM(
            {
                "bob": """{
                "primary_path": "profile.personal.identity.name.first",
                "confidence": 0.90,
                "alternative_paths": ["profile.personal.identity.name"],
                "reasoning": "First name identification"
            }""",
                "30 years old": """{
                "primary_path": "profile.personal.demographics.age",
                "confidence": 0.85,
                "alternative_paths": ["profile.personal.demographics"],
                "reasoning": "Age information"
            }""",
                "san francisco": """{
                "primary_path": "profile.personal.location.current.city",
                "confidence": 0.85,
                "alternative_paths": ["profile.personal.location"],
                "reasoning": "Current location"
            }""",
                "startup": """{
                "primary_path": "profile.professional.current.company.type",
                "confidence": 0.80,
                "alternative_paths": ["profile.professional.current"],
                "reasoning": "Company type information"
            }""",
            }
        )

    @pytest.fixture
    def classifier(self, mock_llm):
        return SemanticClassifier(llm=mock_llm)

    @pytest.mark.asyncio
    async def test_identity_classification(self, classifier):
        """Test identity-related classifications."""
        test_cases = [
            ("My name is Bob", "identity"),
            ("I'm 30 years old", "age"),
            ("I'm from San Francisco", "location"),
        ]

        for text, expected_keyword in test_cases:
            result = await classifier.classify_async(text)
            assert (
                expected_keyword in result.primary_path.lower()
                or expected_keyword in result.reasoning.lower()
            ), f"Failed for: {text}, got: {result.primary_path}"

    @pytest.mark.asyncio
    async def test_professional_classification(self, classifier):
        """Test professional-related classifications."""
        test_cases = [
            ("I work at a startup", "professional"),
        ]

        for text, expected_keyword in test_cases:
            result = await classifier.classify_async(text)
            path_lower = result.primary_path.lower()
            # More flexible matching for professional content
            assert (
                "professional" in path_lower
                or "work" in path_lower
                or expected_keyword in path_lower
            ), f"Failed for: {text}, got: {result.primary_path}"

    @pytest.mark.asyncio
    async def test_batch_like_processing(self, classifier):
        """Test processing multiple memories (simulating batch)."""
        memories = [
            "My name is Alice",
            "I work at Microsoft",
            "I prefer Python over Java",
            "My goal is to learn Rust",
        ]

        results = []
        for memory in memories:
            result = await classifier.classify_async(memory)
            results.append(result)

        assert len(results) == 4
        assert all(isinstance(r, ClassificationResult) for r in results)

        # Check that we get reasonable classifications
        assert all(r.confidence > 0 for r in results)
        assert all(r.primary_path for r in results)


class TestErrorHandling:
    """Test error handling in classifier."""

    @pytest.mark.asyncio
    async def test_no_llm_fallback(self):
        """Test fallback when no LLM provided."""
        classifier = SemanticClassifier(llm=None)
        result = await classifier.classify_async("test content")

        # Should get fallback classification, not raise error
        assert isinstance(result, ClassificationResult)
        assert result.primary_path == "context.current.session.topic.main"
        assert result.confidence == 0.5

    @pytest.mark.asyncio
    async def test_llm_exception_handling(self):
        """Test handling of LLM exceptions."""

        class FailingLLM:
            async def ainvoke(self, prompt):
                raise Exception("LLM failed")

        classifier = SemanticClassifier(llm=FailingLLM())

        # Should not raise exception but return fallback
        result = await classifier.classify_async("test content")
        assert isinstance(result, ClassificationResult)
        assert result.primary_path == "context.current.session.topic.main"

    @pytest.mark.asyncio
    async def test_malformed_json_response(self):
        """Test handling of malformed JSON from LLM."""

        class BadJSONLLM:
            async def ainvoke(self, prompt):
                return MockLLMResponse("not valid json")

        classifier = SemanticClassifier(llm=BadJSONLLM())

        # Should not raise exception but return fallback
        result = await classifier.classify_async("test content")
        assert isinstance(result, ClassificationResult)
        assert result.primary_path == "context.current.session.topic.main"


class TestIntegrationWithTaxonomy:
    """Test integration between classifier and taxonomy system."""

    @pytest.fixture
    def classifier(self):
        """Create classifier with simple mock LLM."""
        llm = MockLLM()
        return SemanticClassifier(llm=llm)

    def test_taxonomy_integration(self, classifier):
        """Test that classifier uses taxonomy correctly."""
        # Test that classifier has access to taxonomy
        assert classifier.taxonomy is not None

        # Test that taxonomy has the expected attributes
        assert hasattr(classifier.taxonomy, "_all_paths")
        assert len(classifier.taxonomy._all_paths) > 0

    @pytest.mark.asyncio
    async def test_valid_path_checking(self, classifier):
        """Test that classifier validates paths against taxonomy."""
        # This should use the default fallback path since mock returns generic response
        result = await classifier.classify_async("some random content")

        # Verify the returned path is valid in taxonomy
        assert classifier.taxonomy.is_valid_path(result.primary_path)

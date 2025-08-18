"""
Test the iterative taxonomy with real OpenAI GPT models.
Tests actual LLM integration without mocking responses.

These tests are disabled by default to avoid API costs and dependency on external services.

To run manually:
1. Set environment variable: ENABLE_GPT_TESTS=1 pytest tests/test_gpt_taxonomy.py -v -s
2. Set OPENAI_API_KEY environment variable for real API calls
3. Install langchain-openai: pip install langchain-openai

Example:
    OPENAI_API_KEY=your_key ENABLE_GPT_TESTS=1 pytest tests/test_gpt_taxonomy.py -v -s
"""

import json
import logging
import os
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from langmem_prollytree.taxonomy.iterative_taxonomy import (
    ExpansionContext,
    LLMExpansionStrategy,
    LLMIterativeTaxonomy,
)
from langmem_prollytree.taxonomy.semantic_taxonomy import SemanticTaxonomy

# Skip all tests in this module by default unless explicitly enabled
# To run these tests manually, use: pytest tests/test_gpt_taxonomy.py -m "not skip_gpt" -v -s
# Or set environment variable: ENABLE_GPT_TESTS=1 pytest tests/test_gpt_taxonomy.py -v -s
enable_gpt_tests = os.getenv("ENABLE_GPT_TESTS", "").lower() in ("1", "true", "yes")
pytestmark = pytest.mark.skipif(
    not enable_gpt_tests,
    reason="GPT integration tests disabled by default. Set ENABLE_GPT_TESTS=1 or use -m 'not skip_gpt' to enable.",
)

# Configure logging to show LLM results
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_test_responses():
    """Load test responses from JSON file."""
    data_file = Path(__file__).parent / "data" / "llm_responses.json"
    with open(data_file) as f:
        return json.load(f)


TEST_DATA = load_test_responses()


@pytest.fixture
def real_openai_llm():
    """Create real OpenAI LLM if API key is available."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not found - skipping real LLM tests")

    try:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model="gpt-3.5-turbo", temperature=0, api_key=api_key, max_tokens=500
        )
    except ImportError:
        pytest.skip(
            "langchain_openai not available - install with: pip install langchain-openai"
        )


@pytest.fixture
def base_taxonomy():
    """Create base taxonomy for testing."""
    taxonomy = AsyncMock(spec=SemanticTaxonomy)
    taxonomy.get_all_paths.return_value = [
        # Core categories
        "knowledge",
        "knowledge.technical",
        "knowledge.technical.web",
        "knowledge.technical.other",
        "profile",
        "profile.professional",
        "profile.professional.career",
        "profile.professional.other",
        "preferences",
        "preferences.work",
        "preferences.work.environment",
        "preferences.work.other",
        "experience",
        "experience.projects",
        "experience.projects.types",
        "experience.projects.other",
        "context",
        "context.current",
        "context.current.activities",
        "context.current.other",
        "relationships",
        "relationships.professional",
        "relationships.professional.types",
        "relationships.professional.other",
        "goals",
        "goals.career",
        "goals.career.aspirations",
        "goals.career.other",
        "behavior",
        "behavior.communication",
        "behavior.communication.patterns",
        "behavior.communication.other",
    ]
    return taxonomy


@pytest.fixture
def gpt_taxonomy(base_taxonomy, real_openai_llm):
    """Create GPT-powered iterative taxonomy."""
    return LLMIterativeTaxonomy(
        base_taxonomy=base_taxonomy,
        llm=real_openai_llm,
        expansion_strategy=LLMExpansionStrategy.FOCUSED_SUBTREE,
        min_items_threshold=3,
        max_categories_per_expansion=5,
    )


class TestGPTTaxonomyIntegration:
    """Test iterative taxonomy with real GPT models."""

    @pytest.mark.asyncio
    async def test_gpt_expand_web_development_knowledge(self, gpt_taxonomy):
        """Test GPT expansion for web development knowledge."""
        taxonomy = gpt_taxonomy

        # Add web development memories using example user inputs
        node = taxonomy.path_index["knowledge.technical.other"]
        web_examples = TEST_DATA["knowledge_technical_web"]["example_user_inputs"]
        node.other_items = [
            {"content": example, "context": "web development"}
            for example in web_examples[:4]  # Use first 4 examples
        ]

        # Test LLM expansion with real GPT
        result = await taxonomy.expand_subtree_with_llm("knowledge.technical.other")

        # Print the LLM result for inspection
        print("\n" + "=" * 60)
        print("GPT Web Development Knowledge Expansion Result:")
        print(f"LLM type: {type(taxonomy.llm).__name__}")
        print(f"OpenAI API Key available: {'OPENAI_API_KEY' in os.environ}")
        print(f"Input examples: {web_examples[:4]}")
        print(f"New paths created: {result.new_paths}")
        print(f"Items migrated: {result.migrated_items}")
        print(f"GPT reasoning: {result.reasoning}")
        print("=" * 60)

        # Assert that GPT provided valid responses
        assert result is not None
        assert hasattr(result, "new_paths")
        assert hasattr(result, "migrated_items")
        assert hasattr(result, "reasoning")

        # Should have created some new paths
        assert len(result.new_paths) > 0

        # Paths should be valid (contain the parent path)
        for path in result.new_paths:
            assert "knowledge.technical.other" in path
            assert isinstance(path, str)
            assert len(path.split(".")) > 3  # Should be deeper than parent

        # Should have migrated some items
        assert result.migrated_items >= 0

        # Should have reasoning
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 0

    @pytest.mark.asyncio
    async def test_gpt_expand_professional_career(self, gpt_taxonomy):
        """Test GPT expansion for professional career profiles."""
        taxonomy = gpt_taxonomy

        # Add career memories using example user inputs
        node = taxonomy.path_index["profile.professional.other"]
        career_examples = TEST_DATA["profile_professional_career"][
            "example_user_inputs"
        ]
        node.other_items = [
            {"content": example, "context": "career"} for example in career_examples[:4]
        ]

        result = await taxonomy.expand_subtree_with_llm("profile.professional.other")

        # Print the LLM result for inspection
        print("\n" + "=" * 60)
        print("GPT Professional Career Expansion Result:")
        print(f"Input examples: {career_examples[:4]}")
        print(f"New paths created: {result.new_paths}")
        print(f"Items migrated: {result.migrated_items}")
        print(f"GPT reasoning: {result.reasoning}")
        print("=" * 60)

        # Assert GPT provided valid career-related expansion
        assert result is not None
        assert len(result.new_paths) > 0

        # All new paths should extend the parent
        for path in result.new_paths:
            assert "profile.professional.other" in path

        assert result.migrated_items >= 0
        assert len(result.reasoning) > 0

    @pytest.mark.asyncio
    async def test_gpt_expand_work_preferences(self, gpt_taxonomy):
        """Test GPT expansion for work environment preferences."""
        taxonomy = gpt_taxonomy

        # Add work preference memories
        node = taxonomy.path_index["preferences.work.other"]
        pref_examples = TEST_DATA["preferences_work_environment"]["example_user_inputs"]
        node.other_items = [
            {"content": example, "context": "work preferences"}
            for example in pref_examples[:3]
        ]

        result = await taxonomy.expand_subtree_with_llm("preferences.work.other")

        # Print the LLM result for inspection
        print("\n" + "=" * 60)
        print("GPT Work Preferences Expansion Result:")
        print(f"Input examples: {pref_examples[:3]}")
        print(f"New paths created: {result.new_paths}")
        print(f"Items migrated: {result.migrated_items}")
        print(f"GPT reasoning: {result.reasoning}")
        print("=" * 60)

        # Assert valid preference expansion
        assert result is not None
        assert len(result.new_paths) > 0

        for path in result.new_paths:
            assert "preferences.work.other" in path

        assert isinstance(result.reasoning, str)

    @pytest.mark.asyncio
    async def test_gpt_parallel_expansion(self, gpt_taxonomy):
        """Test parallel expansion across different domains with GPT."""
        taxonomy = gpt_taxonomy

        # Set up multiple different memory types
        expansion_nodes = [
            (
                "knowledge.technical.other",
                TEST_DATA["knowledge_technical_web"]["example_user_inputs"][:3],
            ),
            (
                "profile.professional.other",
                TEST_DATA["profile_professional_career"]["example_user_inputs"][:3],
            ),
            (
                "goals.career.other",
                TEST_DATA["goals_career_aspirations"]["example_user_inputs"][:3],
            ),
        ]

        for path, examples in expansion_nodes:
            if path in taxonomy.path_index:
                node = taxonomy.path_index[path]
                node.other_items = [
                    {"content": example, "context": "test"} for example in examples
                ]

        # Test parallel expansion
        results = await taxonomy.parallel_expand([path for path, _ in expansion_nodes])

        # Print the parallel expansion results
        print("\n" + "=" * 60)
        print("GPT Parallel Expansion Results:")
        for i, (result, (path, examples)) in enumerate(zip(results, expansion_nodes)):
            print(f"\nExpansion {i + 1} - {path}:")
            print(f"  Input examples: {examples}")
            print(f"  New paths: {result.new_paths}")
            print(f"  Items migrated: {result.migrated_items}")
            print(f"  Reasoning: {result.reasoning}")
        print("=" * 60)

        # Assert all expansions succeeded
        assert len(results) == 3

        for result in results:
            assert result is not None
            assert len(result.new_paths) > 0
            assert result.migrated_items >= 0
            assert len(result.reasoning) > 0

    @pytest.mark.asyncio
    async def test_gpt_handles_mixed_content(self, gpt_taxonomy):
        """Test GPT handling of mixed/edge case content."""
        taxonomy = gpt_taxonomy

        node = taxonomy.path_index["context.current.other"]
        mixed_examples = TEST_DATA["edge_case_mixed_items"]["example_user_inputs"]
        node.other_items = [
            {"content": example, "context": "mixed content"}
            for example in mixed_examples[:4]
        ]

        result = await taxonomy.expand_subtree_with_llm("context.current.other")

        # Print the mixed content result
        print("\n" + "=" * 60)
        print("GPT Mixed Content Handling Result:")
        print(f"Input examples: {mixed_examples[:4]}")
        print(f"New paths created: {result.new_paths}")
        print(f"Items migrated: {result.migrated_items}")
        print(f"GPT reasoning: {result.reasoning}")
        print("=" * 60)

        # Should handle mixed content gracefully
        assert result is not None
        # May or may not create paths depending on GPT's interpretation
        assert result.migrated_items >= 0
        assert isinstance(result.reasoning, str)

    @pytest.mark.asyncio
    async def test_gpt_expansion_context_building(self, gpt_taxonomy):
        """Test that GPT receives proper context for expansion."""
        taxonomy = gpt_taxonomy

        # Add items to test context building
        node = taxonomy.path_index["relationships.professional.other"]
        relationship_examples = TEST_DATA["relationships_professional_types"][
            "example_user_inputs"
        ]
        node.other_items = [
            {"content": example, "context": "professional relationships"}
            for example in relationship_examples[:3]
        ]

        # Build context manually to verify structure
        context = taxonomy._build_expansion_context(node)

        # Verify context structure
        assert context.node_path == "relationships.professional.other"
        assert "relationships" in context.parent_hierarchy
        assert "professional" in context.parent_hierarchy
        assert len(context.unclassified_items) == 3
        assert context.current_depth == 3

        # Test actual expansion
        result = await taxonomy.expand_subtree_with_llm(
            "relationships.professional.other"
        )

        # Print the context building result
        print("\n" + "=" * 60)
        print("GPT Context Building Result:")
        print(f"Node path: {context.node_path}")
        print(f"Parent hierarchy: {context.parent_hierarchy}")
        print(f"Sibling categories: {context.sibling_categories}")
        print(f"Unclassified items count: {len(context.unclassified_items)}")
        print(f"Current depth: {context.current_depth}")
        print(f"Result new paths: {result.new_paths}")
        print(f"Result reasoning: {result.reasoning}")
        print("=" * 60)

        assert result is not None
        assert len(result.reasoning) > 0

    @pytest.mark.asyncio
    async def test_gpt_prompt_generation(self, gpt_taxonomy):
        """Test that GPT prompts are properly formatted."""
        taxonomy = gpt_taxonomy

        # Create test context
        context = ExpansionContext(
            node_path="experience.projects.other",
            parent_hierarchy=["experience", "projects", "other"],
            sibling_categories=["types", "other"],
            unclassified_items=[
                {"content": content, "context": "test"}
                for content in TEST_DATA["experience_projects_types"][
                    "example_user_inputs"
                ][:2]
            ],
            current_depth=3,
            taxonomy_snapshot={},
        )

        # Generate prompt
        prompt = taxonomy._build_expansion_prompt(context)

        # Print the generated prompt
        print("\n" + "=" * 60)
        print("Generated GPT Prompt:")
        print(prompt)
        print("=" * 60)

        # Verify prompt structure
        assert "experience.projects.other" in prompt
        assert (
            "machine learning" in prompt or "mobile app" in prompt
        )  # From example inputs
        assert "expanding" in prompt.lower() or "taxonomy" in prompt.lower()
        assert len(prompt) > 100  # Should be substantial

    def test_gpt_statistics_tracking(self, gpt_taxonomy):
        """Test that statistics are properly tracked with GPT."""
        taxonomy = gpt_taxonomy

        # Get initial statistics
        stats = taxonomy.get_expansion_statistics()

        # Verify basic statistics structure
        assert "expansion_history" in stats
        assert "total_migrated" in stats
        assert "total_paths" in stats
        assert isinstance(stats["expansion_history"], int)
        assert isinstance(stats["total_migrated"], int)
        assert isinstance(stats["total_paths"], int)

    @pytest.mark.asyncio
    async def test_gpt_configurable_max_categories(
        self, base_taxonomy, real_openai_llm
    ):
        """Test that max_categories_per_expansion parameter works correctly."""
        # Test with smaller limit
        taxonomy_small = LLMIterativeTaxonomy(
            base_taxonomy=base_taxonomy,
            llm=real_openai_llm,
            expansion_strategy=LLMExpansionStrategy.FOCUSED_SUBTREE,
            min_items_threshold=3,
            max_categories_per_expansion=5,  # Limit to 5 categories
        )

        # Add test items
        node = taxonomy_small.path_index["knowledge.technical.other"]
        web_examples = TEST_DATA["knowledge_technical_web"]["example_user_inputs"]
        node.other_items = [
            {"content": example, "context": "web development"}
            for example in web_examples[:4]
        ]

        # Test expansion with limited categories
        result = await taxonomy_small.expand_subtree_with_llm(
            "knowledge.technical.other"
        )

        # Print results for inspection
        print("\n🔢 Max Categories Limit Test (limit=5):")
        print(f"Categories created: {len(result.new_paths)}")
        print(f"New paths: {result.new_paths}")

        # Should respect the limit (though LLM might return fewer)
        assert result is not None
        assert len(result.new_paths) <= 5  # Should not exceed our limit
        assert len(result.new_paths) > 0  # Should create some categories

        # Verify the parameter is stored correctly
        assert taxonomy_small.max_categories_per_expansion == 5

    def test_llm_classification_prompt_generation(self, gpt_taxonomy):
        """Test that LLM classification prompts are properly generated."""
        taxonomy = gpt_taxonomy

        content = "I'm learning React for frontend development"
        candidate_paths = [
            "knowledge.technical.other.frontend",
            "knowledge.technical.other.backend",
            "knowledge.technical.other.databases",
        ]

        # Test classification prompt generation
        prompt = taxonomy._build_classification_prompt(content, candidate_paths)

        print("\n📝 Classification Prompt Generated:")
        print(prompt)

        # Verify prompt structure
        assert (
            "Content to classify: I'm learning React for frontend development" in prompt
        )
        assert "1. frontend" in prompt
        assert "2. backend" in prompt
        assert "3. databases" in prompt
        assert "Return ONLY the number" in prompt
        assert "semantic meaning" in prompt

        # Test response parsing
        correct_response = taxonomy._parse_best_category_response("1", candidate_paths)
        assert correct_response == "knowledge.technical.other.frontend"

        no_match_response = taxonomy._parse_best_category_response("0", candidate_paths)
        assert no_match_response is None

        invalid_response = taxonomy._parse_best_category_response(
            "invalid", candidate_paths
        )
        assert invalid_response is None


class TestGPTErrorHandling:
    """Test error handling with real GPT integration."""

    @pytest.mark.asyncio
    async def test_gpt_api_error_handling(self, base_taxonomy):
        """Test handling of GPT API errors."""
        # Create taxonomy with invalid API key to test error handling
        try:
            from langchain_openai import ChatOpenAI

            invalid_llm = ChatOpenAI(
                model="gpt-3.5-turbo",
                temperature=0,
                api_key="invalid-key",
                max_tokens=500,
            )

            taxonomy = LLMIterativeTaxonomy(
                base_taxonomy=base_taxonomy,
                llm=invalid_llm,
                expansion_strategy=LLMExpansionStrategy.FOCUSED_SUBTREE,
                min_items_threshold=3,
                max_categories_per_expansion=10,  # Use default value explicitly
            )

            node = taxonomy.path_index["knowledge.technical.other"]
            node.other_items = [{"content": "test content", "context": "test"}]

            # Should handle API errors gracefully
            result = await taxonomy.expand_subtree_with_llm("knowledge.technical.other")

            # Should return some result even on error (fallback behavior)
            assert result is not None

        except ImportError:
            pytest.skip("langchain_openai not available")

    @pytest.mark.asyncio
    async def test_gpt_empty_content_handling(self, gpt_taxonomy):
        """Test GPT handling of empty or minimal content."""
        taxonomy = gpt_taxonomy

        # Test with empty items
        node = taxonomy.path_index["behavior.communication.other"]
        node.other_items = []

        result = await taxonomy.expand_subtree_with_llm("behavior.communication.other")

        # Should handle empty content gracefully
        assert result is not None
        assert result.migrated_items == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

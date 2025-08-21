"""
Enhanced tests for LLM-driven iterative taxonomy with realistic mock data.
Tests follow the paper's methodology with actual GPT-4-style responses.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from memoir.taxonomy.iterative import (
    ExpansionContext,
    LLMExpansionStrategy,
    LLMIterativeTaxonomy,
    TaxonomyCombination,
)
from memoir.taxonomy.semantic import SemanticTaxonomy


# Load test data from JSON file
def load_llm_test_data():
    """Load LLM test responses from JSON file."""
    data_file = Path(__file__).parent / "data" / "llm_responses.json"
    with open(data_file) as f:
        return json.load(f)


LLM_TEST_DATA = load_llm_test_data()


class RealisticMockLLM:
    """
    Mock LLM that returns realistic responses based on recorded GPT-4-style outputs.
    Uses JSON test data to simulate actual LLM behavior for different contexts.
    """

    def __init__(self, use_random_subset=False):
        """
        Initialize the mock LLM.

        Args:
            use_random_subset: If True, returns a random subset of categories to simulate variation
        """
        self.test_data = LLM_TEST_DATA
        self.use_random_subset = use_random_subset
        self.call_history = []  # Track calls for testing

    async def generate(self, prompt: str) -> str:
        """Generate a response based on the prompt content."""
        self.call_history.append(prompt)

        # Match prompt to test data based on content and context keywords
        for data_key, data_value in self.test_data.items():
            if data_key == "defaults":
                continue

            # Check if any context keywords match the prompt
            if "context_keywords" in data_value:
                keywords = data_value["context_keywords"]
                if any(keyword in prompt for keyword in keywords):
                    response = data_value["response"]
                    break
        else:
            # No specific match found, use contextual defaults
            if "knowledge.technical.other" in prompt:
                response = self.test_data["defaults"]["knowledge_technical_general"]
            elif "profile.professional.other" in prompt:
                response = self.test_data["defaults"]["profile_professional_general"]
            elif "goals" in prompt and "career" in prompt:
                response = self.test_data["defaults"]["goals_career_general"]
            elif "preferences.work.other" in prompt:
                response = self.test_data["defaults"]["preferences_work_general"]
            else:
                response = self.test_data["defaults"]["fallback"]

        # Optionally return a subset to simulate variation
        if self.use_random_subset:
            import random

            lines = response.strip().split("\n")
            num_to_return = random.randint(3, min(8, len(lines)))
            selected = random.sample(lines, num_to_return)
            response = "\n".join(selected)

        return response

    async def __call__(self, prompt: str) -> str:
        """Make the class callable like a function."""
        return await self.generate(prompt)

    def get_call_history(self) -> list[str]:
        """Get the history of prompts sent to this mock LLM."""
        return self.call_history

    def clear_history(self):
        """Clear the call history."""
        self.call_history = []


def generate_expansion_prompt(
    node_path: str,
    depth: int,
    siblings: list[str],
    unclassified_items: list[str],
    max_items: int = 10,
) -> str:
    """
    Generate a prompt for taxonomy expansion following the paper's approach.

    Args:
        node_path: Current path in taxonomy
        depth: Current depth level
        siblings: Existing sibling categories
        unclassified_items: Sample items to classify
        max_items: Maximum items to include in prompt

    Returns:
        Formatted prompt string
    """
    prompt_parts = [
        "You are expanding a hierarchical taxonomy. Based on the unclassified items below, ",
        "suggest new categories that would logically fit into the existing structure.",
        "",
        f"Current path: {node_path}",
        f"Depth level: {depth}",
        "",
        "Existing sibling categories:",
    ]

    for sibling in siblings:
        prompt_parts.append(f"  - {sibling}")

    prompt_parts.extend(["", "Sample unclassified items:"])

    for item in unclassified_items[:max_items]:
        prompt_parts.append(f"  - {item}")

    prompt_parts.extend(
        [
            "",
            "Suggest up to 10 new category names that would logically group these items.",
            "Categories should:",
            "1. Be semantically coherent with existing siblings",
            "2. Be at the appropriate level of specificity for this depth",
            "3. Not duplicate existing categories",
            "4. Follow the naming convention of siblings",
            "",
            "Return only the category names, one per line.",
        ]
    )

    return "\n".join(prompt_parts)


@pytest.fixture
def realistic_llm():
    """Create a realistic mock LLM with recorded responses."""
    return RealisticMockLLM(use_random_subset=False)


@pytest.fixture
def mock_base_taxonomy():
    """Create a mock base taxonomy with realistic structure."""
    taxonomy = AsyncMock(spec=SemanticTaxonomy)
    # More comprehensive base paths based on the paper
    taxonomy.get_all_paths.return_value = [
        # Profile category
        "profile",
        "profile.personal",
        "profile.personal.name",
        "profile.personal.age",
        "profile.personal.location",
        "profile.professional",
        "profile.professional.occupation",
        "profile.professional.experience",
        "profile.professional.skills",
        "profile.professional.education",
        "profile.professional.certifications",
        # Knowledge category
        "knowledge",
        "knowledge.technical",
        "knowledge.technical.programming",
        "knowledge.technical.databases",
        "knowledge.technical.networking",
        "knowledge.technical.systems",
        "knowledge.technical.algorithms",
        "knowledge.technical.other",
        "knowledge.domain",
        "knowledge.domain.business",
        "knowledge.domain.science",
        "knowledge.domain.arts",
        "knowledge.domain.technology",
        "knowledge.domain.humanities",
        "knowledge.domain.other",
        # Preferences category
        "preferences",
        "preferences.work",
        "preferences.work.schedule",
        "preferences.work.location",
        "preferences.work.culture",
        "preferences.work.benefits",
        "preferences.work.tools",
        "preferences.work.other",
        "preferences.personal",
        # Experience category
        "experience",
        "experience.projects",
        "experience.projects.personal",
        "experience.projects.professional",
        "experience.projects.academic",
        "experience.projects.volunteer",
        "experience.projects.hackathon",
        "experience.companies",
        # Context category
        "context",
        "context.current",
        "context.current.session",
        "context.current.task",
        "context.current.environment",
        "context.current.time",
        "context.current.mood",
        # Relationships category
        "relationships",
        "relationships.professional",
        "relationships.professional.colleagues",
        "relationships.professional.managers",
        "relationships.professional.reports",
        "relationships.professional.clients",
        "relationships.professional.partners",
        "relationships.professional.other",
        "relationships.personal",
        # Goals category
        "goals",
        "goals.career",
        "goals.career.short_term",
        "goals.career.long_term",
        "goals.career.skills_development",
        "goals.career.role_advancement",
        "goals.career.compensation",
        "goals.career.other",
        "goals.personal",
        # Behavior category
        "behavior",
        "behavior.communication",
        "behavior.communication.style",
        "behavior.communication.frequency",
        "behavior.communication.channels",
        "behavior.communication.preferences",
        "behavior.communication.languages",
        "behavior.work_patterns",
    ]
    return taxonomy


@pytest.fixture
def taxonomy_with_realistic_llm(mock_base_taxonomy, realistic_llm):
    """Create taxonomy with realistic mock LLM."""
    return LLMIterativeTaxonomy(
        base_taxonomy=mock_base_taxonomy,
        llm=realistic_llm,
        expansion_strategy=LLMExpansionStrategy.FOCUSED_SUBTREE,
        min_items_threshold=3,
        max_categories_per_expansion=10,  # Use default value explicitly
        use_full_base_taxonomy=True,  # Use the full mock taxonomy structure
    )


class TestRealisticLLMExpansion:
    """Test suite with realistic LLM responses based on the paper."""

    @pytest.mark.asyncio
    async def test_expand_web_development_taxonomy(self, taxonomy_with_realistic_llm):
        """Test expansion of web development categories with realistic data."""
        taxonomy = taxonomy_with_realistic_llm

        # Add realistic web development items
        node = taxonomy.path_index["knowledge.technical.other"]
        node.other_items = [
            {
                "content": "React hooks and component lifecycle management",
                "original_classification": "knowledge.technical.frontend.react",
                "confidence": 0.6,
                "metadata": {"source": "user_input", "timestamp": "2024-01-15"},
            },
            {
                "content": "Vue.js reactive data binding and composition API",
                "original_classification": "knowledge.technical.frontend.vue",
                "confidence": 0.5,
            },
            {
                "content": "Node.js Express middleware and routing",
                "original_classification": "knowledge.technical.backend.nodejs",
                "confidence": 0.7,
            },
            {
                "content": "GraphQL schema design and resolvers",
                "original_classification": "knowledge.technical.api.graphql",
                "confidence": 0.6,
            },
            {
                "content": "WebSocket real-time communication",
                "original_classification": "knowledge.technical.realtime.websocket",
                "confidence": 0.5,
            },
        ]

        # Mock the LLM call to return realistic categories
        with patch.object(taxonomy, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = LLM_TEST_DATA["knowledge_technical_web"]["response"]

            result = await taxonomy.expand_subtree_with_llm("knowledge.technical.other")

        # Verify realistic categories were created
        assert "knowledge.technical.other.frontend" in result.new_paths
        assert "knowledge.technical.other.backend" in result.new_paths
        assert "knowledge.technical.other.api_design" in result.new_paths
        assert "knowledge.technical.other.real_time" in result.new_paths
        assert len(result.new_paths) == 10  # All categories from response

        # Check that nodes were properly created
        assert "knowledge.technical.other.frontend" in taxonomy.path_index
        assert "knowledge.technical.other.web_frameworks" in taxonomy.path_index

        # Verify the expansion follows the paper's depth constraints
        frontend_node = taxonomy.path_index["knowledge.technical.other.frontend"]
        assert frontend_node.depth == 4
        assert frontend_node.is_dynamic

    @pytest.mark.asyncio
    async def test_expand_professional_relationships(self, taxonomy_with_realistic_llm):
        """Test expansion of professional relationship categories."""
        taxonomy = taxonomy_with_realistic_llm

        # Add realistic professional relationship items
        node = taxonomy.path_index["relationships.professional.other"]
        node.other_items = [
            {
                "content": "Technical mentor who guides career development",
                "metadata": {"importance": "high", "frequency": "weekly"},
            },
            {
                "content": "Industry expert providing domain knowledge",
                "metadata": {"field": "machine_learning"},
            },
            {
                "content": "Recruiter from tech companies",
                "metadata": {"companies": ["Google", "Meta", "Amazon"]},
            },
            {
                "content": "Open source collaborator on GitHub",
                "metadata": {"projects": ["tensorflow", "pytorch"]},
            },
        ]

        with patch.object(taxonomy, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = LLM_TEST_DATA["relationships_professional_types"][
                "response"
            ]

            result = await taxonomy.expand_subtree_with_llm(
                "relationships.professional.other"
            )

        # Verify professional relationship categories
        assert "relationships.professional.other.mentors" in result.new_paths
        assert "relationships.professional.other.industry_experts" in result.new_paths
        assert "relationships.professional.other.recruiters" in result.new_paths
        assert (
            "relationships.professional.other.open_source_collaborators"
            in result.new_paths
        )

    @pytest.mark.asyncio
    async def test_parallel_expansion_multiple_domains(
        self, taxonomy_with_realistic_llm
    ):
        """Test parallel expansion across different domains as per the paper."""
        taxonomy = taxonomy_with_realistic_llm

        # Set up multiple nodes with realistic data
        test_nodes = [
            (
                "knowledge.technical.other",
                [
                    {"content": "React hooks and state management"},
                    {"content": "GraphQL API design"},
                    {"content": "Docker containerization"},
                ],
            ),
            (
                "goals.career.other",
                [
                    {"content": "Become technical lead within 2 years"},
                    {"content": "Publish research paper in top conference"},
                    {"content": "Build successful SaaS product"},
                ],
            ),
            (
                "preferences.work.other",
                [
                    {"content": "Prefers standing desk and ergonomic setup"},
                    {"content": "Likes open office with collaboration spaces"},
                    {"content": "Values quiet environment for deep work"},
                ],
            ),
        ]

        for path, items in test_nodes:
            if path in taxonomy.path_index:
                node = taxonomy.path_index[path]
                node.other_items = items

        # Mock different responses for different paths
        async def mock_llm_response(prompt):
            if "knowledge.technical" in prompt:
                return LLM_TEST_DATA["knowledge_technical_web"]["response"]
            elif "goals.career" in prompt:
                return LLM_TEST_DATA["goals_career_aspirations"]["response"]
            elif "preferences.work" in prompt:
                return LLM_TEST_DATA["preferences_work_environment"]["response"]
            return "category1\ncategory2\ncategory3"

        with patch.object(taxonomy, "_call_llm", side_effect=mock_llm_response):
            results = await taxonomy.parallel_expand([path for path, _ in test_nodes])

        # Verify all three expansions succeeded
        assert len(results) == 3

        # Check that appropriate categories were created for each domain
        assert "knowledge.technical.other.frontend" in taxonomy.path_index
        assert "goals.career.other.leadership_goals" in taxonomy.path_index
        assert "preferences.work.other.workspace_design" in taxonomy.path_index

    @pytest.mark.asyncio
    async def test_interdisciplinary_expansion(self, taxonomy_with_realistic_llm):
        """Test expansion with interdisciplinary items that span multiple domains."""
        taxonomy = taxonomy_with_realistic_llm

        # Add items that don't fit neatly into existing categories
        node = taxonomy.path_index["knowledge.domain.other"]
        node.other_items = [
            {"content": "Cryptocurrency trading strategies"},
            {"content": "Sustainable agriculture practices"},
            {"content": "Digital art NFT creation"},
            {"content": "Bioinformatics algorithms"},
            {"content": "Social media marketing analytics"},
            {"content": "Renewable energy systems"},
            {"content": "Game theory applications"},
            {"content": "Behavioral economics principles"},
        ]

        with patch.object(taxonomy, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = LLM_TEST_DATA["edge_case_mixed_items"]["response"]

            result = await taxonomy.expand_subtree_with_llm("knowledge.domain.other")

        # Verify interdisciplinary categories were created
        assert "knowledge.domain.other.interdisciplinary" in result.new_paths
        assert "knowledge.domain.other.emerging_fields" in result.new_paths
        assert "knowledge.domain.other.digital_economy" in result.new_paths
        assert "knowledge.domain.other.sustainability" in result.new_paths

    def test_prompt_generation_follows_paper_format(self, taxonomy_with_realistic_llm):
        """Test that generated prompts follow the paper's format."""
        taxonomy = taxonomy_with_realistic_llm

        # Create a realistic context
        context = ExpansionContext(
            node_path="knowledge.technical.other",
            parent_hierarchy=["knowledge", "technical", "other"],
            sibling_categories=[
                "programming",
                "databases",
                "networking",
                "systems",
                "algorithms",
            ],
            unclassified_items=[
                {"content": "React hooks and component lifecycle"},
                {"content": "Vue.js reactive data binding"},
                {"content": "GraphQL schema design"},
            ],
            current_depth=3,
            taxonomy_snapshot={
                "path": "knowledge.technical",
                "children": {
                    "programming": {"path": "knowledge.technical.programming"},
                    "databases": {"path": "knowledge.technical.databases"},
                },
            },
        )

        prompt = taxonomy._build_expansion_prompt(context)

        # Verify prompt structure matches paper's methodology
        assert "You are expanding a hierarchical taxonomy" in prompt
        assert "Current path: knowledge.technical.other" in prompt
        assert "Depth level: 3" in prompt
        assert "Existing sibling categories:" in prompt
        assert "- programming" in prompt
        assert "- databases" in prompt
        assert "Sample unclassified items:" in prompt
        assert "React hooks" in prompt
        assert "Suggest up to 10 new category names" in prompt
        assert "Be semantically coherent with existing siblings" in prompt
        assert "Return only the category names, one per line" in prompt

    @pytest.mark.asyncio
    async def test_reclassification_with_realistic_categories(
        self, taxonomy_with_realistic_llm
    ):
        """Test item reclassification with realistic category matching."""
        taxonomy = taxonomy_with_realistic_llm

        # Create node with mixed items
        node = taxonomy.path_index["knowledge.technical.other"]
        node.other_items = [
            {
                "content": "React component lifecycle tutorial",
                "metadata": {"type": "frontend"},
            },
            {
                "content": "Express.js middleware for authentication",
                "metadata": {"type": "backend"},
            },
            {
                "content": "Machine learning model deployment",
                "metadata": {"type": "ml"},
            },
            {"content": "GraphQL resolver optimization", "metadata": {"type": "api"}},
            {
                "content": "WebSocket connection handling",
                "metadata": {"type": "realtime"},
            },
        ]

        # Create realistic new categories
        new_paths = [
            "knowledge.technical.other.frontend",
            "knowledge.technical.other.backend",
            "knowledge.technical.other.machine_learning",
            "knowledge.technical.other.api_design",
            "knowledge.technical.other.real_time",
        ]

        for path in new_paths:
            taxonomy._add_path_to_tree(taxonomy.root, path, is_dynamic=True)
        taxonomy._rebuild_index()

        # Test reclassification
        migrated = await taxonomy._reclassify_items(node, new_paths)

        # Should migrate items that match categories
        assert migrated >= 2  # At least React and Express items
        assert len(node.other_items) < 5  # Some items migrated

        # Check specific migrations
        frontend_node = taxonomy.path_index["knowledge.technical.other.frontend"]
        backend_node = taxonomy.path_index["knowledge.technical.other.backend"]
        assert frontend_node.item_count > 0 or backend_node.item_count > 0

    def test_apply_location_technology_combinations(self, taxonomy_with_realistic_llm):
        """Test pattern-based combinations as described in the paper."""
        taxonomy = taxonomy_with_realistic_llm

        # Add location and technology paths
        locations = ["silicon_valley", "seattle", "austin", "new_york", "london"]
        technologies = [
            "artificial_intelligence",
            "blockchain",
            "cloud_computing",
            "cybersecurity",
        ]

        for loc in locations:
            taxonomy._add_path_to_tree(
                taxonomy.root, f"location.{loc}", is_dynamic=False
            )

        for tech in technologies:
            taxonomy._add_path_to_tree(
                taxonomy.root, f"technology.{tech}", is_dynamic=False
            )

        taxonomy._rebuild_index()

        # Apply combination pattern from the paper
        combination = TaxonomyCombination(
            pattern="Location + Technology",
            template="{domain}_in_{location}",
            examples=[
                "ai_in_silicon_valley",
                "blockchain_in_london",
                "cloud_in_seattle",
            ],
        )

        new_paths = taxonomy.apply_combinations(combination)

        # Should create multiple combinations
        assert len(new_paths) > 0

        # Check for specific expected combinations
        possible_combinations = [
            "combined.artificial_intelligence_in_silicon_valley",
            "combined.blockchain_in_london",
            "combined.cloud_computing_in_seattle",
        ]

        # At least some combinations should be created
        created_combinations = [
            p for p in possible_combinations if p in taxonomy.path_index
        ]
        assert len(created_combinations) > 0

    def test_expansion_statistics_with_realistic_data(
        self, taxonomy_with_realistic_llm
    ):
        """Test that expansion statistics accurately reflect realistic expansions."""
        taxonomy = taxonomy_with_realistic_llm

        # Simulate multiple expansions by adding to history
        from memoir.taxonomy.iterative import (
            TaxonomyExpansionResult,
        )

        # Add realistic expansion results
        expansions = [
            TaxonomyExpansionResult(
                parent_path="knowledge.technical.other",
                new_paths=[
                    "knowledge.technical.other.frontend",
                    "knowledge.technical.other.backend",
                ],
                migrated_items=15,
                confidence=0.8,
                strategy="focused_subtree",
                reasoning="Expanded web development categories based on 20 items",
                timestamp=1640995200.0,
            ),
            TaxonomyExpansionResult(
                parent_path="goals.career.other",
                new_paths=[
                    "goals.career.other.leadership",
                    "goals.career.other.entrepreneurship",
                ],
                migrated_items=8,
                confidence=0.9,
                strategy="focused_subtree",
                reasoning="Created career goal categories from 10 items",
                timestamp=1640995300.0,
            ),
        ]

        taxonomy.expansion_history.extend(expansions)

        # Get statistics
        stats = taxonomy.get_expansion_statistics()

        # Verify statistics reflect realistic data
        assert stats["expansion_history"] == 2
        assert stats["total_migrated"] == 23  # 15 + 8
        assert stats["total_paths"] > 50  # Base paths plus 'other' categories

    def test_depth_aware_expansion(self, taxonomy_with_realistic_llm):
        """Test that expansion respects depth constraints from the paper."""
        taxonomy = taxonomy_with_realistic_llm

        # Test expansion at different depths
        shallow_node = taxonomy.path_index.get("profile.other")
        deep_node = taxonomy.path_index.get("knowledge.technical.other")

        assert shallow_node.depth == 2
        assert deep_node.depth == 3

        # Build contexts for different depths
        shallow_context = taxonomy._build_expansion_context(shallow_node)
        deep_context = taxonomy._build_expansion_context(deep_node)

        # Verify depth is correctly tracked
        assert shallow_context.current_depth == 2
        assert deep_context.current_depth == 3

        # Generate prompts should reflect depth
        shallow_prompt = taxonomy._build_expansion_prompt(shallow_context)
        deep_prompt = taxonomy._build_expansion_prompt(deep_context)

        assert "Depth level: 2" in shallow_prompt
        assert "Depth level: 3" in deep_prompt


class TestRealisticMockLLM:
    """Test the realistic mock LLM itself."""

    @pytest.mark.asyncio
    async def test_mock_llm_returns_appropriate_responses(self):
        """Test that mock LLM returns context-appropriate responses."""
        llm = RealisticMockLLM()

        # Test web development context
        web_prompt = generate_expansion_prompt(
            "knowledge.technical.other",
            3,
            ["programming", "databases"],
            ["React hooks tutorial", "Vue.js components", "GraphQL API"],
        )

        response = await llm.generate(web_prompt)
        assert "frontend" in response or "backend" in response

        # Test career goals context
        career_prompt = generate_expansion_prompt(
            "goals.career.other",
            3,
            ["short_term", "long_term"],
            ["Become technical lead", "Start SaaS business", "Speak at conference"],
        )

        response = await llm.generate(career_prompt)
        # Should return relevant career categories
        lines = response.strip().split("\n")
        assert len(lines) > 3

    def test_mock_llm_tracks_history(self):
        """Test that mock LLM tracks call history."""
        llm = RealisticMockLLM()

        async def make_calls():
            await llm.generate("prompt1")
            await llm.generate("prompt2")
            await llm.generate("prompt3")

        asyncio.run(make_calls())

        history = llm.get_call_history()
        assert len(history) == 3
        assert history[0] == "prompt1"
        assert history[2] == "prompt3"

        llm.clear_history()
        assert len(llm.get_call_history()) == 0

    @pytest.mark.asyncio
    async def test_mock_llm_with_random_subset(self):
        """Test mock LLM with random subset feature."""
        llm = RealisticMockLLM(use_random_subset=True)

        # Make multiple calls to see variation
        responses = []
        for _ in range(5):
            response = await llm.generate(
                "knowledge.technical.other with React and Vue items"
            )
            responses.append(len(response.strip().split("\n")))

        # Should have some variation in response lengths
        assert min(responses) >= 3  # At least 3 categories
        assert max(responses) <= 8  # At most 8 categories


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

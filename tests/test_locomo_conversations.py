"""
Test the iterative taxonomy with LOCOMO conversation dataset.
Demonstrates classification of conversation memories for long-term memory systems.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from memoir.taxonomy.iterative import (
    ExpansionContext,
    LLMExpansionStrategy,
    LLMIterativeTaxonomy,
)
from memoir.taxonomy.semantic import SemanticTaxonomy


def load_locomo_responses():
    """Load LOCOMO conversation test responses from JSON file."""
    data_file = Path(__file__).parent / "data" / "llm_locomo10_responses.json"
    with open(data_file) as f:
        return json.load(f)


LOCOMO_TEST_DATA = load_locomo_responses()


class LocomoMockLLM:
    """
    Mock LLM specialized for conversation-based memory classification.
    Uses LOCOMO-style responses for realistic conversation taxonomy expansion.
    """

    def __init__(self):
        self.test_data = LOCOMO_TEST_DATA
        self.call_history = []

    async def generate(self, prompt: str) -> str:
        """Generate conversation-focused taxonomy responses."""
        self.call_history.append(prompt)

        # Match based on conversation context keywords
        for data_key, data_value in self.test_data.items():
            if data_key == "defaults":
                continue

            if "context_keywords" in data_value:
                keywords = data_value["context_keywords"]
                if any(keyword in prompt.lower() for keyword in keywords):
                    return data_value["response"]

        # Contextual defaults for conversation memories
        if "conversation" in prompt.lower():
            if "relationship" in prompt.lower() or "family" in prompt.lower():
                return self.test_data["defaults"]["conversation_general"]
            elif "activity" in prompt.lower() or "event" in prompt.lower():
                return self.test_data["defaults"]["conversation_context"]
            else:
                return self.test_data["defaults"]["conversation_general"]

        return self.test_data["defaults"]["fallback"]

    def get_call_history(self):
        return self.call_history


@pytest.fixture
def conversation_base_taxonomy():
    """Create taxonomy focused on conversation memories."""
    taxonomy = AsyncMock(spec=SemanticTaxonomy)
    taxonomy.get_all_paths.return_value = [
        # Core conversation categories
        "conversation",
        "conversation.personal",
        "conversation.personal.identity",
        "conversation.personal.relationships",
        "conversation.personal.activities",
        "conversation.personal.emotions",
        "conversation.personal.other",
        # Social conversation aspects
        "conversation.social",
        "conversation.social.friends",
        "conversation.social.family",
        "conversation.social.community",
        "conversation.social.events",
        "conversation.social.other",
        # Topical conversation areas
        "conversation.topics",
        "conversation.topics.work",
        "conversation.topics.hobbies",
        "conversation.topics.health",
        "conversation.topics.education",
        "conversation.topics.other",
        # Temporal aspects
        "conversation.temporal",
        "conversation.temporal.recent",
        "conversation.temporal.planning",
        "conversation.temporal.memories",
        # Context of conversation
        "conversation.context",
        "conversation.context.location",
        "conversation.context.purpose",
        "conversation.context.participants",
    ]
    return taxonomy


@pytest.fixture
def locomo_taxonomy(conversation_base_taxonomy):
    """Create LOCOMO-focused iterative taxonomy."""
    return LLMIterativeTaxonomy(
        base_taxonomy=conversation_base_taxonomy,
        llm=LocomoMockLLM(),
        expansion_strategy=LLMExpansionStrategy.FOCUSED_SUBTREE,
        min_items_threshold=3,
        max_categories_per_expansion=5,  # Use default value explicitly
        use_full_base_taxonomy=True,  # Use the full mock taxonomy structure
    )


class TestLocomoConversationTaxonomy:
    """Test conversation memory classification with LOCOMO-style data."""

    @pytest.mark.asyncio
    async def test_expand_identity_conversations(self, locomo_taxonomy):
        """Test expansion for identity-related conversations."""
        taxonomy = locomo_taxonomy

        # Add LGBTQ identity conversation memories
        node = taxonomy.path_index["conversation.personal.other"]
        node.other_items = [
            {
                "content": "I went to a LGBTQ support group yesterday and it was so powerful",
                "speaker": "Caroline",
                "context": "personal identity",
                "timestamp": "2023-05-08",
            },
            {
                "content": "The transgender stories were so inspiring! I was so happy and thankful for all the support",
                "speaker": "Caroline",
                "context": "identity exploration",
                "timestamp": "2023-05-08",
            },
            {
                "content": "I joined a new activist group focused on LGBTQ rights",
                "speaker": "Caroline",
                "context": "community involvement",
                "timestamp": "2023-07-20",
            },
            {
                "content": "Going to pride parades has been amazing for my sense of community",
                "speaker": "Caroline",
                "context": "LGBTQ community",
                "timestamp": "2023-08-14",
            },
        ]

        # Mock LLM expansion
        with patch.object(taxonomy, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = LOCOMO_TEST_DATA["conversation_personal_identity"][
                "response"
            ]

            result = await taxonomy.expand_subtree_with_llm(
                "conversation.personal.other"
            )

        # Verify identity-focused categories were created
        assert "conversation.personal.other.identity_exploration" in result.new_paths
        assert "conversation.personal.other.LGBTQ_community" in result.new_paths
        assert "conversation.personal.other.support_groups" in result.new_paths
        assert "conversation.personal.other.advocacy_activities" in result.new_paths

        assert len(result.new_paths) == 10  # All categories from response

    @pytest.mark.asyncio
    async def test_expand_family_conversations(self, locomo_taxonomy):
        """Test expansion for family-related conversations."""
        taxonomy = locomo_taxonomy

        # Add family conversation memories
        node = taxonomy.path_index["conversation.social.other"]
        node.other_items = [
            {
                "content": "I'm swamped with the kids & work",
                "speaker": "Melanie",
                "context": "family life",
                "timestamp": "2023-05-08",
            },
            {
                "content": "My daughter's birthday is on 13 August",
                "speaker": "Melanie",
                "context": "family events",
                "timestamp": "2023-08-14",
            },
            {
                "content": "The kids love dinosaurs and nature activities",
                "speaker": "Melanie",
                "context": "children interests",
                "timestamp": "2023-06-27",
            },
            {
                "content": "We went camping as a family in the mountains",
                "speaker": "Melanie",
                "context": "family activities",
                "timestamp": "2023-07-17",
            },
        ]

        with patch.object(taxonomy, "_call_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = LOCOMO_TEST_DATA[
                "conversation_relationships_family"
            ]["response"]

            result = await taxonomy.expand_subtree_with_llm("conversation.social.other")

        # Verify family-focused categories
        assert "conversation.social.other.family_dynamics" in result.new_paths
        assert "conversation.social.other.parenting_experiences" in result.new_paths
        assert "conversation.social.other.children_activities" in result.new_paths
        assert "conversation.social.other.family_outings" in result.new_paths

    @pytest.mark.asyncio
    async def test_expand_activity_conversations(self, locomo_taxonomy):
        """Test expansion for activity-based conversations."""
        taxonomy = locomo_taxonomy

        # Add creative and outdoor activity memories
        node = taxonomy.path_index["conversation.topics.other"]
        node.other_items = [
            {
                "content": "I painted a beautiful sunset last weekend",
                "speaker": "Melanie",
                "context": "creative activities",
                "timestamp": "2023-07-17",
            },
            {
                "content": "Went camping at the beach for two nights",
                "speaker": "Melanie",
                "context": "outdoor activities",
                "timestamp": "2023-07-20",
            },
            {
                "content": "I love doing pottery to destress after work",
                "speaker": "Melanie",
                "context": "creative hobbies",
                "timestamp": "2023-07-03",
            },
            {
                "content": "Running helps me clear my mind and stay fit",
                "speaker": "Melanie",
                "context": "fitness activities",
                "timestamp": "2023-07-12",
            },
        ]

        # Test with multiple responses for different activity types
        async def activity_llm_response(prompt):
            if "painted" in prompt or "pottery" in prompt or "creative" in prompt:
                return LOCOMO_TEST_DATA["conversation_hobbies_creative"]["response"]
            elif "camping" in prompt or "beach" in prompt or "outdoor" in prompt:
                return LOCOMO_TEST_DATA["conversation_outdoor_activities"]["response"]
            elif "running" in prompt or "fitness" in prompt:
                return LOCOMO_TEST_DATA["conversation_health_wellness"]["response"]
            else:
                return LOCOMO_TEST_DATA["defaults"]["conversation_general"]

        with patch.object(taxonomy, "_call_llm", side_effect=activity_llm_response):
            result = await taxonomy.expand_subtree_with_llm("conversation.topics.other")

        # Should get creative activities categories (first match)
        assert any(
            "artistic" in path or "creative" in path for path in result.new_paths
        )

    @pytest.mark.asyncio
    async def test_parallel_conversation_expansion(self, locomo_taxonomy):
        """Test parallel expansion across different conversation domains."""
        taxonomy = locomo_taxonomy

        # Set up multiple conversation memory types
        conversation_nodes = [
            (
                "conversation.personal.other",
                [
                    {
                        "content": "Joined a transgender support group",
                        "context": "identity",
                    },
                    {
                        "content": "Coming out process has been challenging",
                        "context": "identity",
                    },
                    {
                        "content": "Pride parade was incredibly empowering",
                        "context": "LGBTQ",
                    },
                ],
            ),
            (
                "conversation.topics.other",
                [
                    {
                        "content": "Started reading psychology books for my career",
                        "context": "education",
                    },
                    {
                        "content": "Want to become a certified counselor",
                        "context": "career",
                    },
                    {
                        "content": "Gave a speech at the local school",
                        "context": "professional",
                    },
                ],
            ),
            (
                "conversation.temporal.other",
                [
                    {
                        "content": "Planning camping trip for June",
                        "context": "future planning",
                    },
                    {
                        "content": "Last weekend was spent with family",
                        "context": "recent events",
                    },
                    {
                        "content": "Looking forward to summer activities",
                        "context": "planning",
                    },
                ],
            ),
        ]

        for path, items in conversation_nodes:
            if path in taxonomy.path_index:
                node = taxonomy.path_index[path]
                node.other_items = items

        # Mock different responses for different conversation types
        async def conversation_llm_response(prompt):
            if "transgender" in prompt or "LGBTQ" in prompt:
                return LOCOMO_TEST_DATA["conversation_personal_identity"]["response"]
            elif "career" in prompt or "education" in prompt:
                return LOCOMO_TEST_DATA["conversation_career_education"]["response"]
            elif "planning" in prompt or "weekend" in prompt:
                return LOCOMO_TEST_DATA["conversation_time_scheduling"]["response"]
            return LOCOMO_TEST_DATA["defaults"]["conversation_general"]

        with patch.object(taxonomy, "_call_llm", side_effect=conversation_llm_response):
            results = await taxonomy.parallel_expand(
                [path for path, _ in conversation_nodes]
            )

        # Verify all three expansions succeeded
        assert len(results) == 3

        # Check domain-appropriate categories were created
        all_paths = []
        for result in results:
            all_paths.extend(result.new_paths)

        # Should have identity, career, and temporal categories
        assert any("identity" in path for path in all_paths)
        assert any("career" in path or "education" in path for path in all_paths)
        assert any("schedule" in path or "time" in path for path in all_paths)

    @pytest.mark.asyncio
    async def test_conversation_memory_migration(self, locomo_taxonomy):
        """Test migration of conversation memories to appropriate categories."""
        taxonomy = locomo_taxonomy

        # Create conversation memories
        node = taxonomy.path_index["conversation.topics.other"]
        node.other_items = [
            {
                "content": "Went hiking in the mountains with friends",
                "speaker": "Melanie",
            },
            {
                "content": "Painted an abstract art piece for the gallery",
                "speaker": "Caroline",
            },
            {"content": "Running a charity race this weekend", "speaker": "Melanie"},
            {"content": "Reading Charlotte's Web to the kids", "speaker": "Melanie"},
        ]

        # Create realistic categories
        new_paths = [
            "conversation.topics.other.outdoor_adventures",
            "conversation.topics.other.artistic_pursuits",
            "conversation.topics.other.fitness_activities",
            "conversation.topics.other.reading_habits",
        ]

        for path in new_paths:
            taxonomy._add_path_to_tree(taxonomy.root, path, is_dynamic=True)
        taxonomy._rebuild_index()

        # Test reclassification
        migrated = await taxonomy._reclassify_items(node, new_paths)

        # Should migrate most items based on enhanced keyword matching
        assert migrated >= 2  # At least hiking and art items
        assert len(node.other_items) <= 4  # Some or all items migrated

    def test_conversation_context_awareness(self, locomo_taxonomy):
        """Test that conversation context is properly captured."""
        taxonomy = locomo_taxonomy

        # Test building context for conversation memories
        node = taxonomy.path_index["conversation.personal.other"]
        node.other_items = [
            {
                "content": "Transgender support group was powerful",
                "speaker": "Caroline",
                "dialog_id": "D1:3",
                "session": "session_1",
            },
            {
                "content": "LGBTQ community has been so welcoming",
                "speaker": "Caroline",
                "dialog_id": "D1:5",
                "session": "session_1",
            },
        ]

        context = taxonomy._build_expansion_context(node)

        # Verify conversation-specific context
        assert context.node_path == "conversation.personal.other"
        assert (
            "identity" in context.sibling_categories
            or "relationships" in context.sibling_categories
        )
        assert len(context.unclassified_items) == 2
        assert "Transgender" in context.unclassified_items[0]["content"]

    def test_locomo_prompt_generation(self, locomo_taxonomy):
        """Test prompt generation for conversation memories."""
        taxonomy = locomo_taxonomy

        context = ExpansionContext(
            node_path="conversation.personal.other",
            parent_hierarchy=["conversation", "personal", "other"],
            sibling_categories=["identity", "relationships", "activities", "emotions"],
            unclassified_items=[
                {"content": "LGBTQ support group was incredibly empowering"},
                {"content": "Transgender stories shared were so inspiring"},
                {"content": "Pride parade brought sense of community"},
            ],
            current_depth=3,
            taxonomy_snapshot={},
        )

        prompt = taxonomy._build_expansion_prompt(context)

        # Verify conversation-focused prompt elements
        assert "conversation.personal.other" in prompt
        assert "LGBTQ support group" in prompt
        assert "Transgender stories" in prompt
        assert "Pride parade" in prompt
        assert "relationships" in prompt
        assert "identity" in prompt

    def test_conversation_statistics(self, locomo_taxonomy):
        """Test statistics tracking for conversation taxonomies."""
        taxonomy = locomo_taxonomy

        # Simulate conversation memory expansion
        from memoir.taxonomy.iterative import (
            TaxonomyExpansionResult,
        )

        expansions = [
            TaxonomyExpansionResult(
                parent_path="conversation.personal.other",
                new_paths=[
                    "conversation.personal.identity_exploration",
                    "conversation.personal.LGBTQ_community",
                ],
                migrated_items=12,
                confidence=0.85,
                strategy="focused_subtree",
                reasoning="Expanded identity conversation categories",
                timestamp=1640995400.0,
            ),
            TaxonomyExpansionResult(
                parent_path="conversation.topics.other",
                new_paths=[
                    "conversation.topics.outdoor_adventures",
                    "conversation.topics.artistic_pursuits",
                ],
                migrated_items=8,
                confidence=0.80,
                strategy="focused_subtree",
                reasoning="Expanded activity conversation categories",
                timestamp=1640995500.0,
            ),
        ]

        taxonomy.expansion_history.extend(expansions)
        stats = taxonomy.get_expansion_statistics()

        # Verify conversation-focused statistics
        assert stats["expansion_history"] == 2
        assert stats["total_migrated"] == 20  # 12 + 8
        assert stats["total_paths"] > 20  # Base conversation paths + others


class TestLocomoMockLLM:
    """Test the LOCOMO-specific mock LLM."""

    @pytest.mark.asyncio
    async def test_locomo_identity_responses(self):
        """Test identity-focused conversation responses."""
        llm = LocomoMockLLM()

        prompt = "conversation about transgender support groups and LGBTQ community"
        response = await llm.generate(prompt)

        assert "identity_exploration" in response
        assert "LGBTQ_community" in response
        assert "support_groups" in response

    @pytest.mark.asyncio
    async def test_locomo_family_responses(self):
        """Test family-focused conversation responses."""
        llm = LocomoMockLLM()

        prompt = "conversation about kids and parenting experiences"
        response = await llm.generate(prompt)

        assert "family_dynamics" in response
        assert "parenting_experiences" in response
        assert "children_activities" in response

    @pytest.mark.asyncio
    async def test_locomo_activity_responses(self):
        """Test activity-focused conversation responses."""
        llm = LocomoMockLLM()

        prompt = "conversation about painting and creative activities"
        response = await llm.generate(prompt)

        assert "artistic_pursuits" in response
        assert "creative_expression" in response
        assert "painting_activities" in response


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

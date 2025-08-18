"""
Taxonomy presets for different use cases.
Each preset defines a first-level base taxonomy optimized for specific domains.
"""

from enum import Enum
from typing import ClassVar


class TaxonomyVersion(Enum):
    """Available taxonomy versions for different use cases."""

    GENERAL = "general"
    AGENT_CONVERSATION = "agent_conversation"
    WORKFLOW_AUTOMATION = "workflow_automation"
    CUSTOMER_SERVICE = "customer_service"
    KNOWLEDGE_BASE = "knowledge_base"
    PERSONAL_ASSISTANT = "personal_assistant"


class TaxonomyPresets:
    """Defines base taxonomy presets for different use cases."""

    PRESETS: ClassVar[dict[TaxonomyVersion, dict[str, list[str]]]] = {
        TaxonomyVersion.GENERAL: {
            "profile": [],
            "preferences": [],
            "experience": [],
            "context": [],
            "knowledge": [],
            "relationships": [],
            "goals": [],
            "behavior": [],
        },
        TaxonomyVersion.AGENT_CONVERSATION: {
            "conversation": [],
            "user_profile": [],
            "agent_state": [],
            "dialogue_history": [],
            "intent": [],
            "entities": [],
            "sentiment": [],
            "topics": [],
            "actions": [],
            "feedback": [],
        },
        TaxonomyVersion.WORKFLOW_AUTOMATION: {
            "workflows": [],
            "tasks": [],
            "triggers": [],
            "conditions": [],
            "actions": [],
            "integrations": [],
            "data_mappings": [],
            "schedules": [],
            "notifications": [],
            "errors": [],
            "logs": [],
            "metrics": [],
        },
        TaxonomyVersion.CUSTOMER_SERVICE: {
            "customers": [],
            "tickets": [],
            "issues": [],
            "products": [],
            "solutions": [],
            "escalations": [],
            "satisfaction": [],
            "faq": [],
            "policies": [],
            "communications": [],
            "analytics": [],
        },
        TaxonomyVersion.KNOWLEDGE_BASE: {
            "documents": [],
            "categories": [],
            "tags": [],
            "concepts": [],
            "definitions": [],
            "procedures": [],
            "references": [],
            "examples": [],
            "metadata": [],
            "versions": [],
            "permissions": [],
        },
        TaxonomyVersion.PERSONAL_ASSISTANT: {
            "personal_info": [],
            "calendar": [],
            "reminders": [],
            "notes": [],
            "contacts": [],
            "preferences": [],
            "routines": [],
            "health": [],
            "finance": [],
            "projects": [],
            "learning": [],
        },
    }

    @classmethod
    def get_preset(cls, version: TaxonomyVersion) -> dict[str, list[str]]:
        """
        Get a taxonomy preset for a specific version.

        Args:
            version: The taxonomy version to retrieve

        Returns:
            Dictionary with first-level categories and their subcategories (empty for dynamic expansion)
        """
        return cls.PRESETS.get(version, cls.PRESETS[TaxonomyVersion.GENERAL]).copy()

    @classmethod
    def get_first_level_categories(cls, version: TaxonomyVersion) -> list[str]:
        """
        Get only the first-level categories for a taxonomy version.

        Args:
            version: The taxonomy version

        Returns:
            List of first-level category names
        """
        preset = cls.get_preset(version)
        return list(preset.keys())

    @classmethod
    def list_versions(cls) -> list[TaxonomyVersion]:
        """
        List all available taxonomy versions.

        Returns:
            List of available TaxonomyVersion enums
        """
        return list(TaxonomyVersion)

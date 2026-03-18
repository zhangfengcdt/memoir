"""
Taxonomy presets - FALLBACK DATA ONLY.

IMPORTANT: This hardcoded data exists solely as a fallback when:
1. No TaxonomyLoader is provided to the classifier/search engine
2. The store has not been initialized with taxonomy data

The canonical source of taxonomy data is the markdown files in:
    src/memoir/taxonomy/data/general/*.md

These markdown files are loaded via TaxonomyLoader into the store.
The hardcoded data below should be kept minimal and may be removed
in a future version once store-based taxonomy loading is mandatory.

To use store-based taxonomy (recommended):
    taxonomy_loader = TaxonomyLoader(store)
    taxonomy_loader.init_store(include_builtin=True)
    classifier = IntelligentClassifier(llm=llm, taxonomy_loader=taxonomy_loader)
"""

from enum import Enum
from typing import ClassVar


class TaxonomyVersion(Enum):
    """Available taxonomy versions."""

    GENERAL = "general"
    SIMPLIFIED = "simplified"


class TaxonomyPresets:
    """
    Minimal fallback taxonomy data.

    WARNING: This is fallback data only. Use TaxonomyLoader for full taxonomy.
    See module docstring for details.
    """

    # ==========================================================================
    # FALLBACK CLASSIFICATION EXAMPLES (minimal set)
    # Full examples are in: src/memoir/taxonomy/data/general/examples.md
    # ==========================================================================
    CLASSIFICATION_EXAMPLES: ClassVar[list[tuple[str, str, str]]] = [
        # Profile
        ("My name is Sarah", "profile.personal.identity", "identity"),
        ("I work as a software engineer", "profile.professional.occupation", "job"),
        # Preferences
        ("I prefer VS Code", "preferences.tools.editors", "tool preference"),
        ("I like Python", "preferences.coding.languages", "language preference"),
        # Context
        ("We use PostgreSQL", "context.project.database", "project context"),
        ("Our team does standups daily", "context.team.meetings", "team context"),
        # Experience
        ("I worked at Google for 3 years", "experience.work.jobs", "work history"),
        ("I built a REST API last month", "experience.work.projects", "project"),
        # Goals
        ("I want to learn Rust", "goals.learning.skills", "learning goal"),
        ("I aim to become a tech lead", "goals.career.advancement", "career goal"),
        # Relationships
        ("My manager is John", "relationships.professional.manager", "work relation"),
        ("I mentor two junior devs", "relationships.professional.mentees", "mentoring"),
        # Knowledge
        (
            "Python uses indentation for blocks",
            "knowledge.technical.languages",
            "tech fact",
        ),
        ("REST APIs use HTTP methods", "knowledge.technical.architecture", "tech fact"),
        # Behavior
        ("I usually code in the morning", "behavior.work.schedule", "work pattern"),
        ("I review PRs before lunch", "behavior.work.practices", "work habit"),
    ]

    # ==========================================================================
    # FALLBACK CATEGORY DESCRIPTIONS (8 main categories)
    # Full descriptions are in: src/memoir/taxonomy/data/general/descriptions.md
    # ==========================================================================
    CATEGORY_DESCRIPTIONS: ClassVar[dict[str, str]] = {
        "profile": "Personal facts: identity, demographics, job, education, skills",
        "preferences": "Likes/dislikes: tools, languages, frameworks, work style",
        "context": "Project/team info: tech stack, infrastructure, team roles",
        "experience": "Past events: work history, projects, achievements",
        "goals": "Aspirations: career, learning, projects, personal growth",
        "relationships": "People: colleagues, manager, mentors, mentees",
        "knowledge": "Facts learned: technical concepts, domain knowledge",
        "behavior": "Patterns: work habits, routines, practices",
    }

    # ==========================================================================
    # FALLBACK PRESET PATHS (minimal set for each category)
    # Full paths are in: src/memoir/taxonomy/data/general/presets.md
    # ==========================================================================
    PRESETS: ClassVar[dict[TaxonomyVersion, dict[str, list[str]]]] = {
        TaxonomyVersion.SIMPLIFIED: {
            "profile": [
                "personal.identity",
                "personal.demographics",
                "personal.location",
                "professional.occupation",
                "professional.education",
                "professional.skills",
            ],
            "preferences": [
                "tools.editors",
                "tools.testing",
                "coding.languages",
                "coding.frameworks",
                "work.environment",
                "work.schedule",
            ],
            "context": [
                "project.stack",
                "project.repository",
                "project.database",
                "team.methodology",
                "team.meetings",
                "team.roles",
            ],
            "experience": [
                "work.jobs",
                "work.projects",
                "education.schools",
                "education.courses",
            ],
            "goals": [
                "career.advancement",
                "career.skills",
                "learning.skills",
                "learning.certifications",
            ],
            "relationships": [
                "professional.manager",
                "professional.colleagues",
                "professional.mentees",
                "personal.family",
            ],
            "knowledge": [
                "technical.languages",
                "technical.architecture",
                "domain.business",
                "domain.industry",
            ],
            "behavior": [
                "work.schedule",
                "work.practices",
                "coding.habits",
                "communication.style",
            ],
        }
    }

    def get_paths_for_category(
        self, version: TaxonomyVersion, category: str
    ) -> list[str]:
        """Get all paths for a specific category."""
        if version not in self.PRESETS:
            raise ValueError(f"Unknown taxonomy version: {version}")

        category_paths = self.PRESETS[version].get(category, [])
        return [f"{category}.{path}" for path in category_paths]

    def get_all_paths(self, version: TaxonomyVersion) -> list[str]:
        """Get all taxonomy paths for a version."""
        if version not in self.PRESETS:
            raise ValueError(f"Unknown taxonomy version: {version}")

        all_paths = []
        for category, paths in self.PRESETS[version].items():
            for path in paths:
                full_path = f"{category}.{path}"
                all_paths.append(full_path)

        return sorted(all_paths)

    @classmethod
    def get_preset(cls, version: TaxonomyVersion) -> dict[str, list[str]]:
        """Get a taxonomy preset for a specific version."""
        return cls.PRESETS.get(version, cls.PRESETS[TaxonomyVersion.SIMPLIFIED]).copy()

    @classmethod
    def get_first_level_categories(cls, version: TaxonomyVersion) -> list[str]:
        """Get only the first-level categories for a taxonomy version."""
        preset = cls.get_preset(version)
        return list(preset.keys())

    @classmethod
    def list_versions(cls) -> list[TaxonomyVersion]:
        """List all available taxonomy versions."""
        return list(cls.PRESETS.keys())

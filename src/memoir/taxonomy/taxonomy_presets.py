"""
Taxonomy presets with under 200 total paths for efficient LLM classification.
"""

from enum import Enum
from typing import ClassVar


class TaxonomyVersion(Enum):
    """Available taxonomy versions."""

    GENERAL = "general"
    SIMPLIFIED = "simplified"


class TaxonomyPresets:
    """Taxonomy presets with essential paths only (~208 total paths)."""

    PRESETS: ClassVar[dict[TaxonomyVersion, dict[str, list[str]]]] = {
        TaxonomyVersion.SIMPLIFIED: {
            # Core Profile Information (53 paths)
            # This is managed by the profile manager service
            "profile": [
                # Essential Personal Identity (8 paths)
                "personal.identity.name.first",
                "personal.identity.name.last",
                "personal.identity.gender.identity",
                "personal.identity.sexual_orientation",
                "personal.demographics.age.current",
                "personal.demographics.birth.date",
                "personal.demographics.marital_status",
                "personal.demographics.children.number",
                # Core Professional (15 paths)
                "professional.current.company",
                "professional.current.title",
                "professional.current.salary.base",
                "professional.aspirations.career_goals",
                "professional.aspirations.industry_interest",
                "professional.motivation.personal_purpose",
                "professional.education.college.name",
                "professional.education.college.degree",
                "professional.education.college.major",
                "professional.education.college.graduation_year",
                "professional.skills.technical.programming",
                "professional.skills.soft.leadership",
                "professional.skills.industry.expertise",
                "professional.history.previous_companies",
                "professional.network.mentors",
                # Essential Health (8 paths)
                "health.physical.height",
                "health.physical.weight",
                "health.physical.fitness_level",
                "health.physical.diet.restrictions",
                "health.mental.conditions.diagnosed",
                "health.mental.therapy.current",
                "health.mental.stress.level",
                "health.medical.conditions.chronic",
                # Key Financial (8 paths)
                "finance.income.primary.amount",
                "finance.expenses.housing.rent_mortgage",
                "finance.debt.student_loans.balance",
                "finance.debt.credit_cards.balance",
                "finance.savings.emergency_fund.amount",
                "finance.investments.stocks.portfolio",
                "finance.credit.score.current",
                "finance.banking.primary.bank",
                # Living Essentials (8 paths)
                "living.current.address.city",
                "living.current.address.state",
                "living.current.type.house_apartment",
                "living.current.ownership.rent_own",
                "living.current.roommates.number",
                "living.current.pets.types",
                "living.transportation.primary.method",
                "living.transportation.car.make_model",
                # Key Relationships (6 paths)
                "relationships.romantic.status.current",
                "relationships.romantic.partner.name",
                "relationships.friendships.close.number",
                "relationships.family.relationship.parents",
                "relationships.social.groups.memberships",
                "relationships.social.media.platforms",
            ],
            # Events (3 paths) - For keyword-searchable event storage
            # This is managed by the event manager service (TODO)
            "events": [
                "self",  # Events where the user is the primary actor
                "peer",  # Events where a peer/friend is the primary actor
                "group",  # Events involving groups or multiple people
            ],
            # Personal Preferences (20 paths)
            "preferences": [
                "personal.lifestyle.habits",
                "personal.hobbies.creative",
                "personal.hobbies.sports",
                "personal.hobbies.outdoor",
                "personal.interests.subjects",
                "personal.entertainment.movies",
                "personal.entertainment.music",
                "personal.entertainment.books",
                "personal.food.cuisine",
                "personal.food.dietary",
                "personal.travel.destinations",
                "personal.travel.style",
                "social.activities.group",
                "social.activities.solo",
                "social.events.formal",
                "social.events.casual",
                "work.environment.office",
                "work.environment.remote",
                "work.schedule.flexible",
                "work.schedule.structured",
            ],
            # Life Experiences (25 paths)
            "experience": [
                "memories.recent.positive",
                "memories.recent.challenging",
                "memories.significant.achievements",
                "memories.significant.relationships",
                "memories.significant.events",
                "memories.childhood.family",
                "memories.childhood.school",
                "memories.adolescence.friendships",
                "memories.adolescence.challenges",
                "education.primary.schools",
                "education.secondary.schools",
                "education.university.experiences",
                "education.graduate.programs",
                "education.continuing.courses",
                "travel.domestic.trips",
                "travel.international.trips",
                "travel.business.trips",
                "work.jobs.current",
                "work.jobs.previous",
                "work.projects.successful",
                "work.projects.challenging",
                "work.achievements.recognition",
                "life_events.marriage.wedding",
                "life_events.children.birth",
                "life_events.career.changes",
            ],
            # Goals & Aspirations (20 paths)
            "goals": [
                "categories.personal.health",
                "categories.personal.relationships",
                "categories.personal.growth",
                "categories.personal.hobbies",
                "categories.career.advancement",
                "categories.career.change",
                "categories.career.skills",
                "categories.financial.savings",
                "categories.financial.investments",
                "categories.financial.debt_reduction",
                "categories.education.degrees",
                "categories.education.certifications",
                "categories.education.skills",
                "timeline.short_term.immediate",
                "timeline.short_term.months",
                "timeline.long_term.years",
                "timeline.lifelong.dreams",
                "status.active.pursuing",
                "status.planning.considering",
                "status.completed.achieved",
            ],
            # Relationships (20 paths)
            "relationships": [
                "people.family.immediate.parents",
                "people.family.immediate.siblings",
                "people.family.immediate.children",
                "people.family.extended.relatives",
                "people.friends.close.best",
                "people.friends.close.longtime",
                "people.friends.casual.acquaintances",
                "people.friends.work.colleagues",
                "people.romantic.current.partner",
                "people.romantic.former.partners",
                "people.professional.mentors.guides",
                "people.professional.mentees.students",
                "people.professional.clients.customers",
                "people.community.neighbors.local",
                "people.community.groups.members",
                "dynamics.supportive.encouraging",
                "dynamics.challenging.difficult",
                "dynamics.neutral.cordial",
                "interactions.frequency.daily",
                "interactions.frequency.occasional",
            ],
            # Key Entities (25 paths)
            "entity": [
                "people.mentioned.friends.close",
                "people.mentioned.family.members",
                "people.mentioned.colleagues.work",
                "people.mentioned.public.figures",
                "people.mentioned.service.providers",
                "places.locations.cities.current",
                "places.locations.cities.previous",
                "places.buildings.homes.current",
                "places.buildings.offices.work",
                "places.venues.restaurants.favorite",
                "places.venues.entertainment.frequent",
                "organizations.companies.current",
                "organizations.companies.previous",
                "organizations.groups.social.clubs",
                "organizations.institutions.schools",
                "objects.items.personal.important",
                "objects.items.technology.devices",
                "objects.media.books.favorite",
                "objects.media.movies.liked",
                "events.activities.social.gatherings",
                "events.milestones.personal.important",
                "events.milestones.professional.career",
                "time.dates.specific.important",
                "time.periods.durations.significant",
                "concepts.topics.discussed.main",
            ],
            # Essential Topics (20 paths)
            "topics": [
                "health.mental_health.wellness",
                "health.fitness.exercise",
                "health.nutrition.diet",
                "career.professional_development.skills",
                "career.job_search.opportunities",
                "career.workplace.culture",
                "technology.artificial_intelligence.developments",
                "technology.social_media.platforms",
                "finance.personal.budgeting",
                "finance.investing.strategies",
                "education.learning.methods",
                "education.skills.development",
                "relationships.communication.improvement",
                "relationships.family.dynamics",
                "entertainment.movies.reviews",
                "entertainment.music.preferences",
                "travel.destinations.planning",
                "travel.experiences.memorable",
                "current_events.news.important",
                "social_issues.community.involvement",
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
        """
        Get a taxonomy preset for a specific version.

        Args:
            version: The taxonomy version to retrieve

        Returns:
            Dictionary with first-level categories and their subcategories
        """
        return cls.PRESETS.get(version, cls.PRESETS[TaxonomyVersion.SIMPLIFIED]).copy()

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
            List of TaxonomyVersion enums
        """
        return list(cls.PRESETS.keys())

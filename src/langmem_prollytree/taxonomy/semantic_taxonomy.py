"""
Comprehensive semantic taxonomy for AI memory classification.
Defines ~800 hierarchical paths for deterministic memory organization.
"""

from dataclasses import dataclass
from enum import Enum


class TaxonomyCategory(Enum):
    """Top-level taxonomy categories."""

    PROFILE = "profile"
    PREFERENCES = "preferences"
    EXPERIENCE = "experience"
    CONTEXT = "context"
    KNOWLEDGE = "knowledge"
    RELATIONSHIPS = "relationships"
    GOALS = "goals"
    BEHAVIOR = "behavior"


@dataclass
class TaxonomyNode:
    """Represents a node in the taxonomy tree."""

    path: str
    category: TaxonomyCategory
    depth: int
    is_leaf: bool
    description: str
    examples: list[str]


class SemanticTaxonomy:
    """
    Fixed semantic taxonomy with approximately 800 predefined paths.
    Provides hierarchical organization for AI memory classification.
    """

    def __init__(self):
        self._taxonomy = self._build_taxonomy()
        self._all_paths = self._generate_all_paths()
        self._path_index = self._build_path_index()

    def _build_taxonomy(self) -> dict:
        """Build the complete semantic taxonomy structure."""
        return {
            "profile": {
                "personal": {
                    "identity": {
                        "name": ["first", "middle", "last", "nickname", "preferred"],
                        "age": ["current", "birthday", "generation"],
                        "gender": ["identity", "pronouns", "expression"],
                        "nationality": ["citizenship", "ethnicity", "heritage"],
                        "personality": [
                            "traits",
                            "mbti",
                            "enneagram",
                            "strengths",
                            "weaknesses",
                        ],
                    },
                    "location": {
                        "current": [
                            "country",
                            "state",
                            "city",
                            "neighborhood",
                            "address",
                        ],
                        "hometown": ["country", "state", "city", "significance"],
                        "previous": ["countries", "cities", "duration", "reasons"],
                        "preferred": ["climate", "urban_rural", "region", "criteria"],
                    },
                    "family": {
                        "spouse": ["name", "occupation", "relationship", "anniversary"],
                        "children": ["names", "ages", "interests", "schools"],
                        "parents": ["names", "occupations", "relationship", "location"],
                        "siblings": ["names", "ages", "occupations", "relationship"],
                        "extended": [
                            "grandparents",
                            "aunts_uncles",
                            "cousins",
                            "in_laws",
                        ],
                    },
                    "health": {
                        "physical": [
                            "conditions",
                            "allergies",
                            "medications",
                            "fitness",
                        ],
                        "mental": ["conditions", "therapy", "medications", "wellness"],
                        "diet": ["restrictions", "preferences", "allergies", "goals"],
                        "sleep": ["schedule", "quality", "issues", "preferences"],
                    },
                    "appearance": {
                        "physical": [
                            "height",
                            "build",
                            "hair",
                            "eyes",
                            "distinguishing",
                        ],
                        "style": ["clothing", "accessories", "grooming", "preferences"],
                    },
                },
                "professional": {
                    "current": {
                        "company": ["name", "industry", "size", "culture", "location"],
                        "position": ["title", "level", "department", "tenure"],
                        "team": ["size", "structure", "members", "dynamics"],
                        "responsibilities": [
                            "primary",
                            "secondary",
                            "projects",
                            "kpis",
                        ],
                        "compensation": ["salary", "equity", "benefits", "perks"],
                    },
                    "history": {
                        "companies": [
                            "names",
                            "positions",
                            "durations",
                            "reasons_left",
                        ],
                        "industries": [
                            "types",
                            "experience",
                            "expertise",
                            "preferences",
                        ],
                        "achievements": [
                            "awards",
                            "recognition",
                            "milestones",
                            "impact",
                        ],
                        "failures": [
                            "lessons",
                            "mistakes",
                            "learnings",
                            "improvements",
                        ],
                    },
                    "skills": {
                        "technical": {
                            "programming": [
                                "languages",
                                "frameworks",
                                "tools",
                                "years",
                            ],
                            "data": ["databases", "analytics", "ml", "visualization"],
                            "infrastructure": [
                                "cloud",
                                "devops",
                                "networking",
                                "security",
                            ],
                            "domain": [
                                "industry",
                                "business",
                                "regulatory",
                                "specialized",
                            ],
                        },
                        "soft": {
                            "leadership": [
                                "style",
                                "experience",
                                "strengths",
                                "development",
                            ],
                            "communication": [
                                "written",
                                "verbal",
                                "presentation",
                                "languages",
                            ],
                            "collaboration": [
                                "teamwork",
                                "conflict",
                                "mentoring",
                                "networking",
                            ],
                            "thinking": [
                                "analytical",
                                "creative",
                                "strategic",
                                "critical",
                            ],
                        },
                        "certifications": ["active", "expired", "pursuing", "planned"],
                    },
                    "education": {
                        "formal": ["degrees", "institutions", "majors", "years"],
                        "continuing": [
                            "courses",
                            "workshops",
                            "conferences",
                            "self_study",
                        ],
                        "interests": ["topics", "fields", "resources", "goals"],
                    },
                },
            },
            "preferences": {
                "technology": {
                    "programming": {
                        "languages": ["primary", "secondary", "learning", "avoided"],
                        "paradigms": ["functional", "oop", "procedural", "declarative"],
                        "frameworks": ["web", "mobile", "desktop", "embedded"],
                        "tools": ["editors", "ides", "version_control", "debugging"],
                    },
                    "ui": {
                        "theme": ["dark", "light", "auto", "custom"],
                        "layout": ["density", "sidebar", "navigation", "widgets"],
                        "accessibility": [
                            "font_size",
                            "contrast",
                            "motion",
                            "screen_reader",
                        ],
                        "customization": ["shortcuts", "aliases", "macros", "plugins"],
                    },
                    "platforms": {
                        "operating_systems": [
                            "primary",
                            "secondary",
                            "mobile",
                            "preferences",
                        ],
                        "cloud": ["providers", "services", "regions", "preferences"],
                        "databases": ["relational", "nosql", "graph", "time_series"],
                        "architecture": [
                            "monolith",
                            "microservices",
                            "serverless",
                            "edge",
                        ],
                    },
                    "ai": {
                        "models": ["preferred", "avoided", "fine_tuned", "custom"],
                        "interactions": ["style", "detail", "format", "frequency"],
                        "privacy": ["data_sharing", "training", "storage", "deletion"],
                    },
                },
                "work": {
                    "environment": {
                        "location": ["remote", "office", "hybrid", "travel"],
                        "schedule": [
                            "hours",
                            "flexibility",
                            "time_zone",
                            "availability",
                        ],
                        "workspace": ["desk", "equipment", "noise", "privacy"],
                    },
                    "collaboration": {
                        "communication": ["email", "chat", "video", "in_person"],
                        "meetings": [
                            "frequency",
                            "duration",
                            "format",
                            "participation",
                        ],
                        "documentation": ["style", "tools", "detail", "organization"],
                        "feedback": ["giving", "receiving", "frequency", "format"],
                    },
                    "productivity": {
                        "focus": [
                            "deep_work",
                            "multitasking",
                            "breaks",
                            "distractions",
                        ],
                        "planning": ["daily", "weekly", "quarterly", "tools"],
                        "prioritization": [
                            "methods",
                            "criteria",
                            "flexibility",
                            "delegation",
                        ],
                        "automation": ["tasks", "tools", "scripts", "workflows"],
                    },
                    "culture": {
                        "values": [
                            "important",
                            "dealbreakers",
                            "alignment",
                            "conflicts",
                        ],
                        "team": ["size", "diversity", "hierarchy", "dynamics"],
                        "management": ["style", "autonomy", "support", "recognition"],
                        "growth": [
                            "learning",
                            "advancement",
                            "mentorship",
                            "challenges",
                        ],
                    },
                },
                "personal": {
                    "lifestyle": {
                        "routine": ["morning", "evening", "weekend", "exercise"],
                        "hobbies": ["active", "creative", "intellectual", "social"],
                        "entertainment": ["music", "movies", "books", "games"],
                        "travel": ["frequency", "style", "destinations", "planning"],
                    },
                    "social": {
                        "interactions": [
                            "introverted",
                            "extroverted",
                            "ambivert",
                            "preferences",
                        ],
                        "relationships": [
                            "quality",
                            "quantity",
                            "maintenance",
                            "boundaries",
                        ],
                        "activities": ["group", "individual", "virtual", "in_person"],
                        "communication": ["style", "frequency", "medium", "topics"],
                    },
                    "values": {
                        "core": [
                            "family",
                            "career",
                            "health",
                            "spirituality",
                            "community",
                        ],
                        "ethics": ["principles", "causes", "activism", "donations"],
                        "politics": ["leaning", "issues", "engagement", "preferences"],
                        "environment": [
                            "sustainability",
                            "consumption",
                            "lifestyle",
                            "advocacy",
                        ],
                    },
                    "finance": {
                        "management": ["budgeting", "saving", "investing", "tracking"],
                        "goals": ["short_term", "long_term", "retirement", "legacy"],
                        "risk": [
                            "tolerance",
                            "insurance",
                            "emergency",
                            "diversification",
                        ],
                        "spending": [
                            "priorities",
                            "habits",
                            "splurges",
                            "restrictions",
                        ],
                    },
                },
            },
            "experience": {
                "projects": {
                    "current": {
                        "active": ["name", "status", "timeline", "blockers"],
                        "planning": ["ideas", "research", "requirements", "design"],
                        "paused": ["reasons", "dependencies", "timeline", "priority"],
                    },
                    "completed": {
                        "successful": ["outcomes", "impact", "learnings", "artifacts"],
                        "failed": ["reasons", "lessons", "decisions", "alternatives"],
                        "partial": ["achievements", "gaps", "future", "value"],
                    },
                    "types": {
                        "personal": [
                            "side_projects",
                            "hobbies",
                            "learning",
                            "creative",
                        ],
                        "professional": ["work", "freelance", "consulting", "products"],
                        "open_source": [
                            "contributions",
                            "maintenance",
                            "creation",
                            "collaboration",
                        ],
                        "academic": ["research", "papers", "thesis", "coursework"],
                    },
                },
                "achievements": {
                    "professional": [
                        "promotions",
                        "awards",
                        "recognition",
                        "milestones",
                    ],
                    "personal": ["goals", "challenges", "growth", "breakthroughs"],
                    "academic": ["degrees", "honors", "publications", "research"],
                    "community": ["contributions", "leadership", "impact", "service"],
                },
                "challenges": {
                    "overcome": ["technical", "personal", "professional", "health"],
                    "ongoing": ["struggles", "obstacles", "efforts", "support"],
                    "learned": ["failures", "mistakes", "feedback", "growth"],
                },
                "memories": {
                    "significant": ["events", "people", "places", "moments"],
                    "formative": ["childhood", "education", "career", "relationships"],
                    "recent": ["today", "week", "month", "year"],
                    "emotional": ["happy", "sad", "proud", "difficult"],
                },
            },
            "context": {
                "current": {
                    "session": {
                        "topic": ["main", "subtopics", "related", "avoided"],
                        "goal": [
                            "primary",
                            "secondary",
                            "constraints",
                            "success_criteria",
                        ],
                        "progress": ["completed", "remaining", "blocked", "next_steps"],
                        "mood": ["focused", "exploratory", "urgent", "relaxed"],
                    },
                    "temporal": {
                        "day": ["date", "weekday", "time", "timezone"],
                        "schedule": [
                            "appointments",
                            "deadlines",
                            "availability",
                            "conflicts",
                        ],
                        "energy": ["level", "peak_times", "low_times", "breaks"],
                        "priorities": ["urgent", "important", "delegated", "deferred"],
                    },
                    "environment": {
                        "location": ["physical", "virtual", "timezone", "connectivity"],
                        "devices": [
                            "primary",
                            "secondary",
                            "capabilities",
                            "limitations",
                        ],
                        "distractions": [
                            "notifications",
                            "interruptions",
                            "noise",
                            "multitasking",
                        ],
                        "resources": ["available", "limited", "needed", "alternatives"],
                    },
                },
                "history": {
                    "conversations": {
                        "recent": ["topics", "decisions", "questions", "actions"],
                        "frequent": ["themes", "patterns", "preferences", "issues"],
                        "important": [
                            "decisions",
                            "insights",
                            "breakthroughs",
                            "agreements",
                        ],
                    },
                    "interactions": {
                        "patterns": ["frequency", "duration", "depth", "satisfaction"],
                        "preferences": ["style", "pace", "detail", "format"],
                        "feedback": [
                            "positive",
                            "negative",
                            "suggestions",
                            "adjustments",
                        ],
                    },
                },
            },
            "knowledge": {
                "domains": {
                    "expertise": {
                        "deep": ["fields", "topics", "skills", "experience"],
                        "broad": ["areas", "connections", "applications", "trends"],
                        "emerging": ["learning", "exploring", "interested", "tracking"],
                    },
                    "technical": {
                        "computer_science": [
                            "algorithms",
                            "data_structures",
                            "theory",
                            "systems",
                        ],
                        "engineering": [
                            "software",
                            "hardware",
                            "mechanical",
                            "electrical",
                        ],
                        "sciences": ["physics", "chemistry", "biology", "mathematics"],
                        "applied": ["ml", "ai", "robotics", "blockchain", "quantum"],
                    },
                    "business": {
                        "management": ["strategy", "operations", "finance", "hr"],
                        "industries": ["tech", "finance", "healthcare", "retail"],
                        "skills": [
                            "analysis",
                            "presentation",
                            "negotiation",
                            "leadership",
                        ],
                    },
                    "creative": {
                        "arts": ["visual", "music", "writing", "performance"],
                        "design": ["ui_ux", "graphic", "product", "architecture"],
                        "content": ["writing", "video", "audio", "multimedia"],
                    },
                },
                "learning": {
                    "style": ["visual", "auditory", "kinesthetic", "reading"],
                    "pace": ["fast", "moderate", "thorough", "iterative"],
                    "preferences": ["examples", "theory", "practice", "discussion"],
                    "resources": ["books", "videos", "courses", "mentors"],
                },
                "facts": {
                    "remembered": ["important", "frequently_used", "recently_learned"],
                    "references": ["sources", "links", "documents", "contacts"],
                    "definitions": ["terms", "concepts", "acronyms", "jargon"],
                },
            },
            "relationships": {
                "people": {
                    "close": {
                        "family": ["immediate", "extended", "chosen", "estranged"],
                        "friends": ["best", "close", "casual", "online"],
                        "romantic": ["current", "past", "interests", "preferences"],
                    },
                    "professional": {
                        "colleagues": ["current", "former", "collaborators", "mentors"],
                        "network": ["industry", "alumni", "communities", "online"],
                        "clients": ["current", "past", "potential", "relationships"],
                    },
                    "community": {
                        "neighbors": [
                            "immediate",
                            "building",
                            "neighborhood",
                            "community",
                        ],
                        "groups": ["clubs", "organizations", "causes", "hobbies"],
                        "online": ["forums", "social_media", "gaming", "professional"],
                    },
                },
                "dynamics": {
                    "communication": ["styles", "frequency", "topics", "boundaries"],
                    "trust": ["levels", "building", "broken", "repair"],
                    "conflict": ["sources", "resolution", "avoidance", "patterns"],
                    "support": ["giving", "receiving", "types", "networks"],
                },
            },
            "goals": {
                "timeframes": {
                    "immediate": ["today", "week", "urgent", "blocking"],
                    "short_term": ["month", "quarter", "projects", "milestones"],
                    "medium_term": ["year", "multi_year", "career", "personal"],
                    "long_term": ["life", "legacy", "retirement", "dreams"],
                },
                "categories": {
                    "career": ["position", "skills", "company", "industry", "income"],
                    "personal": ["health", "relationships", "growth", "experiences"],
                    "financial": ["savings", "investments", "purchases", "freedom"],
                    "learning": ["skills", "knowledge", "certifications", "degrees"],
                    "creative": ["projects", "skills", "recognition", "expression"],
                },
                "progress": {
                    "tracking": ["metrics", "milestones", "checkpoints", "reviews"],
                    "obstacles": [
                        "blockers",
                        "challenges",
                        "dependencies",
                        "resources",
                    ],
                    "adjustments": ["pivots", "refinements", "timeline", "scope"],
                },
            },
            "behavior": {
                "patterns": {
                    "daily": ["routines", "habits", "triggers", "responses"],
                    "work": ["productivity", "procrastination", "focus", "breaks"],
                    "social": ["interactions", "avoidance", "seeking", "boundaries"],
                    "stress": ["responses", "coping", "triggers", "management"],
                },
                "decisions": {
                    "style": ["analytical", "intuitive", "collaborative", "decisive"],
                    "factors": ["logic", "emotion", "values", "constraints"],
                    "process": ["research", "consultation", "timeline", "review"],
                    "history": ["successful", "regretted", "learned", "patterns"],
                },
                "adaptation": {
                    "change": ["embracing", "resisting", "managing", "initiating"],
                    "learning": [
                        "from_mistakes",
                        "from_success",
                        "from_others",
                        "continuous",
                    ],
                    "flexibility": ["plans", "opinions", "methods", "goals"],
                },
            },
        }

    def _generate_all_paths(self) -> set[str]:
        """Generate all valid paths from the taxonomy."""
        paths = set()

        def traverse(obj, prefix=""):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_prefix = f"{prefix}.{key}" if prefix else key
                    paths.add(new_prefix)
                    traverse(value, new_prefix)
            elif isinstance(obj, list):
                for item in obj:
                    new_path = f"{prefix}.{item}" if prefix else item
                    paths.add(new_path)

        traverse(self._taxonomy)
        return paths

    def _build_path_index(self) -> dict[str, list[str]]:
        """Build an index for efficient path lookups."""
        index = {}
        for path in self._all_paths:
            parts = path.split(".")
            for i in range(len(parts)):
                prefix = ".".join(parts[: i + 1])
                if prefix not in index:
                    index[prefix] = []
                if path != prefix:
                    index[prefix].append(path)
        return index

    def get_all_paths(self) -> list[str]:
        """Return all valid taxonomy paths."""
        return sorted(self._all_paths)

    def get_children(self, path: str) -> list[str]:
        """Get immediate children of a path."""
        if path not in self._path_index:
            return []

        children = []
        path_depth = len(path.split("."))
        for child in self._path_index[path]:
            if len(child.split(".")) == path_depth + 1:
                children.append(child)
        return sorted(children)

    def get_descendants(self, path: str) -> list[str]:
        """Get all descendants of a path."""
        if path not in self._path_index:
            return []
        return sorted(self._path_index[path])

    def is_valid_path(self, path: str) -> bool:
        """Check if a path exists in the taxonomy."""
        return path in self._all_paths

    def get_path_depth(self, path: str) -> int:
        """Get the depth of a path in the hierarchy."""
        return len(path.split("."))

    def get_category(self, path: str) -> TaxonomyCategory:
        """Get the top-level category for a path."""
        if not path:
            return None
        root = path.split(".")[0]
        try:
            return TaxonomyCategory(root)
        except ValueError:
            return None

    def get_related_paths(self, path: str, max_distance: int = 2) -> list[str]:
        """Get paths related to the given path within a certain distance."""
        if not self.is_valid_path(path):
            return []

        related = set()
        parts = path.split(".")

        # Get siblings
        if len(parts) > 1:
            parent = ".".join(parts[:-1])
            related.update(self.get_children(parent))

        # Get ancestors up to max_distance
        for i in range(1, min(max_distance + 1, len(parts))):
            ancestor = ".".join(parts[:-i])
            related.add(ancestor)

        # Get descendants up to max_distance
        if max_distance > 0:
            descendants = self.get_descendants(path)
            for desc in descendants:
                if (
                    self.get_path_depth(desc) - self.get_path_depth(path)
                    <= max_distance
                ):
                    related.add(desc)

        related.discard(path)  # Remove the path itself
        return sorted(related)

    def get_statistics(self) -> dict:
        """Get statistics about the taxonomy."""
        category_counts = {}
        depth_counts = {}

        for path in self._all_paths:
            category = self.get_category(path)
            if category:
                cat_name = category.value
                category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

            depth = self.get_path_depth(path)
            depth_counts[depth] = depth_counts.get(depth, 0) + 1

        return {
            "total_paths": len(self._all_paths),
            "categories": len(list(TaxonomyCategory)),
            "max_depth": max(depth_counts.keys()),
            "paths_by_category": category_counts,
            "paths_by_depth": depth_counts,
        }


# Singleton instance
_taxonomy_instance = None


def get_taxonomy() -> SemanticTaxonomy:
    """Get the singleton taxonomy instance."""
    global _taxonomy_instance
    if _taxonomy_instance is None:
        _taxonomy_instance = SemanticTaxonomy()
    return _taxonomy_instance

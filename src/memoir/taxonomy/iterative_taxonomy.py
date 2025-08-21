"""
LLM-Driven Iterative Taxonomy Expansion System.
Based on "Creating a Fine Grained Entity Type Taxonomy Using LLMs" paper.
Implements iterative, focused subtree expansion with GPT-4.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from memoir.classifier.base import BaseTaxonomy

from .semantic_taxonomy import SemanticTaxonomy
from .taxonomy_presets import TaxonomyPresets, TaxonomyVersion

logger = logging.getLogger(__name__)


@dataclass
class DynamicNode:
    """Represents a node in the dynamic taxonomy tree."""

    path: str
    category: Optional[str]
    depth: int
    is_leaf: bool
    is_dynamic: bool
    created_at: datetime
    children: dict[str, "DynamicNode"] = field(default_factory=dict)
    other_items: list[dict[str, Any]] = field(default_factory=list)
    item_count: int = field(default=0)


class TaxonomyExpansionResult(BaseModel):
    """Result of a taxonomy expansion operation."""

    parent_path: str = Field(description="Path of the expanded parent node")
    new_paths: list[str] = Field(description="New taxonomy paths created")
    migrated_items: int = Field(description="Number of items migrated to new paths")
    confidence: float = Field(description="Confidence in the expansion quality")
    strategy: str = Field(description="Strategy used for expansion")
    reasoning: str = Field(description="Human-readable reasoning for expansion")
    timestamp: float = Field(description="When the expansion occurred")


# Configuration constants
MIN_ITEMS_FOR_EXPANSION = 5  # Minimum items in 'other' before LLM expansion
MAX_DEPTH = 10  # Maximum taxonomy depth
MAX_CATEGORIES_PER_EXPANSION = 10  # Max new categories per expansion
PARALLEL_EXPANSION_LIMIT = 3  # Max concurrent subtree expansions


class LLMExpansionStrategy(Enum):
    """LLM-based expansion strategies."""

    FOCUSED_SUBTREE = "focused_subtree"  # Expand one subtree at a time
    BREADTH_FIRST = "breadth_first"  # Expand all nodes at same level
    DEPTH_FIRST = "depth_first"  # Expand deepest nodes first
    PATTERN_BASED = "pattern_based"  # Use pattern combinations


@dataclass
class ExpansionContext:
    """Context for LLM-driven expansion."""

    node_path: str
    parent_hierarchy: list[str]  # Full path from root
    sibling_categories: list[str]  # Existing siblings
    unclassified_items: list[dict[str, Any]]
    current_depth: int
    taxonomy_snapshot: dict[str, Any]  # Relevant taxonomy portion


class TaxonomyCombination(BaseModel):
    """Pattern-based taxonomy combination."""

    pattern: str = Field(description="Combination pattern e.g. 'Location + Domain'")
    template: str = Field(description="Result template e.g. '{domain} in {location}'")
    examples: list[str] = Field(description="Example results")


class LLMIterativeTaxonomy(BaseTaxonomy):
    """
    LLM-driven iterative taxonomy that expands intelligently using GPT-4.
    Implements the methodology from the paper with focused subtree expansion.
    """

    def __init__(
        self,
        taxonomy_version: TaxonomyVersion = TaxonomyVersion.GENERAL,
        base_taxonomy: Optional[SemanticTaxonomy] = None,
        llm: Optional[Any] = None,
        expansion_strategy: LLMExpansionStrategy = LLMExpansionStrategy.FOCUSED_SUBTREE,
        min_items_threshold: int = MIN_ITEMS_FOR_EXPANSION,
        enable_combinations: bool = True,
        max_categories_per_expansion: int = MAX_CATEGORIES_PER_EXPANSION,
        use_full_base_taxonomy: bool = False,
    ):
        """
        Initialize LLM-driven iterative taxonomy.

        Args:
            taxonomy_version: The taxonomy preset version to use (e.g., GENERAL, AGENT_CONVERSATION)
            base_taxonomy: Optional custom taxonomy structure (overrides taxonomy_version if provided)
            llm: Language model for expansion (GPT-4 recommended)
            expansion_strategy: Strategy for taxonomy expansion
            min_items_threshold: Minimum items before triggering expansion
            enable_combinations: Enable pattern-based combinations
            max_categories_per_expansion: Maximum categories to suggest per LLM expansion (default: 10)
            use_full_base_taxonomy: If True, imports full taxonomy hierarchy; if False, only first level
        """
        self.taxonomy_version = taxonomy_version
        self.base_taxonomy = base_taxonomy
        self.use_full_base_taxonomy = use_full_base_taxonomy
        self.llm = llm
        self.expansion_strategy = expansion_strategy
        self.min_items_threshold = min_items_threshold
        self.enable_combinations = enable_combinations
        self.max_categories_per_expansion = max_categories_per_expansion

        # Build initial structure
        self.root = self._build_initial_tree()
        self.path_index: dict[str, DynamicNode] = {}
        self._rebuild_index()

        # Track expansions and combinations
        self.expansion_history: list[TaxonomyExpansionResult] = []
        self.active_expansions: set[str] = set()  # Paths being expanded
        self.combinations: list[TaxonomyCombination] = []

        # Expansion queue for parallel processing
        self.expansion_queue: asyncio.Queue = None
        self.expansion_workers: list[asyncio.Task] = []

    def _build_initial_tree(self) -> DynamicNode:
        """Build initial tree from base taxonomy."""
        root = DynamicNode(
            path="",
            category=None,
            depth=0,
            is_leaf=False,
            is_dynamic=False,
            created_at=datetime.now(),
        )

        # Use custom taxonomy if provided, otherwise use preset
        if self.base_taxonomy and self.use_full_base_taxonomy:
            # Import full base taxonomy paths (legacy behavior)
            base_paths = self.base_taxonomy.get_all_paths()
            for path in base_paths:
                self._add_path_to_tree(root, path, is_dynamic=False)
        else:
            # Use only first-level categories from the selected preset
            first_level_categories = TaxonomyPresets.get_first_level_categories(
                self.taxonomy_version
            )
            for category in first_level_categories:
                # Add first-level category as non-leaf to allow expansion
                node = self._add_path_to_tree(root, category, is_dynamic=False)
                # Force it to be non-leaf even if it has no children yet
                node.is_leaf = False

        # Add strategic 'other' categories for expansion
        self._add_strategic_other_categories(root)

        return root

    def _add_strategic_other_categories(self, node: DynamicNode, max_depth: int = 3):
        """Add 'other' categories only at strategic levels for expansion."""
        if node.depth >= max_depth:
            return

        # Add 'other' to non-leaf nodes or nodes with children
        # This includes first-level categories that were marked as non-leaf
        if (node.children or not node.is_leaf) and "other" not in node.children:
            other_path = f"{node.path}.other" if node.path else "other"
            node.children["other"] = DynamicNode(
                path=other_path,
                category=node.category,
                depth=node.depth + 1,
                is_leaf=False,
                is_dynamic=True,
                created_at=datetime.now(),
            )

        # Recursively add to non-other children
        for name, child in node.children.items():
            if name != "other":
                self._add_strategic_other_categories(child, max_depth)

    async def expand_subtree_with_llm(
        self, node_path: str, focus_depth: Optional[int] = None
    ) -> TaxonomyExpansionResult:
        """
        Expand a subtree using LLM-driven analysis.
        Implements the paper's focused subtree expansion approach.

        Args:
            node_path: Path to the node to expand
            focus_depth: Optional depth limit for expansion

        Returns:
            TaxonomyExpansionResult with expansion details
        """
        if node_path not in self.path_index:
            return TaxonomyExpansionResult(
                parent_path=node_path,
                new_paths=[],
                migrated_items=0,
                confidence=0.0,
                strategy=self.expansion_strategy.value,
                reasoning="Node not found",
                timestamp=time.time(),
            )

        node = self.path_index[node_path]

        # Check if enough items for expansion
        if len(node.other_items) < self.min_items_threshold:
            return TaxonomyExpansionResult(
                parent_path=node_path,
                new_paths=[],
                migrated_items=0,
                confidence=0.0,
                strategy=self.expansion_strategy.value,
                reasoning=f"Insufficient items ({len(node.other_items)} < {self.min_items_threshold})",
                timestamp=time.time(),
            )

        # Mark as active expansion
        self.active_expansions.add(node_path)

        try:
            # Build expansion context
            context = self._build_expansion_context(node)

            # Generate categories using LLM
            new_categories = await self._generate_categories_with_llm(context)

            # Create new nodes
            new_paths = []
            for category in new_categories:
                new_path = f"{node_path}.{category}".lstrip(".")
                if new_path not in self.path_index:
                    self._add_path_to_tree(self.root, new_path, is_dynamic=True)
                    new_paths.append(new_path)

                    # Add 'other' subcategory if at appropriate depth
                    if node.depth < MAX_DEPTH - 2:
                        other_subpath = f"{new_path}.other"
                        self._add_path_to_tree(
                            self.root, other_subpath, is_dynamic=True
                        )

            # Rebuild index
            self._rebuild_index()

            # Reclassify and migrate items
            migrated_count = await self._reclassify_items(node, new_paths)

            result = TaxonomyExpansionResult(
                parent_path=node_path,
                new_paths=new_paths,
                migrated_items=migrated_count,
                confidence=0.8,  # Default confidence for LLM expansion
                strategy=self.expansion_strategy.value,
                reasoning=f"LLM-driven expansion created {len(new_paths)} categories from {len(node.other_items)} items",
                timestamp=time.time(),
            )

            self.expansion_history.append(result)
            return result

        finally:
            self.active_expansions.discard(node_path)

    def _build_expansion_context(self, node: DynamicNode) -> ExpansionContext:
        """Build context for LLM expansion."""
        # Get parent hierarchy
        path_parts = node.path.split(".") if node.path else []

        # Get sibling categories
        parent_path = ".".join(path_parts[:-1]) if len(path_parts) > 1 else ""
        parent_node = self.path_index.get(parent_path, self.root)
        siblings = [name for name in parent_node.children if name != "other"]

        # Get relevant taxonomy snapshot (parent and siblings structure)
        taxonomy_snapshot = self._get_taxonomy_snapshot(parent_node, depth=2)

        return ExpansionContext(
            node_path=node.path,
            parent_hierarchy=path_parts,
            sibling_categories=siblings,
            unclassified_items=node.other_items[:20],  # Sample for LLM
            current_depth=node.depth,
            taxonomy_snapshot=taxonomy_snapshot,
        )

    def _get_taxonomy_snapshot(
        self, node: DynamicNode, depth: int = 2
    ) -> dict[str, Any]:
        """Get a snapshot of taxonomy structure around a node."""
        if depth <= 0 or not node.children:
            return {"path": node.path, "is_leaf": node.is_leaf}

        snapshot = {"path": node.path, "children": {}}

        for name, child in node.children.items():
            if name != "other":  # Exclude 'other' from snapshot
                snapshot["children"][name] = self._get_taxonomy_snapshot(
                    child, depth - 1
                )

        return snapshot

    async def _generate_categories_with_llm(
        self, context: ExpansionContext
    ) -> list[str]:
        """
        Generate new categories using LLM based on context.
        Implements the paper's prompting strategy.
        """
        if not self.llm:
            # Fallback to pattern analysis if no LLM
            return self._fallback_category_generation(context)

        # Build prompt following paper's approach
        prompt = self._build_expansion_prompt(context)

        try:
            # Call LLM (implementation depends on LLM interface)
            # This is a placeholder - actual implementation would use the LLM's API
            response = await self._call_llm(prompt)
            categories = self._parse_llm_response(response)

            # Validate and filter categories
            valid_categories = []
            for category in categories[:MAX_CATEGORIES_PER_EXPANSION]:
                if self._validate_category(category, context):
                    valid_categories.append(category)

            return valid_categories

        except Exception as e:
            logger.error(f"LLM expansion failed: {e}")
            return self._fallback_category_generation(context)

    def _build_expansion_prompt(self, context: ExpansionContext) -> str:
        """Build prompt for LLM expansion following paper's methodology."""
        prompt_parts = [
            "You are expanding a hierarchical taxonomy. Based on the unclassified items below, "
            "suggest new categories that would logically fit into the existing structure.",
            "",
            f"Current path: {context.node_path or 'root'}",
            f"Depth level: {context.current_depth}",
        ]

        # Add domain-specific guidance
        domain_guidance = self._get_domain_guidance(context.node_path)
        if domain_guidance:
            prompt_parts.extend(["", "Domain-specific guidance:", domain_guidance])

        prompt_parts.extend(["", "Existing sibling categories:"])

        for sibling in context.sibling_categories[:10]:
            prompt_parts.append(f"  - {sibling}")

        prompt_parts.extend(
            [
                "",
                "Sample unclassified items:",
            ]
        )

        for item in context.unclassified_items[:10]:
            content = item.get("content", "")
            content = content[:100] if isinstance(content, str) else str(content)[:100]
            prompt_parts.append(f"  - {content}")

        prompt_parts.extend(
            [
                "",
                f"Suggest up to {self.max_categories_per_expansion} new category names that would logically group these items.",
                "Categories should:",
                "1. Be semantically coherent with existing siblings AND maintain domain consistency",
                "2. Be at the appropriate level of specificity for this depth",
                "3. Not duplicate existing categories",
                "4. Follow the naming convention of siblings",
                "5. Ensure categories belong semantically to the domain/area context",
                "",
                "IMPORTANT: Only suggest categories that truly belong in this domain/area.",
                "If items seem to belong elsewhere, suggest 'needs_reclassification' instead.",
                "",
                "Return only the category names, one per line.",
            ]
        )

        return "\n".join(prompt_parts)

    def _get_domain_guidance(self, node_path: str) -> str:
        """Get dynamic domain-specific guidance for expansion based on existing taxonomy structure."""
        if not node_path:
            return ""

        path_parts = node_path.split(".")
        if len(path_parts) < 1:
            return ""

        domain = path_parts[0]
        area = path_parts[1] if len(path_parts) > 1 else None

        # Dynamically analyze existing taxonomy structure for this domain
        domain_analysis = self._analyze_domain_patterns(domain, area)

        guidance_parts = [f"This expansion is in the {domain}"]
        if area:
            guidance_parts[0] += f".{area}"
        guidance_parts[0] += " domain."

        # Add context from existing sibling areas
        if domain_analysis["sibling_areas"]:
            guidance_parts.append(
                f"Related areas in {domain}: {', '.join(domain_analysis['sibling_areas'][:5])}."
            )

        # Add semantic consistency guidance based on actual taxonomy diversity
        if domain_analysis["concept_diversity"] > 0.5:
            guidance_parts.append(
                "Maintain semantic consistency - avoid mixing unrelated concepts from other domains."
            )

        # Add depth-appropriate guidance
        current_depth = len(path_parts)
        if current_depth <= 2:
            guidance_parts.append(
                "Focus on creating intermediate categories that logically group related concepts."
            )
        else:
            guidance_parts.append(
                "Create specific categories that maintain the hierarchical progression."
            )

        return " ".join(guidance_parts)

    def suggest_intermediate_levels(self, path: str, content: str) -> dict:
        """
        Dynamically suggest intermediate levels based on existing taxonomy structure and content analysis.

        Args:
            path: Current taxonomy path
            content: Content being classified

        Returns:
            Dict with intermediate level suggestions
        """
        path_parts = path.split(".")
        suggestions = []
        reasoning = ""

        # Only suggest intermediates for shallow paths (depth 1-2)
        if len(path_parts) <= 2:
            # Analyze existing taxonomy to find common intermediate patterns
            intermediate_analysis = self._analyze_intermediate_patterns(path, content)

            suggestions = intermediate_analysis["suggestions"]
            reasoning = intermediate_analysis["reasoning"]

        return {
            "suggestions": suggestions,
            "reasoning": reasoning,
        }

    def _analyze_domain_patterns(self, domain: str, area: Optional[str] = None) -> dict:
        """
        Dynamically analyze existing taxonomy patterns for a domain/area.

        Args:
            domain: The domain to analyze
            area: Optional specific area within the domain

        Returns:
            Dict with domain pattern analysis
        """
        all_paths = self.get_all_paths()

        # Find all paths in this domain
        domain_paths = [p for p in all_paths if p.startswith(f"{domain}.")]

        # Extract areas (second level categories)
        areas = set()
        for path in domain_paths:
            parts = path.split(".")
            if len(parts) >= 2:
                areas.add(parts[1])

        # Calculate concept diversity (how varied the domain is)
        concept_diversity = (
            len(areas) / max(len(domain_paths), 1) if domain_paths else 0
        )

        # Find sibling areas if we're analyzing a specific area
        sibling_areas = list(areas)
        if area and area in sibling_areas:
            sibling_areas.remove(area)

        return {
            "sibling_areas": sibling_areas,
            "concept_diversity": concept_diversity,
            "total_paths": len(domain_paths),
            "depth_distribution": self._get_depth_distribution(domain_paths),
        }

    def _analyze_intermediate_patterns(self, path: str, content: str) -> dict:
        """
        Analyze existing taxonomy structure to suggest intermediate levels dynamically.

        Args:
            path: Current path (domain or domain.area)
            content: Content being classified

        Returns:
            Dict with suggested intermediate patterns
        """
        path_parts = path.split(".")
        suggestions = []
        reasoning = ""

        if len(path_parts) == 1:
            # Domain level - suggest areas based on existing taxonomy
            domain = path_parts[0]
            domain_analysis = self._analyze_domain_patterns(domain)

            # Suggest existing areas that might match content
            content_words = set(content.lower().split())
            for area in domain_analysis["sibling_areas"]:
                area_words = set(area.replace("_", " ").split())
                if content_words.intersection(area_words):
                    suggestions.append(f"{path}.{area}")

            if suggestions:
                reasoning = f"Suggested existing areas in {domain} domain that match content keywords"

        elif len(path_parts) == 2:
            # Area level - suggest intermediate categories based on similar paths
            domain, area = path_parts

            # Find existing paths that go deeper than current path
            all_paths = self.get_all_paths()
            deeper_paths = [
                p
                for p in all_paths
                if p.startswith(f"{path}.") and len(p.split(".")) == 3
            ]

            if deeper_paths:
                # Extract third-level categories
                third_levels = [p.split(".")[2] for p in deeper_paths]

                # Check which ones might match the content
                content_lower = content.lower()
                for third_level in set(third_levels):
                    if third_level.lower() in content_lower or any(
                        word in content_lower
                        for word in third_level.replace("_", " ").split()
                    ):
                        suggestions.append(f"{path}.{third_level}")

                if suggestions:
                    reasoning = (
                        f"Suggested existing subcategories in {area} that match content"
                    )
            else:
                # No existing deeper paths, suggest based on common patterns
                suggestions = self._suggest_common_intermediates(path, content)
                if suggestions:
                    reasoning = (
                        "Suggested common intermediate patterns for better specificity"
                    )

        return {
            "suggestions": suggestions,
            "reasoning": reasoning,
        }

    def _suggest_common_intermediates(self, path: str, content: str) -> list[str]:
        """
        Suggest intermediate patterns based purely on learned patterns from existing taxonomy.
        No hard-coded assumptions - only learns from actual taxonomy structure.
        """
        suggestions = []
        content_lower = content.lower()
        content_words = set(content_lower.split())

        # Find similar paths in the taxonomy to learn patterns from
        all_paths = self.get_all_paths()
        path_parts = path.split(".")

        if len(path_parts) >= 2:
            _, area = path_parts[0], path_parts[1]

            # Look for similar area patterns in any domain
            similar_patterns = []
            for existing_path in all_paths:
                existing_parts = existing_path.split(".")
                if len(existing_parts) >= 3:
                    existing_domain, existing_area, existing_sub = existing_parts[:3]

                    # Find areas with similar naming patterns or content overlap
                    area_words = set(area.replace("_", " ").split())
                    existing_area_words = set(existing_area.replace("_", " ").split())

                    # Check for word overlap or semantic similarity
                    word_overlap = area_words.intersection(existing_area_words)
                    content_overlap = content_words.intersection(
                        set(existing_sub.replace("_", " ").split())
                    )

                    if word_overlap or content_overlap:
                        similar_patterns.append(existing_sub)

            # Extract the most relevant patterns based on content matching
            pattern_scores = {}
            for pattern in set(similar_patterns):
                pattern_words = set(pattern.replace("_", " ").split())
                overlap = content_words.intersection(pattern_words)
                if overlap:
                    pattern_scores[pattern] = len(overlap)

            # Suggest top scoring patterns
            if pattern_scores:
                sorted_patterns = sorted(
                    pattern_scores.items(), key=lambda x: x[1], reverse=True
                )
                for pattern, _score in sorted_patterns[:3]:  # Top 3 suggestions
                    suggestions.append(f"{path}.{pattern}")

        return suggestions

    def _get_depth_distribution(self, paths: list[str]) -> dict:
        """Get the distribution of path depths."""
        depth_counts = {}
        for path in paths:
            depth = len(path.split("."))
            depth_counts[depth] = depth_counts.get(depth, 0) + 1
        return depth_counts

    def _validate_with_learned_patterns(
        self, domain: str, area: str, content_lower: str
    ) -> dict:
        """
        Validate domain/area using purely learned patterns from existing taxonomy structure.
        No hard-coded rules - everything is learned from actual usage patterns.

        Args:
            domain: Domain to validate
            area: Area within domain to validate
            content_lower: Lowercase content to check

        Returns:
            Dict with validation info and keywords to use
        """
        # Only use learned patterns from existing taxonomy - no hard-coded rules
        learned_keywords = self._extract_keywords_from_taxonomy(domain, area)

        return {
            "has_rules": len(learned_keywords) > 0,
            "keywords": learned_keywords,
        }

    def _extract_keywords_from_taxonomy(self, domain: str, area: str) -> list[str]:
        """
        Extract keywords from existing taxonomy paths and content for this domain.area.

        This allows the system to learn validation patterns from actual usage.
        """
        keywords = []
        all_paths = self.get_all_paths()

        # Find paths in this domain.area
        area_paths = [p for p in all_paths if p.startswith(f"{domain}.{area}.")]

        # Extract keywords from path components
        for path in area_paths:
            parts = path.split(".")[2:]  # Skip domain.area
            for part in parts:
                # Convert underscore/camelCase to words
                words = part.replace("_", " ").lower().split()
                keywords.extend(words)

        # Could also extract from stored content in 'other' nodes (future enhancement)

        return list(set(keywords))

    def _validate_with_structure_analysis(self, path: str, content: str) -> dict:
        """
        Validate using structural analysis when no specific rules exist.

        This is the fallback for completely new domains/areas.
        """
        path_parts = path.split(".")
        domain = path_parts[0]

        # Check if content seems related to any existing paths in this domain
        all_paths = self.get_all_paths()
        domain_paths = [p for p in all_paths if p.startswith(f"{domain}.")]

        if not domain_paths:
            # Brand new domain - assume valid
            return {"valid": True, "confidence": 0.5, "issues": [], "suggestions": []}

        # Analyze similarity to existing paths
        content_words = set(content.lower().split())

        # Find most similar existing paths
        similarities = []
        for existing_path in domain_paths:
            path_words = set()
            for part in existing_path.split("."):
                path_words.update(part.replace("_", " ").split())

            intersection = content_words.intersection(path_words)
            if intersection:
                similarity = len(intersection) / len(content_words.union(path_words))
                similarities.append((existing_path, similarity))

        if similarities:
            similarities.sort(key=lambda x: x[1], reverse=True)
            best_match = similarities[0]

            if best_match[1] > 0.3:  # Good similarity
                return {
                    "valid": True,
                    "confidence": 0.8,
                    "issues": [],
                    "suggestions": [],
                }
            else:
                # Suggest the best matching path
                return {
                    "valid": False,
                    "confidence": 0.4,
                    "issues": [
                        f"Content doesn't seem to match {path} based on structural analysis"
                    ],
                    "suggestions": [best_match[0]],
                }

        # No similar paths found - might be misclassified
        return {
            "valid": False,
            "confidence": 0.2,
            "issues": [f"Content doesn't seem to match existing patterns in {domain}"],
            "suggestions": [],
        }

    def analyze_path_quality(self, path: str, content: str) -> dict:
        """
        Comprehensive analysis of classification path quality.

        Args:
            path: Taxonomy path to analyze
            content: Content being classified

        Returns:
            Dict with comprehensive quality analysis
        """
        analysis = {
            "overall_score": 0.0,
            "domain_consistency": {},
            "intermediate_suggestions": {},
            "depth_analysis": {},
            "recommendations": [],
        }

        # 1. Domain consistency analysis
        domain_validation = self.validate_domain_consistency(path, content)
        analysis["domain_consistency"] = domain_validation

        # 2. Intermediate level suggestions
        intermediate_analysis = self.suggest_intermediate_levels(path, content)
        analysis["intermediate_suggestions"] = intermediate_analysis

        # 3. Depth analysis
        path_parts = path.split(".")
        depth = len(path_parts)

        analysis["depth_analysis"] = {
            "current_depth": depth,
            "optimal_range": "2-4 levels",
            "is_optimal": 2 <= depth <= 4,
            "issues": [],
        }

        if depth == 1:
            analysis["depth_analysis"]["issues"].append(
                "Too broad - needs more specificity"
            )
        elif depth > 4:
            analysis["depth_analysis"]["issues"].append(
                "Too deep - may be overly specific"
            )

        # 4. Calculate overall score
        score = 0.0

        # Domain consistency (40% weight)
        if domain_validation["valid"]:
            score += 0.4 * domain_validation["confidence"]

        # Depth appropriateness (30% weight)
        if 2 <= depth <= 4:
            score += 0.3
        elif depth == 1:
            score += 0.1  # Very broad
        elif depth > 4:
            score += 0.2  # Too specific

        # Path completeness (30% weight)
        if intermediate_analysis["suggestions"]:
            score += 0.1  # Some issues but fixable
        else:
            score += 0.3  # No obvious missing levels

        analysis["overall_score"] = min(1.0, score)

        # 5. Generate recommendations
        recommendations = []

        if not domain_validation["valid"]:
            recommendations.append(
                f"Domain mismatch detected. Consider: {', '.join(domain_validation['suggestions'][:2])}"
            )

        if intermediate_analysis["suggestions"]:
            recommendations.append(
                f"Add intermediate level: {intermediate_analysis['suggestions'][0]}"
            )

        if depth == 1:
            recommendations.append(
                "Classification too broad - add more specific categories"
            )
        elif depth > 4:
            recommendations.append(
                "Classification too specific - consider using parent category"
            )

        analysis["recommendations"] = recommendations

        return analysis

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the prompt."""
        if self.llm is None:
            # Fallback when no LLM is provided
            return "category1\ncategory2\ncategory3"

        try:
            # Use the provided LLM (works with LangChain LLMs)
            response = await self.llm.ainvoke(prompt)

            # Handle different response types
            if hasattr(response, "content"):
                content = response.content
                print(f"\n🤖 GPT Response: {content}")
                return content
            elif isinstance(response, str):
                print(f"LLM String Response: {response}")
                return response
            else:
                str_response = str(response)
                print(f"LLM String Conversion: {str_response}")
                return str_response
        except Exception as e:
            # Log the error and fall back to default categories
            print(f"LLM call failed: {e}")
            return "category1\ncategory2\ncategory3"

    def _parse_llm_response(self, response: str) -> list[str]:
        """Parse LLM response to extract category names."""
        categories = []
        for line in response.strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):  # Skip comments
                # Clean up the category name - handle numbered lists, bullets, etc.
                category = line

                # Remove numbered list prefixes (1., 2., etc.)
                import re

                category = re.sub(r"^\d+\.\s*", "", category)

                # Remove bullet prefixes (-, *, etc.)
                category = category.strip("- ").strip("* ").strip()

                if category:
                    categories.append(category)

        print(f"📋 Parsed categories: {categories}")
        return categories

    def _validate_category(self, category: str, context: ExpansionContext) -> bool:
        """Validate a proposed category name."""
        # Check for duplicates
        if category in context.sibling_categories:
            return False

        # Check for invalid characters
        if not category or "/" in category or "." in category:
            return False

        # Check length
        return not len(category) > 50

    def _fallback_category_generation(self, context: ExpansionContext) -> list[str]:
        """Fallback category generation without LLM."""
        # Analyze patterns in unclassified items
        categories = set()

        for item in context.unclassified_items:
            if "original_classification" in item:
                orig_path = item["original_classification"]
                parts = orig_path.split(".")

                # Extract the next level that was attempted
                if len(parts) > context.current_depth:
                    next_level = parts[context.current_depth]
                    categories.add(next_level)

        return list(categories)[:MAX_CATEGORIES_PER_EXPANSION]

    async def _reclassify_items(self, node: DynamicNode, new_paths: list[str]) -> int:
        """Reclassify items from 'other' to new categories using LLM if available."""
        if not node.other_items or not new_paths:
            return 0

        migrated_count = 0
        remaining_items = []

        for item in node.other_items:
            best_path = await self._find_best_category(item, new_paths)

            if best_path:
                # Migrate to new category
                target_node = self.path_index[best_path]
                target_node.item_count += 1
                migrated_count += 1
            else:
                remaining_items.append(item)

        node.other_items = remaining_items
        return migrated_count

    async def _find_best_category(
        self, item: dict[str, Any], candidate_paths: list[str]
    ) -> Optional[str]:
        """Find the best category for an item among candidates using LLM-based classification."""
        if not candidate_paths:
            return None

        content = item.get("content", "")
        if not content:
            return None

        # Use LLM for intelligent classification
        if self.llm:
            try:
                prompt = self._build_classification_prompt(content, candidate_paths)
                response = await self._call_llm(prompt)
                return self._parse_best_category_response(response, candidate_paths)
            except Exception as e:
                print(f"LLM classification failed for item: {e}")
                # Fall back to simple heuristic

        # Simple fallback: find best category using basic string matching
        return self._find_category_by_text_similarity(content, candidate_paths)

    def _build_classification_prompt(
        self, content: str, candidate_paths: list[str]
    ) -> str:
        """Build a prompt for LLM to classify content into best category."""
        # Extract just the category names for cleaner prompt
        categories = [path.split(".")[-1] for path in candidate_paths]

        prompt_parts = [
            "You are classifying content into the most appropriate category.",
            "",
            f"Content to classify: {content}",
            "",
            "Available categories:",
        ]

        for i, category in enumerate(categories, 1):
            prompt_parts.append(f"{i}. {category}")

        prompt_parts.extend(
            [
                "",
                "Return ONLY the number (1, 2, 3, etc.) of the best matching category.",
                "If no category is a good match, return 0.",
                "Consider semantic meaning, not just exact keyword matches.",
            ]
        )

        return "\n".join(prompt_parts)

    def _parse_best_category_response(
        self, response: str, candidate_paths: list[str]
    ) -> Optional[str]:
        """Parse LLM response to get the best category path."""
        try:
            # Extract number from response
            import re

            numbers = re.findall(r"\d+", response.strip())
            if not numbers:
                return None

            choice = int(numbers[0])

            # Return None if LLM said no good match (0)
            if choice == 0:
                return None

            # Return the corresponding path (1-indexed)
            if 1 <= choice <= len(candidate_paths):
                chosen_path = candidate_paths[choice - 1]
                print(
                    f"🎯 LLM chose category: {chosen_path.split('.')[-1]} for content: {response.strip()}"
                )
                return chosen_path

        except Exception as e:
            print(f"Failed to parse LLM category response '{response}': {e}")

        return None

    def _find_category_by_text_similarity(
        self, content: str, candidate_paths: list[str]
    ) -> Optional[str]:
        """Fallback method using simple text similarity when LLM is unavailable."""
        content_lower = content.lower()

        # Try exact category name matches first
        for path in candidate_paths:
            category = path.split(".")[-1].lower()
            if category in content_lower:
                return path

        # Try partial matches with category name parts
        for path in candidate_paths:
            category = path.split(".")[-1].lower()
            category_parts = category.replace("-", "_").split("_")

            # Look for category parts in content (minimum 4 chars to avoid false matches)
            if any(part in content_lower for part in category_parts if len(part) >= 4):
                return path

        # No good match found
        return None

    async def parallel_expand(
        self, target_paths: Optional[list[str]] = None
    ) -> list[TaxonomyExpansionResult]:
        """
        Perform parallel expansion of multiple subtrees.
        Implements the paper's approach of concurrent work on different branches.

        Args:
            target_paths: Specific paths to expand, or None for automatic selection

        Returns:
            List of expansion results
        """
        if not target_paths:
            target_paths = self._select_expansion_targets()

        # Limit parallel expansions
        target_paths = target_paths[:PARALLEL_EXPANSION_LIMIT]

        # Create expansion tasks
        tasks = []
        for path in target_paths:
            if path not in self.active_expansions:
                task = asyncio.create_task(self.expand_subtree_with_llm(path))
                tasks.append(task)

        # Wait for all expansions
        results = await asyncio.gather(*tasks)

        return results

    def _select_expansion_targets(self) -> list[str]:
        """Select nodes for expansion based on strategy."""
        targets = []

        if self.expansion_strategy == LLMExpansionStrategy.FOCUSED_SUBTREE:
            # Find nodes with most items in 'other'
            candidates = [
                (path, node)
                for path, node in self.path_index.items()
                if path.endswith(".other")
                and len(node.other_items) >= self.min_items_threshold
            ]
            candidates.sort(key=lambda x: len(x[1].other_items), reverse=True)
            targets = [path for path, _ in candidates]

        elif self.expansion_strategy == LLMExpansionStrategy.BREADTH_FIRST:
            # Expand all nodes at the shallowest depth with items
            min_depth = float("inf")
            for path, node in self.path_index.items():
                if (
                    path.endswith(".other")
                    and len(node.other_items) >= self.min_items_threshold
                ):
                    min_depth = min(min_depth, node.depth)

            targets = [
                path
                for path, node in self.path_index.items()
                if path.endswith(".other")
                and node.depth == min_depth
                and len(node.other_items) >= self.min_items_threshold
            ]

        elif self.expansion_strategy == LLMExpansionStrategy.DEPTH_FIRST:
            # Expand deepest nodes first
            candidates = [
                (path, node)
                for path, node in self.path_index.items()
                if path.endswith(".other")
                and len(node.other_items) >= self.min_items_threshold
            ]
            candidates.sort(key=lambda x: x[1].depth, reverse=True)
            targets = [path for path, _ in candidates]

        return targets

    def apply_combinations(self, combination: TaxonomyCombination) -> list[str]:
        """
        Apply pattern-based combinations to reduce redundancy.
        Implements the paper's combination approach.

        Args:
            combination: Pattern combination to apply

        Returns:
            List of newly created combination paths
        """
        if not self.enable_combinations:
            return []

        new_paths = []

        # Parse combination pattern (e.g., "Location + Domain")
        parts = combination.pattern.split(" + ")
        if len(parts) != 2:
            return []

        category1, category2 = parts[0].strip(), parts[1].strip()

        # Find matching paths
        paths1 = [p for p in self.path_index if category1.lower() in p.lower()]
        paths2 = [p for p in self.path_index if category2.lower() in p.lower()]

        # Create combinations
        for path1 in paths1[:10]:  # Limit combinations
            for path2 in paths2[:10]:
                # Extract relevant parts
                loc_part = path1.split(".")[-1]
                dom_part = path2.split(".")[-1]

                # Apply template
                combined = combination.template.format(
                    location=loc_part, domain=dom_part
                )

                # Create new path
                new_path = f"combined.{combined.replace(' ', '_').lower()}"
                if new_path not in self.path_index:
                    self._add_path_to_tree(self.root, new_path, is_dynamic=True)
                    new_paths.append(new_path)

        # Rebuild index
        self._rebuild_index()

        # Track combination
        self.combinations.append(combination)

        return new_paths

    def _add_path_to_tree(
        self, root: DynamicNode, path: str, is_dynamic: bool = False
    ) -> DynamicNode:
        """Add a path to the tree structure."""
        parts = path.split(".")
        current = root

        for i, part in enumerate(parts):
            current_path = ".".join(parts[: i + 1])

            if part not in current.children:
                current.children[part] = DynamicNode(
                    path=current_path,
                    category=None,
                    depth=i + 1,
                    is_leaf=(i == len(parts) - 1),
                    is_dynamic=is_dynamic,
                    created_at=datetime.now(),
                )

            current = current.children[part]

        return current

    def _rebuild_index(self):
        """Rebuild the path index."""
        self.path_index = {}

        def traverse(node: DynamicNode):
            if node.path:
                self.path_index[node.path] = node
            for child in node.children.values():
                traverse(child)

        traverse(self.root)

    def is_valid_path(self, path: str) -> bool:
        """Check if a path exists in the taxonomy."""
        return path in self.path_index

    def get_all_paths(self) -> list[str]:
        """Get all available paths in the taxonomy."""
        return list(self.path_index.keys())

    def export_for_llm(self) -> str:
        """
        Export taxonomy in a format suitable for LLM context.
        Follows the paper's approach for maintaining taxonomy in GPT-4 context.
        """

        def node_to_dict(node: DynamicNode, max_depth: int = 5) -> dict[str, Any]:
            if node.depth >= max_depth or not node.children:
                return {"path": node.path, "item_count": node.item_count}

            return {
                "path": node.path,
                "children": {
                    name: node_to_dict(child, max_depth)
                    for name, child in node.children.items()
                    if not name.endswith("other")  # Exclude 'other' for clarity
                },
            }

        taxonomy_dict = node_to_dict(self.root)
        return json.dumps(taxonomy_dict, indent=2)

    def validate_domain_consistency(self, path: str, content: str) -> dict:
        """
        Validate if content semantically belongs in the domain/area of the given path.

        Args:
            path: The taxonomy path to validate
            content: The content being classified

        Returns:
            Dict with validation results and suggestions
        """
        path_parts = path.split(".")
        if len(path_parts) < 2:
            return {"valid": True, "confidence": 1.0, "issues": [], "suggestions": []}

        domain = path_parts[0]
        area = path_parts[1]
        content_lower = content.lower()

        # Use dynamic validation combining core rules with learned patterns
        validation_result = self._validate_with_learned_patterns(
            domain, area, content_lower
        )

        if validation_result["has_rules"]:
            area_keywords = validation_result["keywords"]
        else:
            # No specific rules - use taxonomy structure analysis
            return self._validate_with_structure_analysis(path, content)

        # Check if content contains keywords relevant to this area
        content_matches_area = any(
            keyword in content_lower for keyword in area_keywords
        )

        if content_matches_area:
            return {"valid": True, "confidence": 0.9, "issues": [], "suggestions": []}

        # Content doesn't match - find better alternatives using dynamic analysis
        suggestions = []

        # Check other areas in same domain
        domain_analysis = self._analyze_domain_patterns(domain)
        for other_area in domain_analysis["sibling_areas"]:
            if other_area != area:
                other_validation = self._validate_with_learned_patterns(
                    domain, other_area, content_lower
                )
                if other_validation["has_rules"]:
                    other_keywords = other_validation["keywords"]
                    if any(keyword in content_lower for keyword in other_keywords):
                        suggestions.append(f"{domain}.{other_area}")

        # Check if content might belong to different domain entirely
        all_paths = self.get_all_paths()
        domains = list({p.split(".")[0] for p in all_paths if "." in p})

        for other_domain in domains:
            if other_domain != domain:
                other_domain_analysis = self._analyze_domain_patterns(other_domain)
                for other_area in other_domain_analysis["sibling_areas"]:
                    other_validation = self._validate_with_learned_patterns(
                        other_domain, other_area, content_lower
                    )
                    if other_validation["has_rules"]:
                        other_keywords = other_validation["keywords"]
                        if any(keyword in content_lower for keyword in other_keywords):
                            suggestions.append(f"{other_domain}.{other_area}")
                            break  # Only suggest one from each domain

        issues = [
            f"Content doesn't seem to match {domain}.{area} based on semantic analysis"
        ]

        return {
            "valid": False,
            "confidence": 0.3,
            "issues": issues,
            "suggestions": suggestions[:3],  # Limit to top 3 suggestions
        }

    def track_classification(
        self, path: str, content: str, metadata: Optional[dict] = None
    ) -> bool:
        """
        Track a classification result and trigger expansion if needed.

        This method should be called by the semantic_classifier whenever
        content is classified to help the iterative taxonomy learn and expand.

        Args:
            path: The classified path
            content: The content that was classified
            metadata: Optional metadata about the classification

        Returns:
            True if expansion was triggered, False otherwise
        """
        import time

        # Validate domain consistency first
        validation = self.validate_domain_consistency(path, content)
        if not validation["valid"] and validation["suggestions"]:
            logger.warning(
                f"Domain consistency issue for path '{path}': {validation['issues'][0]}. "
                f"Suggested alternatives: {', '.join(validation['suggestions'])}"
            )
            # Add to metadata for tracking
            if metadata is None:
                metadata = {}
            metadata["domain_validation"] = validation

        # Find the node for this path
        node = self.path_index.get(path)
        if not node:
            return False

        # If this is an 'other' path, track the item for future expansion
        if path.endswith(".other"):
            if not hasattr(node, "other_items"):
                node.other_items = []

            # Add item with metadata
            item_data = {
                "content": content,
                "timestamp": time.time(),
                "metadata": metadata or {},
            }
            node.other_items.append(item_data)

            # Check if we should trigger expansion
            if len(node.other_items) >= self.min_items_threshold:
                # Mark for expansion
                if path not in self.active_expansions:
                    logger.info(
                        f"Path {path} ready for expansion with {len(node.other_items)} items"
                    )
                return True

        return False

    def get_classification_hints(self, content: str) -> dict[str, Any]:
        """
        Get hints for better classification based on similar content in 'other' paths.

        This helps the semantic_classifier make better decisions by learning
        from previously unclassified content.

        Args:
            content: Content to get hints for

        Returns:
            Dictionary with classification hints
        """
        hints = {
            "suggested_paths": [],
            "avoid_paths": [],
            "similar_content": [],
            "expansion_candidates": [],
        }

        content_lower = content.lower()

        # Look through 'other' paths for similar content
        for path, node in self.path_index.items():
            if path.endswith(".other") and hasattr(node, "other_items"):
                for item in node.other_items:
                    item_content = item.get("content", "").lower()

                    # Simple similarity check
                    common_words = set(content_lower.split()) & set(
                        item_content.split()
                    )
                    if len(common_words) >= 2:  # At least 2 common words
                        hints["similar_content"].append(
                            {
                                "path": path,
                                "content": item.get("content"),
                                "similarity": len(common_words),
                            }
                        )

                        # Suggest the parent path instead of 'other'
                        parent_path = ".".join(path.split(".")[:-1])
                        if parent_path and parent_path not in hints["suggested_paths"]:
                            hints["suggested_paths"].append(parent_path)

                # Mark paths with many items as expansion candidates
                if len(node.other_items) >= self.min_items_threshold - 1:
                    hints["expansion_candidates"].append(
                        {"path": path, "item_count": len(node.other_items)}
                    )

        return hints

    def get_taxonomy_info(self) -> dict[str, Any]:
        """Get information about the current taxonomy configuration."""
        return {
            "version": self.taxonomy_version.value,
            "first_level_categories": TaxonomyPresets.get_first_level_categories(
                self.taxonomy_version
            ),
            "use_full_base": self.use_full_base_taxonomy,
            "expansion_strategy": self.expansion_strategy.value,
            "min_items_threshold": self.min_items_threshold,
            "max_categories_per_expansion": self.max_categories_per_expansion,
        }

    def get_expansion_statistics(self) -> dict[str, Any]:
        """Get detailed statistics about expansions."""
        stats = {
            "taxonomy_version": self.taxonomy_version.value,
            "total_paths": len(self.path_index),
            "dynamic_paths": sum(1 for n in self.path_index.values() if n.is_dynamic),
            "expansion_history": len(self.expansion_history),
            "active_expansions": len(self.active_expansions),
            "total_migrated": sum(r.migrated_items for r in self.expansion_history),
            "combinations_applied": len(self.combinations),
            "depth_distribution": defaultdict(int),
            "items_in_other": 0,
        }

        for node in self.path_index.values():
            stats["depth_distribution"][node.depth] += 1
            if node.path.endswith(".other") and hasattr(node, "other_items"):
                stats["items_in_other"] += len(node.other_items)

        return stats

    async def classify_with_confidence(
        self,
        content: str,
        metadata: Optional[dict] = None,
        confidence_threshold: float = 0.6,
    ) -> dict[str, Any]:
        """
        Classify content and return classification with confidence and expansion recommendations.

        Args:
            content: Content to classify
            metadata: Optional metadata
            confidence_threshold: Minimum confidence for accepting classification

        Returns:
            Dictionary with classification results and recommendations
        """
        if not self.llm:
            # Fallback to basic pattern matching
            return {
                "is_memory": True,
                "path": "context.general",
                "confidence": 0.5,
                "reasoning": "Basic fallback classification",
                "needs_expansion": False,
                "suggested_action": "classify",
            }

        # Get current taxonomy structure for LLM context
        structure = self._get_taxonomy_structure_for_llm()

        # Build classification prompt
        prompt = self._build_classification_prompt_with_structure(
            content, structure, metadata
        )

        try:
            response = await self.llm.ainvoke(prompt)
            result = self._parse_classification_with_confidence(response)

            # Check if expansion is needed
            if result["confidence"] < confidence_threshold and result["is_memory"]:
                result["needs_expansion"] = True
                result["suggested_action"] = "expand"

                # Get expansion suggestions
                expansion_suggestion = await self._suggest_expansion_for_low_confidence(
                    content, result["path"], metadata
                )
                result.update(expansion_suggestion)
            else:
                result["needs_expansion"] = False
                result["suggested_action"] = (
                    "classify" if result["is_memory"] else "skip"
                )

            return result

        except Exception as e:
            logger.error(f"Classification with confidence failed: {e}")
            return {
                "is_memory": False,
                "path": None,
                "confidence": 0.0,
                "reasoning": f"Classification failed: {e!s}",
                "needs_expansion": False,
                "suggested_action": "skip",
            }

    def _get_taxonomy_structure_for_llm(self) -> dict:
        """Get taxonomy structure optimized for LLM context."""
        # Get hierarchical structure
        structure = {}
        for path in self.get_all_paths():
            if path.endswith(".other"):
                continue  # Skip 'other' paths in structure

            parts = path.split(".")
            current = structure

            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {} if i < len(parts) - 1 else None
                current = current[part] if current[part] is not None else {}

        return {
            "version": self.taxonomy_version.value,
            "structure": structure,
            "sample_paths": [
                p for p in self.get_all_paths() if not p.endswith(".other")
            ][:20],
            "total_categories": len(
                [p for p in self.get_all_paths() if not p.endswith(".other")]
            ),
        }

    def _build_classification_prompt_with_structure(
        self, content: str, structure: dict, metadata: Optional[dict]
    ) -> str:
        """Build classification prompt with full taxonomy structure."""
        prompt_parts = [
            "You are an intelligent memory classifier. Analyze the following content and determine:",
            "1. Is this information worth storing as a memory? (true/false)",
            "2. If yes, which taxonomy path best fits this content?",
            "3. What is your confidence in this classification (0.0 to 1.0)?",
            "",
            f"Content to analyze: {content}",
        ]

        if metadata:
            prompt_parts.append(f"Metadata: {json.dumps(metadata)}")

        prompt_parts.extend(
            [
                "",
                f"Current taxonomy version: {structure['version']}",
                f"Total available categories: {structure['total_categories']}",
                "",
                "Sample available paths:",
            ]
        )

        for path in structure["sample_paths"][:15]:
            prompt_parts.append(f"  - {path}")

        if len(structure["sample_paths"]) > 15:
            prompt_parts.append(f"  ... and {len(structure['sample_paths']) - 15} more")

        prompt_parts.extend(
            [
                "",
                "Guidelines:",
                "- Only classify as memory if the content has lasting value",
                "- Choose the most specific appropriate path",
                "- If unsure between paths, prefer higher-level categories",
                "- Confidence should reflect how well the content fits the chosen path",
                "",
                "Respond in JSON format:",
                "{",
                '  "is_memory": true/false,',
                '  "path": "best.matching.path" or null,',
                '  "confidence": 0.0-1.0,',
                '  "reasoning": "explanation of decision"',
                "}",
            ]
        )

        return "\n".join(prompt_parts)

    def _parse_classification_with_confidence(self, response: Any) -> dict:
        """Parse LLM classification response with confidence."""
        try:
            if hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            # Extract JSON from response
            import re

            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "is_memory": data.get("is_memory", False),
                    "path": data.get("path"),
                    "confidence": float(data.get("confidence", 0.0)),
                    "reasoning": data.get("reasoning", ""),
                }

        except Exception as e:
            logger.error(f"Failed to parse classification response: {e}")

        return {
            "is_memory": False,
            "path": None,
            "confidence": 0.0,
            "reasoning": "Failed to parse classification response",
        }

    async def _suggest_expansion_for_low_confidence(
        self, content: str, path: str, metadata: Optional[dict]
    ) -> dict:
        """Suggest expansion options for low confidence classification."""
        if not path:
            return {"expansion_suggestions": [], "use_parent": False}

        prompt_parts = [
            f"Content '{content}' was classified to '{path}' with low confidence.",
            "",
            "Should we:",
            "1. Expand the taxonomy with more specific subcategories",
            "2. Use a more general parent category",
            "3. Create new categories at the same level",
            "",
            "Consider the content specificity and taxonomy depth.",
            "",
            "Respond in JSON:",
            "{",
            '  "action": "expand" | "use_parent" | "same_level",',
            '  "reasoning": "explanation",',
            '  "suggested_categories": ["category1", "category2"] (if expanding),',
            '  "parent_path": "parent.path" (if using parent)',
            "}",
        ]

        try:
            response = await self.llm.ainvoke("\n".join(prompt_parts))

            if hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            import re

            json_match = re.search(r"\{[^{}]*\}", content, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return {
                    "expansion_action": data.get("action", "expand"),
                    "expansion_reasoning": data.get("reasoning", ""),
                    "suggested_categories": data.get("suggested_categories", []),
                    "parent_path": data.get("parent_path"),
                }

        except Exception as e:
            logger.error(f"Expansion suggestion failed: {e}")

        return {
            "expansion_action": "expand",
            "expansion_reasoning": "Default expansion due to low confidence",
            "suggested_categories": [],
            "parent_path": None,
        }

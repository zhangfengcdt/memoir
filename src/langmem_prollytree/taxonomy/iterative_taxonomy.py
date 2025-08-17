"""
LLM-Driven Iterative Taxonomy Expansion System.
Based on "Creating a Fine Grained Entity Type Taxonomy Using LLMs" paper.
Implements iterative, focused subtree expansion with GPT-4.
"""

import asyncio
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import BaseTaxonomy
from .dynamic_taxonomy import DynamicNode, TaxonomyExpansionResult
from .semantic_taxonomy import SemanticTaxonomy, get_taxonomy

logger = logging.getLogger(__name__)

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
        base_taxonomy: Optional[SemanticTaxonomy] = None,
        llm: Optional[Any] = None,
        expansion_strategy: LLMExpansionStrategy = LLMExpansionStrategy.FOCUSED_SUBTREE,
        min_items_threshold: int = MIN_ITEMS_FOR_EXPANSION,
        enable_combinations: bool = True,
        max_categories_per_expansion: int = MAX_CATEGORIES_PER_EXPANSION,
    ):
        """
        Initialize LLM-driven iterative taxonomy.

        Args:
            base_taxonomy: Starting taxonomy structure
            llm: Language model for expansion (GPT-4 recommended)
            expansion_strategy: Strategy for taxonomy expansion
            min_items_threshold: Minimum items before triggering expansion
            enable_combinations: Enable pattern-based combinations
            max_categories_per_expansion: Maximum categories to suggest per LLM expansion (default: 10)
        """
        self.base_taxonomy = base_taxonomy or get_taxonomy()
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

        # Import base taxonomy paths
        base_paths = self.base_taxonomy.get_all_paths()
        for path in base_paths:
            self._add_path_to_tree(root, path, is_dynamic=False)

        # Add strategic 'other' categories for expansion
        self._add_strategic_other_categories(root)

        return root

    def _add_strategic_other_categories(self, node: DynamicNode, max_depth: int = 3):
        """Add 'other' categories only at strategic levels for expansion."""
        if node.depth >= max_depth:
            return

        # Add 'other' only if node has existing children (not leaf)
        if node.children and "other" not in node.children:
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
                new_paths=[],
                migrated_items=0,
                suggested_paths=[],
                reasoning="Node not found",
            )

        node = self.path_index[node_path]

        # Check if enough items for expansion
        if len(node.other_items) < self.min_items_threshold:
            return TaxonomyExpansionResult(
                new_paths=[],
                migrated_items=0,
                suggested_paths=[],
                reasoning=f"Insufficient items ({len(node.other_items)} < {self.min_items_threshold})",
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
                new_paths=new_paths,
                migrated_items=migrated_count,
                suggested_paths=[],
                reasoning=f"LLM-driven expansion created {len(new_paths)} categories from {len(node.other_items)} items",
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
            "",
            "Existing sibling categories:",
        ]

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
                "1. Be semantically coherent with existing siblings",
                "2. Be at the appropriate level of specificity for this depth",
                "3. Not duplicate existing categories",
                "4. Follow the naming convention of siblings",
                "",
                "Return only the category names, one per line.",
            ]
        )

        return "\n".join(prompt_parts)

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

    def get_expansion_statistics(self) -> dict[str, Any]:
        """Get detailed statistics about expansions."""
        stats = {
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
            if node.path.endswith(".other"):
                stats["items_in_other"] += len(node.other_items)

        return stats

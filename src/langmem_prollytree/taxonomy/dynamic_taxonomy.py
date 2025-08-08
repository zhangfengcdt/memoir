"""
Dynamic taxonomy system that expands over time based on unclassified memories.
Provides 'other' categories at each level for uncategorized items.
"""

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import BaseTaxonomy
from .semantic_taxonomy import SemanticTaxonomy, TaxonomyCategory, get_taxonomy

logger = logging.getLogger(__name__)

# Configuration constants
OTHER_CATEGORY_NAME = "other"  # Name for fallback categories
DEFAULT_EXPANSION_THRESHOLD = 10  # Default threshold for expansion
DEFAULT_CONFIDENCE_THRESHOLD = 0.7  # Default confidence threshold
EXPANSION_WORKER_SLEEP_SECONDS = 60  # Background worker sleep interval


class ExpansionStrategy(Enum):
    """Strategies for expanding the taxonomy."""

    THRESHOLD_BASED = "threshold_based"  # Expand when N items in 'other'
    PERIODIC = "periodic"  # Expand on schedule
    ML_DRIVEN = "ml_driven"  # Use ML to identify patterns
    MANUAL = "manual"  # Require manual review


@dataclass
class DynamicNode:
    """Node in the dynamic taxonomy tree."""

    path: str
    category: Optional[TaxonomyCategory]
    depth: int
    is_leaf: bool
    is_dynamic: bool  # True if this was dynamically added
    created_at: datetime
    item_count: int = 0
    last_accessed: Optional[datetime] = None
    children: dict[str, "DynamicNode"] = field(default_factory=dict)
    other_items: list[dict[str, Any]] = field(default_factory=list)


class TaxonomyExpansionResult(BaseModel):
    """Result of a taxonomy expansion operation."""

    new_paths: list[str] = Field(description="Newly created taxonomy paths")
    migrated_items: int = Field(description="Number of items migrated from 'other'")
    suggested_paths: list[str] = Field(description="Suggested paths pending approval")
    reasoning: str = Field(description="Explanation of the expansion")


class DynamicTaxonomy(BaseTaxonomy):
    """
    Dynamic taxonomy that expands based on unclassified memories.
    Maintains compatibility with the base taxonomy while allowing growth.
    Implements AdvancedTaxonomyInterface for intelligent path selection.
    """

    def __init__(
        self,
        base_taxonomy: Optional[SemanticTaxonomy] = None,
        expansion_threshold: int = DEFAULT_EXPANSION_THRESHOLD,
        strategy: ExpansionStrategy = ExpansionStrategy.THRESHOLD_BASED,
        enable_other_categories: bool = True,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ):
        """
        Initialize the dynamic taxonomy.

        Args:
            base_taxonomy: Base taxonomy to start with
            expansion_threshold: Number of items in 'other' before expansion
            strategy: Expansion strategy to use
            enable_other_categories: Whether to add 'other' categories
            confidence_threshold: Min confidence for accepting classification
        """
        self.base_taxonomy = base_taxonomy or get_taxonomy()
        self.expansion_threshold = expansion_threshold
        self.strategy = strategy
        self.enable_other_categories = enable_other_categories
        self.confidence_threshold = confidence_threshold

        # Build dynamic tree from base taxonomy
        self.root = self._build_dynamic_tree()
        self.path_index: dict[str, DynamicNode] = {}
        self._rebuild_index()

        # Track expansion history
        self.expansion_history: list[TaxonomyExpansionResult] = []
        self.pending_expansions: list[dict[str, Any]] = []

        # Async expansion queue
        self.expansion_queue: asyncio.Queue = None
        self.expansion_task: Optional[asyncio.Task] = None

    def _build_dynamic_tree(self) -> DynamicNode:
        """Build the initial dynamic tree from base taxonomy."""
        root = DynamicNode(
            path="",
            category=None,
            depth=0,
            is_leaf=False,
            is_dynamic=False,
            created_at=datetime.now(),
        )

        # Add all base taxonomy paths
        base_paths = self.base_taxonomy.get_all_paths()
        for path in base_paths:
            self._add_path_to_tree(root, path, is_dynamic=False)

        # Add 'other' categories at each level if enabled
        if self.enable_other_categories:
            self._add_other_categories(root)

        return root

    def _add_path_to_tree(
        self, root: DynamicNode, path: str, is_dynamic: bool = False
    ) -> DynamicNode:
        """Add a path to the dynamic tree."""
        parts = path.split(".")
        current = root

        for i, part in enumerate(parts):
            current_path = ".".join(parts[: i + 1])

            if part not in current.children:
                # Create new node
                category = None
                if i == 0:
                    from contextlib import suppress

                    with suppress(ValueError):
                        category = TaxonomyCategory(part)

                current.children[part] = DynamicNode(
                    path=current_path,
                    category=category,
                    depth=i + 1,
                    is_leaf=(i == len(parts) - 1),
                    is_dynamic=is_dynamic,
                    created_at=datetime.now(),
                )

            current = current.children[part]

        return current

    def _add_other_categories(self, node: DynamicNode, max_depth: int = 5):
        """Recursively add 'other' categories to each level."""
        if node.depth >= max_depth:
            return

        # Add 'other' child if it doesn't exist
        if OTHER_CATEGORY_NAME not in node.children:
            other_path = f"{node.path}.other" if node.path else OTHER_CATEGORY_NAME
            node.children[OTHER_CATEGORY_NAME] = DynamicNode(
                path=other_path,
                category=node.category,
                depth=node.depth + 1,
                is_leaf=False,
                is_dynamic=True,
                created_at=datetime.now(),
            )

        # Recursively add to all children
        for child in node.children.values():
            if not child.path.endswith(".other"):
                self._add_other_categories(child, max_depth)

    def _rebuild_index(self):
        """Rebuild the path index for fast lookups."""
        self.path_index = {}

        def traverse(node: DynamicNode):
            if node.path:
                self.path_index[node.path] = node
            for child in node.children.values():
                traverse(child)

        traverse(self.root)

    def select_path_with_fallback(
        self,
        classification_result: Any,
        memory_content: str,
        metadata: Optional[dict] = None,
    ) -> tuple[str, float]:
        """
        Select taxonomy path with fallback to 'other' categories based on classification result.

        Args:
            classification_result: Result from SemanticClassifier
            memory_content: The memory content (for tracking)
            metadata: Optional metadata about the memory

        Returns:
            Tuple of (taxonomy path, confidence score)
        """
        result = classification_result

        # Check if the path exists and confidence is high enough
        if (
            result.primary_path in self.path_index
            and result.confidence >= self.confidence_threshold
        ):
            node = self.path_index[result.primary_path]
            node.item_count += 1
            node.last_accessed = datetime.now()
            return result.primary_path, result.confidence

        # Low confidence or invalid path - find appropriate 'other' category
        other_path = self._find_best_other_category(result, memory_content, metadata)

        if other_path and other_path in self.path_index:
            node = self.path_index[other_path]
            node.item_count += 1
            node.last_accessed = datetime.now()

            # Store the unclassified item for later analysis
            node.other_items.append(
                {
                    "content": memory_content,
                    "metadata": metadata,
                    "original_classification": result.primary_path,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning,
                    "alternatives": result.alternative_paths,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Check if we should trigger expansion
            if (
                self.strategy == ExpansionStrategy.THRESHOLD_BASED
                and len(node.other_items) >= self.expansion_threshold
            ):
                self._queue_expansion(node)

        return other_path or OTHER_CATEGORY_NAME, result.confidence

    def _find_best_other_category(
        self, classification_result: Any, memory_content: str, metadata: Optional[dict]
    ) -> str:
        """Find the most appropriate 'other' category for unclassified content.

        Uses the classification result to determine the best 'other' category
        based on the attempted path, without hardcoding categories.
        """
        # Extract the top-level category from the classification attempt
        if classification_result and classification_result.primary_path:
            path_parts = classification_result.primary_path.split(".")
            if path_parts:
                # Try progressively broader 'other' categories
                for i in range(len(path_parts), 0, -1):
                    # Build potential 'other' path at this level
                    prefix = ".".join(path_parts[: i - 1])
                    if prefix:
                        other_path = f"{prefix}.other"
                    else:
                        other_path = f"{path_parts[0]}.other"

                    # Check if this 'other' path exists
                    if other_path in self.path_index:
                        return other_path

                # Try root-level category 'other'
                root_other = f"{path_parts[0]}.other"
                if root_other in self.path_index:
                    return root_other

        # Ultimate fallback to root 'other'
        return OTHER_CATEGORY_NAME if OTHER_CATEGORY_NAME in self.path_index else None

    def is_valid_path(self, path: str) -> bool:
        """Check if a path exists in the dynamic taxonomy."""
        return path in self.path_index

    def get_all_paths(self) -> list[str]:
        """Get all available paths in the dynamic taxonomy."""
        return list(self.path_index.keys())

    def _queue_expansion(self, node: DynamicNode):
        """Queue a node for expansion analysis."""
        expansion_request = {
            "node": node,
            "timestamp": datetime.now(),
            "item_count": len(node.other_items),
        }
        self.pending_expansions.append(expansion_request)

        # Log for monitoring
        logger.info(
            f"Queued expansion for {node.path} with {len(node.other_items)} items"
        )

    async def expand_taxonomy(
        self, node_path: str, suggested_categories: Optional[list[str]] = None
    ) -> TaxonomyExpansionResult:
        """
        Expand the taxonomy at a specific node.

        Args:
            node_path: Path to the node to expand
            suggested_categories: Optional list of new categories to add

        Returns:
            TaxonomyExpansionResult with details of the expansion
        """
        if node_path not in self.path_index:
            return TaxonomyExpansionResult(
                new_paths=[],
                migrated_items=0,
                suggested_paths=[],
                reasoning=f"Node {node_path} not found",
            )

        node = self.path_index[node_path]

        # Analyze items in 'other' to identify patterns
        if not suggested_categories:
            suggested_categories = await self._analyze_other_items(node)

        new_paths = []
        migrated_count = 0

        # Create new categories
        for category in suggested_categories:
            new_path = f"{node.path}.{category}".lstrip(".")
            if new_path not in self.path_index:
                new_node = self._add_path_to_tree(self.root, new_path, is_dynamic=True)
                new_paths.append(new_path)

                # Add 'other' subcategory
                if self.enable_other_categories:
                    self._add_other_categories(new_node, max_depth=node.depth + 2)

        # Rebuild index after adding new paths
        self._rebuild_index()

        # Migrate items from 'other' to new categories
        remaining_items = []
        for item in node.other_items:
            migrated = False
            for new_path in new_paths:
                if self._should_migrate_item(item, new_path):
                    # Move item to new category
                    new_node = self.path_index[new_path]
                    new_node.item_count += 1
                    migrated_count += 1
                    migrated = True
                    break

            if not migrated:
                remaining_items.append(item)

        node.other_items = remaining_items

        # Record expansion
        result = TaxonomyExpansionResult(
            new_paths=new_paths,
            migrated_items=migrated_count,
            suggested_paths=[],  # Could include additional suggestions
            reasoning=f"Expanded {node_path} with {len(new_paths)} new categories based on {len(node.other_items)} unclassified items",
        )

        self.expansion_history.append(result)
        return result

    async def _analyze_other_items(self, node: DynamicNode) -> list[str]:
        """
        Analyze items in 'other' category to suggest new categories.

        This method can use:
        1. Pattern analysis from stored classification attempts
        2. LLM to identify common themes
        3. Clustering algorithms on content
        """
        if not node.other_items:
            return []

        suggestions = []

        # Analyze original classification attempts
        attempted_paths = defaultdict(int)
        for item in node.other_items:
            if "original_classification" in item:
                # Extract the next level from attempted classification
                orig_path = item["original_classification"]
                node_path_depth = len(node.path.split(".")) if node.path else 0

                orig_parts = orig_path.split(".")
                if len(orig_parts) > node_path_depth:
                    # Get the next level that was attempted
                    next_level = orig_parts[node_path_depth]
                    attempted_paths[next_level] += 1

        # Suggest categories that appeared multiple times
        for category, count in attempted_paths.items():
            if count >= 2:  # At least 2 attempts at this category
                suggestions.append(category)

        # If we have LLM reasoning, analyze that too
        if any("reasoning" in item for item in node.other_items):
            # Extract common themes from reasoning
            # This could be enhanced with NLP/clustering
            pass

        # Limit suggestions to top 5
        return suggestions[:5]

    def _should_migrate_item(self, item: dict, new_path: str) -> bool:
        """Determine if an item should be migrated to a new category."""
        # Check if the original classification matches the new path
        if "original_classification" in item:
            orig_path = item["original_classification"]
            if new_path in orig_path or orig_path.startswith(new_path):
                return True

        # Check content similarity (simplified)
        content = item["content"].lower()
        category = new_path.split(".")[-1].lower()
        return category in content

    async def start_background_expansion(self):
        """Start background task for automatic taxonomy expansion."""
        if self.expansion_task and not self.expansion_task.done():
            return

        self.expansion_queue = asyncio.Queue()
        self.expansion_task = asyncio.create_task(self._expansion_worker())
        logger.info("Started background taxonomy expansion worker")

    async def stop_background_expansion(self):
        """Stop the background expansion task."""
        if self.expansion_task:
            self.expansion_task.cancel()
            from contextlib import suppress

            with suppress(asyncio.CancelledError):
                await self.expansion_task
            logger.info("Stopped background taxonomy expansion worker")

    async def _expansion_worker(self):
        """Worker that processes expansion requests in the background."""
        while True:
            try:
                # Check pending expansions periodically
                if self.pending_expansions:
                    # Process oldest expansion request
                    request = self.pending_expansions.pop(0)
                    node = request["node"]

                    if len(node.other_items) >= self.expansion_threshold:
                        logger.info(f"Processing expansion for {node.path}")
                        await self.expand_taxonomy(node.path)

                # Sleep before next check
                await asyncio.sleep(
                    EXPANSION_WORKER_SLEEP_SECONDS
                )  # Check periodically

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in expansion worker: {e}")
                await asyncio.sleep(EXPANSION_WORKER_SLEEP_SECONDS)

    def get_statistics(self) -> dict[str, Any]:
        """Get statistics about the dynamic taxonomy."""
        total_paths = len(self.path_index)
        dynamic_paths = sum(1 for n in self.path_index.values() if n.is_dynamic)
        other_paths = sum(1 for p in self.path_index if p.endswith(".other"))

        # Count items in 'other' categories
        other_items_total = sum(
            len(n.other_items)
            for n in self.path_index.values()
            if n.path.endswith(".other")
        )

        return {
            "total_paths": total_paths,
            "base_paths": total_paths - dynamic_paths,
            "dynamic_paths": dynamic_paths,
            "other_categories": other_paths,
            "unclassified_items": other_items_total,
            "expansions_completed": len(self.expansion_history),
            "expansions_pending": len(self.pending_expansions),
        }

    def export_taxonomy(self) -> dict[str, Any]:
        """Export the current taxonomy structure."""

        def node_to_dict(node: DynamicNode) -> dict:
            return {
                "path": node.path,
                "is_dynamic": node.is_dynamic,
                "item_count": node.item_count,
                "other_items_count": len(node.other_items),
                "children": {
                    name: node_to_dict(child) for name, child in node.children.items()
                },
            }

        return {
            "root": node_to_dict(self.root),
            "statistics": self.get_statistics(),
            "expansion_history": [
                {
                    "new_paths": r.new_paths,
                    "migrated_items": r.migrated_items,
                    "reasoning": r.reasoning,
                }
                for r in self.expansion_history
            ],
        }

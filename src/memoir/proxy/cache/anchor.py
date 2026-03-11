"""
Cache Anchor Generation.

Generates ProllyTree-based cache anchors for LLM provider requests.
The anchor identifies the exact KV cache state to use.
"""

import hashlib
from dataclasses import dataclass
from typing import Optional

from memoir.proxy.segmentation.pipeline import SegmentedPrompt


@dataclass
class CacheAnchor:
    """
    A cache anchor pointing to a specific ProllyTree state.

    The anchor serves as a "committish" reference that tells the LLM provider
    exactly which KV cache to use for the stable prefix.
    """

    root_hash: str
    tier1_hash: str
    tier2_hash: str
    prefix_length: int
    metadata: dict

    @property
    def committish(self) -> str:
        """Return a Git-style short reference."""
        return self.root_hash[:8]

    def to_header(self) -> dict[str, str]:
        """Convert to HTTP header format for provider requests."""
        return {
            "X-Memoir-Cache-Anchor": self.root_hash,
            "X-Memoir-Prefix-Length": str(self.prefix_length),
        }


class AnchorGenerator:
    """
    Generates cache anchors from segmented prompts.

    Uses ProllyTree-style content-addressed hashing to create stable
    references for the cached portion of prompts.
    """

    def __init__(self) -> None:
        """Initialize the anchor generator."""
        self._anchor_cache: dict[str, CacheAnchor] = {}

    def generate(
        self,
        segmented: SegmentedPrompt,
        namespace: Optional[str] = None,
    ) -> CacheAnchor:
        """
        Generate a cache anchor for a segmented prompt.

        Args:
            segmented: The segmented prompt.
            namespace: Optional namespace for multi-tenant isolation.

        Returns:
            CacheAnchor with root hash and metadata.
        """
        # Hash each tier independently
        tier1_hash = self._hash_content(segmented.tier1_content)
        tier2_hash = self._hash_content(segmented.tier2_content)

        # Combine for root hash (like a Merkle tree)
        combined = f"{tier1_hash}:{tier2_hash}"
        if namespace:
            combined = f"{namespace}:{combined}"
        root_hash = self._hash_content(combined)

        # Check cache
        if root_hash in self._anchor_cache:
            return self._anchor_cache[root_hash]

        # Create new anchor
        anchor = CacheAnchor(
            root_hash=root_hash,
            tier1_hash=tier1_hash,
            tier2_hash=tier2_hash,
            prefix_length=len(segmented.stable_prefix),
            metadata={
                "tier1_blocks": len(segmented.get_blocks_by_tier(1)),
                "tier2_blocks": len(segmented.get_blocks_by_tier(2)),
                "tier3_blocks": len(segmented.get_blocks_by_tier(3)),
                "namespace": namespace,
            },
        )

        self._anchor_cache[root_hash] = anchor
        return anchor

    def _hash_content(self, content: str) -> str:
        """
        Generate a SHA-256 hash for content.

        Args:
            content: The content to hash.

        Returns:
            Hex-encoded hash string.
        """
        if not content:
            return "empty_" + "0" * 58  # Deterministic empty hash
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def lookup(self, root_hash: str) -> Optional[CacheAnchor]:
        """
        Look up a cached anchor by root hash.

        Args:
            root_hash: The root hash to look up.

        Returns:
            CacheAnchor if found, None otherwise.
        """
        return self._anchor_cache.get(root_hash)

    def invalidate(self, root_hash: str) -> bool:
        """
        Invalidate a cached anchor.

        Args:
            root_hash: The root hash to invalidate.

        Returns:
            True if anchor was found and removed.
        """
        if root_hash in self._anchor_cache:
            del self._anchor_cache[root_hash]
            return True
        return False

    def clear(self) -> int:
        """
        Clear all cached anchors.

        Returns:
            Number of anchors cleared.
        """
        count = len(self._anchor_cache)
        self._anchor_cache.clear()
        return count

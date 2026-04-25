"""
Service layer data models.

These dataclasses define the return types for all service operations,
providing a consistent interface for CLI, TUI, SDK, and HTTP handlers.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RememberResult:
    """Result of a remember (store memory) operation."""

    success: bool
    key: str  # Primary classification path
    keys: list[str]  # All paths (multi-label classification)
    confidence: float  # Classification confidence 0.0-1.0
    reasoning: str  # Explanation of classification
    commit_hash: str | None = None  # Git commit hash
    commit_date: str | None = None  # Git commit date
    timings: dict[str, float] = field(default_factory=dict)  # Step timings
    timeline_events: list[dict] | None = None  # Extracted timeline events
    location_events: list[dict] | None = None  # Extracted location events
    timeline_applied: bool = False  # Whether timeline events were applied
    location_applied: bool = False  # Whether location events were applied
    namespace: str = "default"
    content: str = ""  # Original content
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "key": self.key,
            "keys": self.keys,
            "full_key": f"{self.namespace}:{self.key}",
            "full_keys": [f"{self.namespace}:{k}" for k in self.keys],
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "commit_hash": self.commit_hash,
            "commit_date": self.commit_date,
            "timings": self.timings,
            "timeline_events": self.timeline_events,
            "location_events": self.location_events,
            "timeline_applied": self.timeline_applied,
            "location_applied": self.location_applied,
            "namespace": self.namespace,
            "content": self.content,
            "error": self.error,
        }


@dataclass
class Memory:
    """A single memory item returned from recall."""

    path: str  # Semantic taxonomy path
    content: str  # Memory content
    namespace: str = "default"
    relevance_score: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": self.path,
            "content": self.content,
            "namespace": self.namespace,
            "relevance_score": self.relevance_score,
            "metadata": self.metadata,
        }


@dataclass
class RecallResult:
    """Result of a recall (search) operation."""

    success: bool
    memories: list[Memory]
    query: str
    timing_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "memories": [m.to_dict() for m in self.memories],
            "query": self.query,
            "count": len(self.memories),
            "timing_ms": self.timing_ms,
            "metadata": self.metadata,
            "error": self.error,
        }


@dataclass
class DeleteResult:
    """Result of a forget (delete) operation."""

    success: bool
    key: str
    namespace: str = "default"
    commit_hash: str | None = None
    message: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "key": self.key,
            "namespace": self.namespace,
            "commit_hash": self.commit_hash,
            "message": self.message,
            "error": self.error,
        }


@dataclass
class GetResult:
    """Result of a direct get (key lookup) operation.

    Unlike recall, this performs no LLM call and no semantic search — it is a
    direct key/value fetch from the ProllyTree store, suitable for fast
    lookups when the caller already knows the taxonomy path(s).
    """

    success: bool
    items: list[dict[str, Any]]  # Each: {key, namespace, found, value}
    timing_ms: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "items": self.items,
            "count": len(self.items),
            "found_count": sum(1 for i in self.items if i.get("found")),
            "timing_ms": self.timing_ms,
            "error": self.error,
        }


@dataclass
class BranchInfo:
    """Information about branches in the repository."""

    branches: list[str]
    current: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "branches": self.branches,
            "current": self.current,
        }


@dataclass
class CommitInfo:
    """Information about a single commit."""

    hash: str  # Full commit hash
    short_hash: str  # Short (7-8 char) hash
    message: str
    author: str
    email: str
    timestamp: int  # Unix timestamp

    # Annotations filled in by the UI handler for the rich commit list.
    # Empty for legacy callers — ``BranchService.get_commits`` only
    # populates these when ``annotate=True``.
    tags: list[str] = field(default_factory=list)
    refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "hash": self.hash,
            "short_hash": self.short_hash,
            "message": self.message,
            "author": self.author,
            "email": self.email,
            "timestamp": self.timestamp,
            "tags": list(self.tags),
            "refs": list(self.refs),
        }


@dataclass
class CheckoutResult:
    """Result of a checkout operation."""

    success: bool
    target: str  # Branch or commit checked out
    current_branch: str
    message: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "target": self.target,
            "current_branch": self.current_branch,
            "message": self.message,
            "error": self.error,
        }


@dataclass
class MergeResult:
    """Result of a merge operation."""

    success: bool
    source_branch: str
    target_branch: str
    conflicts: list[str] = field(default_factory=list)
    strategy: str | None = None  # Conflict resolution strategy used
    commit_hash: str | None = None  # Merge commit hash
    message: str = ""
    error: str | None = None
    # Set by sync_branch when the original branch was restored after merging
    # into a different target. None for plain merge().
    restored_branch: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "source_branch": self.source_branch,
            "target_branch": self.target_branch,
            "conflicts": self.conflicts,
            "strategy": self.strategy,
            "commit_hash": self.commit_hash,
            "message": self.message,
            "error": self.error,
            "restored_branch": self.restored_branch,
        }


@dataclass
class ProofResult:
    """Result of generating a cryptographic proof."""

    success: bool
    proof_b64: str  # Base64-encoded proof
    key: str
    namespace: str
    full_key: str
    value: Any = None
    proof_size: int = 0
    message: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "proof": self.proof_b64,
            "key": self.key,
            "namespace": self.namespace,
            "full_key": self.full_key,
            "value": self.value,
            "proof_size": self.proof_size,
            "message": self.message,
            "error": self.error,
        }


@dataclass
class VerifyResult:
    """Result of verifying a cryptographic proof."""

    success: bool
    valid: bool
    key: str
    namespace: str
    full_key: str
    current_value: Any = None
    expected_value: Any = None
    message: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "valid": self.valid,
            "key": self.key,
            "namespace": self.namespace,
            "full_key": self.full_key,
            "current_value": self.current_value,
            "expected_value": self.expected_value,
            "message": self.message,
            "error": self.error,
        }


@dataclass
class BlameEntry:
    """A single blame entry showing who changed what."""

    commit: str
    author: str
    date: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "commit": self.commit,
            "author": self.author,
            "date": self.date,
            "message": self.message,
        }


@dataclass
class StoreInfo:
    """Information about a memory store."""

    path: str
    exists: bool
    initialized: bool
    branch: str | None = None
    commit_count: int = 0
    memory_count: int = 0
    namespaces: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": self.path,
            "exists": self.exists,
            "initialized": self.initialized,
            "branch": self.branch,
            "commit_count": self.commit_count,
            "memory_count": self.memory_count,
            "namespaces": self.namespaces,
        }


@dataclass
class CreateStoreResult:
    """Result of creating a new memory store."""

    success: bool
    path: str
    message: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "success": self.success,
            "path": self.path,
            "message": self.message,
            "error": self.error,
        }

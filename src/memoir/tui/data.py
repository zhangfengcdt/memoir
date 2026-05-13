# SPDX-License-Identifier: Apache-2.0
"""DataLoader — in-process facade over memoir services for the TUI.

The TUI never hits HTTP; it calls services directly. This class wraps the
service instantiation, applies a few small caches, and exposes typed
methods the widgets can call from worker threads.

All methods are synchronous. Async work happens behind a fresh
``asyncio.new_event_loop()`` per call (mirrors the pattern used by the
HTTP handlers under ``memoir.ui.handlers``), so each background worker
can run independently without poking the Textual event loop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from memoir.services.branch_service import BranchService

if TYPE_CHECKING:
    from memoir.services.models import CommitInfo


@dataclass
class CommitChange:
    """One key-level change inside a commit's diff."""

    path: str  # Memory path, with namespace prefix stripped.
    op: str  # "added" | "modified" | "deleted"
    namespace: str | None = None  # The original namespace, if any.


@dataclass
class MemoryEntry:
    """One memory in the outline. Body intentionally not eagerly loaded —
    fetch via :meth:`DataLoader.get_memory` when the user actually opens
    the leaf. Keeps tab-switch latency down on stores with many keys."""

    namespace: str
    path: str  # Dotted path within the namespace (e.g. "workflow.coding.style").


@dataclass
class StoreInfo:
    store_path: str
    current_branch: str
    commits_count: int
    head_hash: str | None  # Short hash of the current HEAD; None on empty store.


# Hard cap on the number of keys the outline scans on first load. Above
# this the tree gets unwieldy in a terminal anyway, and on big stores the
# iteration alone is what dominates the wait.
MAX_OUTLINE_KEYS = 10_000


class DataLoader:
    """In-process service facade with light caching."""

    def __init__(self, store_path: str, commit_limit: int = 100) -> None:
        self.store_path = store_path
        self.commit_limit = commit_limit
        self._branch = BranchService(store_path)
        # Raw ``prollytree.VersionedKvStore`` cached for the lifetime of
        # the loader. Constructed once; reused for keys, single-key
        # value reads, and commit-diff lookups. We deliberately skip the
        # ``ProllyTreeStore`` wrapper — its ``_populate_key_registry``
        # walks the whole tree via ``scan()`` (fetching every value
        # blob) on construction, which is the 30s freeze users were
        # seeing on first interaction.
        self._raw_tree_cache: Any | None = None

        # Cached results — populated lazily, cleared by ``refresh()``.
        self._info: StoreInfo | None = None
        self._commits: list[CommitInfo] | None = None
        self._memories: list[MemoryEntry] | None = None

    def refresh(self) -> None:
        """Drop cached **data** but keep the raw-tree handle alive — the
        Rust ``VersionedKvStore`` is expensive to re-instantiate, but
        a fresh ``list_keys()`` call on the same instance picks up any
        new commits."""
        self._info = None
        self._commits = None
        self._memories = None

    def warmup(self) -> None:
        """Pre-fetch the outline keys via direct ``VersionedKvStore.list_keys()``.

        Does **not** open the full ``ProllyTreeStore`` wrapper — that
        triggers ``_populate_key_registry`` which iterates ``scan()``
        (key+value pairs, slow on stores with large system namespaces).
        The wrapper is opened lazily on first leaf click instead, which
        matches the web UI's "open when user asks for content" cost
        profile.
        """
        self.get_memories()

    # ------------------------------------------------------------------
    # Eager / cheap reads
    # ------------------------------------------------------------------

    def get_store_info(self) -> StoreInfo:
        if self._info is not None:
            return self._info
        branch_name, head_hash = self._branch.get_current_branch()
        commits = self.get_commits()
        self._info = StoreInfo(
            store_path=self.store_path,
            current_branch=branch_name or "main",
            commits_count=len(commits),
            head_hash=head_hash,
        )
        return self._info

    def get_head_hash(self) -> str | None:
        """Cheap probe for the auto-refresh tick — uses a fresh
        ``BranchService`` call and bypasses the cache."""
        try:
            _, head = self._branch.get_current_branch()
            return head
        except Exception:
            return None

    def get_commits(self) -> list[CommitInfo]:
        """Commit log for the current branch. Empty list on a fresh store."""
        if self._commits is not None:
            return self._commits
        try:
            self._commits = self._branch.get_commits(
                branch="HEAD", limit=self.commit_limit, annotate=True
            )
        except Exception:
            # Fresh store with no HEAD ref → no commits to show.
            self._commits = []
        return self._commits

    # ------------------------------------------------------------------
    # Lazy / heavier reads
    # ------------------------------------------------------------------

    def get_commit_changes(self, commit_hash: str) -> list[CommitChange]:
        """Return structured key-level changes for ``commit_hash``.

        For the initial commit (no parents) every key is reported as added.
        Failures return an empty list so the caller can render a placeholder.
        Uses the cached raw ``VersionedKvStore`` directly.
        """
        commit = next((c for c in self.get_commits() if c.hash == commit_hash), None)
        self._ensure_raw_tree()
        if self._raw_tree_cache is None:
            return []

        if commit is None or not commit.parents:
            keys = self._call_raw("list_keys") or []
            return [
                CommitChange(path=p, op="added", namespace=ns)
                for p, ns in (self._split_namespaced_key(k) for k in keys)
                if ns is not None
            ]

        parent = commit.parents[0]
        kv_diffs = self._call_raw("diff", parent, commit_hash) or []

        changes: list[CommitChange] = []
        for kv_diff in kv_diffs:
            path, namespace = self._split_namespaced_key(kv_diff.key)
            op_type = kv_diff.operation.operation_type
            if op_type == "Added":
                changes.append(CommitChange(path=path, op="added", namespace=namespace))
            elif op_type == "Removed":
                changes.append(
                    CommitChange(path=path, op="deleted", namespace=namespace)
                )
            elif op_type == "Modified":
                changes.append(
                    CommitChange(path=path, op="modified", namespace=namespace)
                )
        return changes

    def get_memories(self) -> list[MemoryEntry]:
        """Enumerate up to ``MAX_OUTLINE_KEYS`` paths from the ``default``
        namespace — **keys only, no values**.

        Uses the cached raw ``VersionedKvStore``. The body of any single
        memory is fetched lazily via :meth:`get_memory` only when the
        user actually selects a leaf.
        """
        if self._memories is not None:
            return self._memories
        self._ensure_raw_tree()
        entries: list[MemoryEntry] = []
        keys = self._call_raw("list_keys") or []
        prefix = "default:"
        for key_bytes in keys:
            if len(entries) >= MAX_OUTLINE_KEYS:
                break
            try:
                key_str = (
                    key_bytes.decode("utf-8")
                    if isinstance(key_bytes, bytes)
                    else str(key_bytes)
                )
            except Exception:
                continue
            if not key_str.startswith(prefix):
                continue
            path = key_str[len(prefix) :]
            if not path:
                continue
            entries.append(MemoryEntry(namespace="default", path=path))
        self._memories = entries
        return entries

    def get_memory(self, path: str, namespace: str = "default") -> str | None:
        """Read a single memory's content via the raw ``VersionedKvStore``,
        avoiding the ``ProllyTreeStore`` wrapper. Returns ``None`` if missing.
        """
        self._ensure_raw_tree()
        if self._raw_tree_cache is None:
            return None
        full_key = f"{namespace}:{path}".encode()
        value_bytes = self._call_raw("get", full_key)
        if not value_bytes:
            return None
        try:
            value = json.loads(value_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            try:
                return value_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return None
        return self._unwrap_memory_value(value)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _ensure_raw_tree(self) -> None:
        """Open the raw ``VersionedKvStore`` once; idempotent."""
        if self._raw_tree_cache is not None:
            return
        import os as _os

        from prollytree import VersionedKvStore

        data_dir = Path(self.store_path) / "data"
        saved = _os.getcwd()
        try:
            _os.chdir(self.store_path)
            try:
                self._raw_tree_cache = VersionedKvStore(str(data_dir))
            except Exception:
                self._raw_tree_cache = None
        finally:
            _os.chdir(saved)

    def _call_raw(self, method_name: str, *args):
        """Invoke a method on the cached raw tree with ``cwd`` set to the
        store path (prollytree's Rust binding looks up the enclosing git
        repo by cwd, not by the absolute path passed to the constructor).
        Returns ``None`` on missing tree or on any inner exception."""
        if self._raw_tree_cache is None:
            return None
        import os as _os

        saved = _os.getcwd()
        try:
            _os.chdir(self.store_path)
            try:
                return getattr(self._raw_tree_cache, method_name)(*args)
            except Exception:
                return None
        finally:
            _os.chdir(saved)

    @staticmethod
    def _split_namespaced_key(key: Any) -> tuple[str, str | None]:
        """Split ``namespace:dotted.path`` → (path, namespace). Decodes bytes."""
        text = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        if ":" in text:
            ns, _, rest = text.partition(":")
            return rest, ns
        return text, None

    @staticmethod
    def _unwrap_memory_value(value: Any) -> str:
        """Pull a printable string out of memoir's value envelope.

        Writes are stored as ``{"content": <payload>, ...}``; the payload may be
        a raw string or a JSON-encoded blob. Anything else is repr-encoded so
        the viewer at least shows something instead of erroring out.
        """
        if value is None:
            return ""
        if isinstance(value, dict) and "content" in value:
            inner = value["content"]
            if isinstance(inner, str):
                stripped = inner.strip()
                if stripped.startswith("{") or stripped.startswith("["):
                    try:
                        parsed = json.loads(stripped)
                        return json.dumps(parsed, indent=2)
                    except (TypeError, ValueError):
                        return inner
                return inner
            return json.dumps(inner, indent=2, default=str)
        if isinstance(value, str):
            return value
        return json.dumps(value, indent=2, default=str)

    @staticmethod
    def store_exists(store_path: str) -> bool:
        p = Path(store_path)
        return p.is_dir() and (p / ".git").exists()

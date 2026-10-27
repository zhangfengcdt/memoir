# SPDX-License-Identifier: Apache-2.0
"""
ProllyTree adapter implementing LangGraph's BaseStore interface.
Provides high-performance semantic memory storage with versioning.
"""

import contextlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

from langgraph.store.base import BaseStore
from prollytree import ProllyTree, VersionedKvStore
from pydantic import BaseModel, Field

from memoir.store.backend import is_memoir_store, resolve_backend, write_backend_lock
from memoir.store.cwd_locked import CwdLockedTree
from memoir.store.git_safety import harden_git_config
from memoir.store.gitcmd import run_git
from memoir.store.write_lock import store_write_lock

# Storage layer doesn't import classification or search modules
# These are handled by higher layers

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def _native_stderr_quiet():
    """FD-level stderr redirect around the prollytree ``VersionedKvStore``
    open/init call.

    Prollytree v0.4 prints "Warning: Failed to load tree from saved root
    hash. This may indicate missing git objects or corrupted hash
    mappings. Attempting to create tree with saved config to avoid data
    loss..." on every open as part of its optimistic-fast-load fallback,
    even on perfectly healthy stores. The message is hardcoded in the
    native binary; we can't change it upstream from here, so we silence
    it at the file-descriptor level when memoir is running as a CLI
    (``_MEMOIR_SUPPRESS_NATIVE_IMPORT_STDERR=1``, set by the CLI
    entrypoint). Library callers (tests, embedded users) still see it.

    Real corruption surfaces as a raised exception from the constructor,
    not stderr noise — suppressing this warning does not hide real
    errors.
    """
    if os.environ.get("_MEMOIR_SUPPRESS_NATIVE_IMPORT_STDERR") != "1":
        yield
        return
    saved_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_fd, 2)
        os.close(devnull_fd)
        os.close(saved_fd)


class MemoryItem(BaseModel):
    """Represents a memory item in the store."""

    key: str = Field(description="Semantic taxonomy key")
    namespace: str = Field(description="User/agent namespace")
    content: Any = Field(description="Memory content")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )
    timestamp: float = Field(
        default_factory=time.time, description="Creation timestamp"
    )
    version: str | None = Field(default=None, description="Version/commit ID")
    confidence: float = Field(default=1.0, description="Classification confidence")


# `_CwdLockedTree` lives in memoir.store.cwd_locked (re-exported below for
# any external caller that imported the underscore-prefixed name).
_CwdLockedTree = CwdLockedTree


class AggregatedMemory(BaseModel):
    """Represents aggregated memories at a semantic path."""

    path: str = Field(description="Semantic taxonomy path")
    memories: list[dict[str, Any]] = Field(
        default_factory=list, description="List of memory entries at this path"
    )
    count: int = Field(default=0, description="Number of memories")
    first_timestamp: float = Field(
        default_factory=time.time, description="Timestamp of first memory"
    )
    last_timestamp: float = Field(
        default_factory=time.time, description="Timestamp of last memory"
    )
    last_updated: float = Field(
        default_factory=time.time, description="Last update timestamp"
    )


# prollytree caps list_keys()/get_keys_at_ref() at 1024 keys, and the subset
# it returns changes between calls. diff() has no such cap, so replay it from
# the root commit to rebuild the full key set.

#: The binding's cap; only used to warn when a root commit hits it.
_PROLLYTREE_KEY_LIMIT = 1024

_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REF_PREFIXES = ("refs/heads/", "refs/tags/", "refs/remotes/")


def _has_revision_syntax(ref: str) -> bool:
    """Whether ``ref`` contains git revision syntax rather than a ref name.

    Must run before the full-ref early return (review #2): otherwise
    ``refs/heads/main~1`` passes on its prefix and fails later in diff with
    a raw git error. A bare ``@`` is fine — ``foo@bar`` is a valid branch.
    """
    return ref.startswith("-") or any(c in ref for c in "~^: \\") or "@{" in ref


def _ref_exists(store_path: Path, ref: str) -> bool:
    """Whether ``ref`` exists; ``--quiet`` mutes stderr, exit 0 means it
    resolves (review #5)."""
    result = run_git(store_path, "rev-parse", "--verify", "--quiet", ref)
    return result.returncode == 0


def _is_commit(store_path: Path, ref: str) -> bool:
    """Whether ``ref`` resolves to a commit (review #3).

    ``rev-parse --verify`` also accepts tree and blob SHAs, which make
    rev-list return no roots and all_keys() look empty. The ``^{commit}``
    suffix asks git to peel to a commit, which those objects cannot.
    """
    result = run_git(
        store_path, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"
    )
    return result.returncode == 0


def _resolve_ref(store_path: Path, ref: str) -> str | None:
    """Return ``ref`` if prollytree can resolve it, else ``None``.

    ``git rev-parse`` also accepts ``HEAD~1`` and abbreviated SHAs, which the
    binding cannot resolve; accepting them used to fall back to the current
    branch's data (review #2).
    """
    if not ref:
        return None

    # Revision syntax first, so refs/heads/main~1 cannot slip through (#2).
    if _has_revision_syntax(ref):
        return None

    if ref == "HEAD":
        return ref

    # A full SHA must peel to a commit, not a tree or blob (#3).
    if _FULL_SHA_RE.match(ref):
        return ref if _is_commit(store_path, ref) else None

    # A full ref form must exist; the prefix alone proves nothing (#5).
    if ref.startswith(_REF_PREFIXES):
        return ref if _ref_exists(store_path, ref) else None

    # Branch first: git ranks refs/tags/<name> above refs/heads/<name>, so a
    # tag shadowing a branch made ``--branch v1`` read the tag (#6).
    branch_ref = f"refs/heads/{ref}"
    if _ref_exists(store_path, branch_ref):
        return branch_ref

    # Not a branch: git's general resolution (tags, remotes, ...).
    result = run_git(store_path, "rev-parse", "--symbolic-full-name", ref)
    if result.returncode != 0:
        return None

    # Only a real refs/ path counts; a short SHA resolves to itself and is
    # rejected here because it carries no refs/ prefix.
    full = result.stdout.strip()
    if not full.startswith(_REF_PREFIXES):
        return None
    return full if _ref_exists(store_path, full) else None


def _git_roots(store_path: Path, ref: str) -> list[str]:
    """Root commits reachable from ``ref``; raises when git cannot answer.

    ``tree.log()`` only returns the newest 100 commits, so it cannot find the
    root of a long history. Raising (rather than returning []) lets callers
    tell "empty history" apart from "could not read history" (review #1).
    """
    result = run_git(store_path, "rev-list", "--max-parents=0", ref)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"cannot resolve '{ref}'")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _replay_snapshot(tree: Any, store_path: Path, ref: str) -> dict[bytes, bytes]:
    """Rebuild ``ref``'s full key/value state from commit history.

    ``diff(root, ref)`` is the complete delta between two trees, so one root
    reconstructs the state. An empty result is valid, not a failure (review #1).
    """
    roots = _git_roots(store_path, ref)
    if not roots:
        return {}
    # One root is enough; accumulating across roots let one root's Removed
    # entry suppress a key another root reported as present.
    return _state_from_root(tree, roots[0], ref)


def _state_from_root(tree: Any, root: str, ref: str) -> dict[bytes, bytes]:
    """Reconstruct ``ref``'s state by replaying the delta from ``root``."""
    data: dict[bytes, bytes] = {}
    # Keys removed since the root must not be re-added by the fill-in below.
    removed: set[bytes] = set()

    for kv in tree.diff(root, ref):
        key = bytes(kv.key)
        op = kv.operation
        kind = op.operation_type
        if kind == "Removed":
            data.pop(key, None)
            removed.add(key)
            continue
        value = op.value if kind == "Added" else op.new_value
        if value is not None:
            data[key] = bytes(value)
            removed.discard(key)

    # Keys present in the root and untouched since never appear in ``diff``.
    root_items = tree.get_keys_at_ref(root)
    # Known limit: a root commit holding 1024+ keys is truncated here. Memoir's
    # root is always the empty initial commit, so this only fires on rewritten
    # history; warn rather than truncate silently (review #3).
    if len(root_items) >= _PROLLYTREE_KEY_LIMIT:
        logger.warning(
            "root commit %s has at least %d keys; unchanged root keys may be "
            "missing from this listing",
            root[:8],
            _PROLLYTREE_KEY_LIMIT,
        )
    for key, value in root_items:
        key_bytes = bytes(key)
        if key_bytes not in removed:
            data.setdefault(key_bytes, bytes(value))

    return data


class ProllyTreeStore(BaseStore):
    """
    High-performance semantic memory store using ProllyTree.
    Implements LangGraph's BaseStore interface following the reference pattern.
    """

    def __init__(
        self,
        path: str,
        enable_versioning: bool = True,
        auto_commit: bool = True,
        cache_size: int = 10000,
        ref: str | None = None,
    ):
        """
        Initialize ProllyTree store.

        Storage layer is responsible only for storing and retrieving data.
        Classification is handled by higher layers (memory manager).

        ProllyTreeStore is strict: it opens an existing memoir store and
        refuses paths that aren't one yet. Use ``StoreService.create_store``
        (or ``memoir new``) to bootstrap a fresh store. Single init path =
        no surprise side-effects from running `memoir remember` in a random
        cwd.

        Args:
            path: Path to an existing memoir store (must contain a ``.git``
                directory when ``enable_versioning`` is True).
            enable_versioning: Whether to enable git-like versioning
            auto_commit: Whether to automatically commit on each put/delete operation
            cache_size: Size of internal caches
            ref: Read the store as it is at this branch (or commit) instead
                of the checked-out one. The tree is loaded from the ref's
                committed root without a checkout, so the store's HEAD and
                every other process are untouched; the store is then
                read-only (``put``/``delete``/``commit`` raise).
        """
        super().__init__()
        self.ref = ref

        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

        if enable_versioning and not (self.path / ".git").exists():
            raise FileNotFoundError(
                f"Not a memoir store: {self.path} (no .git directory). "
                f"Create one with `memoir new <path>` first, or pass "
                f"-s/--store / set MEMOIR_STORE / cd into an existing store."
            )

        # Defense-in-depth: refuse to open a path that is a git repository
        # with existing commits but no memoir-specific markers. ``data/``
        # alone is *not* a memoir marker — many project repos have one and
        # accepting it lets read-side callers (status, recall, UI server's
        # cwd fallback, etc.) lazy-materialize a fresh prolly tree inside
        # an unrelated project repo. ``is_memoir_store`` checks for the
        # backend lock, ``.git/prolly/``, or ``data/prolly_config_tree_config``.
        if enable_versioning and not is_memoir_store(self.path):
            import subprocess as _subprocess

            head_check = _subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.path),
                    "rev-parse",
                    "--verify",
                    "--quiet",
                    "HEAD",
                ],
                capture_output=True,
            )
            if head_check.returncode == 0:
                raise FileNotFoundError(
                    f"Not a memoir store: {self.path} is a git repository "
                    f"with existing commits but no memoir markers "
                    f"(no .git/memoir-backend, no .git/prolly/, no "
                    f"data/prolly_config_tree_config). Use `memoir new "
                    f"<path>` to create a memoir store explicitly, or "
                    f"point at an existing one."
                )

        # Initialize ProllyTree
        if enable_versioning:
            # Apply gc-safety configs to the .git of any memoir store opened
            # here. Idempotent, so retrofits legacy git-backed stores on
            # first open by a memoir version that includes this helper.
            harden_git_config(self.path)

            # Resolve the storage backend BEFORE creating data/ so the legacy
            # detector sees the on-disk state as it is now. Precedence:
            # per-store lock > on-disk detection > env var > File default.
            backend = resolve_backend(self.path)
            logger.debug("opening store at %s with backend=%s", self.path, backend)

            # Create data subdirectory for VersionedKvStore
            data_dir = self.path / "data"
            data_dir.mkdir(exist_ok=True)
            # VersionedKvStore (prollytree Rust binding) uses cwd to locate the
            # enclosing git repository even when handed an absolute path —
            # which means callers in non-git cwds (e.g. /tmp, ~/.memoir) get
            # "Not in a git repository" errors. Construction needs a chdir;
            # so do per-operation calls (`.insert`/`.update`/`.commit`/`.get`).
            # We chdir here for the constructor, then wrap the tree in
            # _CwdLockedTree so every later method call also chdir's first.
            # `VersionedKvStore(path, backend)` *initializes* a fresh tree
            # (running an "Initial commit") on every call — fine for first
            # creation, but overwrites the root_hash in
            # ``data/prolly_config_tree_config`` on a reopen, which silently
            # drops all prior data on the File backend. Use ``.open()`` when
            # the config already exists; the constructor only when this is
            # a brand-new dataset directory.
            prolly_config = data_dir / "prolly_config_tree_config"
            _saved_cwd = os.getcwd()
            try:
                os.chdir(str(self.path))
                # Suppress prollytree's "Failed to load tree from saved root
                # hash" stderr warning when ``_MEMOIR_SUPPRESS_NATIVE_IMPORT_STDERR=1``
                # (set by the CLI entrypoint). The warning fires on every
                # open of an existing store as part of prollytree's
                # optimistic fast-load → fall-back-to-config-load path,
                # even on healthy stores; real corruption surfaces as an
                # exception, not stderr noise. See `_native_stderr_quiet`.
                with _native_stderr_quiet():
                    if prolly_config.exists():
                        _raw_tree = VersionedKvStore.open(str(data_dir), backend)
                        fresh_init = False
                    else:
                        _raw_tree = VersionedKvStore(str(data_dir), backend)
                        fresh_init = True
            finally:
                os.chdir(_saved_cwd)
            self.tree = CwdLockedTree(_raw_tree, self.path)

            # If we just initialized a fresh prollytree (no prior config),
            # persist the resolved backend so future opens go straight to
            # the lock rather than re-running detection/env-default. This
            # covers direct ProllyTreeStore callers (e.g. ui/initializer.py)
            # that bypass StoreService.create_store. For callers that did
            # come through StoreService, the lock is already written with
            # the same value — this is idempotent.
            if fresh_init and not (self.path / ".git" / "memoir-backend").exists():
                write_backend_lock(self.path, backend)
        else:
            # Memory mode doesn't touch git, so no cwd wrapper needed.
            self.tree = ProllyTree("memory")

        self.enable_versioning = enable_versioning
        self.auto_commit = auto_commit
        # Storage layer doesn't need taxonomy, classifier, or search engine
        # These are handled by higher layers

        # Performance tracking
        self._stats = {"reads": 0, "writes": 0, "searches": 0, "classifications": 0}

        if ref is not None:
            if not enable_versioning:
                raise ValueError("ref= needs a versioned store")
            self.tree = _SnapshotTree(self.tree, ref, self.path)
            self.auto_commit = False

        # Memory mode has no history to replay, so it tracks its own keys.
        self._keys = set()

        # Committed state, replayed on first use. Loading it in __init__ made
        # every CLI call and hook pay a git subprocess plus a full replay
        # (review #7).
        self._items: dict[bytes, bytes] | None = None
        # (branch, head commit) the cache was built from; a mismatch means
        # the tree moved underneath us and the cache must be rebuilt.
        self._cache_source: tuple[str, str] | None = None

        # Track aggregated memories to avoid redundant updates
        self._aggregation_cache = {}

    def _cache_key(self) -> tuple[str, str] | None:
        """``(branch, that branch's commit)`` the cached snapshot describes.

        BranchService switches branches through ``tree`` directly, so call
        sites cannot be trusted to clear the cache (#2/#3/#4). Both values
        come from ``refs/heads/<current_branch>``: taking the branch from the
        handle and the commit from on-disk HEAD mixed two sources (#1).
        """
        ref = self.tree.current_branch()
        if isinstance(ref, bytes):
            ref = ref.decode("utf-8")
        ref = ref or "HEAD"

        # Resolve the commit from this handle's branch, not current_commit(),
        # which reports whatever branch the on-disk HEAD points at.
        result = run_git(
            self.path, "rev-parse", "--verify", "--quiet", f"refs/heads/{ref}"
        )
        if result.returncode != 0:
            # No provenance: skip caching and replay every time.
            return None
        head = result.stdout.strip()
        if not head:
            return None
        return ref, head

    def _committed(self) -> dict[bytes, bytes]:
        """Committed key/value state for this handle's branch (cached).

        Reads ``current_branch()`` rather than on-disk HEAD: another process
        moving HEAD made listing disagree with ``get()`` (review #5). A failed
        replay returns empty for that call but is not cached.
        """
        if not self.enable_versioning:
            return {}
        if isinstance(self.tree, _SnapshotTree):
            # A ref-scoped snapshot was replayed once and never changes.
            if self._items is None:
                self._items = dict(self.tree.items())
            return self._items

        # Key and replay target are the same commit, so a concurrent write
        # between the two cannot produce a key that describes other content.
        cache_key = self._cache_key()
        if (
            self._items is not None
            and cache_key is not None
            and self._cache_source == cache_key
        ):
            return self._items

        if cache_key is None:
            # No commit to pin to (branch deleted): replay by name, uncached.
            ref = self.tree.current_branch()
            if isinstance(ref, bytes):
                ref = ref.decode("utf-8")
            replay_target = ref or "HEAD"
        else:
            replay_target = cache_key[1]

        try:
            items = _replay_snapshot(self.tree, self.path, replay_target)
        except Exception as e:
            # Empty for this call only, and never a fallback to the
            # checked-out branch's data (review #1).
            logger.warning("could not enumerate %r: %s", replay_target, e)
            return {}

        # Cache only when the provenance is known, so a bad result cannot
        # become permanent.
        if cache_key is not None:
            self._items = items
            self._cache_source = cache_key
        return items

    def _staged(self) -> tuple[set[str], set[str]]:
        """Keys written and deleted since the last commit.

        ``get()`` and ``list_keys()`` see the staging area; the replayed
        history does not, so enumeration layers it on top (review #4).
        """
        if not self.enable_versioning or isinstance(self.tree, _SnapshotTree):
            return set(), set()

        written: set[str] = set()
        removed: set[str] = set()
        # ``status()`` reads the staging area and is not capped like list_keys.
        for key, state in self.tree.status():
            target = removed if state == "deleted" else written
            target.add(bytes(key).decode("utf-8"))
        return written, removed

    def all_keys(self) -> list[str]:
        """Every key in the store: committed snapshot plus staged changes.

        Single entry point for enumeration; ``tree.list_keys()`` stops at 1024
        keys and returns a different subset each call.
        """
        if not self.enable_versioning:
            return sorted(self._keys)

        written, removed = self._staged()
        keys = {key.decode("utf-8") for key in self._committed()}
        # Parentheses matter: ``keys | written - removed`` parses as
        # ``keys | (written - removed)`` and left staged deletes in place (#1).
        return sorted((keys | written) - removed)

    def all_items(self) -> dict[str, Any]:
        """Every key and decoded value, so callers skip a get() per key.

        promote and export used to call all_keys() and then read each value;
        the replay already has them (review #8).
        """
        if not self.enable_versioning:
            items = {}
            for key in self._keys:
                raw = self.tree.find(key.encode("utf-8"))
                if raw is not None:
                    items[key] = self._decode_value(raw)
            return dict(sorted(items.items()))

        written, removed = self._staged()

        items = {
            key.decode("utf-8"): self._decode_value(value)
            for key, value in self._committed().items()
            if key.decode("utf-8") not in removed
        }
        # Staged keys are not in the replay yet; read just those.
        for key in written:
            raw = self.tree.get(key.encode("utf-8"))
            if raw is not None:
                items[key] = self._decode_value(raw)

        return dict(sorted(items.items()))

    def _encode_value(self, value: Any) -> bytes:
        """Encode any value to bytes for storage."""
        if isinstance(value, bytes):
            return value
        elif isinstance(value, str):
            return value.encode("utf-8")
        else:
            # Use JSON for complex objects
            json_str = json.dumps(value, default=str)
            return json_str.encode("utf-8")

    def _decode_value(self, data: bytes) -> Any:
        """Decode bytes from storage back to original type."""
        if not data:
            return None
        try:
            # Try to decode as JSON first
            json_str = data.decode("utf-8")
            return json.loads(json_str)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Return as string if not JSON
            try:
                return data.decode("utf-8")
            except UnicodeDecodeError:
                return data

    # BaseStore interface methods
    def batch(self, ops: list[tuple]) -> list[Any]:
        """Batch operations - required by BaseStore."""
        results = []
        for op in ops:
            if len(op) == 2:
                method, args = op
                result = getattr(self, method)(*args)
                results.append(result)
        return results

    def abatch(self, ops: list[tuple]) -> list[Any]:
        """Async batch operations - synchronous implementation."""
        return self.batch(ops)

    def search(
        self, namespace: tuple, *, filter: dict | None = None, limit: int = 10
    ) -> list[tuple]:
        """Search for items in a namespace."""
        self._stats["searches"] += 1
        prefix = ":".join(namespace) + ":"
        results = []

        try:
            # all_keys() merges committed and staged keys; the old registry
            # was capped at 1024.
            count = 0
            for full_key in self.all_keys():
                if count >= limit:
                    break

                if full_key.startswith(prefix):
                    key_bytes = full_key.encode("utf-8")
                    if self.enable_versioning:
                        value = self.tree.get(key_bytes)
                    else:
                        value = self.tree.find(key_bytes)
                    decoded_value = self._decode_value(value)

                    # Apply filter if provided
                    if filter and not all(
                        decoded_value.get(k) == v
                        for k, v in filter.items()
                        if isinstance(decoded_value, dict)
                    ):
                        continue

                    # Extract item key from full key
                    item_key = full_key[len(prefix) :]
                    results.append((namespace, item_key, decoded_value))
                    count += 1
        except Exception as e:
            logger.error(f"Error searching namespace {namespace}: {e}")

        return results

    def put(self, namespace: tuple, key: str, value: dict) -> None:
        """Store a value in a namespace."""
        self._refuse_write("put")
        self._stats["writes"] += 1
        full_key = ":".join(namespace) + ":" + key
        key_bytes = full_key.encode("utf-8")
        value_bytes = self._encode_value(value)

        try:
            with self._write_lock():
                self._follow_head()
                self._put_locked(namespace, key, key_bytes, value_bytes)

            # Memory mode tracks its own keys; the replay cache is now stale.
            self._keys.add(full_key)
            self._items = None
            self._cache_source = None
        except Exception as e:
            logger.error(f"Error storing {full_key}: {e}")
            raise

    def _put_locked(
        self, namespace: tuple, key: str, key_bytes: bytes, value_bytes: bytes
    ) -> None:
        if self.enable_versioning:
            # VersionedKvStore API - check if key exists using get
            existing = self.tree.get(key_bytes)
            if existing:
                self.tree.update(key_bytes, value_bytes)
            else:
                self.tree.insert(key_bytes, value_bytes)
            # Commit the change if auto_commit is enabled
            if self.auto_commit:
                self.tree.commit(f"Store {key} in {':'.join(namespace)}")
        else:
            # ProllyTree API - check if key exists using find
            existing = self.tree.find(key_bytes)
            if existing:
                self.tree.update(key_bytes, value_bytes)
            else:
                self.tree.insert(key_bytes, value_bytes)

    def _refuse_write(self, what: str) -> None:
        if self.ref is not None:
            raise ReadOnlyStoreError(
                f"Cannot {what}: this store is a read-only view of '{self.ref}'. "
                f"Check the branch out, or route the write with --branch."
            )

    def _write_lock(self):
        """The store-wide write lock, a no-op for memory mode."""
        if not self.enable_versioning:
            return contextlib.nullcontext()
        return store_write_lock(self.path)

    def _follow_head(self) -> None:
        """Commit onto the branch the store has checked out *now*.

        The tree remembers the branch it was opened on. A process that opened
        the store while another had a branch routed (``--branch`` checks it
        out for a write), or that stays open across someone else's checkout,
        would otherwise commit onto that stale branch once it gets the lock.
        Called with the write lock held.
        """
        if not self.enable_versioning:
            return
        try:
            head = (self.path / ".git" / "HEAD").read_text(encoding="utf-8").strip()
        except OSError:
            return
        prefix = "ref: refs/heads/"
        if not head.startswith(prefix):
            return
        on_disk = head[len(prefix) :]
        current = self.tree.current_branch()
        if isinstance(current, bytes):
            current = current.decode("utf-8")
        if current == on_disk:
            return
        logger.info(
            "store checked out '%s' since this instance loaded '%s': following it",
            on_disk,
            current,
        )
        self.tree.checkout(on_disk)

        # Drop the cache instead of replaying now; the caller may not
        # enumerate at all after a checkout.
        self._keys = set()
        self._items = None
        self._cache_source = None

    def get(self, namespace: tuple, key: str) -> dict | None:
        """Retrieve a value from a namespace."""
        self._stats["reads"] += 1
        full_key = ":".join(namespace) + ":" + key
        key_bytes = full_key.encode("utf-8")

        try:
            if self.enable_versioning:
                # VersionedKvStore API
                data = self.tree.get(key_bytes)
            else:
                # ProllyTree API
                data = self.tree.find(key_bytes)
            return self._decode_value(data) if data else None
        except Exception as e:
            logger.error(f"Error getting key {full_key}: {e}")
            return None

    def delete(self, namespace: tuple, key: str) -> None:
        """Delete a key from a namespace."""
        self._refuse_write("delete")
        full_key = ":".join(namespace) + ":" + key
        key_bytes = full_key.encode("utf-8")

        try:
            with self._write_lock():
                self._follow_head()
                self.tree.delete(key_bytes)

                self._keys.discard(full_key)

                if self.enable_versioning and self.auto_commit:
                    self.tree.commit(f"Delete {key} from {':'.join(namespace)}")

            # With auto_commit=False the delete lives in the staging area,
            # which _staged() reads.
            self._items = None
            self._cache_source = None
        except Exception as e:
            logger.error(f"Error deleting {full_key}: {e}")

    def commit(self, message: str = "Manual commit") -> str | None:
        """
        Manually commit pending changes to the versioned store.

        This is useful when auto_commit is disabled and you want to batch
        multiple operations before committing.

        Args:
            message: Commit message

        Returns:
            Commit hash if versioning is enabled, None otherwise
        """
        if not self.enable_versioning:
            logger.warning("Commit requested but versioning is not enabled")
            return None
        self._refuse_write("commit")

        try:
            with self._write_lock():
                self._follow_head()
                commit_hash = self.tree.commit(message)

            # The staging area is empty now; the cached snapshot is stale.
            self._items = None
            self._cache_source = None

            logger.debug(f"Manual commit successful: {message}")
            return commit_hash
        except Exception as e:
            logger.error(f"Error committing changes: {e}")
            raise

    def get_key_history(
        self, namespace: tuple, key: str, limit: int = 10
    ) -> list[dict]:
        """
        Get commit history for a specific key.

        Args:
            namespace: Namespace tuple
            key: Key to get history for
            limit: Maximum number of commits to return

        Returns:
            List of commit dictionaries with id, timestamp, message, author, committer
        """
        if not self.enable_versioning:
            return []

        full_key = ":".join(namespace) + ":" + key
        key_bytes = full_key.encode("utf-8")

        try:
            commits = self.tree.get_commits_for_key(key_bytes)
            # Limit results and return most recent first
            return commits[:limit]
        except Exception as e:
            logger.error(f"Error getting history for {full_key}: {e}")
            return []

    def get_key_at_commit(
        self, namespace: tuple, key: str, commit_id: str
    ) -> dict | None:
        """
        Get the value of a key at a specific commit.

        Note: Current implementation returns None since VersionedKvStore doesn't support
        direct commit checkout. This is a placeholder for future enhancement.

        Args:
            namespace: Namespace tuple
            key: Key to retrieve
            commit_id: Commit ID to retrieve from

        Returns:
            None (historical content retrieval not yet implemented)
        """
        if not self.enable_versioning:
            return None

        # TODO: Implement historical content retrieval when VersionedKvStore supports it
        # Current limitation: VersionedKvStore only supports branch checkout, not commit checkout
        logger.debug(
            f"Historical content retrieval not yet implemented for commit {commit_id[:8]}"
        )
        return None

    def create_time_snapshot(self, snapshot_name: str) -> bool:
        """
        Create a branch snapshot at the current point in time.

        When auto_commit=False, this will first commit any pending changes
        before creating the snapshot to ensure all recent changes are included.

        Args:
            snapshot_name: Name for the snapshot branch

        Returns:
            True if snapshot created successfully
        """
        if not self.enable_versioning:
            return False

        try:
            # If auto_commit is disabled, commit pending changes before snapshot
            if not self.auto_commit:
                commit_hash = self.commit(
                    f"Auto-commit before snapshot: {snapshot_name}"
                )
                if commit_hash:
                    logger.debug(
                        f"Auto-committed pending changes before snapshot: {commit_hash[:8]}"
                    )

            self.tree.create_branch(snapshot_name)
            logger.debug(f"Created time snapshot: {snapshot_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to create snapshot {snapshot_name}: {e}")
            return False

    def get_state_at_snapshot(
        self, namespace: tuple, snapshot_name: str
    ) -> dict[str, Any]:
        """
        Get all keys in a namespace at a specific snapshot.

        Args:
            namespace: Namespace tuple
            snapshot_name: Name of the snapshot branch

        Returns:
            Dictionary of key -> value at that snapshot
        """
        if not self.enable_versioning:
            return {}

        try:
            # Save current branch
            current_branch = self.tree.current_branch()

            # Switch to snapshot
            self.tree.checkout(snapshot_name)

            # The cached snapshot belongs to the previous branch.
            self._items = None
            self._cache_source = None

            # Get all keys in namespace
            state = {}
            namespace_prefix = ":".join(namespace) + ":"

            # all_keys() rather than list_keys(), which caps at 1024.
            keys = [key.encode("utf-8") for key in self.all_keys()]
            for key in keys:
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                if key_str.startswith(namespace_prefix):
                    # Get value
                    value = self.tree.get(
                        key if isinstance(key, bytes) else key.encode("utf-8")
                    )
                    if value:
                        # Extract the key without namespace prefix
                        short_key = key_str[len(namespace_prefix) :]
                        state[short_key] = self._decode_value(value)

            # Return to original branch
            self.tree.checkout(current_branch)
            self._items = None
            self._cache_source = None

            return state

        except Exception as e:
            logger.error(f"Failed to get state at snapshot {snapshot_name}: {e}")
            # Try to return to original branch
            with contextlib.suppress(Exception):
                self.tree.checkout(current_branch)
            # The error path restores the branch, so the snapshot's keys
            # must not stay cached here (review #4).
            self._items = None
            self._cache_source = None
            return {}

    # Enhanced methods for semantic memory functionality
    async def store_memory_async(
        self, namespace: str, content: Any, key: str
    ) -> MemoryItem:
        """
        Store a memory at the given semantic key.

        Note: Classification must be done by the caller (memory manager).
        Storage layer is responsible only for storing, not classifying.

        Args:
            namespace: User/agent namespace
            content: Memory content to store
            key: Semantic key where to store (REQUIRED - no classification here)

        Returns:
            MemoryItem with storage results
        """
        # Storage layer: just use the provided semantic key (no classification)
        semantic_key = key
        confidence = 1.0  # Confidence is determined by the caller (memory manager)

        # Use semantic key for aggregation
        storage_key = semantic_key

        # Create memory entry (not the full item)
        memory_entry = {
            "content": content,
            "confidence": confidence,
            "timestamp": time.time(),
            "metadata": {},
        }

        # Convert namespace to tuple format
        if ":" in namespace:
            namespace_parts = namespace.split(":")
            namespace_tuple = tuple(namespace_parts)
        else:
            namespace_tuple = (namespace,)

        # Get existing aggregated memory or create new one
        existing = self.get(namespace_tuple, storage_key)

        if existing and isinstance(existing, dict) and "memories" in existing:
            # Append to existing aggregated memory
            aggregated = AggregatedMemory(**existing)
            aggregated.memories.append(memory_entry)
            aggregated.count += 1
            aggregated.last_timestamp = memory_entry["timestamp"]
            aggregated.last_updated = time.time()
        else:
            # Create new aggregated memory
            aggregated = AggregatedMemory(
                path=semantic_key,
                memories=[memory_entry],
                count=1,
                first_timestamp=memory_entry["timestamp"],
                last_timestamp=memory_entry["timestamp"],
            )

        # Store the aggregated memory
        self.put(namespace_tuple, storage_key, aggregated.model_dump())

        # Create MemoryItem for return value (for compatibility)
        item = MemoryItem(
            key=semantic_key,
            namespace=namespace,
            content=content,
            confidence=confidence,
            timestamp=memory_entry["timestamp"],
        )

        if self.enable_versioning and hasattr(self.tree, "get_head"):
            item.version = self.tree.get_head()

        return item

    # Sync store_memory method removed - use store_memory_async for all operations
    # This eliminates the async/sync mismatch and fallback issues

    async def asearch(self, namespace: str, path_prefix: str) -> list[tuple[str, Any]]:
        """
        Async search for items with a given path prefix.
        Used by HierarchicalSearchEngine.

        Args:
            namespace: User namespace
            path_prefix: Path prefix to search for

        Returns:
            List of (semantic_key, data) tuples
        """
        # Use synchronous search with prefix
        results = []
        # Convert string namespace to tuple format
        # "memory:general" -> ("memory", "general")
        namespace_parts = namespace.split(":")
        namespace_tuple = tuple(namespace_parts)

        search_results = self.search(namespace_tuple, limit=100)

        for _, storage_key, data in search_results:
            semantic_key = storage_key

            # Check if semantic path matches prefix
            if semantic_key.startswith(path_prefix):
                # For aggregated memories, we return them as-is
                # The search engine will handle expanding them
                if isinstance(data, dict) and "memories" in data:
                    # This is an aggregated memory - return it
                    results.append((semantic_key, data))
                else:
                    # Legacy single memory format
                    results.append((semantic_key, data))

        return results

    async def retrieve_memories_async(
        self, namespace: str, query: str, limit: int = 10
    ) -> list[MemoryItem]:
        """
        Retrieve memories using semantic search (async version).

        Args:
            namespace: User/agent namespace
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching memory items
        """
        # Use the hierarchical search engine to find relevant memories
        search_results = await self.search_engine.search(query, namespace)

        # Convert search results to memory items with deduplication
        memories = []
        seen_content = set()

        for result in search_results:
            # The search result contains combined content from multiple items
            if result.combined_content:
                try:
                    # Split combined content back into individual memories
                    individual_contents = result.combined_content.split(" | ")
                    for content_text in individual_contents:
                        if content_text.strip():
                            # Create a memory item from the content
                            memory = MemoryItem(
                                key=result.path,
                                namespace=result.namespace,
                                content=content_text.strip(),
                                confidence=1.0,  # Default confidence
                                timestamp=time.time(),
                            )
                            # Deduplicate by content
                            content_hash = hash(memory.content)
                            if content_hash not in seen_content:
                                seen_content.add(content_hash)
                                memories.append(memory)
                                # Stop when we have enough unique results
                                if len(memories) >= limit:
                                    break
                    if len(memories) >= limit:
                        break
                except Exception as e:
                    logger.warning(f"Failed to parse memory item: {e}")

        return memories

    def retrieve_memories(
        self, namespace: str, query: str, limit: int = 10
    ) -> list[MemoryItem]:
        """
        Retrieve memories using semantic search (sync fallback).

        Note: This is a simple fallback. For proper semantic search,
        use retrieve_memories_async() which leverages the HierarchicalSearchEngine.

        Args:
            namespace: User/agent namespace
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching memory items
        """
        logger.warning(
            "Using fallback sync search. For better results, use retrieve_memories_async()"
        )

        # Simple fallback - just return all memories
        all_memories = []
        search_results = self.search((namespace,), limit=limit)

        for _, _key, data in search_results:
            if isinstance(data, dict):
                try:
                    memory = MemoryItem(**data)
                    all_memories.append(memory)
                except Exception as e:
                    logger.warning(f"Failed to parse memory item: {e}")

        return all_memories

    def get_statistics(self) -> dict[str, Any]:
        """Get store statistics."""
        # all_keys() counts committed plus staged keys, without the 1024 cap.
        keys = self.all_keys()
        stats = {
            "performance": self._stats.copy(),
            "total_keys": len(keys),
            "total_namespaces": len({key.split(":")[0] for key in keys}),
        }

        if self.enable_versioning and hasattr(self.tree, "get_head"):
            try:
                stats["versioning"] = {
                    "current_commit": self.tree.get_head(),
                }
                if hasattr(self.tree, "log"):
                    commits = self.tree.log()
                    stats["versioning"]["total_commits"] = len(commits)
            except Exception:
                pass

        return stats

    def export_namespace(self, namespace: str, output_path: str) -> None:
        """
        Export all memories from a namespace to JSON.

        Iterates ``all_items()`` rather than ``search(..., limit=1000)``: the
        old cap silently dropped everything past the thousandth memory, and
        the underlying ``list_keys`` cap made that loss non-deterministic.

        Args:
            namespace: Namespace to export
            output_path: Path to save JSON file
        """
        # One all_items() pass instead of all_keys() plus a get() per key,
        # and no search(limit=1000) cap (review #8).
        prefix = f"{namespace}:"
        memories = {
            full_key[len(prefix) :]: data
            for full_key, data in self.all_items().items()
            if full_key.startswith(prefix)
        }

        with open(output_path, "w") as f:
            json.dump(
                {
                    "namespace": namespace,
                    "timestamp": time.time(),
                    "memories": memories,
                },
                f,
                indent=2,
            )

        logger.info(f"Exported {len(memories)} memories to {output_path}")


class ReadOnlyStoreError(RuntimeError):
    """A write was attempted on a store opened as a read-only view of a ref."""


class _SnapshotTree:
    """The key-value state of one ref, read once; the ``VersionedKvStore``
    surface the adapter's read paths use, with every write refused.

    Built from commit history (``diff`` from the root) rather than
    ``get_keys_at_ref`` alone, which stops at 1024 keys: no checkout, so the
    store's HEAD and the other processes sharing the store never notice
    (issue #179).
    """

    def __init__(self, tree: Any, ref: str, store_path: Path):
        # _resolve_ref() rejects refs the binding cannot resolve (review #2).
        # store_path is required now; the old None branch was unreachable and
        # duplicated this error message (review #9b).
        resolved = _resolve_ref(store_path, ref)
        if resolved is None:
            raise ValueError(
                f"Branch '{ref}' does not exist. Create it explicitly with "
                f"`memoir branch {ref}`, or use a write command "
                f"(e.g. `memoir remember --branch={ref} ...`) to bootstrap it."
            )

        self._ref = ref
        # An empty branch is a valid snapshot; no fallback to list_keys().
        self._data = _replay_snapshot(tree, store_path, resolved)

    def get(self, key: bytes) -> bytes | None:
        return self._data.get(bytes(key))

    find = get

    def list_keys(self) -> list[bytes]:
        return list(self._data.keys())

    def items(self) -> list[tuple[bytes, bytes]]:
        return list(self._data.items())

    def current_branch(self) -> str:
        return self._ref

    def __getattr__(self, name: str) -> Any:
        # Anything not implemented above (status, checkout, ...) is a write
        # attempt on a read-only view.
        raise ReadOnlyStoreError(
            f"Cannot {name}: this store is a read-only view of '{self._ref}'."
        )

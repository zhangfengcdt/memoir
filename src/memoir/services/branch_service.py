# SPDX-License-Identifier: Apache-2.0
"""
Branch service for git operations and version control.

This service extracts the business logic from ui/handlers/branch_handler.py
to be shared by CLI, TUI, SDK, and HTTP handlers.
"""

import contextlib
import logging
from collections.abc import Iterator
from enum import Enum
from pathlib import Path
from typing import Any

from prollytree import ConflictResolution

from memoir.services.base import (
    BaseService,
    GitOperationError,
    ServiceError,
    StoreNotFoundError,
)
from memoir.services.models import (
    BranchInfo,
    CheckoutResult,
    CommitInfo,
    MergeResult,
)


class MergeStrategy(str, Enum):
    """Merge conflict resolution strategies."""

    OURS = "ours"  # Keep current branch's version (TakeDestination)
    THEIRS = "theirs"  # Take incoming branch's version (TakeSource)
    SKIP = "skip"  # Skip conflicting keys (IgnoreAll)

    def to_conflict_resolution(self) -> ConflictResolution:
        """Convert to prollytree ConflictResolution."""
        mapping = {
            MergeStrategy.OURS: ConflictResolution.TakeDestination,
            MergeStrategy.THEIRS: ConflictResolution.TakeSource,
            MergeStrategy.SKIP: ConflictResolution.IgnoreAll,
        }
        return mapping[self]


logger = logging.getLogger(__name__)


class BranchService(BaseService):
    """
    Service for git branch and version control operations.

    This provides branch management, checkout, merge, and commit history
    operations using git commands.
    """

    def list_branches(self) -> BranchInfo:
        """
        Get list of branches in the store using VersionedKvStore.

        Returns:
            BranchInfo with list of branches and current branch

        Raises:
            StoreNotFoundError: If store path doesn't exist
            GitOperationError: If git operation fails
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            store = self._get_store()

            # Get branch list from VersionedKvStore
            branches_raw = store.tree.list_branches()
            branches = [
                b.decode("utf-8") if isinstance(b, bytes) else b for b in branches_raw
            ]

            # Get current branch
            current_branch = store.tree.current_branch()
            if isinstance(current_branch, bytes):
                current_branch = current_branch.decode("utf-8")

            return BranchInfo(branches=branches, current=current_branch)

        except Exception as e:
            logger.error(f"Failed to list branches: {e}")
            raise GitOperationError(f"Failed to list branches: {e}")

    def get_commits(
        self,
        branch: str = "HEAD",
        limit: int = 20,
        annotate: bool = False,
    ) -> list[CommitInfo]:
        """
        Get commit history for the store.

        Args:
            branch: Branch or commit ref to get history for
            limit: Maximum number of commits to return
            annotate: When true, populate ``tags`` and ``refs`` on each
                ``CommitInfo`` via a single ``git show-ref`` call.
                Default False preserves legacy behaviour.

        Returns:
            List of CommitInfo objects

        Raises:
            StoreNotFoundError: If store path doesn't exist
            GitOperationError: If git operation fails
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            # %P adds space-separated parent hashes; empty for root commit.
            # We place it last so any pipe characters in the subject still
            # land in ``parts[2]`` (we cap that column via maxsplit below).
            result = self._run_git_command(
                [
                    "log",
                    branch,
                    f"-{limit}",
                    "--pretty=format:%H|%h|%s|%an|%ae|%at|%P",
                ],
                check=False,
            )

            commits = []
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split("|")
                        if len(parts) >= 7:
                            parents_str = parts[6].strip()
                            parents = parents_str.split() if parents_str else []
                            commits.append(
                                CommitInfo(
                                    hash=parts[0],
                                    short_hash=parts[1],
                                    message=parts[2],
                                    author=parts[3],
                                    email=parts[4],
                                    timestamp=int(parts[5]),
                                    parents=parents,
                                )
                            )
                        elif len(parts) >= 6:
                            # Backwards compatibility for the rare case where
                            # %P expands to an empty string at the end and the
                            # trailing pipe gets stripped by git's output.
                            commits.append(
                                CommitInfo(
                                    hash=parts[0],
                                    short_hash=parts[1],
                                    message=parts[2],
                                    author=parts[3],
                                    email=parts[4],
                                    timestamp=int(parts[5]),
                                )
                            )

            if annotate and commits:
                refs_by_hash = self._collect_refs()
                for c in commits:
                    entries = refs_by_hash.get(c.hash, [])
                    for ref in entries:
                        if ref.startswith("refs/tags/"):
                            c.tags.append(ref[len("refs/tags/") :])
                        elif ref.startswith("refs/heads/"):
                            c.refs.append(ref[len("refs/heads/") :])
                        else:
                            c.refs.append(ref)

            return commits

        except Exception as e:
            logger.error(f"Failed to get commits: {e}")
            raise GitOperationError(f"Failed to get commits: {e}")

    def _collect_refs(self) -> dict[str, list[str]]:
        """Map commit-hash → list of ref names (``refs/heads/...``,
        ``refs/tags/...``) that point at it.

        One ``git show-ref`` call — O(branches + tags), not O(commits).
        Returns an empty dict if the repo has no refs yet.
        """
        result = self._run_git_command(["show-ref"], check=False)
        out: dict[str, list[str]] = {}
        if result.returncode != 0 or not result.stdout:
            return out
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) != 2:
                continue
            commit_hash, ref = parts
            out.setdefault(commit_hash, []).append(ref)
        return out

    def get_current_branch(self) -> tuple[str, str | None]:
        """
        Get the current branch and commit.

        Returns:
            Tuple of (branch_name, short_commit_hash)

        Raises:
            StoreNotFoundError: If store path doesn't exist
            GitOperationError: If git operation fails
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            store = self._get_store()

            # Get current branch from VersionedKvStore
            current_branch = store.tree.current_branch()
            if isinstance(current_branch, bytes):
                current_branch = current_branch.decode("utf-8")

            # Get current commit
            current_commit = None
            try:
                commit_id = store.tree.current_commit()
                if commit_id:
                    # Convert bytes to string if needed
                    if isinstance(commit_id, bytes):
                        commit_id = commit_id.hex()
                    current_commit = commit_id[:8] if len(commit_id) > 8 else commit_id
            except Exception:
                pass

            return current_branch, current_commit

        except Exception as e:
            logger.error(f"Failed to get current branch: {e}")
            raise GitOperationError(f"Failed to get current branch: {e}")

    @contextlib.contextmanager
    def routed_to(self, branch: str | None, *, auto_create: bool) -> Iterator[None]:
        """Temporarily route store operations to ``branch``, then restore HEAD.

        Used by per-call --branch / MEMOIR_BRANCH routing (issue #123) so a
        single command can target an agent's branch without flipping the
        repo's checkout state for everything else in the process.

        Args:
            branch: Target branch. ``None`` makes this a no-op so callers can
                pass through whatever they read from the CLI option without
                branching their own code.
            auto_create: True for writes (`memoir remember --branch=new-bot`
                bootstraps the branch off current HEAD). False for reads
                (`memoir recall --branch=typo` errors instead of silently
                returning empty).

        Raises:
            ServiceError: when the branch doesn't exist and auto_create is False,
                or when the current branch can't be read (the contract requires
                HEAD restoration on exit, which is impossible without it).
        """
        if branch is None:
            yield
            return

        store = self._get_store()

        # Capture HEAD up front. We must know what to restore to — if we
        # can't read it, refuse to proceed rather than silently leaking the
        # routed branch out of the with-block.
        try:
            current = store.tree.current_branch()
        except Exception as e:
            raise ServiceError(
                f"Cannot route to '{branch}': failed to read current branch "
                f"({e}). Run `memoir status` to inspect the store."
            ) from e
        original = current.decode("utf-8") if isinstance(current, bytes) else current

        if original == branch:
            # Already on the target; nothing to checkout and nothing to restore.
            yield
            return

        branches_raw = store.tree.list_branches()
        branches = [
            b.decode("utf-8") if isinstance(b, bytes) else b for b in branches_raw
        ]

        if branch not in branches:
            if not auto_create:
                raise ServiceError(
                    f"Branch '{branch}' does not exist. Create it explicitly with "
                    f"`memoir branch {branch}`, or use a write command "
                    f"(e.g. `memoir remember --branch={branch} ...`) to bootstrap it."
                )
            # prollytree's create_branch also checks out the new branch, so
            # the subsequent checkout(branch) below is a cheap no-op.
            store.tree.create_branch(branch)

        try:
            store.tree.checkout(branch)
            yield
        finally:
            if original != branch:
                try:
                    store.tree.checkout(original)
                except Exception as restore_err:
                    # Don't re-raise: a finally-block exception would mask the
                    # original wrapped-block exception (if any). Log loudly
                    # instead so the operator knows the store is now stuck on
                    # `branch` and how to recover.
                    logger.error(
                        "routed_to: failed to restore HEAD from '%s' to '%s': "
                        "%s. Store is currently checked out on '%s' — restore "
                        "manually with `memoir checkout %s`.",
                        branch,
                        original,
                        restore_err,
                        branch,
                        original,
                    )

    def checkout(
        self,
        target: str,
        create_branch: str | None = None,
        create_if_missing: bool = False,
    ) -> CheckoutResult:
        """
        Checkout a branch.

        Uses VersionedKvStore's native checkout to ensure data consistency.

        Note: Currently only branch names are supported. Commit hash checkout
        depends on VersionedKvStore implementation and may not be available.

        Args:
            target: Branch name to checkout
            create_branch: If provided, create this branch from target
            create_if_missing: If True and target branch doesn't exist, create it

        Returns:
            CheckoutResult with success status and current branch

        Raises:
            StoreNotFoundError: If store path doesn't exist
            GitOperationError: If git operation fails
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            store = self._get_store()

            if create_branch:
                # Create new branch from target, then checkout
                try:
                    # First checkout target
                    store.tree.checkout(target)
                    # Then create branch
                    store.tree.create_branch(create_branch)
                    # Checkout the new branch
                    store.tree.checkout(create_branch)
                    message = f"Created and switched to new branch '{create_branch}' from {target[:8] if len(target) > 8 else target}"
                except Exception as e:
                    return CheckoutResult(
                        success=False,
                        target=target,
                        current_branch="",
                        error=str(e),
                    )
            else:
                # Get list of branches to check if target exists
                try:
                    branches = store.tree.list_branches()
                    branch_names = [
                        b.decode("utf-8") if isinstance(b, bytes) else b
                        for b in branches
                    ]
                except Exception:
                    branch_names = []

                target_exists = target in branch_names

                if target_exists:
                    # Checkout existing branch
                    try:
                        store.tree.checkout(target)
                        message = f"Switched to {target}"
                    except Exception as e:
                        return CheckoutResult(
                            success=False,
                            target=target,
                            current_branch="",
                            error=str(e),
                        )
                elif create_if_missing:
                    # Create and checkout new branch
                    try:
                        store.tree.create_branch(target)
                        store.tree.checkout(target)
                        message = f"Created and switched to new branch '{target}'"
                    except Exception as e:
                        return CheckoutResult(
                            success=False,
                            target=target,
                            current_branch="",
                            error=str(e),
                        )
                else:
                    return CheckoutResult(
                        success=False,
                        target=target,
                        current_branch="",
                        error=f"Branch or commit '{target}' not found",
                    )

            # Get current branch from store
            try:
                current_branch = store.tree.current_branch()
                if isinstance(current_branch, bytes):
                    current_branch = current_branch.decode("utf-8")
            except Exception:
                current_branch = target

            return CheckoutResult(
                success=True,
                target=target,
                current_branch=current_branch,
                message=message,
            )

        except Exception as e:
            logger.error(f"Checkout failed: {e}")
            return CheckoutResult(
                success=False,
                target=target,
                current_branch="",
                error=str(e),
            )

    def create_branch(
        self,
        branch_name: str,
        from_ref: str | None = None,
    ) -> CheckoutResult:
        """
        Create a new branch using VersionedKvStore.

        Args:
            branch_name: Name for the new branch
            from_ref: Reference to create branch from (currently creates from current state)

        Returns:
            CheckoutResult with success status

        Raises:
            StoreNotFoundError: If store path doesn't exist
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            store = self._get_store()

            # Save current branch to restore later
            original_branch = None
            try:
                original_branch = store.tree.current_branch()
                if isinstance(original_branch, bytes):
                    original_branch = original_branch.decode("utf-8")
            except Exception:
                pass

            # If from_ref specified, checkout that first
            if from_ref and from_ref != "HEAD":
                try:
                    store.tree.checkout(from_ref)
                except Exception as e:
                    return CheckoutResult(
                        success=False,
                        target=branch_name,
                        current_branch=original_branch or "",
                        error=f"Cannot checkout '{from_ref}': {e}",
                    )

            # Create the branch
            try:
                store.tree.create_branch(branch_name)
            except Exception as e:
                # Restore original branch on failure
                if original_branch and from_ref:
                    with contextlib.suppress(Exception):
                        store.tree.checkout(original_branch)
                return CheckoutResult(
                    success=False,
                    target=branch_name,
                    current_branch=original_branch or "",
                    error=str(e),
                )

            # Restore original branch after creating new branch
            if original_branch and from_ref:
                with contextlib.suppress(Exception):
                    store.tree.checkout(original_branch)

            # Get current branch
            try:
                current_branch = store.tree.current_branch()
                if isinstance(current_branch, bytes):
                    current_branch = current_branch.decode("utf-8")
            except Exception:
                current_branch = original_branch or "main"

            return CheckoutResult(
                success=True,
                target=branch_name,
                current_branch=current_branch,
                message=f"Created branch '{branch_name}'"
                + (f" from {from_ref}" if from_ref else ""),
            )

        except Exception as e:
            logger.error(f"Failed to create branch: {e}")
            return CheckoutResult(
                success=False,
                target=branch_name,
                current_branch="",
                error=str(e),
            )

    def delete_branch(
        self,
        branch_name: str,
        force: bool = False,
    ) -> CheckoutResult:
        """
        Delete a branch.

        Args:
            branch_name: Name of branch to delete
            force: Force delete even if not fully merged

        Returns:
            CheckoutResult with success status

        Raises:
            StoreNotFoundError: If store path doesn't exist
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            # Check if trying to delete current branch
            current_branch, _ = self.get_current_branch()
            if current_branch == branch_name:
                return CheckoutResult(
                    success=False,
                    target=branch_name,
                    current_branch=current_branch,
                    error=f"Cannot delete current branch '{branch_name}'. Switch to another branch first.",
                )

            # Delete the branch
            delete_flag = "-D" if force else "-d"
            result = self._run_git_command(
                ["branch", delete_flag, branch_name],
                check=False,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                if "not fully merged" in error_msg:
                    error_msg = f"Branch '{branch_name}' is not fully merged. Use force=True to delete anyway."
                return CheckoutResult(
                    success=False,
                    target=branch_name,
                    current_branch=current_branch,
                    error=error_msg,
                )

            return CheckoutResult(
                success=True,
                target=branch_name,
                current_branch=current_branch,
                message=f"Deleted branch '{branch_name}'",
            )

        except Exception as e:
            logger.error(f"Failed to delete branch: {e}")
            return CheckoutResult(
                success=False,
                target=branch_name,
                current_branch="",
                error=str(e),
            )

    def merge(
        self,
        source_branch: str,
        strategy: MergeStrategy = MergeStrategy.SKIP,
    ) -> MergeResult:
        """
        Merge a branch into current branch using ProllyTree's native merge.

        Args:
            source_branch: Branch to merge into current
            strategy: Conflict resolution strategy (ours, theirs, skip)

        Returns:
            MergeResult with success status and any conflicts

        Raises:
            StoreNotFoundError: If store path doesn't exist
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            # Get current branch
            current_branch, _ = self.get_current_branch()

            # Get the store's ProllyTree
            store = self._get_store()

            # First, try merge to detect conflicts
            success, conflicts = store.tree.try_merge(source_branch)

            if success:
                # No conflicts - try_merge already applied the merge
                # But we need to get the commit hash, so call merge() anyway
                # to ensure we have a proper merge commit
                try:
                    # Get current commit as the merge commit hash
                    commit_hash = store.tree.current_commit()
                    # Convert bytes to string if needed
                    if isinstance(commit_hash, bytes):
                        commit_hash = commit_hash.hex()
                    return MergeResult(
                        success=True,
                        source_branch=source_branch,
                        target_branch=current_branch,
                        strategy=strategy.value,
                        commit_hash=commit_hash,
                        message=f"Successfully merged '{source_branch}' into '{current_branch}'",
                    )
                except Exception:
                    # Merge succeeded but couldn't get commit hash
                    return MergeResult(
                        success=True,
                        source_branch=source_branch,
                        target_branch=current_branch,
                        strategy=strategy.value,
                        message=f"Successfully merged '{source_branch}' into '{current_branch}'",
                    )

            # There are conflicts - apply the resolution strategy
            if conflicts:
                conflict_keys = [
                    c.key.decode("utf-8") if isinstance(c.key, bytes) else str(c.key)
                    for c in conflicts
                ]
                logger.info(
                    f"Merge has {len(conflicts)} conflicts, "
                    f"resolving with strategy: {strategy.value}"
                )

                # Apply merge with the specified conflict resolution
                conflict_resolution = strategy.to_conflict_resolution()
                try:
                    commit_hash = store.tree.merge(source_branch, conflict_resolution)
                    # Convert bytes to string if needed
                    if isinstance(commit_hash, bytes):
                        commit_hash = commit_hash.hex()
                    return MergeResult(
                        success=True,
                        source_branch=source_branch,
                        target_branch=current_branch,
                        strategy=strategy.value,
                        conflicts=conflict_keys,
                        commit_hash=commit_hash,
                        message=f"Merged '{source_branch}' into '{current_branch}' "
                        f"with {len(conflicts)} conflicts resolved using '{strategy.value}' strategy",
                    )
                except Exception as e:
                    return MergeResult(
                        success=False,
                        source_branch=source_branch,
                        target_branch=current_branch,
                        strategy=strategy.value,
                        conflicts=conflict_keys,
                        error=f"Merge failed: {e}",
                    )

            # No conflicts but try_merge returned False - unexpected
            return MergeResult(
                success=False,
                source_branch=source_branch,
                target_branch=current_branch,
                strategy=strategy.value,
                error="Merge failed for unknown reason",
            )

        except Exception as e:
            logger.error(f"Merge failed: {e}")
            return MergeResult(
                success=False,
                source_branch=source_branch,
                target_branch="",
                strategy=strategy.value if strategy else None,
                error=str(e),
            )

    def get_default_branch(self) -> str:
        """
        Return the repository's default branch.

        Resolves in order:
          1. "main" if it exists.
          2. "master" if it exists.
          3. The first branch returned by list_branches().
          4. "main" as a last-resort empty-repo fallback.
        """
        try:
            info = self.list_branches()
        except Exception as e:
            logger.warning(f"get_default_branch: list_branches failed: {e}")
            return "main"

        if "main" in info.branches:
            return "main"
        if "master" in info.branches:
            return "master"
        if info.branches:
            return info.branches[0]
        return "main"

    def get_divergence(
        self,
        branch: str,
        base: str | None = None,
    ) -> dict:
        """
        Count how many commits `branch` is ahead/behind `base`.

        Uses `git rev-list --count --left-right base...branch` — left side
        (base-only) becomes `behind`, right side (branch-only) becomes `ahead`.

        Args:
            branch: Branch to compare.
            base: Base branch. Defaults to get_default_branch().

        Returns:
            Dict with keys: branch, base, ahead, behind, error (optional).
            On any git failure, ahead and behind are 0 and `error` is set.
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        resolved_base = base if base is not None else self.get_default_branch()
        out = {
            "branch": branch,
            "base": resolved_base,
            "ahead": 0,
            "behind": 0,
        }

        if branch == resolved_base:
            return out

        try:
            result = self._run_git_command(
                [
                    "rev-list",
                    "--count",
                    "--left-right",
                    f"{resolved_base}...{branch}",
                ],
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                out["error"] = (result.stderr or "").strip() or "rev-list failed"
                return out

            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                out["behind"] = int(parts[0])
                out["ahead"] = int(parts[1])
        except Exception as e:
            logger.warning(f"get_divergence({branch}, {resolved_base}) failed: {e}")
            out["error"] = str(e)
        return out

    def _batch_branch_tips(self) -> dict[str, dict[str, object]]:
        """Return ``{branch_name: {"iso": str|None, "unix": int|None}}`` for
        every local branch in a single ``git for-each-ref`` call.

        ``get_branches_status`` calls this once and looks up per-branch
        timestamps from the dict instead of forking ``git log -1`` per branch
        per format — replaces 2N subprocesses with 1.
        """
        try:
            result = self._run_git_command(
                [
                    "for-each-ref",
                    "--format=%(refname:short)|%(committerdate:iso8601)|%(committerdate:unix)",
                    "refs/heads/",
                ],
                check=False,
            )
            if result.returncode != 0:
                return {}
            tips: dict[str, dict[str, object]] = {}
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|", 2)
                if len(parts) < 3:
                    continue
                name, iso, unix_str = parts
                try:
                    unix_val: int | None = int(unix_str) if unix_str else None
                except ValueError:
                    unix_val = None
                tips[name] = {
                    "iso": iso if iso else None,
                    "unix": unix_val,
                }
            return tips
        except Exception as e:
            logger.warning(f"_batch_branch_tips failed: {e}")
            return {}

    def _get_branch_last_commit_iso(self, branch: str) -> str | None:
        """Return ISO timestamp of the tip commit of `branch`, or None."""
        try:
            result = self._run_git_command(
                ["log", "-1", "--format=%aI", branch],
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def _get_branch_last_commit_unix(self, branch: str) -> int | None:
        """Return unix timestamp of the tip commit of `branch`, or None."""
        try:
            result = self._run_git_command(
                ["log", "-1", "--format=%ct", branch],
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip())
        except Exception:
            pass
        return None

    # Shared sync-marker convention with /memoir-sync-branch:
    # $STORE/.git/plugin-synced-branches/<branch> holds a unix timestamp of
    # the last sync. A branch is considered synced when that timestamp is >=
    # the branch tip's commit timestamp (i.e. no new commits since sync).
    _SYNC_MARKER_DIR = ".git/plugin-synced-branches"

    def _sync_marker_path(self, branch: str) -> Path:
        return Path(self.store_path) / self._SYNC_MARKER_DIR / branch

    def _read_sync_marker(self, branch: str) -> int | None:
        path = self._sync_marker_path(branch)
        try:
            if path.is_file():
                return int(path.read_text().strip())
        except Exception:
            pass
        return None

    def _write_sync_marker(self, branch: str) -> None:
        import time

        path = self._sync_marker_path(branch)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(int(time.time())))
        except Exception as e:
            logger.warning(f"Could not write sync marker for {branch}: {e}")

    def get_branches_status(self) -> dict:
        """
        Return divergence info for every branch relative to the default.

        Returns:
            {
              "default": str,
              "current": str,
              "branches": [
                {name, is_default, is_current, ahead, behind, last_commit_date},
                ...
              ]
            }

        Raises:
            StoreNotFoundError: If store path doesn't exist.
            GitOperationError: If list_branches fails.
        """
        info = self.list_branches()  # raises StoreNotFoundError / GitOperationError
        default = self.get_default_branch()
        # One subprocess instead of 2N: pre-fetch all branch tip timestamps
        # so the per-branch loop reads from memory instead of forking
        # ``git log -1`` twice per branch.
        tips = self._batch_branch_tips()

        branches: list[dict] = []
        for name in info.branches:
            div = self.get_divergence(name, base=default)
            ahead = div["ahead"]
            synced = False

            tip = tips.get(name, {})
            tip_ts = tip.get("unix")
            tip_iso = tip.get("iso")

            # Treat ahead as 0 when a sync marker was written after the branch
            # tip's last commit. ProllyTree's merge creates a single-parent
            # commit on the target, so git ancestry still shows the source as
            # "ahead" even after a successful push — the marker disambiguates.
            marker_ts = self._read_sync_marker(name)
            if marker_ts is not None and tip_ts is not None and marker_ts >= tip_ts:
                synced = True
                ahead = 0

            # ``keys_ahead`` is intentionally NOT computed here. A precise
            # default-namespace key count would require running
            # ``promote_branch(dry_run=True)``, which costs ~200ms per branch
            # in checkout overhead. The popup doesn't need this number — the
            # exact count already appears in the merge confirmation panel
            # (which runs ``previewMerge`` on click), and the pill itself
            # only needs to convey "synced" vs "not synced". Field is kept
            # for backwards compat with clients but always 0.

            branches.append(
                {
                    "name": name,
                    "is_default": name == default,
                    "is_current": name == info.current,
                    "ahead": ahead,
                    "behind": div["behind"],
                    "keys_ahead": 0,
                    "last_commit_date": tip_iso,
                    "synced": synced,
                }
            )

        return {
            "default": default,
            "current": info.current,
            "branches": branches,
        }

    def sync_branch(
        self,
        source: str,
        target: str,
        strategy: MergeStrategy = MergeStrategy.SKIP,
        restore: bool = True,
    ) -> MergeResult:
        """
        Merge `source` into `target` while preserving the caller's current branch.

        Steps: remember current → checkout(target) → merge(source, strategy) →
        checkout(original) if restore=True. The original branch is restored
        whether the merge succeeds or fails, so the user never ends up on an
        unexpected branch.

        Args:
            source: Branch whose commits should flow in.
            target: Branch to merge into.
            strategy: Conflict resolution strategy.
            restore: If True, checkout the original branch at the end.

        Returns:
            MergeResult with `restored_branch` populated when restore succeeded.
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        if source == target:
            return MergeResult(
                success=False,
                source_branch=source,
                target_branch=target,
                strategy=strategy.value,
                error="Source and target are the same branch",
            )

        # Remember the originally-checked-out branch so we can restore it.
        try:
            original_branch, _ = self.get_current_branch()
        except Exception as e:
            return MergeResult(
                success=False,
                source_branch=source,
                target_branch=target,
                strategy=strategy.value,
                error=f"Could not read current branch: {e}",
            )

        # Checkout the target branch.
        if original_branch != target:
            checkout_target = self.checkout(target)
            if not checkout_target.success:
                return MergeResult(
                    success=False,
                    source_branch=source,
                    target_branch=target,
                    strategy=strategy.value,
                    error=checkout_target.error
                    or f"Could not checkout target '{target}'",
                )
            # Drop the cached VersionedKvStore so the next step re-reads the
            # on-disk prolly_hash_mappings for `target`. Without this, prollytree
            # can look up tree roots that belong to the previous branch and emit
            # "Root node not found in storage" (history.rs:118) — cosmetic, but
            # a fresh store instance avoids it.
            self._store = None

        # Perform the merge on `target`.
        merge_result = self.merge(source, strategy=strategy)

        # On a successful merge, record a sync marker for `source`. ProllyTree's
        # merge is single-parent, so git ancestry alone cannot tell us that
        # `source` has been promoted. The marker fills that gap and is shared
        # with the /memoir-sync-branch slash command.
        if merge_result.success:
            self._write_sync_marker(source)

        # Always attempt to restore the caller's original branch.
        restored: str | None = None
        if restore and original_branch and original_branch != target:
            # Same reasoning as above — fresh store for the restore.
            self._store = None
            restore_result = self.checkout(original_branch)
            if restore_result.success:
                restored = original_branch
            else:
                logger.warning(
                    f"sync_branch: failed to restore '{original_branch}' "
                    f"after merging '{source}' into '{target}': "
                    f"{restore_result.error}"
                )

        merge_result.restored_branch = restored
        return merge_result

    def _reset_working_tree_to_head(self) -> None:
        """Force the memoir store's working tree to match the current branch HEAD.

        Why this exists: prollytree's ``VersionedKvStore`` reads the on-disk
        ``data/prolly_*`` files. ``tree.checkout(...)`` updates git refs but
        does NOT necessarily restore those files when they're dirty in the
        caller's process. In a long-lived host (the UI server processing many
        requests in one Python process), the working tree accumulates writes
        across requests, so a subsequent ``promote_branch`` would read the
        same accumulated state for both source and target — making them look
        identical and silently zeroing out the diff. A fresh subprocess
        doesn't hit this; a fresh ``BranchService`` in the same process does.

        The fix: after each git-level checkout, run ``git checkout HEAD -- data/``
        to restore the working tree to the branch's committed state. Cheap
        (one subprocess), bounded (only ``data/``), and idempotent.
        """
        import subprocess as _sp

        try:
            _sp.run(
                ["git", "-C", self.store_path, "checkout", "HEAD", "--", "data/"],
                check=False,
                capture_output=True,
                timeout=5,
            )
        except (OSError, _sp.SubprocessError) as e:
            # Non-fatal; the diff may be stale but we don't want to abort
            # the user's request. Logged for ops visibility.
            logger.warning(f"_reset_working_tree_to_head: git checkout failed: {e}")

    def _read_default_namespace(self) -> dict[str, Any]:
        """
        Return all values stored under the ``default`` namespace on the
        currently checked-out branch as ``{key: decoded_value}``.

        Walks ``store.tree.list_keys()`` and filters for the ``default:``
        prefix, then strips the prefix to return the bare taxonomy paths
        callers know (e.g. ``preferences.coding.style``). Used by
        ``promote_branch`` to copy only default-namespace memories across
        branches without touching system namespaces like ``codebase:onboard``.
        """
        store = self._get_store()
        out: dict[str, Any] = {}
        try:
            raw_keys = (
                store.tree.list_keys() if hasattr(store.tree, "list_keys") else []
            )
        except Exception as e:
            logger.warning(f"_read_default_namespace: list_keys failed: {e}")
            raw_keys = []
        prefix = "default:"
        for k in raw_keys:
            full_key = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            if not full_key.startswith(prefix):
                continue
            bare_key = full_key[len(prefix) :]
            value = store.get(("default",), bare_key)
            if value is not None:
                out[bare_key] = value
        return out

    def preview_default_namespace_diff(
        self,
        source: str,
        target: str,
    ) -> dict:
        """
        Return what ``promote_branch(source → target)`` would actually carry,
        with the **values** (not just key names). Same checkout dance as
        ``promote_branch(dry_run=True)`` but captures the raw stored values
        so callers can render BEFORE/AFTER content.

        Used by ``/api/branch-merge-preview`` to back the BranchCommitsModal,
        which wants a flat-by-key view consistent with the merge confirmation
        panel — no per-commit grouping, no deletions, just the net add/update
        operations.

        Returns:
            ``{"success": bool, "added": {path: raw_value},
              "modified": {path: (old_raw, new_raw)},
              "error": str | None, "restored_branch": str | None}``
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        if source == target:
            return {
                "success": False,
                "added": {},
                "modified": {},
                "error": "Source and target are the same branch",
                "restored_branch": None,
            }

        try:
            original_branch, _ = self.get_current_branch()
        except Exception as e:
            return {
                "success": False,
                "added": {},
                "modified": {},
                "error": f"Could not read current branch: {e}",
                "restored_branch": None,
            }

        # Read source values.
        if original_branch != source:
            checkout_source = self.checkout(source)
            if not checkout_source.success:
                return {
                    "success": False,
                    "added": {},
                    "modified": {},
                    "error": checkout_source.error
                    or f"Could not checkout source '{source}'",
                    "restored_branch": original_branch,
                }
            self._store = None
        self._reset_working_tree_to_head()
        self._store = None

        try:
            source_data = self._read_default_namespace()
        except Exception as e:
            self._restore_after_promote(original_branch, True)
            return {
                "success": False,
                "added": {},
                "modified": {},
                "error": f"Failed to read source branch '{source}': {e}",
                "restored_branch": original_branch,
            }

        # Switch to target and read its values for the keys present on source.
        checkout_target = self.checkout(target)
        if not checkout_target.success:
            self._restore_after_promote(original_branch, True)
            return {
                "success": False,
                "added": {},
                "modified": {},
                "error": checkout_target.error
                or f"Could not checkout target '{target}'",
                "restored_branch": original_branch,
            }
        self._reset_working_tree_to_head()
        self._store = None
        store = self._get_store()

        added: dict[str, Any] = {}
        modified: dict[str, tuple] = {}
        for key, src_value in source_data.items():
            tgt_value = store.get(("default",), key)
            if tgt_value is None:
                added[key] = src_value
            elif tgt_value != src_value:
                modified[key] = (tgt_value, src_value)
            # else: identical — no-op.

        restored = self._restore_after_promote(original_branch, True)
        return {
            "success": True,
            "added": added,
            "modified": modified,
            "error": None,
            "restored_branch": restored,
        }

    def promote_branch(
        self,
        source: str,
        target: str,
        dry_run: bool = False,
        restore: bool = True,
        excluded_keys: list[str] | None = None,
    ) -> MergeResult:
        """
        Promote ``default``-namespace memories from ``source`` onto ``target``
        as additive insert/update operations only.

        Unlike ``merge()`` (which uses prollytree's native 3-way tree merge),
        this method:

          * touches **only** the ``default`` namespace — system namespaces
            such as ``codebase:onboard`` and any custom user namespaces on
            ``target`` are left untouched.
          * never deletes — keys present on ``target`` but absent from
            ``source`` are preserved.
          * never overwrites with an identical value — unchanged keys are
            skipped, so the resulting commit (if any) reflects the real diff.

        This is the safe, predictable primitive behind ``/memoir-sync-branch``
        and the UI's "Sync Branch" button.

        Args:
            source: Branch to read default-namespace memories from.
            target: Branch to apply additions/updates to.
            dry_run: If True, return ``added_keys``/``updated_keys`` without
                writing or committing.
            restore: If True, return to the caller's original branch after.
            excluded_keys: Optional list of source keys to skip. They are
                filtered out of ``source_data`` before the diff is computed,
                so they appear in neither ``added_keys`` nor ``updated_keys``
                and are never written to ``target``.

        Returns:
            ``MergeResult`` with ``added_keys``, ``updated_keys``, ``dry_run``,
            ``commit_hash`` (None on dry-run / no-op), and ``restored_branch``.
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        if source == target:
            return MergeResult(
                success=False,
                source_branch=source,
                target_branch=target,
                error="Source and target are the same branch",
                dry_run=dry_run,
            )

        try:
            original_branch, _ = self.get_current_branch()
        except Exception as e:
            return MergeResult(
                success=False,
                source_branch=source,
                target_branch=target,
                error=f"Could not read current branch: {e}",
                dry_run=dry_run,
            )

        # Step 1: read default-namespace memories on the source branch.
        if original_branch != source:
            checkout_source = self.checkout(source)
            if not checkout_source.success:
                return MergeResult(
                    success=False,
                    source_branch=source,
                    target_branch=target,
                    error=checkout_source.error
                    or f"Could not checkout source '{source}'",
                    dry_run=dry_run,
                )
            # Drop the cached store so the next read re-loads from `source`.
            self._store = None
        # Always reset the working tree to HEAD before reading — even when
        # we skipped the checkout above, the working tree may carry stale
        # `data/` files from prior in-process activity (long-running UI
        # server, prior promote_branch call, etc.). See
        # `_reset_working_tree_to_head` for the full rationale.
        self._reset_working_tree_to_head()
        self._store = None

        try:
            source_data = self._read_default_namespace()
        except Exception as e:
            self._restore_after_promote(original_branch, restore)
            return MergeResult(
                success=False,
                source_branch=source,
                target_branch=target,
                error=f"Failed to read source branch '{source}': {e}",
                dry_run=dry_run,
            )

        if excluded_keys:
            excluded_set = set(excluded_keys)
            source_data = {
                k: v for k, v in source_data.items() if k not in excluded_set
            }

        # Step 2: switch to target and compute the diff.
        checkout_target = self.checkout(target)
        if not checkout_target.success:
            self._restore_after_promote(original_branch, restore)
            return MergeResult(
                success=False,
                source_branch=source,
                target_branch=target,
                error=checkout_target.error or f"Could not checkout target '{target}'",
                dry_run=dry_run,
            )
        # Reset working tree + drop cached store so we read target's
        # committed state, not stale `data/` files left over from the
        # source-branch read above. Same rationale as the pre-source
        # reset; without this, the long-running UI server consistently
        # computes a zero-key diff because both reads see identical
        # working-tree garbage.
        self._reset_working_tree_to_head()
        self._store = None
        store = self._get_store()

        added: list[str] = []
        updated: list[str] = []
        for key, src_value in source_data.items():
            tgt_value = store.get(("default",), key)
            if tgt_value is None:
                added.append(key)
            elif tgt_value != src_value:
                updated.append(key)
            # else: identical — no-op, skip.

        if dry_run:
            restored = self._restore_after_promote(original_branch, restore)
            return MergeResult(
                success=True,
                source_branch=source,
                target_branch=target,
                added_keys=sorted(added),
                updated_keys=sorted(updated),
                dry_run=True,
                restored_branch=restored,
                message=(
                    f"Dry-run: would add {len(added)} and update "
                    f"{len(updated)} default-namespace keys on '{target}'"
                ),
            )

        # Step 3: apply add/update batched into a single commit.
        commit_hash: str | None = None
        if added or updated:
            saved_auto_commit = store.auto_commit
            store.auto_commit = False
            try:
                for key in added + updated:
                    store.put(("default",), key, source_data[key])
                commit_msg = (
                    f"Promote default-namespace memories from '{source}' "
                    f"to '{target}' "
                    f"({len(added)} added, {len(updated)} updated)"
                )
                commit_hash = store.commit(commit_msg)
                if isinstance(commit_hash, bytes):
                    commit_hash = commit_hash.hex()
            except Exception as e:
                store.auto_commit = saved_auto_commit
                self._restore_after_promote(original_branch, restore)
                return MergeResult(
                    success=False,
                    source_branch=source,
                    target_branch=target,
                    added_keys=sorted(added),
                    updated_keys=sorted(updated),
                    error=f"Failed to apply promotion on '{target}': {e}",
                )
            finally:
                store.auto_commit = saved_auto_commit

            # Mark source as synced so the unmerged-branch detector and the
            # UI badge stop flagging it.
            self._write_sync_marker(source)

        restored = self._restore_after_promote(original_branch, restore)
        return MergeResult(
            success=True,
            source_branch=source,
            target_branch=target,
            added_keys=sorted(added),
            updated_keys=sorted(updated),
            commit_hash=commit_hash,
            restored_branch=restored,
            message=(
                f"Promoted {len(added)} added and {len(updated)} updated "
                f"default-namespace keys from '{source}' to '{target}'"
            ),
        )

    def _restore_after_promote(
        self, original_branch: str | None, restore: bool
    ) -> str | None:
        """Return to ``original_branch`` and return its name if the checkout
        succeeded; ``None`` if restore was disabled or the checkout failed."""
        if not (restore and original_branch):
            return None
        # Always re-read with a fresh store.
        self._store = None
        try:
            current, _ = self.get_current_branch()
        except Exception:
            current = None
        if current == original_branch:
            return original_branch
        result = self.checkout(original_branch)
        return original_branch if result.success else None

    def time_travel(
        self,
        target: str,
    ) -> CheckoutResult:
        """
        Travel to a specific commit or date.

        This is a convenience method that creates a detached HEAD
        or temporary branch at the specified point.

        Args:
            target: Commit hash, date, or relative reference

        Returns:
            CheckoutResult with success status
        """
        # For now, just delegate to checkout
        # In the future, could add date parsing and commit lookup
        return self.checkout(target)

    def diff(
        self,
        commit1: str | None = None,
        commit2: str | None = None,
        stat_only: bool = False,
    ) -> dict:
        """
        Show differences between commits.

        Args:
            commit1: First commit (default: HEAD~1)
            commit2: Second commit (default: HEAD)
            stat_only: If True, return only --stat summary; otherwise full diff.

        Returns:
            Dict with diff information
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            if commit1 and commit2:
                cmd = ["diff", commit1, commit2]
            elif commit1:
                cmd = ["diff", commit1]
            else:
                cmd = ["diff", "HEAD~1", "HEAD"]
            if stat_only:
                cmd.append("--stat")

            result = self._run_git_command(cmd, check=False)

            return {
                "success": result.returncode == 0,
                "diff": result.stdout if result.returncode == 0 else "",
                "error": result.stderr if result.returncode != 0 else None,
            }

        except Exception as e:
            logger.error(f"Diff failed: {e}")
            return {
                "success": False,
                "diff": "",
                "error": str(e),
            }

    # Alias kept because the CLI command (cli/commands/branch.py:314) calls
    # `service.get_diff(...)`. Rather than touching two call sites, expose
    # both names. New callers should prefer `diff()`.
    get_diff = diff

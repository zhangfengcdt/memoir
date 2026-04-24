"""
Branch service for git operations and version control.

This service extracts the business logic from ui/handlers/branch_handler.py
to be shared by CLI, TUI, SDK, and HTTP handlers.
"""

import contextlib
import logging
from enum import Enum
from pathlib import Path

from prollytree import ConflictResolution

from memoir.services.base import BaseService, GitOperationError, StoreNotFoundError
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
    ) -> list[CommitInfo]:
        """
        Get commit history for the store.

        Args:
            branch: Branch or commit ref to get history for
            limit: Maximum number of commits to return

        Returns:
            List of CommitInfo objects

        Raises:
            StoreNotFoundError: If store path doesn't exist
            GitOperationError: If git operation fails
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            result = self._run_git_command(
                [
                    "log",
                    branch,
                    f"-{limit}",
                    "--pretty=format:%H|%h|%s|%an|%ae|%at",
                ],
                check=False,
            )

            commits = []
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split("|")
                        if len(parts) >= 6:
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

            return commits

        except Exception as e:
            logger.error(f"Failed to get commits: {e}")
            raise GitOperationError(f"Failed to get commits: {e}")

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

        branches: list[dict] = []
        for name in info.branches:
            div = self.get_divergence(name, base=default)
            ahead = div["ahead"]
            synced = False

            # Treat ahead as 0 when a sync marker was written after the branch
            # tip's last commit. ProllyTree's merge creates a single-parent
            # commit on the target, so git ancestry still shows the source as
            # "ahead" even after a successful push — the marker disambiguates.
            marker_ts = self._read_sync_marker(name)
            tip_ts = self._get_branch_last_commit_unix(name)
            if marker_ts is not None and tip_ts is not None and marker_ts >= tip_ts:
                synced = True
                ahead = 0

            branches.append(
                {
                    "name": name,
                    "is_default": name == default,
                    "is_current": name == info.current,
                    "ahead": ahead,
                    "behind": div["behind"],
                    "last_commit_date": self._get_branch_last_commit_iso(name),
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

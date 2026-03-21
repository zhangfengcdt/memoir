"""
Branch service for git operations and version control.

This service extracts the business logic from ui/handlers/branch_handler.py
to be shared by CLI, TUI, SDK, and HTTP handlers.
"""

import logging
from enum import Enum
from pathlib import Path
from typing import Optional

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

    def get_current_branch(self) -> tuple[str, Optional[str]]:
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
        create_branch: Optional[str] = None,
        create_if_missing: bool = False,
    ) -> CheckoutResult:
        """
        Checkout a specific commit or branch.

        Uses VersionedKvStore's native checkout to ensure data consistency.

        Args:
            target: Commit hash or branch name to checkout
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
        from_ref: Optional[str] = None,
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

            # If from_ref specified, checkout that first
            if from_ref and from_ref != "HEAD":
                try:
                    store.tree.checkout(from_ref)
                except Exception as e:
                    return CheckoutResult(
                        success=False,
                        target=branch_name,
                        current_branch="",
                        error=f"Cannot checkout '{from_ref}': {e}",
                    )

            # Create the branch
            try:
                store.tree.create_branch(branch_name)
            except Exception as e:
                return CheckoutResult(
                    success=False,
                    target=branch_name,
                    current_branch="",
                    error=str(e),
                )

            # Get current branch
            try:
                current_branch = store.tree.current_branch()
                if isinstance(current_branch, bytes):
                    current_branch = current_branch.decode("utf-8")
            except Exception:
                current_branch = "main"

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
                # Merge was applied successfully (no conflicts)
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
        commit1: Optional[str] = None,
        commit2: Optional[str] = None,
    ) -> dict:
        """
        Show differences between commits.

        Args:
            commit1: First commit (default: HEAD~1)
            commit2: Second commit (default: HEAD)

        Returns:
            Dict with diff information
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            if commit1 and commit2:
                cmd = ["diff", commit1, commit2, "--stat"]
            elif commit1:
                cmd = ["diff", commit1, "--stat"]
            else:
                cmd = ["diff", "HEAD~1", "HEAD", "--stat"]

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

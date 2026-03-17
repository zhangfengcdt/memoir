"""
Branch service for git operations and version control.

This service extracts the business logic from ui/handlers/branch_handler.py
to be shared by CLI, TUI, SDK, and HTTP handlers.
"""

import logging
from pathlib import Path
from typing import Optional

from memoir.services.base import BaseService, GitOperationError, StoreNotFoundError
from memoir.services.models import (
    BranchInfo,
    CheckoutResult,
    CommitInfo,
    MergeResult,
)

logger = logging.getLogger(__name__)


class BranchService(BaseService):
    """
    Service for git branch and version control operations.

    This provides branch management, checkout, merge, and commit history
    operations using git commands.
    """

    def list_branches(self) -> BranchInfo:
        """
        Get list of branches in the store.

        Returns:
            BranchInfo with list of branches and current branch

        Raises:
            StoreNotFoundError: If store path doesn't exist
            GitOperationError: If git operation fails
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            # Get branch list
            result = self._run_git_command(
                ["branch", "--format=%(refname:short)"],
                check=False,
            )

            branches = []
            if result.returncode == 0 and result.stdout:
                branches = [
                    b.strip() for b in result.stdout.strip().split("\n") if b.strip()
                ]

            # Get current branch
            current_result = self._run_git_command(
                ["rev-parse", "--abbrev-ref", "HEAD"],
                check=False,
            )
            current_branch = (
                current_result.stdout.strip()
                if current_result.returncode == 0
                else "main"
            )

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
            # Get current branch
            branch_result = self._run_git_command(
                ["rev-parse", "--abbrev-ref", "HEAD"],
                check=False,
            )
            current_branch = (
                branch_result.stdout.strip()
                if branch_result.returncode == 0
                else "HEAD"
            )

            # Get current commit
            commit_result = self._run_git_command(
                ["rev-parse", "HEAD"],
                check=False,
            )
            current_commit = None
            if commit_result.returncode == 0 and commit_result.stdout:
                current_commit = commit_result.stdout.strip()[:8]

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
            if create_branch:
                # Create and checkout new branch from target
                result = self._run_git_command(
                    ["checkout", "-b", create_branch, target],
                    check=False,
                )
                if result.returncode != 0:
                    return CheckoutResult(
                        success=False,
                        target=target,
                        current_branch="",
                        error=result.stderr.strip(),
                    )
                message = f"Created and switched to new branch '{create_branch}' from {target[:8]}"
            else:
                # Try to checkout the target
                result = self._run_git_command(
                    ["checkout", target],
                    check=False,
                )

                if result.returncode != 0:
                    # If create_if_missing, try creating the branch
                    if create_if_missing:
                        create_result = self._run_git_command(
                            ["checkout", "-b", target],
                            check=False,
                        )
                        if create_result.returncode == 0:
                            message = f"Created and switched to new branch '{target}'"
                        else:
                            return CheckoutResult(
                                success=False,
                                target=target,
                                current_branch="",
                                error=create_result.stderr.strip(),
                            )
                    else:
                        return CheckoutResult(
                            success=False,
                            target=target,
                            current_branch="",
                            error=result.stderr.strip(),
                        )
                else:
                    message = f"Switched to {target}"

            # Get updated branch info
            current_branch, _ = self.get_current_branch()

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
        from_ref: str = "HEAD",
    ) -> CheckoutResult:
        """
        Create a new branch.

        Args:
            branch_name: Name for the new branch
            from_ref: Reference to create branch from

        Returns:
            CheckoutResult with success status

        Raises:
            StoreNotFoundError: If store path doesn't exist
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            result = self._run_git_command(
                ["branch", branch_name, from_ref],
                check=False,
            )

            if result.returncode != 0:
                return CheckoutResult(
                    success=False,
                    target=branch_name,
                    current_branch="",
                    error=result.stderr.strip(),
                )

            return CheckoutResult(
                success=True,
                target=branch_name,
                current_branch=self.get_current_branch()[0],
                message=f"Created branch '{branch_name}' from {from_ref}",
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
    ) -> MergeResult:
        """
        Merge a branch into current branch.

        Args:
            source_branch: Branch to merge into current

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

            # Perform merge
            result = self._run_git_command(
                [
                    "merge",
                    source_branch,
                    "--no-ff",
                    "-m",
                    f"Merge branch '{source_branch}' into {current_branch}",
                ],
                check=False,
            )

            if result.returncode != 0:
                # Check for conflicts
                output = (result.stdout + result.stderr).lower()
                if "conflict" in output:
                    # Abort the merge
                    self._run_git_command(["merge", "--abort"], check=False)
                    return MergeResult(
                        success=False,
                        source_branch=source_branch,
                        target_branch=current_branch,
                        conflicts=["Merge conflict detected"],
                        error="Merge conflict detected. Please resolve manually.",
                    )
                else:
                    return MergeResult(
                        success=False,
                        source_branch=source_branch,
                        target_branch=current_branch,
                        error=result.stderr.strip(),
                    )

            return MergeResult(
                success=True,
                source_branch=source_branch,
                target_branch=current_branch,
                message=f"Successfully merged '{source_branch}' into '{current_branch}'",
            )

        except Exception as e:
            logger.error(f"Merge failed: {e}")
            return MergeResult(
                success=False,
                source_branch=source_branch,
                target_branch="",
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

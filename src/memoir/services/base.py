"""
Base service class with common utilities.

All services inherit from BaseService to share:
- Store path management
- Lazy store initialization
- Namespace handling utilities
- Git command execution
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class BaseService:
    """Base class for all memoir services."""

    def __init__(self, store_path: str):
        """
        Initialize service with store path.

        Args:
            store_path: Path to the memory store directory
        """
        self.store_path = str(Path(store_path).expanduser().resolve())
        self._store = None

    def _get_store(self):
        """
        Lazily initialize and return the ProllyTreeStore.

        Returns:
            ProllyTreeStore instance
        """
        if self._store is None:
            from memoir.store.prolly_adapter import ProllyTreeStore

            self._store = ProllyTreeStore(
                path=self.store_path,
                enable_versioning=True,
                auto_commit=True,
                cache_size=10000,
            )
        return self._store

    @staticmethod
    def namespace_to_tuple(namespace: str) -> tuple:
        """
        Convert namespace string to tuple format.

        Args:
            namespace: Namespace string, possibly with colons

        Returns:
            Tuple of namespace parts

        Examples:
            "default" -> ("default",)
            "user:preferences" -> ("user", "preferences")
        """
        if ":" in namespace:
            return tuple(namespace.split(":"))
        return (namespace,)

    @staticmethod
    def tuple_to_namespace(namespace_tuple: tuple) -> str:
        """
        Convert namespace tuple back to string format.

        Args:
            namespace_tuple: Tuple of namespace parts

        Returns:
            Colon-separated namespace string
        """
        return ":".join(namespace_tuple)

    def _run_git_command(
        self,
        args: list[str],
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Run a git command in the store directory.

        Args:
            args: Git command arguments (without 'git' prefix)
            check: Raise exception on non-zero exit
            capture_output: Capture stdout/stderr

        Returns:
            CompletedProcess instance

        Raises:
            subprocess.CalledProcessError: If check=True and command fails
        """
        cmd = ["git", *args]
        logger.debug(f"Running git command: {' '.join(cmd)}")

        result = subprocess.run(
            cmd,
            cwd=self.store_path,
            capture_output=capture_output,
            text=True,
            check=check,
        )

        if result.returncode != 0:
            logger.warning(f"Git command failed: {result.stderr}")

        return result

    def _get_current_commit_info(self) -> tuple[str | None, str | None]:
        """
        Get current commit hash and date.

        Returns:
            Tuple of (commit_hash, commit_date) or (None, None) on error
        """
        try:
            result = self._run_git_command(
                ["log", "-1", "--format=%H|%aI"],
                check=False,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|")
                if len(parts) >= 2:
                    return parts[0][:8], parts[1]
            return None, None
        except Exception as e:
            logger.warning(f"Failed to get commit info: {e}")
            return None, None

    def validate_store_path(self) -> bool:
        """
        Validate that the store path exists and is a git repository.

        Returns:
            True if valid, False otherwise
        """
        path = Path(self.store_path)
        if not path.exists():
            return False
        return (path / ".git").exists()


class ServiceError(Exception):
    """Base exception for service errors."""

    def __init__(self, message: str, code: int = 1):
        self.message = message
        self.code = code
        super().__init__(message)


class StoreNotFoundError(ServiceError):
    """Raised when the store path doesn't exist."""

    def __init__(self, path: str):
        super().__init__(f"Store not found: {path}", code=3)


class ClassificationError(ServiceError):
    """Raised when classification fails."""

    def __init__(self, message: str):
        super().__init__(message, code=4)


class GitOperationError(ServiceError):
    """Raised when a git operation fails."""

    def __init__(self, message: str):
        super().__init__(message, code=5)

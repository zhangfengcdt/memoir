"""
Store service for memory store operations.

This service extracts the business logic from ui/handlers/store_handler.py
to be shared by CLI, TUI, SDK, and HTTP handlers.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import Any

from memoir.services.base import BaseService, ServiceError, StoreNotFoundError
from memoir.services.models import CreateStoreResult, StoreInfo

logger = logging.getLogger(__name__)


class StoreService(BaseService):
    """
    Service for memory store operations.

    This provides store creation, reading, and status operations.
    """

    def __init__(self, store_path: str | None = None):
        """
        Initialize store service.

        Args:
            store_path: Path to the memory store directory (optional for create)
        """
        if store_path:
            super().__init__(store_path)
        else:
            # Allow initialization without a path for create operations
            self.store_path = None
            self._store = None

    def create_store(
        self,
        path: str,
        initial_branch: str | None = None,
    ) -> CreateStoreResult:
        """
        Create a new memory store with git repository.

        Args:
            path: Path where to create the store.
            initial_branch: Optional name for the store's primary branch
                (e.g. ``"master"``, ``"single"``). When set, the initial
                commit lands on a branch with this name AND
                ``git config memoir.primaryBranch <name>`` is written so
                downstream code (BranchService.get_default_branch, plugin
                hooks, sync target resolution) routes to it. When ``None``,
                git's own default-branch behavior takes over and no
                ``memoir.primaryBranch`` config is written — backwards-compat
                for stores that don't care.

        Returns:
            CreateStoreResult with success status.
        """
        try:
            # Validate and normalize the path
            store_path = Path(path).expanduser().resolve()

            # Check if path is writable by trying to create parent directories
            try:
                store_path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                return CreateStoreResult(
                    success=False,
                    path=str(store_path),
                    error=f"Permission denied: Cannot create directory at {store_path}",
                )
            except OSError as e:
                return CreateStoreResult(
                    success=False,
                    path=str(store_path),
                    error=f"Invalid path: {e}",
                )

            # Verify we can write to this directory
            try:
                test_file = store_path / ".write_test"
                test_file.touch()
                test_file.unlink()
            except (PermissionError, OSError) as e:
                return CreateStoreResult(
                    success=False,
                    path=str(store_path),
                    error=f"Directory not writable: {store_path} - {e}",
                )

            # Initialize git repository. When the caller supplied an
            # initial_branch, pass it via `git init -b <name>` so the
            # initial commit lands on that branch directly. We could
            # alternatively `git init` then `git branch -m`, but -b is
            # supported on every git release we target (>=2.28) and avoids
            # the rename round-trip entirely.
            git_path = store_path / ".git"
            if not git_path.exists():
                git_init_cmd: list[str] = ["git", "init"]
                if initial_branch:
                    git_init_cmd.extend(["-b", initial_branch])
                subprocess.run(
                    git_init_cmd,
                    cwd=store_path,
                    check=True,
                    capture_output=True,
                )

            # Create data directory
            data_path = store_path / "data"
            data_path.mkdir(exist_ok=True)

            # Create initial commit
            subprocess.run(
                ["git", "add", "."],
                cwd=store_path,
                check=True,
                capture_output=True,
            )

            # Check if there are any changes to commit
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            if status_result.stdout.strip():
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit"],
                    cwd=store_path,
                    check=True,
                    capture_output=True,
                )
                commit_message = "Initial commit created"
            else:
                commit_message = "Repository already initialized"

            # Persist the primary-branch designation so all downstream
            # code paths route to the chosen name. We write the config
            # only when the caller explicitly asked for a custom name —
            # leaving the default unset for `memoir new <path>` (no flag)
            # preserves the backwards-compat invariant that an unset
            # config is functionally identical to the pre-feature state.
            if initial_branch:
                subprocess.run(
                    ["git", "config", "memoir.primaryBranch", initial_branch],
                    cwd=store_path,
                    check=True,
                    capture_output=True,
                )

            # Update store_path for future operations
            self.store_path = str(store_path)

            return CreateStoreResult(
                success=True,
                path=str(store_path),
                message=f"Memory store initialized at {store_path}. {commit_message}",
            )

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode("utf-8") if e.stderr else str(e)
            return CreateStoreResult(
                success=False,
                path=path,
                error=f"Git operation failed: {error_msg}",
            )
        except Exception as e:
            logger.error(f"Failed to create store: {e}")
            return CreateStoreResult(
                success=False,
                path=path,
                error=str(e),
            )

    def read_store(self) -> dict[str, Any]:
        """
        Read complete store data.

        Returns:
            Dictionary with store structure and memories

        Raises:
            StoreNotFoundError: If store path doesn't exist
        """
        if not self.store_path or not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path or "")

        try:
            # Try to use the reader module
            from memoir.ui.reader import read_store_data

            data_json = read_store_data(self.store_path)
            return json.loads(data_json)
        except ImportError:
            # Fallback to basic store reading
            store = self._get_store()
            return self._read_store_basic(store)
        except Exception as e:
            logger.error(f"Failed to read store: {e}")
            raise ServiceError(f"Failed to read store: {e}")

    def _read_store_basic(self, store) -> dict[str, Any]:
        """
        Basic store reading without the reader module.

        Args:
            store: ProllyTreeStore instance

        Returns:
            Dictionary with store structure
        """
        result = {
            "path": self.store_path,
            "namespaces": {},
            "statistics": {},
        }

        try:
            # Get all keys from the store
            if hasattr(store, "tree") and hasattr(store.tree, "list_keys"):
                all_keys = store.tree.list_keys()

                namespaces = {}
                for key in all_keys:
                    key_str = (
                        key.decode("utf-8") if isinstance(key, bytes) else str(key)
                    )
                    parts = key_str.split(":")
                    if len(parts) >= 2:
                        ns = parts[0]
                        if ns not in namespaces:
                            namespaces[ns] = []
                        namespaces[ns].append(key_str)

                result["namespaces"] = namespaces
                result["statistics"] = {
                    "total_keys": len(all_keys),
                    "namespace_count": len(namespaces),
                }

        except Exception as e:
            logger.warning(f"Error reading store details: {e}")

        return result

    def get_status(self) -> StoreInfo:
        """
        Get status information about the store.

        Returns:
            StoreInfo with store status

        Raises:
            StoreNotFoundError: If store path doesn't exist
        """
        if not self.store_path:
            return StoreInfo(
                path="",
                exists=False,
                initialized=False,
            )

        path = Path(self.store_path)
        exists = path.exists()
        initialized = exists and (path / ".git").exists()

        if not exists:
            return StoreInfo(
                path=self.store_path,
                exists=False,
                initialized=False,
            )

        try:
            # Get branch info
            branch = None
            commit_count = 0

            if initialized:
                branch_result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=self.store_path,
                    capture_output=True,
                    text=True,
                )
                if branch_result.returncode == 0:
                    branch = branch_result.stdout.strip()

                # Count commits
                count_result = subprocess.run(
                    ["git", "rev-list", "--count", "HEAD"],
                    cwd=self.store_path,
                    capture_output=True,
                    text=True,
                )
                if count_result.returncode == 0:
                    commit_count = int(count_result.stdout.strip())

            # Get memory count and namespaces
            memory_count = 0
            namespaces = []

            if initialized:
                try:
                    store = self._get_store()
                    if hasattr(store, "tree") and hasattr(store.tree, "list_keys"):
                        all_keys = store.tree.list_keys()
                        memory_count = len(all_keys)

                        ns_set = set()
                        for key in all_keys:
                            key_str = (
                                key.decode("utf-8")
                                if isinstance(key, bytes)
                                else str(key)
                            )
                            parts = key_str.split(":")
                            if parts:
                                ns_set.add(parts[0])
                        namespaces = list(ns_set)
                except Exception as e:
                    logger.warning(f"Error getting store details: {e}")

            # Surface the user-designated primary branch when one is set
            # in `git config memoir.primaryBranch`. Stays None for stores
            # that haven't opted in — to_dict() omits the key entirely in
            # that case so the JSON shape is identical to pre-feature
            # responses.
            primary_branch: str | None = None
            if initialized:
                try:
                    pb_result = subprocess.run(
                        ["git", "config", "--get", "memoir.primaryBranch"],
                        cwd=self.store_path,
                        capture_output=True,
                        text=True,
                    )
                    if pb_result.returncode == 0:
                        value = pb_result.stdout.strip()
                        if value:
                            primary_branch = value
                except Exception as e:
                    logger.debug(f"primary_branch lookup failed: {e}")

            return StoreInfo(
                path=self.store_path,
                exists=exists,
                initialized=initialized,
                branch=branch,
                commit_count=commit_count,
                memory_count=memory_count,
                namespaces=namespaces,
                primary_branch=primary_branch,
            )

        except Exception as e:
            logger.error(f"Failed to get store status: {e}")
            return StoreInfo(
                path=self.store_path,
                exists=exists,
                initialized=initialized,
            )

    def get_statistics(self) -> dict[str, Any]:
        """
        Get performance and storage statistics.

        Returns:
            Dictionary with store statistics
        """
        if not self.store_path or not Path(self.store_path).exists():
            return {"error": "Store not found"}

        try:
            store = self._get_store()
            if hasattr(store, "get_statistics"):
                return store.get_statistics()
            else:
                return {
                    "path": self.store_path,
                    "message": "Statistics not available",
                }
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"error": str(e)}

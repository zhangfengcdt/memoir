# SPDX-License-Identifier: Apache-2.0
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

from prollytree import StorageBackend

from memoir.services.base import BaseService, ServiceError, StoreNotFoundError
from memoir.services.models import CreateStoreResult, StoreInfo
from memoir.store.backend import parse_backend_name, resolve_backend, write_backend_lock
from memoir.store.git_safety import harden_git_config

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
        backend: str | StorageBackend | None = None,
    ) -> CreateStoreResult:
        """
        Create a new memory store with git repository.

        Args:
            path: Path where to create the store.
            backend: Storage backend for prollytree nodes. Accepts a
                ``StorageBackend`` enum, a name string (``git`` / ``file`` /
                ``rocksdb`` / ``memory``), or ``None``. When ``None``, falls
                back to the ``MEMOIR_PROLLY_BACKEND`` env var, then to
                ``File`` (the default for new stores).

        Returns:
            CreateStoreResult with success status
        """
        try:
            if backend is None:
                resolved_backend = resolve_backend()
            elif isinstance(backend, str):
                resolved_backend = parse_backend_name(backend)
            else:
                resolved_backend = backend

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

            # Helper: run a git step with check=True, capture both streams,
            # and surface git's stderr in the exception message rather than
            # letting CalledProcessError print a useless `non-zero exit
            # status N`. Single auto-create path now (ProllyTreeStore is
            # strict), so any "directory has .git but no commit" / "not a
            # repo" / etc. flavours of git errors land here.
            def _git_step(
                args: list[str], op_label: str
            ) -> "subprocess.CompletedProcess":
                try:
                    return subprocess.run(
                        ["git", *args],
                        cwd=store_path,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                except subprocess.CalledProcessError as e:
                    stderr = (e.stderr or "").strip()
                    detail = stderr or f"exit {e.returncode}"
                    raise RuntimeError(
                        f"Failed to initialize Git store: Git object error: "
                        f"{op_label} failed: {detail}"
                    ) from e

            # Initialize git repository.
            #
            # Guardrail: the "Initial commit" path may only run when the repo
            # has no commits yet. If `.git/` already exists *and* HEAD
            # resolves, the repo belongs to someone else (typically a project
            # repo whose root happened to resolve as the store path) and
            # committing into it would leak prolly storage files into their
            # history. Refuse loudly instead.
            git_path = store_path / ".git"
            if git_path.exists():
                head_check = subprocess.run(
                    ["git", "rev-parse", "--verify", "--quiet", "HEAD"],
                    cwd=str(store_path),
                    capture_output=True,
                )
                if head_check.returncode == 0:
                    raise RuntimeError(
                        f"Refusing to initialize memoir store at "
                        f"{store_path}: path is already a git repository "
                        f"with existing commits. memoir stores must live in "
                        f"a dedicated directory (e.g. ~/.memoir/<slug>). If "
                        f"the store path resolved to a project repo, set "
                        f"MEMOIR_STORE explicitly."
                    )
            else:
                _git_step(["init"], "git init")

            # Apply gc-safety configs (disables auto gc + prevents dangling
            # blob pruning) so prollytree's Git-backend nodes survive any
            # automatic / default-config `git gc`. Idempotent.
            harden_git_config(store_path)

            # Persist the backend choice so future opens use the same one.
            # A store's backend is fixed at create time.
            write_backend_lock(store_path, resolved_backend)

            # Create data directory
            data_path = store_path / "data"
            data_path.mkdir(exist_ok=True)

            # Stage only memoir's storage subtree. Using `git add data/`
            # rather than `git add .` is defense in depth: even if some
            # caller hands us a path that contains unrelated working-tree
            # files, we never sweep them into the initial commit.
            _git_step(["add", "data"], "git add")

            # Check if there are any changes to commit
            status_result = _git_step(["status", "--porcelain"], "git status")

            if status_result.stdout.strip():
                _git_step(["commit", "-m", "Initial commit"], "git commit")
                commit_message = "Initial commit created"
            else:
                commit_message = "Repository already initialized"

            # Update store_path for future operations
            self.store_path = str(store_path)

            return CreateStoreResult(
                success=True,
                path=str(store_path),
                message=f"Memory store initialized at {store_path}. {commit_message}",
            )

        except RuntimeError as e:
            # _git_step already formatted a useful message; keep it verbatim.
            return CreateStoreResult(
                success=False,
                path=path,
                error=str(e),
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

            return StoreInfo(
                path=self.store_path,
                exists=exists,
                initialized=initialized,
                branch=branch,
                commit_count=commit_count,
                memory_count=memory_count,
                namespaces=namespaces,
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

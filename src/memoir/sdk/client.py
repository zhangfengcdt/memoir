# SPDX-License-Identifier: Apache-2.0
"""
Memoir SDK Client.

Provides a Python API for AI agents to interact with memoir memory stores.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from memoir.services.models import (
        BranchInfo,
        CheckoutResult,
        CommitInfo,
        DeleteResult,
        MergeResult,
        RecallResult,
        RememberResult,
    )


class BranchManager:
    """Manager for git branch operations."""

    def __init__(self, store_path: str):
        """
        Initialize branch manager.

        Args:
            store_path: Path to the memory store
        """
        self._store_path = store_path
        self._service = None

    def _get_service(self):
        """Lazy load the branch service."""
        if self._service is None:
            from memoir.services.branch_service import BranchService

            self._service = BranchService(self._store_path)
        return self._service

    def list(self) -> BranchInfo:
        """
        List all branches.

        Returns:
            BranchInfo with branches list and current branch
        """
        return self._get_service().list_branches()

    def current(self) -> tuple[str, str | None]:
        """
        Get current branch and commit.

        Returns:
            Tuple of (branch_name, commit_hash)
        """
        return self._get_service().get_current_branch()

    def create(self, name: str, from_ref: str | None = None) -> CheckoutResult:
        """
        Create a new branch.

        Args:
            name: Name for the new branch
            from_ref: Reference to create branch from (default: HEAD)

        Returns:
            CheckoutResult with success status
        """
        return self._get_service().create_branch(name, from_ref=from_ref)

    def checkout(self, target: str, create: bool = False) -> CheckoutResult:
        """
        Switch to a branch or commit.

        Args:
            target: Branch name or commit hash
            create: Create the branch if it doesn't exist

        Returns:
            CheckoutResult with success status
        """
        return self._get_service().checkout(target, create=create)

    def merge(self, source: str) -> MergeResult:
        """
        Merge a branch into current branch.

        Args:
            source: Source branch to merge

        Returns:
            MergeResult with success status and any conflicts
        """
        return self._get_service().merge(source)

    def delete(self, name: str, force: bool = False) -> CheckoutResult:
        """
        Delete a branch.

        Args:
            name: Branch name to delete
            force: Force delete even if not merged

        Returns:
            CheckoutResult with success status
        """
        return self._get_service().delete_branch(name, force=force)

    def commits(self, ref: str = "HEAD", limit: int = 20) -> list[CommitInfo]:
        """
        Get commit history.

        Args:
            ref: Reference to get commits from
            limit: Maximum number of commits

        Returns:
            List of CommitInfo objects
        """
        return self._get_service().get_commits(ref, limit=limit)


class MemoryClient:
    """
    SDK client for AI agent memory operations.

    Provides async interface for storing, retrieving, and managing memories.

    Usage:
        async with MemoryClient("/path/to/store") as memory:
            result = await memory.remember("User prefers dark mode")
            memories = await memory.recall("user preferences")
    """

    def __init__(self, store_path: str | Path):
        """
        Initialize the memory client.

        Args:
            store_path: Path to the memory store directory
        """
        self._store_path = str(Path(store_path).expanduser().resolve())
        self._memory_service = None
        self._crypto_service = None
        self._store_service = None
        self._branch = None

    async def __aenter__(self) -> MemoryClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args):
        """Async context manager exit."""
        pass

    def __enter__(self) -> MemoryClient:
        """Sync context manager entry."""
        return self

    def __exit__(self, *args):
        """Sync context manager exit."""
        pass

    @property
    def store_path(self) -> str:
        """Get the store path."""
        return self._store_path

    @property
    def branch(self) -> BranchManager:
        """
        Get branch manager for git operations.

        Returns:
            BranchManager instance
        """
        if self._branch is None:
            self._branch = BranchManager(self._store_path)
        return self._branch

    def _get_memory_service(self):
        """Lazy load the memory service."""
        if self._memory_service is None:
            from memoir.services.memory_service import MemoryService

            self._memory_service = MemoryService(self._store_path)
        return self._memory_service

    def _get_crypto_service(self):
        """Lazy load the crypto service."""
        if self._crypto_service is None:
            from memoir.services.crypto_service import CryptoService

            self._crypto_service = CryptoService(self._store_path)
        return self._crypto_service

    def _get_store_service(self):
        """Lazy load the store service."""
        if self._store_service is None:
            from memoir.services.store_service import StoreService

            self._store_service = StoreService(self._store_path)
        return self._store_service

    async def remember(
        self,
        content: str,
        namespace: str = "default",
    ) -> RememberResult:
        """
        Store content in memory with intelligent classification.

        Args:
            content: The content to store
            namespace: Namespace for the memory (default: "default")

        Returns:
            RememberResult with key, confidence, and commit info
        """
        service = self._get_memory_service()
        return await service.remember(content, namespace)

    def remember_sync(
        self,
        content: str,
        namespace: str = "default",
    ) -> RememberResult:
        """
        Synchronous version of remember.

        Args:
            content: The content to store
            namespace: Namespace for the memory

        Returns:
            RememberResult with key, confidence, and commit info
        """
        return asyncio.run(self.remember(content, namespace))

    async def recall(
        self,
        query: str,
        limit: int = 10,
        namespace: str | None = None,
    ) -> RecallResult:
        """
        Search memories using semantic query.

        Args:
            query: Search query
            limit: Maximum results to return
            namespace: Limit search to specific namespace (default: all)

        Returns:
            RecallResult with matching memories
        """
        service = self._get_memory_service()
        return await service.recall(query, limit=limit, namespace=namespace)

    def recall_sync(
        self,
        query: str,
        limit: int = 10,
        namespace: str | None = None,
    ) -> RecallResult:
        """
        Synchronous version of recall.

        Args:
            query: Search query
            limit: Maximum results to return
            namespace: Limit search to specific namespace

        Returns:
            RecallResult with matching memories
        """
        return asyncio.run(self.recall(query, limit, namespace))

    async def forget(
        self,
        key: str,
        namespace: str = "default",
    ) -> DeleteResult:
        """
        Delete a memory by its key.

        Args:
            key: Memory key/path to delete
            namespace: Namespace containing the memory

        Returns:
            DeleteResult with success status
        """
        service = self._get_memory_service()
        return await service.forget(key, namespace)

    def forget_sync(
        self,
        key: str,
        namespace: str = "default",
    ) -> DeleteResult:
        """
        Synchronous version of forget.

        Args:
            key: Memory key/path to delete
            namespace: Namespace containing the memory

        Returns:
            DeleteResult with success status
        """
        return asyncio.run(self.forget(key, namespace))

    def status(self) -> dict:
        """
        Get store status information.

        Returns:
            Dictionary with store status
        """
        service = self._get_store_service()
        return service.get_status().to_dict()

    def warmup(self) -> float:
        """
        Pre-load models for faster subsequent calls.

        Returns:
            Time taken to warm up in seconds
        """
        service = self._get_memory_service()
        return service.warmup()

    def generate_proof(self, key: str, namespace: str = "default"):
        """
        Generate a cryptographic proof for a memory.

        Args:
            key: Memory key to generate proof for
            namespace: Namespace containing the memory

        Returns:
            ProofResult with base64-encoded proof
        """
        service = self._get_crypto_service()
        return service.generate_proof(key, namespace)

    def verify_proof(
        self,
        proof_b64: str,
        key: str,
        namespace: str = "default",
        expected_value=None,
    ):
        """
        Verify a cryptographic proof.

        Args:
            proof_b64: Base64-encoded proof
            key: Memory key the proof is for
            namespace: Namespace containing the memory
            expected_value: Optional expected value to verify

        Returns:
            VerifyResult with validity status
        """
        service = self._get_crypto_service()
        return service.verify_proof(proof_b64, key, namespace, expected_value)

# SPDX-License-Identifier: Apache-2.0
"""
Memoir Services Layer.

This module provides the business logic layer shared by all interfaces:
- Web UI (HTTP handlers)
- CLI (command-line interface)
- TUI (terminal user interface)
- SDK (Python API for agents)
- MCP Server (Model Context Protocol)
"""

from memoir.services.models import (
    BlameEntry,
    BranchInfo,
    CheckoutResult,
    CommitInfo,
    CreateStoreResult,
    DeleteResult,
    Memory,
    MergeResult,
    ProofResult,
    RecallResult,
    RememberResult,
    StoreInfo,
    VerifyResult,
)

# Services are imported lazily to avoid heavy dependencies at import time
# For direct imports, use:
#   from memoir.services.memory_service import MemoryService
#   from memoir.services.branch_service import BranchService
#   etc.


def get_memory_service(store_path: str):
    """Get a MemoryService instance for the given store path."""
    from memoir.services.memory_service import MemoryService

    return MemoryService(store_path)


def get_branch_service(store_path: str):
    """Get a BranchService instance for the given store path."""
    from memoir.services.branch_service import BranchService

    return BranchService(store_path)


def get_crypto_service(store_path: str):
    """Get a CryptoService instance for the given store path."""
    from memoir.services.crypto_service import CryptoService

    return CryptoService(store_path)


def get_store_service(store_path: str | None = None):
    """Get a StoreService instance for the given store path."""
    from memoir.services.store_service import StoreService

    return StoreService(store_path)


__all__ = [
    # Models
    "BlameEntry",
    "BranchInfo",
    "CheckoutResult",
    "CommitInfo",
    "CreateStoreResult",
    "DeleteResult",
    "Memory",
    "MergeResult",
    "ProofResult",
    "RecallResult",
    "RememberResult",
    "StoreInfo",
    "VerifyResult",
    # Service factories
    "get_branch_service",
    "get_crypto_service",
    "get_memory_service",
    "get_store_service",
]

# SPDX-License-Identifier: Apache-2.0
"""
Memoir SDK - Python API for AI agent memory operations.

Usage:
    from memoir.sdk import MemoryClient

    # Async usage
    async with MemoryClient("/path/to/store") as memory:
        result = await memory.remember("User prefers dark mode")
        print(f"Stored at: {result.key}")

        memories = await memory.recall("user preferences")
        for m in memories.memories:
            print(f"  {m['path']}: {m['content']}")

    # Sync usage
    with MemoryClient("/path/to/store") as memory:
        result = memory.remember_sync("User prefers dark mode")
        memories = memory.recall_sync("user preferences")

    # Branch operations
    with MemoryClient("/path/to/store") as memory:
        memory.branch.create("experiment")
        memory.branch.checkout("experiment")
        # ... make changes ...
        memory.branch.checkout("main")
        memory.branch.merge("experiment")
"""

from memoir.sdk.client import BranchManager, MemoryClient
from memoir.services.models import (
    BlameEntry,
    BranchInfo,
    CheckoutResult,
    CommitInfo,
    DeleteResult,
    Memory,
    MergeResult,
    ProofResult,
    RecallResult,
    RememberResult,
    VerifyResult,
)

__all__ = [
    "BlameEntry",
    "BranchInfo",
    "BranchManager",
    "CheckoutResult",
    "CommitInfo",
    "DeleteResult",
    "Memory",
    "MemoryClient",
    "MergeResult",
    "ProofResult",
    "RecallResult",
    "RememberResult",
    "VerifyResult",
]

"""
Crypto service for cryptographic proof operations.

This service extracts the business logic from ui/handlers/crypto_handler.py
to be shared by CLI, TUI, SDK, and HTTP handlers.
"""

import base64
import logging
from pathlib import Path
from typing import Any, Optional

from memoir.services.base import BaseService, StoreNotFoundError
from memoir.services.models import BlameEntry, ProofResult, VerifyResult

logger = logging.getLogger(__name__)


class CryptoService(BaseService):
    """
    Service for cryptographic operations.

    This provides proof generation, verification, and blame information
    using the ProllyTree's cryptographic capabilities.
    """

    def generate_proof(
        self,
        key: str,
        namespace: str = "default",
    ) -> ProofResult:
        """
        Generate a cryptographic proof for a memory key.

        Args:
            key: The memory key to generate proof for
            namespace: Namespace containing the memory

        Returns:
            ProofResult with base64-encoded proof

        Raises:
            StoreNotFoundError: If store path doesn't exist
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            store = self._get_store()

            # Convert namespace to tuple format and create full key
            namespace_tuple = self.namespace_to_tuple(namespace)
            full_key = ":".join(namespace_tuple) + ":" + key
            key_bytes = full_key.encode("utf-8")

            # Generate proof using the VersionedKvStore
            if hasattr(store.tree, "generate_proof"):
                proof_bytes = store.tree.generate_proof(key_bytes)

                # Get the value for this key to include in response
                value_bytes = store.tree.get(key_bytes)
                value = store._decode_value(value_bytes) if value_bytes else None

                # Encode proof as base64 for transmission
                proof_b64 = base64.b64encode(proof_bytes).decode("utf-8")

                return ProofResult(
                    success=True,
                    proof_b64=proof_b64,
                    key=key,
                    namespace=namespace,
                    full_key=full_key,
                    value=value,
                    proof_size=len(proof_bytes),
                    message=f"Generated {len(proof_bytes)}-byte proof for {key}",
                )
            else:
                return ProofResult(
                    success=False,
                    proof_b64="",
                    key=key,
                    namespace=namespace,
                    full_key=full_key,
                    error="Proof generation not available (versioning may be disabled)",
                )

        except Exception as e:
            logger.error(f"Failed to generate proof: {e}")
            return ProofResult(
                success=False,
                proof_b64="",
                key=key,
                namespace=namespace,
                full_key=f"{namespace}:{key}",
                error=str(e),
            )

    def verify_proof(
        self,
        proof_b64: str,
        key: str,
        namespace: str = "default",
        expected_value: Optional[Any] = None,
    ) -> VerifyResult:
        """
        Verify a cryptographic proof.

        Args:
            proof_b64: Base64-encoded proof to verify
            key: The memory key the proof is for
            namespace: Namespace containing the memory
            expected_value: Optional expected value to verify against

        Returns:
            VerifyResult with validity status

        Raises:
            StoreNotFoundError: If store path doesn't exist
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            store = self._get_store()

            # Decode proof from base64
            proof_bytes = base64.b64decode(proof_b64)

            # Convert namespace to tuple format and create full key
            namespace_tuple = self.namespace_to_tuple(namespace)
            full_key = ":".join(namespace_tuple) + ":" + key
            key_bytes = full_key.encode("utf-8")

            # Verify proof using the VersionedKvStore
            if hasattr(store.tree, "verify_proof"):
                # Prepare expected value if provided
                expected_bytes = None
                if expected_value:
                    expected_bytes = store._encode_value(expected_value)

                # Verify the proof
                is_valid = store.tree.verify_proof(
                    proof_bytes, key_bytes, expected_bytes
                )

                # Get current value for reference
                current_value_bytes = store.tree.get(key_bytes)
                current_value = (
                    store._decode_value(current_value_bytes)
                    if current_value_bytes
                    else None
                )

                return VerifyResult(
                    success=True,
                    valid=is_valid,
                    key=key,
                    namespace=namespace,
                    full_key=full_key,
                    current_value=current_value,
                    expected_value=expected_value,
                    message="Proof is valid" if is_valid else "Proof is invalid",
                )
            else:
                return VerifyResult(
                    success=False,
                    valid=False,
                    key=key,
                    namespace=namespace,
                    full_key=full_key,
                    error="Proof verification not available (versioning may be disabled)",
                )

        except Exception as e:
            logger.error(f"Failed to verify proof: {e}")
            return VerifyResult(
                success=False,
                valid=False,
                key=key,
                namespace=namespace,
                full_key=f"{namespace}:{key}",
                error=str(e),
            )

    def get_blame(
        self,
        key: str,
        namespace: str = "default",
        limit: int = 10,
    ) -> list[BlameEntry]:
        """
        Get blame/history information for a memory key.

        Uses VersionedKvStore's native commit history for accurate results.

        Args:
            key: The memory key to get blame for
            namespace: Namespace containing the memory
            limit: Maximum number of entries to return

        Returns:
            List of BlameEntry objects showing change history

        Raises:
            StoreNotFoundError: If store path doesn't exist
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            store = self._get_store()

            # Convert namespace to tuple format
            namespace_tuple = self.namespace_to_tuple(namespace)

            # Use get_key_history which calls VersionedKvStore.get_commits_for_key()
            commits = store.get_key_history(namespace_tuple, key, limit=limit)

            entries = []
            for commit in commits:
                # The commit dict should have: id, timestamp, message, author, committer
                commit_id = commit.get("id", "")
                if isinstance(commit_id, bytes):
                    commit_id = commit_id.hex()

                # Format timestamp if available
                timestamp = commit.get("timestamp")
                date_str = ""
                if timestamp:
                    from datetime import datetime

                    try:
                        dt = datetime.fromtimestamp(timestamp)
                        date_str = dt.isoformat()
                    except Exception:
                        date_str = str(timestamp)

                entries.append(
                    BlameEntry(
                        commit=commit_id[:8] if commit_id else "unknown",
                        author=commit.get("author", "Unknown"),
                        date=date_str,
                        message=commit.get("message", ""),
                    )
                )

            return entries

        except Exception as e:
            logger.error(f"Failed to get blame info: {e}")
            return []

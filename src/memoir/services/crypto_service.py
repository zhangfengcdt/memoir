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
    ) -> list[BlameEntry]:
        """
        Get blame/history information for a memory key.

        Args:
            key: The memory key to get blame for
            namespace: Namespace containing the memory

        Returns:
            List of BlameEntry objects showing change history

        Raises:
            StoreNotFoundError: If store path doesn't exist
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            # Use git log to find commits that touched this key
            result = self._run_git_command(
                [
                    "log",
                    "--all",
                    "--pretty=format:%H|%an|%aI|%s",
                    "-p",
                    "--",
                    ".",
                ],
                check=False,
            )

            entries = []
            if result.returncode == 0 and result.stdout:
                current_commit = None
                current_author = None
                current_date = None
                current_message = None

                for line in result.stdout.split("\n"):
                    if "|" in line and line.count("|") >= 3:
                        # This is a commit header line
                        parts = line.split("|")
                        if len(parts) >= 4:
                            current_commit = parts[0][:8]
                            current_author = parts[1]
                            current_date = parts[2]
                            current_message = parts[3]
                    elif key in line and current_commit:
                        # This commit mentions our key
                        entries.append(
                            BlameEntry(
                                commit=current_commit,
                                author=current_author or "Unknown",
                                date=current_date or "",
                                message=current_message or "",
                            )
                        )
                        # Reset to avoid duplicates
                        current_commit = None

            # Deduplicate entries
            seen = set()
            unique_entries = []
            for entry in entries:
                if entry.commit not in seen:
                    seen.add(entry.commit)
                    unique_entries.append(entry)

            return unique_entries[:10]  # Limit to 10 entries

        except Exception as e:
            logger.error(f"Failed to get blame info: {e}")
            return []

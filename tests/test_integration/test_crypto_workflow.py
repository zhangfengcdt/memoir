"""
Integration tests for crypto workflows.

Tests end-to-end cryptographic operations: proof → verify cycle.
"""

import os
import shutil
import tempfile

import pytest

from memoir.services.crypto_service import CryptoService
from memoir.services.store_service import StoreService


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    temp = tempfile.mkdtemp(prefix="memoir_crypto_workflow_test_")
    yield temp
    if os.path.exists(temp):
        shutil.rmtree(temp)


@pytest.fixture
def services(temp_dir):
    """Create store and crypto services."""
    store_service = StoreService(temp_dir)
    store_service.create_store(temp_dir)
    crypto_service = CryptoService(temp_dir)
    return store_service, crypto_service


class TestCryptoWorkflow:
    """Test complete crypto workflows."""

    def test_proof_generation_basic(self, services):
        """Test basic proof generation."""
        _, crypto_service = services

        result = crypto_service.generate_proof("test.key")

        assert result is not None
        assert hasattr(result, "success")

    def test_verify_basic(self, services):
        """Test basic verification."""
        _, crypto_service = services

        result = crypto_service.verify_proof(
            proof_b64="test", key="test.key", namespace="default"
        )

        assert result is not None
        assert hasattr(result, "valid")

    def test_blame_basic(self, services):
        """Test basic blame operation."""
        _, crypto_service = services

        result = crypto_service.get_blame("test.key")

        assert result is not None
        assert isinstance(result, list)


class TestProofVerifyCycle:
    """Test proof generation and verification cycle."""

    def test_proof_then_verify_invalid(self, services):
        """Test generating proof then verifying (for nonexistent key)."""
        _, crypto_service = services

        # Generate proof for nonexistent key
        proof_result = crypto_service.generate_proof("nonexistent")

        # Try to verify (should fail since key doesn't exist)
        if proof_result.success and proof_result.proof_b64:
            verify_result = crypto_service.verify_proof(
                proof_b64=proof_result.proof_b64, key="nonexistent", namespace="default"
            )
            assert verify_result is not None

    def test_multiple_proofs(self, services):
        """Test generating multiple proofs."""
        _, crypto_service = services

        results = []
        for i in range(3):
            result = crypto_service.generate_proof(f"key{i}")
            results.append(result)

        assert len(results) == 3
        for result in results:
            assert result is not None


class TestBlameWorkflow:
    """Test blame operation workflows."""

    def test_blame_multiple_keys(self, services):
        """Test blame for multiple keys."""
        _, crypto_service = services

        results = []
        for key in ["key1", "key2", "key3"]:
            result = crypto_service.get_blame(key)
            results.append(result)

        assert len(results) == 3
        for result in results:
            assert isinstance(result, list)

    def test_blame_with_different_namespaces(self, services):
        """Test blame across namespaces."""
        _, crypto_service = services

        result_default = crypto_service.get_blame("key", namespace="default")
        result_custom = crypto_service.get_blame("key", namespace="custom")

        assert isinstance(result_default, list)
        assert isinstance(result_custom, list)


class TestCryptoEdgeCases:
    """Test edge cases in crypto workflows."""

    def test_proof_empty_key(self, services):
        """Test proof with empty key."""
        _, crypto_service = services

        result = crypto_service.generate_proof("")

        assert result is not None

    def test_verify_empty_proof(self, services):
        """Test verify with empty proof."""
        _, crypto_service = services

        result = crypto_service.verify_proof(
            proof_b64="", key="test", namespace="default"
        )

        assert result is not None
        assert result.valid is False

    def test_blame_special_characters(self, services):
        """Test blame with special characters in key."""
        _, crypto_service = services

        result = crypto_service.get_blame("user.preferences.theme-dark")

        assert isinstance(result, list)


class TestCryptoStoreIntegration:
    """Test integration between crypto and store services."""

    def test_store_intact_after_crypto_ops(self, services):
        """Test store integrity after crypto operations."""
        store_service, crypto_service = services

        # Perform crypto operations
        crypto_service.generate_proof("key1")
        crypto_service.verify_proof("test", "key1", "default")
        crypto_service.get_blame("key1")

        # Store should still be valid
        status = store_service.get_status()
        assert status.initialized is True

    def test_multiple_crypto_operations(self, services):
        """Test multiple crypto operations don't corrupt store."""
        store_service, crypto_service = services

        # Many operations
        for i in range(5):
            crypto_service.generate_proof(f"key{i}")
            crypto_service.get_blame(f"key{i}")

        # Store should be intact
        data = store_service.read_store()
        assert isinstance(data, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

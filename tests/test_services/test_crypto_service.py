"""
Tests for CryptoService.

Tests cryptographic operations: proof generation, verification, blame.
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
    temp = tempfile.mkdtemp(prefix="memoir_crypto_test_")
    yield temp
    if os.path.exists(temp):
        shutil.rmtree(temp)


@pytest.fixture
def initialized_store(temp_dir):
    """Create an initialized store."""
    store_service = StoreService(temp_dir)
    store_service.create_store(temp_dir)
    return temp_dir


@pytest.fixture
def crypto_service(initialized_store):
    """Create a CryptoService."""
    return CryptoService(initialized_store)


class TestCryptoServiceProof:
    """Test proof generation functionality."""

    def test_generate_proof_nonexistent_key(self, crypto_service):
        """Test generating proof for nonexistent key."""
        result = crypto_service.generate_proof("nonexistent.key")

        assert result is not None
        # Should fail or return empty proof
        assert hasattr(result, "success")

    def test_generate_proof_with_namespace(self, crypto_service):
        """Test generating proof with specific namespace."""
        result = crypto_service.generate_proof("test.key", namespace="custom")

        assert result is not None

    def test_proof_result_structure(self, crypto_service):
        """Test that proof result has expected structure."""
        result = crypto_service.generate_proof("test.key")

        assert hasattr(result, "success")
        assert hasattr(result, "key")
        assert hasattr(result, "namespace")


class TestCryptoServiceVerify:
    """Test proof verification functionality."""

    def test_verify_invalid_proof(self, crypto_service):
        """Test verifying an invalid proof."""
        result = crypto_service.verify_proof(
            proof_b64="invalid_proof_data", key="test.key", namespace="default"
        )

        assert result is not None
        assert hasattr(result, "valid")
        # Invalid proof should not verify
        assert result.valid is False

    def test_verify_empty_proof(self, crypto_service):
        """Test verifying an empty proof."""
        result = crypto_service.verify_proof(
            proof_b64="", key="test.key", namespace="default"
        )

        assert result is not None
        assert result.valid is False

    def test_verify_result_structure(self, crypto_service):
        """Test that verify result has expected structure."""
        result = crypto_service.verify_proof(
            proof_b64="test", key="test.key", namespace="default"
        )

        assert hasattr(result, "valid")
        assert hasattr(result, "success")


class TestCryptoServiceBlame:
    """Test blame functionality."""

    def test_blame_nonexistent_key(self, crypto_service):
        """Test blame for nonexistent key."""
        result = crypto_service.get_blame("nonexistent.key")

        assert result is not None
        # Should return empty list or handle gracefully
        assert isinstance(result, list)

    def test_blame_with_namespace(self, crypto_service):
        """Test blame with specific namespace."""
        result = crypto_service.get_blame("test.key", namespace="custom")

        assert result is not None
        assert isinstance(result, list)

    def test_blame_result_structure(self, crypto_service):
        """Test blame result structure when there are entries."""
        result = crypto_service.get_blame("test.key")

        assert isinstance(result, list)
        # If there are entries, check structure
        for entry in result:
            assert isinstance(entry, dict)


class TestCryptoServiceEdgeCases:
    """Test edge cases and error handling."""

    def test_service_with_invalid_path(self):
        """Test service with invalid store path."""
        from memoir.services.base import StoreNotFoundError

        service = CryptoService("/nonexistent/path")

        # Should raise StoreNotFoundError
        with pytest.raises(StoreNotFoundError):
            service.generate_proof("test.key")

    def test_proof_with_special_characters_in_key(self, crypto_service):
        """Test proof with special characters in key."""
        result = crypto_service.generate_proof("user.preferences.theme-dark")

        assert result is not None

    def test_proof_with_empty_key(self, crypto_service):
        """Test proof with empty key."""
        result = crypto_service.generate_proof("")

        assert result is not None
        # Should fail gracefully
        assert result.success is False or result.key == ""

    def test_verify_with_none_values(self, crypto_service):
        """Test verify handles None values."""
        # Should not crash with None
        try:
            result = crypto_service.verify_proof(
                proof_b64=None, key="test", namespace="default"
            )
            assert result is not None
        except (TypeError, AttributeError):
            # Expected - None is not valid
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

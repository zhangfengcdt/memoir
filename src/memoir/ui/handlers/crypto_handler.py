"""
Crypto handler for cryptographic operations.

Delegates to CryptoService for business logic.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler


class CryptoHandler(BaseAPIHandler):
    """Handler for cryptographic proof operations."""

    def handle_proof_api(self, parsed_path):
        """Handle API requests for generating cryptographic proofs."""
        from memoir.services.crypto_service import CryptoService

        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        memory_key = query_params.get("key", [None])[0]
        namespace = query_params.get("namespace", [None])[0] or "default"

        if not store_path:
            self.handler.send_error(400, "Missing 'path' parameter")
            return

        if not memory_key:
            self.handler.send_error(400, "Missing 'key' parameter")
            return

        if not Path(store_path).exists():
            self.handler.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            service = CryptoService(store_path)
            proof_result = service.generate_proof(memory_key, namespace)

            if proof_result.success:
                result = {
                    "success": True,
                    "proof": proof_result.proof_b64,
                    "key": proof_result.key,
                    "namespace": proof_result.namespace,
                    "full_key": proof_result.full_key,
                    "value": proof_result.value,
                    "proof_size": proof_result.proof_size,
                    "message": proof_result.message,
                }
            else:
                result = {
                    "success": False,
                    "error": proof_result.error or "Proof generation failed",
                }

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error generating proof: {e!s}")

    def handle_verify_api(self, parsed_path):
        """Handle API requests for verifying cryptographic proofs."""
        from memoir.services.crypto_service import CryptoService

        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        proof_b64 = query_params.get("proof", [None])[0]
        memory_key = query_params.get("key", [None])[0]
        namespace = query_params.get("namespace", [None])[0] or "default"
        expected_value = query_params.get("value", [None])[0]

        if not store_path:
            self.handler.send_error(400, "Missing 'path' parameter")
            return

        if not proof_b64:
            self.handler.send_error(400, "Missing 'proof' parameter")
            return

        if not memory_key:
            self.handler.send_error(400, "Missing 'key' parameter")
            return

        if not Path(store_path).exists():
            self.handler.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            service = CryptoService(store_path)
            verify_result = service.verify_proof(
                proof_b64, memory_key, namespace, expected_value
            )

            if verify_result.success:
                result = {
                    "success": True,
                    "valid": verify_result.valid,
                    "key": verify_result.key,
                    "namespace": verify_result.namespace,
                    "full_key": verify_result.full_key,
                    "current_value": verify_result.current_value,
                    "expected_value": verify_result.expected_value,
                    "message": (
                        "Proof is valid ✓"
                        if verify_result.valid
                        else "Proof is invalid ✗"
                    ),
                }
            else:
                result = {
                    "success": False,
                    "error": verify_result.error or "Proof verification failed",
                }

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error verifying proof: {e!s}")

    def handle_blame_api(self, parsed_path):
        """Handle API requests for getting blame information for a memory key."""
        from memoir.services.crypto_service import CryptoService

        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        memory_key = query_params.get("key", [None])[0]
        namespace = query_params.get("namespace", [None])[0] or "default"

        if not store_path:
            self.handler.send_error(400, "Missing 'path' parameter")
            return

        if not memory_key:
            self.handler.send_error(400, "Missing 'key' parameter")
            return

        if not Path(store_path).exists():
            self.handler.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            service = CryptoService(store_path)
            entries = service.get_blame(memory_key, namespace)

            result = {
                "success": True,
                "key": memory_key,
                "namespace": namespace,
                "entries": [e.to_dict() for e in entries],
            }

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error getting blame info: {e!s}")

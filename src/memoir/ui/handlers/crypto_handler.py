"""
Crypto handler for cryptographic operations.
"""

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from memoir.store.prolly_adapter import ProllyTreeStore


class CryptoHandler(BaseAPIHandler):
    """Handler for cryptographic proof operations."""

    def handle_proof_api(self, parsed_path):
        """Handle API requests for generating cryptographic proofs."""
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
            # Initialize store with versioning enabled
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Convert namespace to tuple format and create full key
            namespace_tuple = (
                tuple(namespace.split(":")) if ":" in namespace else (namespace,)
            )
            full_key = ":".join(namespace_tuple) + ":" + memory_key
            key_bytes = full_key.encode("utf-8")

            # Generate proof using the VersionedKvStore
            if hasattr(store.tree, "generate_proof"):
                proof_bytes = store.tree.generate_proof(key_bytes)

                # Get the value for this key to include in response
                value_bytes = store.tree.get(key_bytes)
                value = store._decode_value(value_bytes) if value_bytes else None

                # Encode proof as base64 for transmission
                proof_b64 = base64.b64encode(proof_bytes).decode("utf-8")

                result = {
                    "success": True,
                    "proof": proof_b64,
                    "key": memory_key,
                    "namespace": namespace,
                    "full_key": full_key,
                    "value": value,
                    "proof_size": len(proof_bytes),
                    "message": f"Generated {len(proof_bytes)}-byte proof for {memory_key}",
                }
            else:
                result = {
                    "success": False,
                    "error": "Proof generation not available (versioning may be disabled)",
                }

            # Send response
            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error generating proof: {e!s}")

    def handle_verify_api(self, parsed_path):
        """Handle API requests for verifying cryptographic proofs."""
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
            # Initialize store with versioning enabled
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Decode proof from base64
            proof_bytes = base64.b64decode(proof_b64)

            # Convert namespace to tuple format and create full key
            namespace_tuple = (
                tuple(namespace.split(":")) if ":" in namespace else (namespace,)
            )
            full_key = ":".join(namespace_tuple) + ":" + memory_key
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

                result = {
                    "success": True,
                    "valid": is_valid,
                    "key": memory_key,
                    "namespace": namespace,
                    "full_key": full_key,
                    "current_value": current_value,
                    "expected_value": expected_value,
                    "message": "Proof is valid ✓" if is_valid else "Proof is invalid ✗",
                }
            else:
                result = {
                    "success": False,
                    "error": "Proof verification not available (versioning may be disabled)",
                }

            # Send response
            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error verifying proof: {e!s}")

    def handle_blame_api(self, parsed_path):
        """Handle API requests for getting blame information for a memory key."""
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
            # Use the memory_store_reader to get blame data
            sys.path.append(str(Path(__file__).parent))
            from reader import get_blame_info

            data_json = get_blame_info(store_path, memory_key, namespace)
            data = json.loads(data_json)

            # Send response
            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error getting blame info: {e!s}")

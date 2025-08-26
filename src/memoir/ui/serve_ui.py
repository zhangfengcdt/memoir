#!/usr/bin/env python3
"""
Simple HTTP server to serve the Memoir UI and handle memory store data.
"""

import base64
import http.server
import json
import socketserver
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


from memoir.classifier.intelligent import IntelligentClassifier
from memoir.store.prolly_adapter import ProllyTreeStore

PORT = 8080


class MemoryStoreHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Set the directory to serve from
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)

    def do_GET(self):
        parsed_path = urlparse(self.path)

        # Handle API endpoints
        if parsed_path.path == "/api/store":
            self.handle_store_api(parsed_path)
        elif parsed_path.path == "/api/proof":
            self.handle_proof_api(parsed_path)
        elif parsed_path.path == "/api/verify":
            self.handle_verify_api(parsed_path)
        elif parsed_path.path == "/":
            # Serve the visualization HTML
            self.path = "/visualization.html"
            super().do_GET()
        else:
            # Default file serving
            super().do_GET()

    def do_POST(self):
        parsed_path = urlparse(self.path)

        # Handle API endpoints
        if parsed_path.path == "/api/new":
            self.handle_new_api()
        elif parsed_path.path == "/api/remember":
            self.handle_remember_api()
        elif parsed_path.path == "/api/forget":
            self.handle_forget_api()
        else:
            self.send_error(404, "Endpoint not found")

    def handle_store_api(self, parsed_path):
        """Handle API requests for memory store data."""
        import sys
        from pathlib import Path

        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]

        if not store_path:
            self.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            # Use the memory_store_reader to get complete data
            sys.path.append(str(Path(__file__).parent))
            from memory_store_reader import read_store_data

            data_json = read_store_data(store_path)
            data = json.loads(data_json)

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            self.send_error(500, str(e))

    def handle_proof_api(self, parsed_path):
        """Handle API requests for generating cryptographic proofs."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        memory_key = query_params.get("key", [None])[0]
        namespace = query_params.get("namespace", ["alice_chen"])[0]

        if not store_path:
            self.send_error(400, "Missing 'path' parameter")
            return

        if not memory_key:
            self.send_error(400, "Missing 'key' parameter")
            return

        if not Path(store_path).exists():
            self.send_error(404, f"Store path does not exist: {store_path}")
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
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error generating proof: {e!s}")

    def handle_verify_api(self, parsed_path):
        """Handle API requests for verifying cryptographic proofs."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        proof_b64 = query_params.get("proof", [None])[0]
        memory_key = query_params.get("key", [None])[0]
        namespace = query_params.get("namespace", ["alice_chen"])[0]
        expected_value = query_params.get("value", [None])[0]

        if not store_path:
            self.send_error(400, "Missing 'path' parameter")
            return

        if not proof_b64:
            self.send_error(400, "Missing 'proof' parameter")
            return

        if not memory_key:
            self.send_error(400, "Missing 'key' parameter")
            return

        if not Path(store_path).exists():
            self.send_error(404, f"Store path does not exist: {store_path}")
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
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error verifying proof: {e!s}")

    def handle_new_api(self):
        """Handle /new command to create a new git repository and initialize memory store."""
        try:
            # Read POST data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            # Validate and normalize the path
            path = Path(store_path).expanduser().resolve()

            # Check if path is writable by trying to create parent directories
            try:
                path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                self.send_error(
                    400, f"Permission denied: Cannot create directory at {path}"
                )
                return
            except OSError as e:
                self.send_error(400, f"Invalid path: {e}")
                return

            # Verify we can write to this directory
            try:
                test_file = path / ".write_test"
                test_file.touch()
                test_file.unlink()
            except (PermissionError, OSError) as e:
                self.send_error(400, f"Directory not writable: {path} - {e}")
                return

            # Initialize git repository
            git_path = path / ".git"
            if not git_path.exists():
                subprocess.run(
                    ["git", "init"], cwd=path, check=True, capture_output=True
                )

            # Create data directory
            data_path = path / "data"
            data_path.mkdir(exist_ok=True)

            # Skip VersionedKvStore initialization for now - ProllyTreeStore will handle it
            # The store will be properly initialized when first used

            # Create initial commit
            subprocess.run(
                ["git", "add", "."], cwd=path, check=True, capture_output=True
            )

            # Check if there are any changes to commit
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=path,
                capture_output=True,
                text=True,
            )

            if status_result.stdout.strip():
                subprocess.run(
                    ["git", "commit", "-m", "Initial commit"],
                    cwd=path,
                    check=True,
                    capture_output=True,
                )
                commit_message = "Initial commit created"
            else:
                commit_message = "Repository already initialized"

            result = {
                "success": True,
                "path": str(path),
                "message": f"Memory store initialized at {path}",
                "commit": commit_message,
            }

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error creating memory store: {e!s}")

    def handle_remember_api(self):
        """Handle /remember command to classify and store content."""
        try:
            # Read POST data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            content = data.get("content")
            namespace = data.get("namespace", "alice_chen")

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not content:
                self.send_error(400, "Missing 'content' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=True,
                cache_size=10000,
            )

            # Use intelligent classification to generate semantic keys
            try:
                # Initialize the intelligent classifier
                from langchain_openai import ChatOpenAI

                from memoir.taxonomy.taxonomy_presets import TaxonomyVersion

                # Initialize LLM for classification
                llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

                classifier = IntelligentClassifier(
                    llm=llm,
                    taxonomy_version=TaxonomyVersion.GENERAL,
                    confidence_thresholds={
                        "high": 0.8,  # High confidence threshold - memories above this are stored immediately
                        "medium": 0.5,  # Medium confidence threshold - memories above this are considered good
                        "low": 0.0,  # CRITICAL: Low confidence threshold - anything below this gets REJECTED
                    },
                    min_items_for_expansion=2,  # Lower threshold for demo - higher values = less taxonomy expansion
                )

                # Try to classify the content
                try:
                    # Use async classification (we need to run it synchronously in this context)
                    import asyncio

                    # Create event loop for async classification
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        result = loop.run_until_complete(
                            classifier.classify_async(content)
                        )
                        key = result.path
                        confidence = result.confidence
                        reasoning = (
                            f"Classified as {key} (confidence: {confidence:.2f})"
                        )
                    finally:
                        loop.close()
                except Exception as e:
                    # Fallback to simple semantic classification
                    print(f"LLM classification failed: {e}, using pattern matching")
                    from memoir.classifier.semantic import SemanticClassifier

                    semantic_classifier = SemanticClassifier()
                    result = semantic_classifier.classify(content)
                    key = result.path
                    confidence = result.confidence
                    reasoning = (
                        f"Pattern-matched as {key} (confidence: {confidence:.2f})"
                    )

            except Exception as e:
                print(f"Classification failed: {e}, using timestamp fallback")
                # Fallback to timestamp if classification completely fails
                key = f"memory.{int(time.time())}"
                confidence = 1.0
                reasoning = "Fallback to timestamp key due to classification error"

            # Store in memory
            namespace_tuple = (
                tuple(namespace.split(":")) if ":" in namespace else (namespace,)
            )

            # Prepare memory item
            memory_item = {
                "content": content,
                "key": key,
                "namespace": namespace,
                "confidence": confidence,
                "timestamp": time.time(),
            }

            # Store the memory using sync method
            store.put(namespace_tuple, key, memory_item)

            # Full key for display
            full_key = ":".join(namespace_tuple) + ":" + key

            result = {
                "success": True,
                "key": key,
                "full_key": full_key,
                "namespace": namespace,
                "confidence": confidence,
                "reasoning": reasoning,
                "message": f"Memory stored at {key}",
            }

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error storing memory: {e!s}")

    def handle_forget_api(self):
        """Handle /forget command to delete a memory key."""
        try:
            # Read POST data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            key = data.get("key")
            namespace = data.get("namespace", "alice_chen")

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not key:
                self.send_error(400, "Missing 'key' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=True,
                cache_size=10000,
            )

            # Convert namespace to tuple format
            namespace_tuple = (
                tuple(namespace.split(":")) if ":" in namespace else (namespace,)
            )

            # Delete the memory using sync method
            store.delete(namespace_tuple, key)

            # The auto_commit=True should handle the git commit, but let's ensure it
            # Create commit message
            commit_message = f"Deleted memory: {key}"

            result = {
                "success": True,
                "key": key,
                "namespace": namespace,
                "message": f"Memory deleted: {key}",
                "commit": commit_message,
            }

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error deleting memory: {e!s}")

    def end_headers(self):
        # Add CORS headers
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()


def main():
    print(f"Starting Memoir UI server on http://localhost:{PORT}")
    print(f"Open http://localhost:{PORT} in your browser")
    print("\nTo connect to a memory store, use the command in the UI:")
    print("  /connect /tmp/memoir_ui_store")
    print("\nPress Ctrl+C to stop the server")

    with socketserver.TCPServer(("", PORT), MemoryStoreHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.shutdown()


if __name__ == "__main__":
    main()

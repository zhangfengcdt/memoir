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
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


from memoir.classifier.intelligent import IntelligentClassifier
from memoir.memento.location import LocationMemento
from memoir.memento.timeline import TimelineMemento
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
        elif parsed_path.path == "/api/blame":
            self.handle_blame_api(parsed_path)
        elif parsed_path.path == "/api/branches":
            self.handle_branches_api(parsed_path)
        elif parsed_path.path == "/api/commits":
            self.handle_commits_api(parsed_path)
        elif parsed_path.path == "/api/current-branch":
            self.handle_current_branch_api(parsed_path)
        elif parsed_path.path == "/api/timeline":
            self.handle_timeline_get_api(parsed_path)
        elif parsed_path.path == "/api/location":
            self.handle_location_get_api(parsed_path)
        elif parsed_path.path == "/api/debug-timeline":
            self.handle_debug_timeline_api(parsed_path)
        elif parsed_path.path == "/api/debug-location":
            self.handle_debug_location_api(parsed_path)
        elif parsed_path.path == "/api/summarize":
            self.handle_summarize_api(parsed_path)
        elif parsed_path.path == "/api/recall":
            self.handle_recall_api(parsed_path)
        elif parsed_path.path == "/api/diff":
            self.handle_diff_api(parsed_path)
        elif parsed_path.path == "/":
            # Serve the main UI HTML file
            self.path = "/ui.html"
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
        elif parsed_path.path == "/api/checkout":
            self.handle_checkout_api()
        elif parsed_path.path == "/api/create-branch":
            self.handle_create_branch_api()
        elif parsed_path.path == "/api/merge-branch":
            self.handle_merge_branch_api()
        elif parsed_path.path == "/api/delete-branch":
            self.handle_delete_branch_api()
        elif parsed_path.path == "/api/timeline":
            self.handle_timeline_post_api()
        elif parsed_path.path == "/api/location":
            self.handle_location_post_api()
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
            from reader import read_store_data

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
        namespace = query_params.get("namespace", [None])[0] or "default"

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
        namespace = query_params.get("namespace", [None])[0] or "default"
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

    def handle_blame_api(self, parsed_path):
        """Handle API requests for getting blame information for a memory key."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        memory_key = query_params.get("key", [None])[0]
        namespace = query_params.get("namespace", [None])[0] or "default"

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
            # Use the memory_store_reader to get blame data
            sys.path.append(str(Path(__file__).parent))
            from reader import get_blame_info

            data_json = get_blame_info(store_path, memory_key, namespace)
            data = json.loads(data_json)

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error getting blame info: {e!s}")

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
            import time

            step_timings = {}
            remember_start = time.time()

            # Read POST data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            content = data.get("content")
            namespace = data.get("namespace") or "default"

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not content:
                self.send_error(400, "Missing 'content' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Step 1: Store Initialization
            step1_start = time.time()
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=True,
                cache_size=10000,
            )
            step_timings["step1_store_initialization"] = round(
                time.time() - step1_start, 3
            )

            # Step 2: Classification & Path Generation
            step2_start = time.time()
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
                timeline_events = None
                location_events = None
                try:
                    # Use async classification (we need to run it synchronously in this context)
                    import asyncio

                    # Create event loop for async classification
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        # Get current date for timeline extraction context
                        from datetime import datetime

                        current_date = datetime.now().strftime("%Y-%m-%d")

                        # Classify with metadata including session date for timeline extraction
                        result = loop.run_until_complete(
                            classifier.classify_input(
                                content,
                                metadata={"session_date": current_date},
                                return_prompt=True,
                            )
                        )
                        # Handle multi-label classification - use all paths if available
                        confidence = result.confidence
                        if result.paths and len(result.paths) > 1:
                            # Multi-label classification - store under multiple paths
                            keys = result.paths
                            key = keys[0]  # Primary key for response
                            reasoning = f"Multi-label classified as {keys} (confidence: {confidence:.2f})"
                        else:
                            # Single classification
                            key = (
                                result.path
                                if result.path
                                else "context.current.session"
                            )
                            keys = [key]
                            reasoning = (
                                f"Classified as {key} (confidence: {confidence:.2f})"
                            )

                        # Extract timeline events if any were detected
                        timeline_events = result.timeline_events

                        # Extract location events if any were detected
                        location_events = result.location_events

                        # Extract LLM prompt if available
                        classification_prompt = result.llm_prompt

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

            step_timings["step2_classification"] = round(time.time() - step2_start, 3)

            # Step 3: Memory Storage
            step3_start = time.time()
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

            # Store the memory using sync method - under all classified paths
            for storage_key in keys:
                memory_item_copy = memory_item.copy()
                memory_item_copy["key"] = storage_key
                store.put(namespace_tuple, storage_key, memory_item_copy)

            # Get commit information after storage
            commit_hash = None
            commit_date = None
            try:
                # Get the latest commit information
                import subprocess

                result = subprocess.run(
                    ["git", "log", "-1", "--format=%H|%ci"],
                    cwd=store_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0 and result.stdout.strip():
                    parts = result.stdout.strip().split("|")
                    commit_hash = parts[0][:8]  # Short hash
                    commit_date = parts[1] if len(parts) > 1 else None
            except Exception:
                # Fallback to timestamp if git is not available
                from datetime import datetime

                commit_date = datetime.now().isoformat()

            step_timings["step3_memory_storage"] = round(time.time() - step3_start, 3)

            # Step 4: Timeline Processing (if applicable)
            step4_start = time.time()
            timeline_applied = False
            if timeline_events and isinstance(timeline_events, list):
                try:
                    # Initialize timeline memento
                    timeline_memento = TimelineMemento(store)

                    # Apply timeline events asynchronously
                    import asyncio

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            timeline_memento.apply_timeline_events(
                                timeline_events, original_content=content
                            )
                        )
                        timeline_applied = True
                    finally:
                        loop.close()
                except Exception as e:
                    print(f"Failed to apply timeline events: {e}")

            step_timings["step4_timeline_processing"] = round(
                time.time() - step4_start, 3
            )

            # Step 5: Location Processing (if applicable)
            step5_start = time.time()
            location_applied = False
            if location_events and isinstance(location_events, list):
                try:
                    # Initialize location memento
                    from memoir.memento.location import LocationMemento

                    location_memento = LocationMemento(store)

                    # Apply location events asynchronously
                    import asyncio

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        loop.run_until_complete(
                            location_memento.apply_location_events(
                                location_events, namespace=namespace
                            )
                        )
                        location_applied = True
                    finally:
                        loop.close()
                except Exception as e:
                    print(f"Failed to apply location events: {e}")

            step_timings["step5_location_processing"] = round(
                time.time() - step5_start, 3
            )
            step_timings["total_remember"] = round(time.time() - remember_start, 3)

            # Full key for display
            full_key = ":".join(namespace_tuple) + ":" + key

            # Extract individual step timings for frontend display
            five_step_timings = {
                "step1_store_initialization": step_timings.get(
                    "step1_store_initialization", 0
                ),
                "step2_classification": step_timings.get("step2_classification", 0),
                "step3_memory_storage": step_timings.get("step3_memory_storage", 0),
                "step4_timeline_processing": step_timings.get(
                    "step4_timeline_processing", 0
                ),
                "step5_location_processing": step_timings.get(
                    "step5_location_processing", 0
                ),
            }

            # Generate message for multi-path storage
            if len(keys) > 1:
                message = f"Memory stored at {len(keys)} paths: {', '.join(keys)}"
                all_full_keys = [":".join(namespace_tuple) + ":" + k for k in keys]
            else:
                message = f"Memory stored at {key}"
                all_full_keys = [full_key]

            result = {
                "success": True,
                "key": key,  # Primary key
                "keys": keys,  # All keys (for multi-label)
                "full_key": full_key,  # Primary full key
                "full_keys": all_full_keys,  # All full keys
                "namespace": namespace,
                "confidence": confidence,
                "reasoning": reasoning,
                "message": message,
                "timeline_events": timeline_events if timeline_events else None,
                "timeline_applied": timeline_applied,
                "location_events": location_events if location_events else None,
                "location_applied": location_applied,
                "commit_hash": commit_hash,
                "commit_date": commit_date,
                "content": content,  # Include the stored content
                "step_timings": step_timings,
                "five_step_timings": five_step_timings,
                "classification_prompt": (
                    classification_prompt
                    if "classification_prompt" in locals()
                    else None
                ),
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
            namespace = data.get("namespace") or "default"

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

    def handle_branches_api(self, parsed_path):
        """Get list of branches in the store."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]

        if not store_path:
            self.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            # Use git to get branch list
            result = subprocess.run(
                ["git", "branch", "--format=%(refname:short)"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            branches = result.stdout.strip().split("\n") if result.stdout else []

            # Get current branch
            current_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            current_branch = current_result.stdout.strip()

            data = {
                "success": True,
                "branches": branches,
                "current": current_branch,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error getting branches: {e!s}")

    def handle_commits_api(self, parsed_path):
        """Get commit history for the store."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        branch = query_params.get("branch", ["HEAD"])[0]
        limit = int(query_params.get("limit", [20])[0])

        if not store_path:
            self.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            # Get commit history using git log
            result = subprocess.run(
                [
                    "git",
                    "log",
                    branch,
                    f"-{limit}",
                    "--pretty=format:%H|%h|%s|%an|%ae|%at",
                ],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            commits = []
            if result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split("|")
                        if len(parts) >= 6:
                            commits.append(
                                {
                                    "hash": parts[0],
                                    "short_hash": parts[1],
                                    "message": parts[2],
                                    "author": parts[3],
                                    "email": parts[4],
                                    "timestamp": int(parts[5]),
                                }
                            )

            data = {
                "success": True,
                "commits": commits,
                "branch": branch,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error getting commits: {e!s}")

    def handle_current_branch_api(self, parsed_path):
        """Get the current branch of the store."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]

        if not store_path:
            self.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            # Get current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            current_branch = result.stdout.strip()

            # Get current commit
            commit_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            current_commit = commit_result.stdout.strip()

            data = {
                "success": True,
                "branch": current_branch,
                "commit": current_commit[:8] if current_commit else None,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error getting current branch: {e!s}")

    def handle_checkout_api(self):
        """Checkout a specific commit or branch."""
        try:
            # Read POST data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            target = data.get("target")  # Can be commit hash or branch name
            create_branch = data.get(
                "create_branch"
            )  # Optional: create new branch from commit

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not target:
                self.send_error(400, "Missing 'target' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Note: ProllyTreeStore initialization not needed for git checkout operations

            if create_branch:
                # Create and checkout new branch from target
                subprocess.run(
                    ["git", "checkout", "-b", create_branch, target],
                    cwd=store_path,
                    check=True,
                    capture_output=True,
                )
                message = f"Created and switched to new branch '{create_branch}' from {target[:8]}"
            else:
                # Just checkout the target
                subprocess.run(
                    ["git", "checkout", target],
                    cwd=store_path,
                    check=True,
                    capture_output=True,
                )
                message = f"Switched to {target}"

            # Get updated branch info
            current_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            current_branch = current_result.stdout.strip()

            result = {
                "success": True,
                "message": message,
                "current_branch": current_branch,
                "target": target,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode("utf-8") if e.stderr else str(e)
            self.send_error(500, f"Git checkout failed: {error_msg}")
        except Exception as e:
            self.send_error(500, f"Error during checkout: {e!s}")

    def handle_create_branch_api(self):
        """Create a new branch."""
        try:
            # Read POST data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            branch_name = data.get("branch")
            from_ref = data.get("from", "HEAD")  # Create from specific ref

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not branch_name:
                self.send_error(400, "Missing 'branch' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Create branch
            subprocess.run(
                ["git", "branch", branch_name, from_ref],
                cwd=store_path,
                check=True,
                capture_output=True,
            )

            result = {
                "success": True,
                "message": f"Created branch '{branch_name}' from {from_ref}",
                "branch": branch_name,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode("utf-8") if e.stderr else str(e)
            self.send_error(500, f"Failed to create branch: {error_msg}")
        except Exception as e:
            self.send_error(500, f"Error creating branch: {e!s}")

    def handle_merge_branch_api(self):
        """Merge a branch into current branch."""
        try:
            # Read POST data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            source_branch = data.get("source")

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not source_branch:
                self.send_error(400, "Missing 'source' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Get current branch
            current_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            current_branch = current_result.stdout.strip()

            # Perform merge
            merge_result = subprocess.run(
                [
                    "git",
                    "merge",
                    source_branch,
                    "--no-ff",
                    "-m",
                    f"Merge branch '{source_branch}' into {current_branch}",
                ],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            if merge_result.returncode != 0:
                # Check for conflicts
                if (
                    "conflict" in merge_result.stdout.lower()
                    or "conflict" in merge_result.stderr.lower()
                ):
                    # Abort the merge
                    subprocess.run(
                        ["git", "merge", "--abort"],
                        cwd=store_path,
                        capture_output=True,
                    )
                    self.send_error(
                        409, "Merge conflict detected. Please resolve manually."
                    )
                    return
                else:
                    raise subprocess.CalledProcessError(
                        merge_result.returncode,
                        "git merge",
                        stderr=merge_result.stderr.encode(),
                    )

            result = {
                "success": True,
                "message": f"Successfully merged '{source_branch}' into '{current_branch}'",
                "target_branch": current_branch,
                "source_branch": source_branch,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode("utf-8") if e.stderr else str(e)
            self.send_error(500, f"Merge failed: {error_msg}")
        except Exception as e:
            self.send_error(500, f"Error during merge: {e!s}")

    def handle_delete_branch_api(self):
        """Delete a branch."""
        try:
            # Read POST data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            branch_name = data.get("branch")
            force = data.get("force", False)

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not branch_name:
                self.send_error(400, "Missing 'branch' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Check if trying to delete current branch
            current_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            current_branch = current_result.stdout.strip()

            if current_branch == branch_name:
                self.send_error(
                    400,
                    f"Cannot delete current branch '{branch_name}'. Switch to another branch first.",
                )
                return

            # Delete the branch
            delete_flag = "-D" if force else "-d"
            subprocess.run(
                ["git", "branch", delete_flag, branch_name],
                cwd=store_path,
                check=True,
                capture_output=True,
            )

            result = {
                "success": True,
                "message": f"Deleted branch '{branch_name}'",
                "branch": branch_name,
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode("utf-8") if e.stderr else str(e)
            if "not fully merged" in error_msg:
                self.send_error(
                    400,
                    f"Branch '{branch_name}' is not fully merged. Use force=true to delete anyway.",
                )
            else:
                self.send_error(500, f"Failed to delete branch: {error_msg}")
        except Exception as e:
            self.send_error(500, f"Error deleting branch: {e!s}")

    def end_headers(self):
        # Add CORS headers
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def handle_timeline_get_api(self, parsed_path):
        """Handle GET /api/timeline to retrieve timeline data."""
        try:
            query_params = parse_qs(parsed_path.query)
            store_path = query_params.get("path", [None])[0]
            start_date = query_params.get("start", [None])[0]
            end_date = query_params.get("end", [None])[0]

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Initialize timeline memento
            timeline_memento = TimelineMemento(store)

            # Get timeline summary asynchronously
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                timeline_summary = loop.run_until_complete(
                    timeline_memento.get_timeline_summary(
                        start_date=start_date, end_date=end_date, namespace="default"
                    )
                )

                # Also get raw timeline data for structured display
                timeline_memories = loop.run_until_complete(
                    store.asearch("default", "timeline.")
                )

                # Process timeline memories into structured format
                timeline_data = {}
                for path, data in timeline_memories:
                    if "." in path:
                        date_str = path.split(".")[-1]
                        if len(date_str) == 8:  # YYYYMMDD format
                            content = self._extract_timeline_content(data, date_str)

                            if (
                                content
                                and content.strip()
                                and not content.startswith("Timeline event on")
                            ):
                                timeline_data[date_str] = content.strip()
                            else:
                                # Let's add a more obvious fallback to see if this is being reached
                                fallback_text = f"FALLBACK EVENT on {date_str[4:6]}/{date_str[6:8]}/{date_str[:4]}"
                                timeline_data[date_str] = fallback_text
                                # Try to extract any meaningful text from the data structure
                                fallback_content = ""
                                if isinstance(data, dict):
                                    # Try to find any text field in the nested structure
                                    def extract_text_from_dict(d, depth=0):
                                        if depth > 3:  # Prevent infinite recursion
                                            return ""
                                        for key, value in d.items():
                                            if (
                                                isinstance(value, str)
                                                and len(value) > 10
                                                and key
                                                in [
                                                    "raw_text",
                                                    "content",
                                                    "description",
                                                    "timeline_content",
                                                ]
                                            ):
                                                return value
                                            elif isinstance(value, dict):
                                                result = extract_text_from_dict(
                                                    value, depth + 1
                                                )
                                                if result:
                                                    return result
                                        return ""

                                    fallback_content = extract_text_from_dict(data)

                                if fallback_content:
                                    timeline_data[date_str] = fallback_content.strip()
                                else:
                                    # Format the date for display
                                    try:
                                        year = date_str[:4]
                                        month = date_str[4:6]
                                        day = date_str[6:8]
                                        formatted_date = f"{month}/{day}/{year}"
                                    except (ValueError, IndexError):
                                        formatted_date = date_str
                                    timeline_data[date_str] = (
                                        f"Event on {formatted_date}"
                                    )

            finally:
                loop.close()

            result = {
                "success": True,
                "summary": timeline_summary,
                "timeline_data": timeline_data,
                "start_date": start_date,
                "end_date": end_date,
            }

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error retrieving timeline: {e!s}")

    def _extract_timeline_content(self, data, date_str):
        """Extract timeline content from various data structure formats."""

        if not data:
            return ""

        # Try different extraction strategies
        content = ""

        if isinstance(data, dict):
            # NEW Strategy: Handle the memory store format with "memories" array
            if (
                "memories" in data
                and isinstance(data["memories"], list)
                and len(data["memories"]) > 0
            ):
                # Get the first (and usually only) memory from the array
                memory_item = data["memories"][0]

                if "content" in memory_item and isinstance(
                    memory_item["content"], dict
                ):
                    content_obj = memory_item["content"]

                    # Priority 1: raw_text (this contains the actual description)
                    content = content_obj.get("raw_text", "")
                    if content and content.strip():
                        return content.strip()

                    # Priority 2: structured_data -> original_content
                    if "structured_data" in content_obj:
                        structured = content_obj["structured_data"]
                        if isinstance(structured, dict):
                            content = structured.get("original_content", "")
                            if content and content.strip():
                                return content.strip()

                            content = structured.get("timeline_content", "")
                            if content and content.strip():
                                return content.strip()

            # OLD Strategy 1: Check if it's the old format with nested content
            if "content" in data and isinstance(data["content"], dict):
                timeline_data_obj = data["content"]

                # Priority 1: original_content from structured_data
                if "structured_data" in timeline_data_obj:
                    structured = timeline_data_obj["structured_data"]
                    if isinstance(structured, dict):
                        content = structured.get("original_content", "")
                        if content:
                            return content

                        content = structured.get("timeline_content", "")
                        if content:
                            return content

                # Priority 2: raw_text
                content = timeline_data_obj.get("raw_text", "")
                if content:
                    return content

            # Strategy 3: Direct fields
            for field in [
                "raw_text",
                "timeline_content",
                "original_content",
                "summary",
                "description",
            ]:
                if data.get(field):
                    content = str(data[field])
                    return content

        elif isinstance(data, str):
            return data

        # Last resort: convert to string and hope for the best
        content = str(data) if data else ""
        return content

    def handle_timeline_post_api(self):
        """Handle POST /api/timeline to add explicit timeline events."""
        try:
            # Read POST data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            date_str = data.get("date")  # YYYYMMDD format
            description = data.get("description")
            content = data.get(
                "content"
            )  # Natural language input (alternative to date+description)

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            # If content is provided, use the IntelligentClassifier to extract timeline events
            if content and not (date_str and description):
                # Initialize the IntelligentClassifier
                try:
                    from langchain_openai import ChatOpenAI

                    from memoir.classifier.intelligent import IntelligentClassifier
                    from memoir.taxonomy.taxonomy_presets import TaxonomyVersion

                    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
                    classifier = IntelligentClassifier(
                        llm=llm,
                        taxonomy_version=TaxonomyVersion.GENERAL,
                    )

                    # Classify the content to extract timeline events
                    import asyncio

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    try:
                        classification = loop.run_until_complete(
                            classifier.classify_async(content)
                        )

                        if classification.timeline_events:
                            # Use the first timeline event
                            event = classification.timeline_events[0]
                            date_str = event.get("date")
                            description = event.get("description")
                        else:
                            self.send_error(
                                400,
                                "No timeline event detected in content. Include a date and event description.",
                            )
                            return
                    finally:
                        loop.close()

                except Exception as e:
                    self.send_error(500, f"Error processing timeline content: {e}")
                    return

            if not date_str:
                self.send_error(
                    400,
                    "Missing 'date' parameter or could not extract date from content",
                )
                return

            if not description:
                self.send_error(
                    400,
                    "Missing 'description' parameter or could not extract description from content",
                )
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Validate date format
            if len(date_str) != 8 or not date_str.isdigit():
                self.send_error(
                    400, f"Invalid date format. Expected YYYYMMDD, got: {date_str}"
                )
                return

            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=True,
                cache_size=10000,
            )

            # Initialize timeline memento
            timeline_memento = TimelineMemento(store)

            # Create timeline event
            timeline_event = {"date": date_str, "description": description}

            # Apply timeline event asynchronously
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    timeline_memento.apply_timeline_events(
                        [timeline_event], namespace="default"
                    )
                )
                success = True

                # Debug: Check what was stored

            finally:
                loop.close()

            result = {
                "success": success,
                "date": date_str,
                "description": description,
                "path": f"timeline.{date_str}",
                "message": f"Timeline event added for {date_str}",
            }

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error adding timeline event: {e!s}")

    def handle_location_get_api(self, parsed_path):
        """Handle GET /api/location to retrieve location data."""
        try:
            query_params = parse_qs(parsed_path.query)
            store_path = query_params.get("path", [None])[0]

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Initialize location memento
            location_memento = LocationMemento(store)

            # Get location summary asynchronously
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                location_summary = loop.run_until_complete(
                    location_memento.get_location_summary()
                )

                # Also get raw location data for structured display
                location_memories = loop.run_until_complete(
                    store.asearch("default", "location.")
                )

                # Process location memories into structured format
                location_data = {}
                for path, data in location_memories:
                    if "." in path:
                        location_key = path.split(".")[-1]
                        content = self._extract_location_content(data, location_key)

                        if content and content.strip():
                            # Convert location key back to display name
                            display_name = location_key.replace("_", " ").title()
                            location_data[location_key] = {
                                "name": display_name,
                                "content": content.strip(),
                            }

            finally:
                loop.close()

            result = {
                "success": True,
                "summary": location_summary,
                "location_data": location_data,
            }

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error retrieving location: {e!s}")

    def handle_location_post_api(self):
        """Handle POST /api/location to add explicit location events."""
        try:
            # Read POST data
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            location_name = data.get("location")
            description = data.get("description")
            content = data.get(
                "content"
            )  # Natural language input (alternative to location+description)

            if not store_path:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"success": False, "error": "Missing 'path' parameter"}
                    ).encode()
                )
                return

            # If content is provided, use the IntelligentClassifier to extract location events
            if content and not (location_name and description):
                # Initialize the IntelligentClassifier
                try:
                    from langchain_openai import ChatOpenAI

                    from memoir.classifier.intelligent import IntelligentClassifier
                    from memoir.taxonomy.taxonomy_presets import TaxonomyVersion

                    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
                    classifier = IntelligentClassifier(
                        llm=llm,
                        taxonomy_version=TaxonomyVersion.GENERAL,
                    )

                    # Classify the content to extract location events
                    import asyncio

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    try:
                        classification = loop.run_until_complete(
                            classifier.classify_async(content)
                        )

                        if classification.location_events:
                            # Use the first location event
                            event = classification.location_events[0]
                            location_name = event.get("location")
                            description = event.get("description")
                        else:
                            self.send_response(400)
                            self.send_header("Content-type", "application/json")
                            self.end_headers()
                            self.wfile.write(
                                json.dumps(
                                    {
                                        "success": False,
                                        "error": "No location event detected in content. Include a place and activity description.",
                                    }
                                ).encode()
                            )
                            return
                    finally:
                        loop.close()

                except Exception as e:
                    self.send_response(500)
                    self.send_header("Content-type", "application/json")
                    self.end_headers()
                    self.wfile.write(
                        json.dumps(
                            {
                                "success": False,
                                "error": f"Error processing location content: {e}",
                            }
                        ).encode()
                    )
                    return

            if not location_name:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "success": False,
                            "error": "Missing 'location' parameter or could not extract location from content",
                        }
                    ).encode()
                )
                return

            if not description:
                self.send_response(400)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "success": False,
                            "error": "Missing 'description' parameter or could not extract description from content",
                        }
                    ).encode()
                )
                return

            if not Path(store_path).exists():
                self.send_response(404)
                self.send_header("Content-type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {
                            "success": False,
                            "error": f"Store path does not exist: {store_path}",
                        }
                    ).encode()
                )
                return

            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=True,
                cache_size=10000,
            )

            # Initialize location memento
            location_memento = LocationMemento(store)

            # Create location event
            location_event = {"location": location_name, "description": description}

            # Apply location event asynchronously
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    location_memento.apply_location_events([location_event])
                )
                success = True

                # Debug: Check what was stored

            finally:
                loop.close()

            result = {
                "success": success,
                "location": location_name,
                "description": description,
                "normalized_location": location_memento._normalize_location_name(
                    location_name
                ),
                "path": f"location.{location_memento._normalize_location_name(location_name)}",
            }

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_response(500)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {"success": False, "error": f"Error adding location event: {e!s}"}
                ).encode()
            )

    def _extract_location_content(self, data, location_key):
        """Extract location content from various data structure formats."""

        if not data:
            return ""

        # Try different extraction strategies
        content = ""

        if isinstance(data, dict):
            # NEW Strategy: Handle the memory store format with "memories" array
            if (
                "memories" in data
                and isinstance(data["memories"], list)
                and len(data["memories"]) > 0
            ):
                # Get the first (and usually only) memory from the array
                memory_item = data["memories"][0]

                if "content" in memory_item and isinstance(
                    memory_item["content"], dict
                ):
                    content_obj = memory_item["content"]

                    # Priority 1: raw_text (this contains the actual description)
                    content = content_obj.get("raw_text", "")
                    if content and content.strip():
                        return content.strip()

                    # Priority 2: structured_data -> location_content
                    if "structured_data" in content_obj:
                        structured = content_obj["structured_data"]
                        if isinstance(structured, dict):
                            content = structured.get("location_content", "")
                            if content and content.strip():
                                return content.strip()

            # Strategy 3: Direct fields
            for field in [
                "raw_text",
                "location_content",
                "summary",
                "description",
            ]:
                if data.get(field):
                    content = str(data[field])
                    return content

        elif isinstance(data, str):
            return data

        # Last resort: convert to string and hope for the best
        content = str(data) if data else ""
        return content

    def handle_debug_location_api(self, parsed_path):
        """Handle GET /api/debug-location for debugging location data structures."""
        try:
            query_params = parse_qs(parsed_path.query)
            store_path = query_params.get("path", [None])[0]

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Get all location-related data for debugging
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Get all data with location prefix
                location_memories = loop.run_until_complete(
                    store.asearch("default", "location.")
                )

                # Also get all data to see what else is stored
                all_memories = loop.run_until_complete(store.asearch("default", ""))

            finally:
                loop.close()

            result = {
                "success": True,
                "location_memories_count": len(location_memories),
                "location_memories": [
                    {"path": path, "data": data} for path, data in location_memories
                ],
                "all_memories_count": len(all_memories),
                "all_memories": [
                    {
                        "path": path,
                        "data_type": str(type(data)),
                        "data": (
                            str(data)[:200] + "..."
                            if len(str(data)) > 200
                            else str(data)
                        ),
                    }
                    for path, data in all_memories
                ],
            }

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error retrieving debug location: {e!s}")

    def handle_debug_timeline_api(self, parsed_path):
        """Handle GET /api/debug-timeline for debugging timeline data structures."""
        try:
            query_params = parse_qs(parsed_path.query)
            store_path = query_params.get("path", [None])[0]

            if not store_path:
                self.send_error(400, "Missing 'path' parameter")
                return

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Get all timeline-related data for debugging
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                # Get all data with timeline prefix
                timeline_memories = loop.run_until_complete(
                    store.asearch("default", "timeline.")
                )

                # Also get all data to see what else is stored
                all_memories = loop.run_until_complete(store.asearch("default", ""))

            finally:
                loop.close()

            result = {
                "success": True,
                "timeline_memories_count": len(timeline_memories),
                "timeline_memories": [
                    {"path": path, "data": data} for path, data in timeline_memories
                ],
                "all_memories_count": len(all_memories),
                "all_memories": [
                    {
                        "path": path,
                        "data_type": str(type(data)),
                        "data": (
                            str(data)[:200] + "..."
                            if len(str(data)) > 200
                            else str(data)
                        ),
                    }
                    for path, data in all_memories
                ],
            }

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.send_error(500, f"Error debugging timeline: {e!s}")

    def handle_summarize_api(self, parsed_path):
        """Handle API requests for summarizing memory store data."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        summary_type = query_params.get("type", ["all"])[
            0
        ]  # all, taxonomy, timeline, places

        if not store_path:
            self.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            # Get branch information first
            import subprocess

            try:
                current_result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=store_path,
                    capture_output=True,
                    text=True,
                )
                current_branch = (
                    current_result.stdout.strip()
                    if current_result.returncode == 0
                    else "unknown"
                )

                commit_result = subprocess.run(
                    ["git", "rev-parse", "--short", "HEAD"],
                    cwd=store_path,
                    capture_output=True,
                    text=True,
                )
                current_commit = (
                    commit_result.stdout.strip()
                    if commit_result.returncode == 0
                    else "unknown"
                )
            except Exception:
                current_branch = "unknown"
                current_commit = "unknown"

            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Initialize LLM for summarization
            try:
                from langchain_openai import ChatOpenAI

                llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            except Exception as e:
                self.send_error(500, f"Error initializing LLM: {e!s}")
                return

            import asyncio
            import time

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Track timing
                start_time = time.time()
                timing_info = {}

                # Collect summaries based on type
                summaries = {}

                if summary_type in ["all", "taxonomy"]:
                    taxonomy_start = time.time()
                    summaries["taxonomy"] = loop.run_until_complete(
                        self._summarize_taxonomy_keys(store, llm)
                    )
                    timing_info["taxonomy"] = round(time.time() - taxonomy_start, 2)

                if summary_type in ["all", "timeline"]:
                    timeline_start = time.time()
                    summaries["timeline"] = loop.run_until_complete(
                        self._summarize_timeline(store, llm)
                    )
                    timing_info["timeline"] = round(time.time() - timeline_start, 2)

                if summary_type in ["all", "places"]:
                    places_start = time.time()
                    summaries["places"] = loop.run_until_complete(
                        self._summarize_places(store, llm)
                    )
                    timing_info["places"] = round(time.time() - places_start, 2)

                # Generate overall summary if requesting all
                if summary_type == "all":
                    overall_start = time.time()
                    summaries["overall"] = loop.run_until_complete(
                        self._generate_overall_summary(summaries, llm)
                    )
                    timing_info["overall"] = round(time.time() - overall_start, 2)

                total_time = round(time.time() - start_time, 2)

                result = {
                    "success": True,
                    "summary_type": summary_type,
                    "summaries": summaries,
                    "metadata": {
                        "store_path": store_path,
                        "current_branch": current_branch,
                        "current_commit": current_commit,
                        "total_time_seconds": total_time,
                        "timing_breakdown": timing_info,
                        "generated_at": time.strftime(
                            "%Y-%m-%d %H:%M:%S UTC", time.gmtime()
                        ),
                    },
                }

                # Send response
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(result, indent=2).encode())

            finally:
                loop.close()

        except Exception as e:
            self.send_error(500, f"Error generating summary: {e!s}")

    async def _summarize_taxonomy_keys(self, store, llm):
        """Summarize all taxonomy keys and their data."""
        try:
            # Get all memories from the store
            all_memories = await store.asearch("default", "")

            if not all_memories:
                return "No memories found in the store."

            # Organize memories by taxonomy path
            taxonomy_data = {}
            for path, data in all_memories:
                # Skip timeline and location specific entries
                if not (path.startswith("timeline.") or path.startswith("location.")):
                    taxonomy_data[path] = data

            if not taxonomy_data:
                return (
                    "No taxonomic data found (only timeline and location data present)."
                )

            # Prepare data for LLM
            taxonomy_summary = "Memory Store Taxonomy Data:\n\n"
            for path, data in taxonomy_data.items():
                content = self._extract_memory_content(data)
                taxonomy_summary += (
                    f"• {path}: {content[:200]}{'...' if len(content) > 200 else ''}\n"
                )

            # Create LLM prompt
            prompt = f"""Analyze this memory store's taxonomy structure and data. Provide a concise summary of:
1. What types of information are stored (categories/domains)
2. The organizational structure and key taxonomy paths
3. Notable patterns or themes in the data
4. Overall scope and purpose of this memory collection

Data to analyze:
{taxonomy_summary}

Provide a clear, informative summary in 2-3 paragraphs."""

            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            return response.content.strip()

        except Exception as e:
            return f"Error summarizing taxonomy: {e!s}"

    async def _summarize_timeline(self, store, llm):
        """Summarize timeline events in chronological order."""
        try:
            # Get timeline memories
            timeline_memories = await store.asearch("default", "timeline.")

            if not timeline_memories:
                return "No timeline events found in memory store."

            # Organize by date
            timeline_events = {}
            for path, data in timeline_memories:
                if "." in path:
                    date_str = path.split(".")[-1]
                    if len(date_str) == 8:  # YYYYMMDD format
                        content = self._extract_timeline_content(data, date_str)
                        if content and content.strip():
                            timeline_events[date_str] = content

            if not timeline_events:
                return "No meaningful timeline events found."

            # Sort by date
            sorted_events = sorted(timeline_events.items())

            # Prepare timeline data for LLM
            timeline_summary = "Timeline Events:\n\n"
            for date_str, content in sorted_events:
                # Format date for display
                try:
                    year, month, day = date_str[:4], date_str[4:6], date_str[6:8]
                    formatted_date = f"{month}/{day}/{year}"
                except (ValueError, IndexError):
                    formatted_date = date_str
                timeline_summary += f"• {formatted_date}: {content[:150]}{'...' if len(content) > 150 else ''}\n"

            # Create LLM prompt
            prompt = f"""Analyze this timeline of events and provide a chronological summary. Focus on:
1. Key themes and patterns over time
2. Important milestones or turning points
3. The overall narrative or story these events tell
4. Temporal relationships between events

Timeline data:
{timeline_summary}

Provide a narrative summary in 2-3 paragraphs that tells the story of what happened over time."""

            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            return response.content.strip()

        except Exception as e:
            return f"Error summarizing timeline: {e!s}"

    async def _summarize_places(self, store, llm):
        """Summarize location/place information."""
        try:
            # Get location memories
            location_memories = await store.asearch("default", "location.")

            if not location_memories:
                return "No location data found in memory store."

            # Organize location data
            location_data = {}
            for path, data in location_memories:
                if "." in path:
                    location_key = path.split(".")[-1]
                    content = self._extract_location_content(data, location_key)
                    if content and not content.startswith("Location event at"):
                        display_name = location_key.replace("_", " ").title()
                        location_data[display_name] = content

            if not location_data:
                return "No meaningful location data found."

            # Prepare location data for LLM
            location_summary = "Location Data:\n\n"
            for location, content in location_data.items():
                location_summary += f"• {location}: {content[:150]}{'...' if len(content) > 150 else ''}\n"

            # Create LLM prompt
            prompt = f"""Analyze this collection of location-based memories and provide a summary. Focus on:
1. Geographic scope and types of places mentioned
2. Activities, events, or significance of each location
3. Patterns in location usage or importance
4. The overall geographic footprint of these memories

Location data:
{location_summary}

Provide an informative summary in 2-3 paragraphs about the places and locations in this memory store."""

            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            return response.content.strip()

        except Exception as e:
            return f"Error summarizing locations: {e!s}"

    async def _generate_overall_summary(self, summaries, llm):
        """Generate an overall summary combining all aspects."""
        try:
            # Combine all summaries
            combined_summary = "MEMORY STORE ANALYSIS:\n\n"

            if "taxonomy" in summaries:
                combined_summary += f"TAXONOMY DATA:\n{summaries['taxonomy']}\n\n"

            if "timeline" in summaries:
                combined_summary += f"TIMELINE EVENTS:\n{summaries['timeline']}\n\n"

            if "places" in summaries:
                combined_summary += f"LOCATION DATA:\n{summaries['places']}\n\n"

            # Create LLM prompt for overall synthesis
            prompt = f"""Based on these detailed analyses of a memory store, provide a brief executive summary in 2-3 sentences that captures:

1. The main purpose/scope of this memory collection
2. Key insights about the person/entity these memories belong to
3. The primary story these memories tell

Analysis data:
{combined_summary}

Provide a concise summary (maximum 3 sentences) that captures the essence of this memory store."""

            response = await llm.ainvoke([{"role": "user", "content": prompt}])
            return response.content.strip()

        except Exception as e:
            return f"Error generating overall summary: {e!s}"

    def handle_recall_api(self, parsed_path):
        """Handle API requests for recalling memories using IntelligentSearchEngine."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        query = query_params.get("query", [None])[0]

        if not store_path:
            self.send_error(400, "Missing 'path' parameter")
            return

        if not query:
            self.send_error(400, "Missing 'query' parameter")
            return

        if not Path(store_path).exists():
            self.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Initialize LLM for intelligent search
            try:
                from langchain_openai import ChatOpenAI

                llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            except Exception as e:
                self.send_error(500, f"Error initializing LLM: {e!s}")
                return

            # Initialize IntelligentSearchEngine
            from memoir.search.intelligent import IntelligentSearchEngine

            search_engine = IntelligentSearchEngine(llm=llm, store=store)

            import asyncio
            import time

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                # Track timing for each stage
                start_time = time.time()
                timing_info = {}

                # Stage 1: Initialize search
                init_start = time.time()
                results = []
                timing_info["initialization"] = round(time.time() - init_start, 2)

                # Stage 2: Path Discovery & Selection (includes LLM path selection in IntelligentSearchEngine)
                # This happens inside the search() call
                search_start = time.time()

                # First try the default namespace
                results = loop.run_until_complete(
                    search_engine.search(
                        query, namespace="default", limit=10, return_prompts=True
                    )
                )
                print(f"🔍 Search in default found {len(results)} results")

                timing_info["path_discovery_and_selection"] = round(
                    time.time() - search_start, 2
                )

                # If no results found, try other namespaces
                if not results:
                    namespace_search_start = time.time()

                    # Get all unique namespaces from the keys we found
                    all_keys = (
                        search_engine.store.tree.list_keys()
                        if hasattr(search_engine.store, "tree")
                        else []
                    )
                    namespaces = set()
                    for key in all_keys:
                        key_str = (
                            key.decode("utf-8") if isinstance(key, bytes) else str(key)
                        )
                        key_parts = key_str.split(":")
                        if len(key_parts) >= 2:
                            namespace = ":".join(
                                key_parts[:2]
                            )  # Take first two parts as namespace
                            namespaces.add(namespace)

                    print(f"🔍 Found namespaces: {namespaces}")

                    # Try each namespace
                    for ns in namespaces:
                        if ns != "memory:general":
                            # Extract just the base namespace (first part before colon)
                            base_namespace = ns.split(":")[0] if ":" in ns else ns
                            print(f"🔍 Trying namespace: {base_namespace}")
                            ns_results = loop.run_until_complete(
                                search_engine.search(
                                    query,
                                    namespace=base_namespace,
                                    limit=10,
                                    return_prompts=True,
                                )
                            )
                            print(
                                f"🔍 Search in {base_namespace} found {len(ns_results)} results"
                            )
                            if ns_results:
                                results.extend(ns_results)
                                break  # Stop after finding results in first namespace

                    # Update timing if we searched other namespaces
                    timing_info["namespace_fallback"] = round(
                        time.time() - namespace_search_start, 2
                    )
                    timing_info["total_search"] = round(time.time() - search_start, 2)
                else:
                    timing_info["total_search"] = timing_info[
                        "path_discovery_and_selection"
                    ]

                # Stage 3: Memory Retrieval (already done, just track formatting time)
                format_start = time.time()
                search_time = round(time.time() - start_time, 2)

                # Format results (filter out timing-only dummy results)
                formatted_results = []
                step_timings = None
                llm_prompts = None

                for result in results:
                    # Extract timing data and prompts from any result (including dummy ones)
                    if hasattr(result, "metadata") and result.metadata:
                        result_step_timings = result.metadata.get("step_timings")
                        if result_step_timings:
                            step_timings = result_step_timings

                        result_llm_prompts = result.metadata.get("llm_prompts")
                        if result_llm_prompts:
                            llm_prompts = result_llm_prompts

                        # Skip dummy timing-only results from formatted output
                        if result.metadata.get("is_timing_only", False):
                            continue

                    # Add real results to formatted output
                    formatted_results.append(
                        {
                            "path": result.path,
                            "content": result.content,
                            "relevance_score": result.relevance_score,
                            "namespace": result.namespace,
                            "metadata": result.metadata,
                        }
                    )

                timing_info["formatting"] = round(time.time() - format_start, 2)
                total_time = round(time.time() - start_time, 2)

                # Create four-step timing breakdown matching UI steps
                four_step_timings = {}
                if step_timings:
                    four_step_timings = {
                        "step1_path_discovery": step_timings.get(
                            "step1_path_discovery", 0
                        ),
                        "step2_path_selection": step_timings.get(
                            "step2_path_selection", 0
                        ),
                        "step3_content_refinement": step_timings.get(
                            "step3_content_refinement", 0
                        ),
                        "step4_memory_retrieval": step_timings.get(
                            "step4_memory_retrieval", 0
                        ),
                    }
                else:
                    # Fallback to the original timing if step timings not available
                    search_duration = timing_info.get("total_search", total_time)
                    four_step_timings = {
                        "step1_path_discovery": round(search_duration * 0.2, 2),
                        "step2_path_selection": round(search_duration * 0.3, 2),
                        "step3_content_refinement": round(search_duration * 0.3, 2),
                        "step4_memory_retrieval": round(search_duration * 0.2, 2),
                    }

                # Create response
                response_data = {
                    "success": True,
                    "results": formatted_results,
                    "metadata": {
                        "store_path": store_path,
                        "results_count": len(formatted_results),
                        "search_time": f"{search_time}s",
                        "total_time_seconds": total_time,
                        "timing_breakdown": timing_info,
                        "four_step_timings": four_step_timings,
                        "llm_prompts": llm_prompts,
                    },
                }

            finally:
                loop.close()

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())

        except Exception as e:
            error_msg = f"Error during recall search: {e!s}"
            print(f"Recall API error: {e}")
            import traceback

            traceback.print_exc()

            response_data = {"success": False, "error": error_msg}
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())

    def _extract_memory_content(self, data):
        """Extract meaningful content from memory data structure."""
        if isinstance(data, str):
            return data

        if isinstance(data, dict):
            # Try different extraction strategies
            if (
                "memories" in data
                and isinstance(data["memories"], list)
                and len(data["memories"]) > 0
            ):
                memory_item = data["memories"][0]
                if "content" in memory_item:
                    content_obj = memory_item["content"]
                    if isinstance(content_obj, dict):
                        # Look for actual content
                        for key in [
                            "content",
                            "raw_text",
                            "original_content",
                            "description",
                        ]:
                            if content_obj.get(key):
                                return str(content_obj[key])
                        # Look in structured_data
                        if "structured_data" in content_obj:
                            structured = content_obj["structured_data"]
                            if isinstance(structured, dict):
                                for key in [
                                    "original_content",
                                    "content",
                                    "description",
                                ]:
                                    if structured.get(key):
                                        return str(structured[key])
                    elif isinstance(content_obj, str):
                        return content_obj

            # Direct field access
            for field in ["content", "raw_text", "description", "summary"]:
                if data.get(field):
                    return str(data[field])

        return str(data) if data else ""

    def handle_diff_api(self, parsed_path):
        """Handle diff API requests."""
        try:
            query_params = parse_qs(parsed_path.query)
            store_path = query_params.get("path", [""])[0]
            commit1 = query_params.get("commit1", [None])[0]
            commit2 = query_params.get("commit2", [None])[0]
            mode = query_params.get("mode", [""])[0]  # 'mock', or empty for real

            if not store_path:
                response_data = {"success": False, "error": "Store path is required"}
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode())
                return

            # Check if store exists
            store_path_obj = Path(store_path)
            if not store_path_obj.exists():
                response_data = {"success": False, "error": "Store path does not exist"}
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode())
                return

            # Handle mock mode
            if mode == "mock":
                response_data = self._generate_mock_diff(commit1, commit2, store_path)
            else:
                # Generate real diff using git/store
                response_data = self._generate_real_diff(store_path, commit1, commit2)

            # Send response
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())

        except Exception as e:
            error_msg = f"Error generating diff: {e!s}"
            print(f"Diff API error: {e}")
            import traceback

            traceback.print_exc()

            response_data = {"success": False, "error": error_msg}
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())

    def _generate_mock_diff(self, commit1, commit2, store_path):
        """Generate mock diff data for demonstration."""
        if commit1 and commit2:
            changes = [
                {
                    "path": "profile.personal.preferences.theme",
                    "type": "modified",
                    "old_content": "dark",
                    "new_content": "light",
                },
                {
                    "path": "experience.memories.recent.learning",
                    "type": "added",
                    "new_content": "Learned about intelligent search algorithms today",
                },
            ]
            stats = {"added": 1, "modified": 1, "deleted": 0}
            header = f"Mock Comparing {commit1} → {commit2}"
        else:
            changes = [
                {
                    "path": "profile.living.current.address.city",
                    "type": "modified",
                    "old_content": "My hometown is in Wuhan, China.",
                    "new_content": "I currently live in San Francisco, California.",
                },
                {
                    "path": "experience.memories.recent.positive",
                    "type": "added",
                    "new_content": "Yesterday we went skiing and had an amazing time at the resort",
                },
                {
                    "path": "preferences.deprecated.old_setting",
                    "type": "deleted",
                    "old_content": "This setting is no longer used",
                },
            ]
            stats = {"added": 1, "modified": 1, "deleted": 1}
            header = "Mock Recent Changes"

        return {
            "success": True,
            "changes": changes,
            "stats": stats,
            "header": header,
            "is_mock": True,
            "metadata": {
                "store_path": store_path,
                "commit1": commit1,
                "commit2": commit2,
                "total_changes": len(changes),
            },
        }

    def _generate_real_diff(self, store_path, commit1, commit2):
        """Generate real diff using ProllyTree's diff functionality."""
        try:
            import subprocess

            if commit1 and commit2:
                # Compare two specific commits using ProllyTree
                changes = self._get_prollytree_diff_between_commits(
                    store_path, commit1, commit2
                )
                header = f"Comparing {commit1[:8]} → {commit2[:8]}"
            else:
                # Compare last two commits
                print("🔍 Real showing last two commits")
                # Get the last two commit hashes
                result = subprocess.run(
                    ["git", "log", "--format=%H", "-2"],
                    cwd=store_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0 and result.stdout.strip():
                    commits = result.stdout.strip().split("\n")
                    if len(commits) >= 2:
                        # Compare the two most recent commits using ProllyTree
                        latest_commit = commits[0]
                        previous_commit = commits[1]
                        changes = self._get_prollytree_diff_between_commits(
                            store_path, previous_commit, latest_commit
                        )
                        header = f"Changes: {previous_commit[:8]} → {latest_commit[:8]}"
                    elif len(commits) == 1:
                        # Only one commit, show all data as added
                        latest_commit = commits[0]
                        changes = self._get_prollytree_initial_commit(
                            store_path, latest_commit
                        )
                        header = f"Initial commit: {latest_commit[:8]}"
                    else:
                        changes = []
                        header = "No commits found"
                else:
                    # No commits yet or git error
                    changes = []
                    header = "No commits found"

            # Calculate stats
            stats = {"added": 0, "modified": 0, "deleted": 0}
            for change in changes:
                stats[change["type"]] += 1

            return {
                "success": True,
                "changes": changes,
                "stats": stats,
                "header": header,
                "is_mock": False,
                "metadata": {
                    "store_path": store_path,
                    "commit1": commit1,
                    "commit2": commit2,
                    "total_changes": len(changes),
                },
            }

        except Exception as e:
            print(f"Error generating real diff: {e}")
            # Fallback to showing no changes
            return {
                "success": True,
                "changes": [],
                "stats": {"added": 0, "modified": 0, "deleted": 0},
                "header": "Unable to generate diff",
                "is_mock": False,
                "error": str(e),
                "metadata": {
                    "store_path": store_path,
                    "commit1": commit1,
                    "commit2": commit2,
                    "total_changes": 0,
                },
            }

    def _get_prollytree_diff_between_commits(self, store_path, commit1, commit2):
        """Get diff between two commits using ProllyTree's native diff."""
        try:
            import subprocess

            changes = []

            # Get the tree root hashes from git for both commits
            # The root hash should be stored in a file or as part of the commit

            # Method 1: Try to get root hash from the commit message or a special file
            # First, let's check what files exist at each commit
            result1 = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", commit1],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            result2 = subprocess.run(
                ["git", "ls-tree", "-r", "--name-only", commit2],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            if result1.returncode == 0 and result2.returncode == 0:
                files1 = (
                    set(result1.stdout.strip().split("\n")) if result1.stdout else set()
                )
                files2 = (
                    set(result2.stdout.strip().split("\n")) if result2.stdout else set()
                )

                # Try to get tree data by examining the actual data files
                # Get all JSON files that represent the actual memory data
                data_files1 = [
                    f
                    for f in files1
                    if f.endswith(".json") and not ("config" in f or "metadata" in f)
                ]
                data_files2 = [
                    f
                    for f in files2
                    if f.endswith(".json") and not ("config" in f or "metadata" in f)
                ]

                # Build data dictionaries from the files
                data1 = {}
                for file in data_files1:
                    result = subprocess.run(
                        ["git", "show", f"{commit1}:{file}"],
                        cwd=store_path,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        try:
                            # Convert file path to memory key
                            key = file.replace(".json", "").replace("/", ":")
                            data1[key] = result.stdout
                        except Exception:
                            pass

                data2 = {}
                for file in data_files2:
                    result = subprocess.run(
                        ["git", "show", f"{commit2}:{file}"],
                        cwd=store_path,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode == 0:
                        try:
                            # Convert file path to memory key
                            key = file.replace(".json", "").replace("/", ":")
                            data2[key] = result.stdout
                        except Exception:
                            pass

                print(
                    f"📊 Commit1 has {len(data1)} memory keys, Commit2 has {len(data2)} memory keys"
                )

                # Compare the data
                keys1_set = set(data1.keys())
                keys2_set = set(data2.keys())

                added_keys = keys2_set - keys1_set
                removed_keys = keys1_set - keys2_set
                common_keys = keys1_set & keys2_set

                print(
                    f"📈 Added: {len(added_keys)}, Removed: {len(removed_keys)}, Common: {len(common_keys)}"
                )

                # Process added keys
                for key in added_keys:
                    try:
                        content = self._parse_memory_content(data2[key])
                        if content:  # Only add if there's actual content
                            changes.append(
                                {
                                    "path": self._format_key_as_path(key),
                                    "type": "added",
                                    "new_content": content,
                                }
                            )
                    except Exception as e:
                        print(f"Error processing added key {key}: {e}")

                # Process removed keys
                for key in removed_keys:
                    try:
                        content = self._parse_memory_content(data1[key])
                        if content:  # Only add if there's actual content
                            changes.append(
                                {
                                    "path": self._format_key_as_path(key),
                                    "type": "deleted",
                                    "old_content": content,
                                }
                            )
                    except Exception as e:
                        print(f"Error processing removed key {key}: {e}")

                # Process potentially modified keys
                for key in common_keys:
                    try:
                        if data1[key] != data2[key]:
                            old_content = self._parse_memory_content(data1[key])
                            new_content = self._parse_memory_content(data2[key])
                            if (
                                old_content != new_content
                            ):  # Only add if content actually changed
                                changes.append(
                                    {
                                        "path": self._format_key_as_path(key),
                                        "type": "modified",
                                        "old_content": old_content,
                                        "new_content": new_content,
                                    }
                                )
                    except Exception as e:
                        print(f"Error processing modified key {key}: {e}")

                # Filter out non-memory changes (like config files)
                memory_changes = [
                    c
                    for c in changes
                    if not any(
                        skip in c["path"] for skip in ["config", "metadata", "mapping"]
                    )
                ]

                if memory_changes:
                    print(
                        f"✨ Returning {len(memory_changes)} memory changes (filtered from {len(changes)} total)"
                    )
                    return memory_changes
                elif changes:
                    print(
                        f"⚠️ Only found config/metadata changes, returning all {len(changes)} changes"
                    )
                    return changes

            print("⚠️ No changes found, falling back to git diff")
            return self._get_git_diff_between_commits(store_path, commit1, commit2)

        except Exception:
            import traceback

            traceback.print_exc()
            # Fallback to git-based diff
            return self._get_git_diff_between_commits(store_path, commit1, commit2)

    def _get_prollytree_initial_commit(self, store_path, commit):
        """Get all content from the initial commit using ProllyTree."""
        try:
            import subprocess

            from prollytree import VersionedKvStore

            store = VersionedKvStore(store_path)

            # Save current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            current_branch = result.stdout.strip() if result.returncode == 0 else "main"

            changes = []

            try:
                # Checkout to the commit
                subprocess.run(
                    ["git", "checkout", commit], cwd=store_path, capture_output=True
                )

                # Get all keys
                all_keys = store.list_keys()

                for key in all_keys:
                    try:
                        key_str = (
                            key.decode("utf-8") if isinstance(key, bytes) else str(key)
                        )
                        value = store.get(key)
                        if value:
                            content = self._parse_prollytree_value(value)
                            changes.append(
                                {
                                    "path": self._format_key_as_path(key_str),
                                    "type": "added",
                                    "new_content": content,
                                }
                            )
                    except Exception:
                        pass

            finally:
                # Restore original branch
                subprocess.run(
                    ["git", "checkout", current_branch],
                    cwd=store_path,
                    capture_output=True,
                )

            return changes

        except Exception as e:
            print(f"Error getting ProllyTree initial commit: {e}")
            # Fallback to git-based diff
            return self._get_git_diff_from_empty(store_path, commit)

    def _format_key_as_path(self, key):
        """Format a ProllyTree key as a semantic path."""
        # Remove namespace prefix and convert to dot notation
        if ":" in key:
            parts = key.split(":")
            # Skip namespace parts and join the rest with dots
            if len(parts) > 1:
                return ".".join(parts[1:])
        return key

    def _parse_prollytree_value(self, value):
        """Parse a value from ProllyTree store."""
        try:
            import json

            # If it's bytes, decode it
            if isinstance(value, bytes):
                value = value.decode("utf-8")

            # Try to parse as JSON
            if isinstance(value, str):
                try:
                    data = json.loads(value)
                    return self._parse_memory_content(json.dumps(data))
                except json.JSONDecodeError:
                    return str(value)[:200]

            # If it's already a dict or other type
            if isinstance(value, dict):
                if "content" in value:
                    return str(value["content"])
                elif "memories" in value and isinstance(value["memories"], list):
                    # Aggregated memory
                    memories = value["memories"][:3]
                    content_parts = []
                    for memory in memories:
                        if isinstance(memory, dict) and "content" in memory:
                            content_parts.append(str(memory["content"])[:100])
                    return " | ".join(content_parts) if content_parts else str(value)

            return str(value)[:200] if value else ""

        except Exception:
            return str(value)[:200] if value else ""

    def _get_git_diff_between_commits(self, store_path, commit1, commit2):
        """Get diff between two specific commits."""
        import subprocess

        try:
            # Get list of changed files between commits
            result = subprocess.run(
                ["git", "diff", "--name-status", f"{commit1}..{commit2}"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            changes = []
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split("\t", 1)
                        if len(parts) >= 2:
                            status, filename = parts[0], parts[1]

                            # Convert git status to our format
                            if status == "A":
                                change_type = "added"
                            elif status == "D":
                                change_type = "deleted"
                            elif status == "M":
                                change_type = "modified"
                            else:
                                change_type = "modified"  # fallback

                            # Try to get file content for the changes
                            old_content, new_content = (
                                self._get_file_content_at_commits(
                                    store_path, filename, commit1, commit2, change_type
                                )
                            )

                            change = {
                                "path": filename.replace(".json", "").replace("/", "."),
                                "type": change_type,
                            }

                            if old_content is not None:
                                change["old_content"] = old_content
                            if new_content is not None:
                                change["new_content"] = new_content

                            changes.append(change)

            return changes

        except Exception as e:
            print(f"Error getting git diff between commits: {e}")
            return []

    def _get_git_diff_working_vs_commit(self, store_path, commit):
        """Get diff between working directory and a specific commit."""
        import subprocess

        try:
            # Get list of changed files between working directory and commit
            result = subprocess.run(
                ["git", "diff", "--name-status", commit],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            changes = []
            if result.returncode == 0 and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    if line:
                        parts = line.split("\t", 1)
                        if len(parts) >= 2:
                            status, filename = parts[0], parts[1]

                            # Convert git status to our format
                            if status == "A":
                                change_type = "added"
                            elif status == "D":
                                change_type = "deleted"
                            elif status == "M":
                                change_type = "modified"
                            else:
                                change_type = "modified"

                            # Get file content for the changes
                            old_content, new_content = (
                                self._get_file_content_working_vs_commit(
                                    store_path, filename, commit, change_type
                                )
                            )

                            change = {
                                "path": filename.replace(".json", "").replace("/", "."),
                                "type": change_type,
                            }

                            if old_content is not None:
                                change["old_content"] = old_content
                            if new_content is not None:
                                change["new_content"] = new_content

                            changes.append(change)

            return changes

        except Exception as e:
            print(f"Error getting git diff working vs commit: {e}")
            return []

    def _get_git_diff_from_empty(self, store_path, commit):
        """Get diff from empty tree to a specific commit (for initial commit)."""
        import subprocess

        try:
            # Get list of all files in the commit (everything is added)
            result = subprocess.run(
                ["git", "diff-tree", "--name-only", "--no-commit-id", commit],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            changes = []
            if result.returncode == 0 and result.stdout:
                for filename in result.stdout.strip().split("\n"):
                    if filename:
                        # Get content for the added file
                        new_content = None
                        try:
                            content_result = subprocess.run(
                                ["git", "show", f"{commit}:{filename}"],
                                cwd=store_path,
                                capture_output=True,
                                text=True,
                            )
                            if content_result.returncode == 0:
                                new_content = self._parse_memory_content(
                                    content_result.stdout
                                )
                        except Exception:
                            pass

                        change = {
                            "path": filename.replace(".json", "").replace("/", "."),
                            "type": "added",
                        }

                        if new_content is not None:
                            change["new_content"] = new_content

                        changes.append(change)

            return changes

        except Exception as e:
            print(f"Error getting git diff from empty: {e}")
            return []

    def _get_file_content_at_commits(
        self, store_path, filename, commit1, commit2, change_type
    ):
        """Get file content at specific commits."""
        import subprocess

        old_content = None
        new_content = None

        try:
            if change_type != "added":
                # Get old content from commit1
                result = subprocess.run(
                    ["git", "show", f"{commit1}:{filename}"],
                    cwd=store_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    old_content = self._parse_memory_content(result.stdout)

            if change_type != "deleted":
                # Get new content from commit2
                result = subprocess.run(
                    ["git", "show", f"{commit2}:{filename}"],
                    cwd=store_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    new_content = self._parse_memory_content(result.stdout)

        except Exception as e:
            print(f"Error getting file content at commits: {e}")

        return old_content, new_content

    def _get_file_content_working_vs_commit(
        self, store_path, filename, commit, change_type
    ):
        """Get file content comparing working directory vs commit."""
        import subprocess

        old_content = None
        new_content = None

        try:
            if change_type != "added":
                # Get old content from commit
                result = subprocess.run(
                    ["git", "show", f"{commit}:{filename}"],
                    cwd=store_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    old_content = self._parse_memory_content(result.stdout)

            if change_type != "deleted":
                # Get current content from working directory
                file_path = Path(store_path) / filename
                if file_path.exists():
                    with open(file_path) as f:
                        new_content = self._parse_memory_content(f.read())

        except Exception as e:
            print(f"Error getting file content working vs commit: {e}")

        return old_content, new_content

    def _parse_memory_content(self, raw_content):
        """Parse memory content from JSON file."""
        try:
            import json

            data = json.loads(raw_content)

            # Extract meaningful content from the memory data
            if isinstance(data, dict):
                if "content" in data:
                    return str(data["content"])
                elif "memories" in data and isinstance(data["memories"], list):
                    # Aggregated memory - show first few entries
                    memories = data["memories"][:3]  # Show first 3
                    content_parts = []
                    for memory in memories:
                        if isinstance(memory, dict) and "content" in memory:
                            content_parts.append(str(memory["content"])[:100])
                    return " | ".join(content_parts) if content_parts else str(data)
                else:
                    return str(data)
            else:
                return str(data)

        except Exception:
            # If not valid JSON or other error, return raw content truncated
            return str(raw_content)[:200] if raw_content else ""


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

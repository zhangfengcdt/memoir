# SPDX-License-Identifier: Apache-2.0
"""
Memory handler for memory store operations.
"""

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from memoir.classifier.intelligent import IntelligentClassifier
from memoir.memento.timeline import TimelineMemento
from memoir.store.prolly_adapter import ProllyTreeStore
from memoir.taxonomy.loader import TaxonomyLoader


class MemoryHandler(BaseAPIHandler):
    """Handler for memory operations."""

    def handle_update_memory_api(self):
        """Write exact content to an exact taxonomy key (bypasses classifier).

        Used by the "Edit" flow in the memory-details popup. Unlike
        /api/remember this does not run the LLM classifier — the caller
        supplies the key they want to overwrite, and we just persist + commit.
        """
        try:
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            key = data.get("key")
            content = data.get("content")
            namespace = data.get("namespace") or "default"
            # Source of the edit, set by the frontend so we can record it in
            # the commit message. One of: "manual", "llm", "llm+manual".
            edit_source = (data.get("edit_source") or "manual").strip().lower()
            if edit_source not in ("manual", "llm", "llm+manual"):
                edit_source = "manual"
            instructions = (data.get("instructions") or "").strip()

            if not store_path:
                self.handler.send_error(400, "Missing 'path' parameter")
                return
            if not key:
                self.handler.send_error(400, "Missing 'key' parameter")
                return
            if content is None:
                self.handler.send_error(400, "Missing 'content' parameter")
                return
            if not Path(store_path).exists():
                self.handler.send_error(404, f"Store path does not exist: {store_path}")
                return

            from memoir.services.memory_service import MemoryService

            service = MemoryService(store_path)

            # remember(path=key) bypasses the classifier entirely and commits
            # directly — exactly what an edit flow needs.
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    service.remember(content, namespace=namespace, path=key)
                )
            finally:
                loop.close()

            if not result.success:
                self.handler.send_error(500, result.error or "Failed to update memory")
                return

            # The store auto-commits with a generic "Store <key> in <ns>"
            # message. Amend it so the history records *how* the edit was
            # made (manual, LLM, or LLM+manual). Truncate the user-supplied
            # instructions string so a long prompt can't blow up the message.
            label = {
                "manual": "Manual edit",
                "llm": "LLM-assisted edit",
                "llm+manual": "LLM-assisted edit (manually adjusted)",
            }.get(edit_source, "Manual edit")

            commit_message = f"{label}: {namespace}:{key}"
            if edit_source in ("llm", "llm+manual") and instructions:
                snippet = instructions.replace("\n", " ").strip()
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                commit_message += f"\n\nInstructions: {snippet}"

            amended_hash = result.commit_hash
            try:
                import subprocess

                amend = subprocess.run(
                    ["git", "commit", "--amend", "-m", commit_message],
                    cwd=store_path,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if amend.returncode == 0:
                    rev = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=store_path,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if rev.returncode == 0 and rev.stdout.strip():
                        amended_hash = rev.stdout.strip()
            except Exception:
                # Amend is a polish-only step. If it fails, we still wrote
                # the data and committed it under the auto-generated message.
                pass

            payload = {
                "success": True,
                "key": result.key,
                "namespace": result.namespace,
                "full_key": f"{result.namespace}:{result.key}",
                "commit_hash": amended_hash,
                "commit_date": result.commit_date,
                "edit_source": edit_source,
                "commit_message": commit_message,
                "message": f"Updated '{namespace}:{key}'",
            }
            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(payload).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error updating memory: {e!s}")

    def handle_rewrite_memory_api(self):
        """Use the UI's LLM to rewrite memory content per natural-language instructions.

        Returns the proposed new content without writing to the store. The
        frontend loads this into the edit textarea and the user saves via
        /api/update-memory if they're happy with it.
        """
        try:
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            current_content = data.get("current_content", "") or ""
            instructions = (data.get("instructions") or "").strip()
            key = data.get("key") or ""

            if not instructions:
                self.handler.send_error(400, "Missing 'instructions' parameter")
                return

            from memoir.llm import default_ui_model, get_llm

            try:
                llm = get_llm(model=default_ui_model(), temperature=0.2)
            except Exception as e:
                self.handler.send_error(500, f"Error initializing LLM: {e!s}")
                return

            prompt = (
                "You are rewriting a single memory entry for a memory store.\n"
                f"Memory key: {key or '(unknown)'}\n"
                "Current content:\n"
                "---\n"
                f"{current_content}\n"
                "---\n"
                "Rewrite instructions from the user:\n"
                f"{instructions}\n\n"
                "Return ONLY the new content as plain text — no preamble, no "
                "markdown fences, no commentary. Preserve the original tone "
                "and level of detail unless the instructions say otherwise."
            )

            try:
                response = llm.invoke(prompt)
                new_content = (response.content or "").strip()
            except Exception as e:
                self.handler.send_error(500, f"LLM rewrite failed: {e!s}")
                return

            if not new_content:
                self.handler.send_error(500, "LLM returned empty content")
                return

            payload = {"success": True, "new_content": new_content}
            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(payload).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error rewriting memory: {e!s}")

    def handle_remember_api(self):
        """Handle /remember command to classify and store content."""
        try:
            import time

            step_timings = {}
            remember_start = time.time()

            # Read POST data
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            content = data.get("content")
            namespace = data.get("namespace") or "default"

            if not store_path:
                self.handler.send_error(400, "Missing 'path' parameter")
                return

            if not content:
                self.handler.send_error(400, "Missing 'content' parameter")
                return

            if not Path(store_path).exists():
                self.handler.send_error(404, f"Store path does not exist: {store_path}")
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
                from memoir.llm import default_ui_model, get_llm
                from memoir.taxonomy.taxonomy import TaxonomyVersion

                # Initialize LLM for classification
                llm = get_llm(model=default_ui_model(), temperature=0)

                # Initialize TaxonomyLoader to load taxonomy from store
                taxonomy_loader = TaxonomyLoader(store)
                if not taxonomy_loader.has_taxonomy_in_store():
                    taxonomy_loader.init_store(include_builtin=True)

                classifier = IntelligentClassifier(
                    llm=llm,
                    taxonomy_version=TaxonomyVersion.GENERAL,
                    confidence_thresholds={
                        "high": 0.8,  # High confidence threshold - memories above this are stored immediately
                        "medium": 0.5,  # Medium confidence threshold - memories above this are considered good
                        "low": 0.0,  # CRITICAL: Low confidence threshold - anything below this gets REJECTED
                    },
                    min_items_for_expansion=2,  # Lower threshold for demo - higher values = less taxonomy expansion
                    taxonomy_loader=taxonomy_loader,
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
            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error storing memory: {e!s}")

    def handle_forget_api(self):
        """Handle /forget command to delete a memory key."""
        try:
            # Read POST data
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            key = data.get("key")
            namespace = data.get("namespace") or "default"

            if not store_path:
                self.handler.send_error(400, "Missing 'path' parameter")
                return

            if not key:
                self.handler.send_error(400, "Missing 'key' parameter")
                return

            if not Path(store_path).exists():
                self.handler.send_error(404, f"Store path does not exist: {store_path}")
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
            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error deleting memory: {e!s}")

    def handle_recall_api(self, parsed_path):
        """Handle API requests for recalling memories using IntelligentSearchEngine."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        query = query_params.get("query", [None])[0]
        person = query_params.get("person", [None])[0]  # New person parameter
        mode = query_params.get("mode", ["single"])[0]

        if not store_path:
            self.handler.send_error(400, "Missing 'path' parameter")
            return

        if not query:
            self.handler.send_error(400, "Missing 'query' parameter")
            return

        if mode not in ("single", "tiered"):
            self.handler.send_error(
                400, f"Invalid 'mode': {mode!r}. Expected 'single' or 'tiered'."
            )
            return

        if not Path(store_path).exists():
            self.handler.send_error(404, f"Store path does not exist: {store_path}")
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
                from memoir.llm import default_ui_model, get_llm

                llm = get_llm(model=default_ui_model(), temperature=0)
            except Exception as e:
                self.handler.send_error(500, f"Error initializing LLM: {e!s}")
                return

            # Initialize IntelligentSearchEngine with TaxonomyLoader
            from memoir.search.intelligent import IntelligentSearchEngine

            # Initialize TaxonomyLoader to load taxonomy from store
            taxonomy_loader = TaxonomyLoader(store)
            if not taxonomy_loader.has_taxonomy_in_store():
                taxonomy_loader.init_store(include_builtin=True)

            search_engine = IntelligentSearchEngine(
                llm=llm, store=store, taxonomy_loader=taxonomy_loader
            )

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
                        query,
                        namespace="default",
                        limit=10,
                        return_prompts=True,
                        person_filter=person,
                        mode=mode,
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
                                    person_filter=person,
                                    mode=mode,
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
            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(response_data).encode())

        except Exception as e:
            error_msg = f"Error during recall search: {e!s}"
            print(f"Recall API error: {e}")
            import traceback

            traceback.print_exc()

            response_data = {"success": False, "error": error_msg}
            self.handler.send_response(500)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(response_data).encode())

#!/usr/bin/env python3
"""
Simple HTTP server to serve the Memoir UI and handle memory store data.
"""

import http.server
import json
import socketserver
import sys
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


from memoir.memento.location import LocationMemento
from memoir.memento.timeline import TimelineMemento
from memoir.store.prolly_adapter import ProllyTreeStore
from memoir.ui.handlers.branch_handler import BranchHandler
from memoir.ui.handlers.crypto_handler import CryptoHandler
from memoir.ui.handlers.memory_handler import MemoryHandler

# Import modular handlers
from memoir.ui.handlers.store_handler import StoreHandler
from memoir.ui.handlers.utils import UtilityHandler

PORT = 8080


class ReusableTCPServer(socketserver.TCPServer):
    """TCPServer with SO_REUSEADDR enabled so quick restarts don't trip over
    TIME_WAIT sockets from a prior run."""

    allow_reuse_address = True


_WEBAPP_DIST = Path(__file__).parent / "webapp" / "dist"


class MemoryStoreHandler(http.server.SimpleHTTPRequestHandler):
    """Serves the React webapp bundle from webapp/dist with SPA-style routing."""

    serve_root: Path = _WEBAPP_DIST
    index_filename: str = "index.html"
    spa_fallback: bool = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(self.serve_root), **kwargs)

    def handle(self):
        # Bump the idle watchdog's last-activity timestamp on every request
        # so the server only counts as "idle" when no request has arrived
        # for a whole idle_timeout window.
        srv = getattr(self, "server", None)
        if srv is not None and hasattr(srv, "last_activity"):
            srv.last_activity = time.monotonic()
        return super().handle()

    def _ensure_handlers_initialized(self):
        """Initialize handlers if not already done."""
        if not hasattr(self, "store_handler") or self.store_handler is None:
            self.store_handler = StoreHandler(self)
        if not hasattr(self, "utility_handler") or self.utility_handler is None:
            self.utility_handler = UtilityHandler(self)
        if not hasattr(self, "memory_handler") or self.memory_handler is None:
            self.memory_handler = MemoryHandler(self)
        if not hasattr(self, "branch_handler") or self.branch_handler is None:
            self.branch_handler = BranchHandler(self)
        if not hasattr(self, "crypto_handler") or self.crypto_handler is None:
            self.crypto_handler = CryptoHandler(self)

    def send_json_response(self, data, status_code=200):
        """Send JSON response with proper error handling for broken pipes."""
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected - this is normal, don't log as error
            pass

    def do_GET(self):
        parsed_path = urlparse(self.path)

        # Handle API endpoints
        if parsed_path.path == "/api/store":
            self._ensure_handlers_initialized()
            self.store_handler.handle_store_api(parsed_path)
        elif parsed_path.path == "/api/proof":
            self._ensure_handlers_initialized()
            self.crypto_handler.handle_proof_api(parsed_path)
        elif parsed_path.path == "/api/verify":
            self._ensure_handlers_initialized()
            self.crypto_handler.handle_verify_api(parsed_path)
        elif parsed_path.path == "/api/blame":
            self._ensure_handlers_initialized()
            self.crypto_handler.handle_blame_api(parsed_path)
        elif parsed_path.path == "/api/branches":
            self._ensure_handlers_initialized()
            self.branch_handler.handle_branches_api(parsed_path)
        elif parsed_path.path == "/api/commits":
            self._ensure_handlers_initialized()
            self.branch_handler.handle_commits_api(parsed_path)
        elif parsed_path.path == "/api/current-branch":
            self._ensure_handlers_initialized()
            self.branch_handler.handle_current_branch_api(parsed_path)
        elif parsed_path.path == "/api/branches-status":
            self._ensure_handlers_initialized()
            self.branch_handler.handle_branches_status_api(parsed_path)
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
            self._ensure_handlers_initialized()
            self.memory_handler.handle_recall_api(parsed_path)
        elif parsed_path.path == "/api/diff":
            self.handle_diff_api(parsed_path)
        elif parsed_path.path == "/api/commit-range-diff":
            self.handle_commit_range_diff_api(parsed_path)
        elif parsed_path.path == "/api/statistics":
            self.handle_statistics_api(parsed_path)
        elif parsed_path.path == "/":
            self.path = "/" + self.index_filename
            super().do_GET()
        else:
            # The React SPA uses client-side routing, so any URL that doesn't
            # match a real file under webapp/dist (and isn't an API/asset
            # request) falls back to index.html — the React router takes over.
            if self.spa_fallback and not self._is_static_asset(parsed_path.path):
                disk_path = self.serve_root / parsed_path.path.lstrip("/")
                if not disk_path.exists():
                    self.path = "/" + self.index_filename
            super().do_GET()

    @staticmethod
    def _is_static_asset(url_path: str) -> bool:
        # Anything under /assets/ or with a file extension is a real file
        # lookup; missing ones should 404, not fall back to index.html.
        if url_path.startswith("/assets/"):
            return True
        tail = url_path.rsplit("/", 1)[-1]
        return "." in tail

    def do_POST(self):
        parsed_path = urlparse(self.path)

        # Handle API endpoints
        if parsed_path.path == "/api/new":
            self._ensure_handlers_initialized()
            self.store_handler.handle_new_api()
        elif parsed_path.path == "/api/remember":
            self._ensure_handlers_initialized()
            self.memory_handler.handle_remember_api()
        elif parsed_path.path == "/api/forget":
            self._ensure_handlers_initialized()
            self.memory_handler.handle_forget_api()
        elif parsed_path.path == "/api/update-memory":
            self._ensure_handlers_initialized()
            self.memory_handler.handle_update_memory_api()
        elif parsed_path.path == "/api/rewrite-memory":
            self._ensure_handlers_initialized()
            self.memory_handler.handle_rewrite_memory_api()
        elif parsed_path.path == "/api/answer":
            self.handle_answer_api()
        elif parsed_path.path == "/api/checkout":
            self._ensure_handlers_initialized()
            self.branch_handler.handle_checkout_api()
        elif parsed_path.path == "/api/create-branch":
            self._ensure_handlers_initialized()
            self.branch_handler.handle_create_branch_api()
        elif parsed_path.path == "/api/merge-branch":
            self._ensure_handlers_initialized()
            self.branch_handler.handle_merge_branch_api()
        elif parsed_path.path == "/api/sync-branches":
            self._ensure_handlers_initialized()
            self.branch_handler.handle_sync_branches_api()
        elif parsed_path.path == "/api/delete-branch":
            self._ensure_handlers_initialized()
            self.branch_handler.handle_delete_branch_api()
        elif parsed_path.path == "/api/timeline":
            self.handle_timeline_post_api()
        elif parsed_path.path == "/api/location":
            self.handle_location_post_api()

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
                            self._ensure_handlers_initialized()
                            content = self.utility_handler.extract_timeline_content(
                                data, date_str
                            )

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

            if not Path(store_path).exists():
                self.send_error(404, f"Store path does not exist: {store_path}")
                return

            # If content is provided, use the IntelligentClassifier to extract timeline events
            if content and not (date_str and description):
                # Initialize the IntelligentClassifier
                try:
                    from memoir.classifier.intelligent import IntelligentClassifier
                    from memoir.llm import default_ui_model, get_llm
                    from memoir.taxonomy.loader import TaxonomyLoader
                    from memoir.taxonomy.taxonomy import TaxonomyVersion

                    # Initialize store for taxonomy loading
                    store = ProllyTreeStore(
                        path=store_path,
                        enable_versioning=True,
                        auto_commit=True,
                        cache_size=10000,
                    )

                    # Initialize TaxonomyLoader to load taxonomy from store
                    taxonomy_loader = TaxonomyLoader(store)
                    if not taxonomy_loader.has_taxonomy_in_store():
                        taxonomy_loader.init_store(include_builtin=True)

                    llm = get_llm(model=default_ui_model(), temperature=0)
                    classifier = IntelligentClassifier(
                        llm=llm,
                        taxonomy_version=TaxonomyVersion.GENERAL,
                        taxonomy_loader=taxonomy_loader,
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

            # Validate date format
            if len(date_str) != 8 or not date_str.isdigit():
                self.send_error(
                    400, f"Invalid date format. Expected YYYYMMDD, got: {date_str}"
                )
                return

            # Initialize store (may already be initialized if content was processed)
            if "store" not in locals():
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
                        self._ensure_handlers_initialized()
                        content = self.utility_handler.extract_location_content(
                            data, location_key
                        )

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

            # If content is provided, use the IntelligentClassifier to extract location events
            if content and not (location_name and description):
                # Initialize the IntelligentClassifier
                try:
                    from memoir.classifier.intelligent import IntelligentClassifier
                    from memoir.llm import default_ui_model, get_llm
                    from memoir.taxonomy.loader import TaxonomyLoader
                    from memoir.taxonomy.taxonomy import TaxonomyVersion

                    # Initialize store for taxonomy loading
                    store = ProllyTreeStore(
                        path=store_path,
                        enable_versioning=True,
                        auto_commit=True,
                        cache_size=10000,
                    )

                    # Initialize TaxonomyLoader to load taxonomy from store
                    taxonomy_loader = TaxonomyLoader(store)
                    if not taxonomy_loader.has_taxonomy_in_store():
                        taxonomy_loader.init_store(include_builtin=True)

                    llm = get_llm(model=default_ui_model(), temperature=0)
                    classifier = IntelligentClassifier(
                        llm=llm,
                        taxonomy_version=TaxonomyVersion.GENERAL,
                        taxonomy_loader=taxonomy_loader,
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

            # Initialize store (may already be initialized if content was processed)
            if "store" not in locals():
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
        ]  # all, taxonomy, timeline, places, keys
        key_pattern = query_params.get("pattern", [None])[0]  # For keys type

        if not store_path:
            self.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.send_error(404, f"Store path does not exist: {store_path}")
            return

        # Validate keys type requires pattern
        if summary_type == "keys" and not key_pattern:
            self.send_error(400, "Keys summary type requires 'pattern' parameter")
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
                from memoir.llm import default_ui_model, get_llm

                llm = get_llm(model=default_ui_model(), temperature=0)
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
                matching_keys = []  # Initialize for keys summary type

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

                if summary_type == "keys":
                    keys_start = time.time()
                    summary_result = loop.run_until_complete(
                        self._summarize_keys_by_pattern(store, llm, key_pattern)
                    )
                    summaries["keys"] = summary_result["summary"]
                    matching_keys = summary_result["matching_keys"]
                    timing_info["keys"] = round(time.time() - keys_start, 2)

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

                # Add keys-specific data to result
                if summary_type == "keys":
                    result["matching_keys"] = matching_keys
                    result["metadata"]["matching_keys_count"] = len(matching_keys)

                # Send response
                self.send_json_response(result)

            finally:
                loop.close()

        except Exception as e:
            import contextlib

            with contextlib.suppress(BrokenPipeError, ConnectionResetError):
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
                self._ensure_handlers_initialized()
                content = self.utility_handler.extract_memory_content(data)
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

    async def _summarize_keys_by_pattern(self, store, llm, pattern):
        """Summarize memories matching a specific key pattern."""
        try:
            import fnmatch

            # First, check if this is an exact key (with or without namespace)
            # If pattern has namespace prefix, try to get it directly
            exact_key_data = None
            has_wildcards = any(wildcard in pattern for wildcard in ["*", "?", "["])

            if not has_wildcards:
                # This looks like an exact key (no wildcards)
                # Try with pattern as-is (could include namespace)
                try:
                    key_bytes = pattern.encode("utf-8")
                    value_bytes = store.tree.get(key_bytes)
                    if value_bytes:
                        exact_key_data = store._decode_value(value_bytes)
                        # Extract the path part for display
                        path_part = (
                            pattern.split(":", 1)[1] if ":" in pattern else pattern
                        )
                        matching_memories = [(path_part, exact_key_data)]
                        matching_keys = [path_part]
                        print(f"Found exact key: {pattern}")
                except Exception as e:
                    print(f"Exact key lookup failed for {pattern}: {e}")
                    pass  # Fall through to pattern matching

            # If not found as exact key, proceed with pattern matching or find children
            if exact_key_data is None:
                # For pattern without wildcards, treat it as prefix to find all children
                search_pattern = pattern
                is_prefix_search = not has_wildcards

                if ":" in pattern and is_prefix_search:
                    # Remove namespace prefix for semantic path matching
                    search_pattern = pattern.split(":", 1)[1]

                print(
                    f"Searching for pattern: {search_pattern}, is_prefix: {is_prefix_search}"
                )

                # Get all memories from default namespace
                all_memories = []
                try:
                    if hasattr(store.tree, "list_keys"):
                        # Using list_keys to get all keys
                        keys = store.tree.list_keys()
                        all_keys = [key.decode("utf-8") for key in keys]

                        for full_key in all_keys:
                            # Parse the key to extract namespace and semantic path
                            if ":" in full_key:
                                parts = full_key.split(":")
                                if (
                                    len(parts) >= 3
                                    and parts[0] == "memory"
                                    and parts[1] == "general"
                                ):
                                    # Handle memory:general:path format
                                    namespace_part = "memory:general"
                                    semantic_path = ":".join(parts[2:])
                                elif len(parts) == 2:
                                    # Handle default:path format
                                    namespace_part, semantic_path = parts
                                else:
                                    namespace_part = ":".join(parts[:-1])
                                    semantic_path = parts[-1]
                            else:
                                namespace_part = ""
                                semantic_path = full_key

                            # Only include default namespace for now
                            if namespace_part == "default":
                                # Get the value for this key
                                key_bytes = full_key.encode("utf-8")
                                value_bytes = store.tree.get(key_bytes)
                                if value_bytes:
                                    value_data = store._decode_value(value_bytes)
                                    all_memories.append((semantic_path, value_data))
                    else:
                        # Fallback to search method
                        namespace_tuple = ("default",)
                        items = list(store.search(namespace_tuple))
                        all_memories = [(path, data) for _, path, data in items]

                except Exception as e:
                    print(f"Error reading from store: {e}")
                    return {
                        "summary": f"Error accessing store data: {e!s}",
                        "matching_keys": [],
                    }

                # Filter keys by pattern (support wildcards and prefix matching)
                matching_memories = []
                matching_keys = []

                print(f"Found {len(all_memories)} total memories in default namespace")

                for path, data in all_memories:
                    # Match against the search pattern (without namespace)
                    if is_prefix_search:
                        # For exact keys without wildcards, match exact or children
                        if path == search_pattern or path.startswith(
                            search_pattern + "."
                        ):
                            matching_memories.append((path, data))
                            matching_keys.append(path)
                            print(f"Matched (prefix): {path}")
                    else:
                        # Use wildcard pattern matching
                        if fnmatch.fnmatch(path, search_pattern):
                            matching_memories.append((path, data))
                            matching_keys.append(path)
                            print(f"Matched (pattern): {path}")

                print(f"Total matches: {len(matching_keys)}")

            if not matching_memories:
                return {
                    "summary": f"No memories found matching pattern: {pattern}",
                    "matching_keys": [],
                }

            # Extract content from matching memories for LLM analysis
            content_for_analysis = []
            for path, data in matching_memories:
                # Extract readable content from the data
                self._ensure_handlers_initialized()
                content = self.utility_handler.extract_memory_content(data)
                if content and content.strip():
                    content_for_analysis.append(f"Key: {path}\nContent: {content}")

            if not content_for_analysis:
                return {
                    "summary": f"Found {len(matching_keys)} matching keys but no readable content",
                    "matching_keys": matching_keys,
                }

            # Create LLM prompt for summarization
            content_text = "\n\n".join(content_for_analysis)
            prompt = f"""Analyze and summarize the following memory data that matches the pattern "{pattern}":

{content_text}

Please provide a comprehensive summary that includes:
1. The main themes and topics present in these memories
2. Key patterns or commonalities across the data
3. Important information or insights from the content
4. The overall scope and nature of the information

Provide a clear, informative summary in 2-4 paragraphs."""

            response = await llm.ainvoke([{"role": "user", "content": prompt}])

            return {"summary": response.content.strip(), "matching_keys": matching_keys}

        except Exception as e:
            return {
                "summary": f"Error summarizing keys by pattern: {e!s}",
                "matching_keys": [],
            }

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

    def handle_answer_api(self):
        """Handle API requests for generating answers based on recalled memories."""
        try:
            # Get request body
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                post_data = self.rfile.read(content_length)
                request_data = json.loads(post_data.decode("utf-8"))
            else:
                request_data = {}

            query = request_data.get("query")
            memories = request_data.get("memories")
            person = request_data.get("person")

            if not query:
                self.send_error(400, "Missing 'query' parameter")
                return

            if not memories:
                self.send_error(400, "Missing 'memories' parameter")
                return

            # Initialize LLM
            try:
                from memoir.llm import default_ui_model, get_llm

                llm_model = default_ui_model()
                llm = get_llm(model=llm_model, temperature=0.7)
            except Exception as e:
                error_response = {
                    "success": False,
                    "error": f"Error initializing LLM: {e!s}",
                }
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(error_response).encode())
                return

            # Create the prompt for answering
            prompt = f"""Based on the following memories retrieved from the knowledge base, please answer the user's question.

User's Question: {query}
{f"Context: This question is related to {person}." if person else ""}

Retrieved Memories:
{memories}

Instructions:
1. Answer the question directly using only the information from the retrieved memories
2. If the memories don't contain enough information to fully answer the question, acknowledge what you can answer and what you cannot
3. Be concise but comprehensive
4. If the memories contain conflicting information, mention this
5. Do not make up information not present in the memories

Answer:"""

            # Generate the answer
            try:
                response = llm.invoke(prompt)
                answer = response.content.strip()
            except Exception as e:
                error_response = {
                    "success": False,
                    "error": f"Error generating answer: {e!s}",
                }
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(error_response).encode())
                return

            # Send successful response
            response_data = {
                "success": True,
                "answer": answer,
                "prompt": prompt,
                "metadata": {
                    "query": query,
                    "person": person,
                    "llm_model": llm_model,
                    "memories_provided": bool(memories),
                },
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())

        except Exception as e:
            import traceback

            traceback.print_exc()
            error_response = {"success": False, "error": f"Server error: {e!s}"}
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode())

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

    @staticmethod
    def _shortref(ref):
        """Truncate only full 40-char commit hashes; leave branch names intact."""
        if not ref:
            return ref
        if len(ref) == 40 and all(c in "0123456789abcdef" for c in ref.lower()):
            return ref[:8]
        return ref

    def _kv_diffs_to_changes(self, kv_diffs):
        """Convert a list of prollytree KvDiff objects to our UI change format.

        Returns (changes, stats). Filters out empty/no-content diffs so the UI
        stays clean.
        """
        self._ensure_handlers_initialized()
        extract = self.utility_handler.extract_diff_content
        changes = []
        for kv_diff in kv_diffs:
            key_str = (
                kv_diff.key.decode("utf-8")
                if isinstance(kv_diff.key, bytes)
                else str(kv_diff.key)
            )
            # Strip namespace prefix (e.g. "default:path" → "path").
            if ":" in key_str:
                parts = key_str.split(":", 1)
                if len(parts) == 2:
                    key_str = parts[1]

            op = kv_diff.operation
            op_type = op.operation_type

            if op_type == "Added":
                new_content = extract(op.value)
                if new_content and new_content.strip() and new_content != "No content":
                    changes.append(
                        {"path": key_str, "type": "added", "new_content": new_content}
                    )
            elif op_type == "Removed":
                old_content = extract(op.value)
                if old_content and old_content.strip() and old_content != "No content":
                    changes.append(
                        {"path": key_str, "type": "deleted", "old_content": old_content}
                    )
            elif op_type == "Modified":
                old_content = extract(op.old_value)
                new_content = extract(op.new_value)
                if (
                    old_content != new_content
                    and old_content
                    and new_content
                    and old_content.strip()
                    and new_content.strip()
                ):
                    changes.append(
                        {
                            "path": key_str,
                            "type": "modified",
                            "old_content": old_content,
                            "new_content": new_content,
                        }
                    )

        stats = {"added": 0, "modified": 0, "deleted": 0}
        for c in changes:
            if c["type"] in stats:
                stats[c["type"]] += 1
        return changes, stats

    def _generate_commit_range_diff(self, store_path, from_ref, to_ref):
        """Return per-commit diffs for the range from_ref..to_ref.

        One entry per commit introduced to `to_ref` that is not reachable from
        `from_ref`. Each entry includes that commit's metadata plus the key-level
        changes it introduced (diff against its first parent).
        """
        self._ensure_handlers_initialized()
        try:
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            if not hasattr(store.tree, "diff"):
                return {
                    "success": False,
                    "error": "VersionedKvStore diff not available",
                }

            import subprocess

            # Chronological order so the list reads top-to-bottom as they landed.
            rev_list = subprocess.run(
                [
                    "git",
                    "log",
                    "--reverse",
                    "--format=%H|%h|%s|%an|%ae|%at|%P",
                    f"{from_ref}..{to_ref}",
                ],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            if rev_list.returncode != 0:
                return {
                    "success": False,
                    "error": f"git log failed: {rev_list.stderr.strip() or 'unknown error'}",
                }

            commits_out = []
            lines = [
                line for line in rev_list.stdout.strip().split("\n") if line.strip()
            ]

            for line in lines:
                parts = line.split("|")
                if len(parts) < 7:
                    continue
                full_hash, short_hash, message, author, email, ts, parents_str = parts[
                    :7
                ]
                parents = parents_str.strip().split() if parents_str.strip() else []
                parent = parents[0] if parents else None

                # Diff the commit against its first parent. For the initial
                # commit (no parent), we skip the diff and just record the
                # metadata — the memory-creation payload shows up in the first
                # commit that has a parent.
                changes: list = []
                stats = {"added": 0, "modified": 0, "deleted": 0}
                if parent:
                    try:
                        kv_diffs = store.tree.diff(parent, full_hash)
                        changes, stats = self._kv_diffs_to_changes(kv_diffs)
                    except Exception as e:
                        print(f"  diff {parent[:8]}..{short_hash}: {e}")

                commits_out.append(
                    {
                        "hash": full_hash,
                        "short_hash": short_hash,
                        "message": message,
                        "author": author,
                        "email": email,
                        "timestamp": int(ts) if ts.isdigit() else 0,
                        "changes": changes,
                        "stats": stats,
                    }
                )

            return {
                "success": True,
                "from": from_ref,
                "to": to_ref,
                "commits": commits_out,
            }

        except Exception as e:
            import traceback

            traceback.print_exc()
            return {"success": False, "error": str(e)}

    def handle_commit_range_diff_api(self, parsed_path):
        """Return per-commit diffs for a given range: ?from=...&to=..."""
        try:
            query_params = parse_qs(parsed_path.query)
            store_path = query_params.get("path", [""])[0]
            from_ref = query_params.get("from", [None])[0]
            to_ref = query_params.get("to", [None])[0]

            if not store_path:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps({"success": False, "error": "path is required"}).encode()
                )
                return

            if not from_ref or not to_ref:
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"success": False, "error": "from and to are required"}
                    ).encode()
                )
                return

            if not Path(store_path).exists():
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(
                    json.dumps(
                        {"success": False, "error": "Store path does not exist"}
                    ).encode()
                )
                return

            response_data = self._generate_commit_range_diff(
                store_path, from_ref, to_ref
            )

            # Successful payloads are shape-validated via the schema so
            # drift in ``_generate_commit_range_diff`` surfaces as a 500
            # with a clear error rather than as an unreadable UI state.
            if response_data.get("success"):
                from memoir.ui.schemas import RangeDiffResponse

                body = RangeDiffResponse.from_legacy(response_data)
                payload = body.to_legacy()
                status = 200
            else:
                payload = response_data
                status = 500

            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        except Exception as e:
            import traceback

            traceback.print_exc()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode())

    def _generate_real_diff(self, store_path, commit1, commit2):
        """Generate real diff using VersionedKvStore's new diff functionality."""
        self._ensure_handlers_initialized()
        try:
            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Check if store has versioning enabled and diff method available
            if not hasattr(store.tree, "diff"):
                print(
                    "VersionedKvStore diff method not available, falling back to mock"
                )
                return self._generate_mock_diff(commit1, commit2, store_path)

            # Determine which commits to compare
            if commit1 and commit2:
                # Compare two specific commits
                from_ref = commit1
                to_ref = commit2
                header = (
                    f"Comparing {self._shortref(commit1)} → {self._shortref(commit2)}"
                )
            else:
                # For default case, we need to check what commits are available
                import subprocess

                # Get the list of commits
                try:
                    result = subprocess.run(
                        ["git", "log", "--format=%H", "-2"],
                        cwd=store_path,
                        capture_output=True,
                        text=True,
                    )

                    if result.returncode == 0 and result.stdout.strip():
                        commits = result.stdout.strip().split("\n")
                        if len(commits) >= 2:
                            # Compare the two most recent commits
                            from_ref = commits[1]  # Previous commit
                            to_ref = commits[0]  # Latest commit
                            header = f"Changes: {self._shortref(commits[1])} → {self._shortref(commits[0])}"
                        elif len(commits) == 1:
                            # Only one commit, show all data as added (initial commit)
                            from_ref = None  # No previous commit
                            to_ref = commits[0]
                            header = f"Initial commit: {self._shortref(commits[0])}"
                        else:
                            # No commits
                            print("No commits found in repository")
                            return {
                                "success": True,
                                "changes": [],
                                "stats": {"added": 0, "modified": 0, "deleted": 0},
                                "header": "No commits found",
                                "is_mock": False,
                                "metadata": {
                                    "store_path": store_path,
                                    "total_changes": 0,
                                },
                            }
                    else:
                        # Git command failed or no output
                        print("Git log command failed or returned no output")
                        return self._generate_mock_diff(None, None, store_path)

                except Exception as e:
                    print(f"Error getting git commits: {e}")
                    return self._generate_mock_diff(None, None, store_path)

            print(f"🔍 Generating diff from {from_ref} to {to_ref}")

            # Use the new diff method
            if from_ref is None:
                # For initial commit, we need to show all current data as additions
                # This might require a different approach since there's no "from" state
                print("Handling initial commit case - showing all data as additions")
                # Try to get all current keys and treat them as additions
                try:
                    # Get current state keys
                    if hasattr(store.tree, "list_keys"):
                        keys = store.tree.list_keys()
                        changes = []
                        for key_bytes in keys:
                            try:
                                key_str = (
                                    key_bytes.decode("utf-8")
                                    if isinstance(key_bytes, bytes)
                                    else str(key_bytes)
                                )
                                value_bytes = store.tree.get(key_bytes)
                                if value_bytes:
                                    value_data = store._decode_value(value_bytes)
                                    self._ensure_handlers_initialized()
                                    content = self.utility_handler.extract_diff_content(
                                        value_data
                                    )

                                    # Remove namespace prefix for display
                                    path = key_str
                                    if ":" in key_str and key_str.count(":") >= 1:
                                        parts = key_str.split(":", 1)
                                        if len(parts) == 2:
                                            path = parts[1]

                                    changes.append(
                                        {
                                            "path": path,
                                            "type": "added",
                                            "new_content": content,
                                        }
                                    )
                            except Exception as e:
                                print(f"Error processing key {key_bytes}: {e}")

                        kv_diffs = changes  # Use our manually created changes
                    else:
                        kv_diffs = []
                except Exception as e:
                    print(f"Error getting initial commit data: {e}")
                    kv_diffs = []
            else:
                # Normal case: compare two commits
                kv_diffs = store.tree.diff(from_ref, to_ref)

            print(f"📊 Found {len(kv_diffs)} key differences")

            # Convert KvDiff objects to our UI format
            changes = []

            if from_ref is None:
                # For initial commit case, kv_diffs is already in our format
                changes = kv_diffs
            else:
                # Normal case: process KvDiff objects
                for kv_diff in kv_diffs:
                    # Extract the semantic path from the key
                    key_str = (
                        kv_diff.key.decode("utf-8")
                        if isinstance(kv_diff.key, bytes)
                        else str(kv_diff.key)
                    )

                    # Remove namespace prefix if present (e.g., "default:" -> "")
                    path = key_str
                    if ":" in key_str and key_str.count(":") >= 1:
                        parts = key_str.split(":", 1)
                        if len(parts) == 2:
                            path = parts[1]  # Use the semantic path part

                    # Convert the diff to our change format
                    # Access the operation object and its type
                    operation = kv_diff.operation
                    operation_type = operation.operation_type

                    if operation_type == "Added":
                        # Extract readable content from new value
                        self._ensure_handlers_initialized()
                        new_content = self.utility_handler.extract_diff_content(
                            operation.value
                        )

                        # Only include if there's meaningful content
                        if (
                            new_content
                            and new_content.strip()
                            and new_content != "No content"
                        ):
                            changes.append(
                                {
                                    "path": path,
                                    "type": "added",
                                    "new_content": new_content,
                                }
                            )
                        else:
                            print(
                                f"🔍 Skipping empty/meaningless added content for key: {path}"
                            )
                    elif operation_type == "Removed":
                        # Extract readable content from old value
                        self._ensure_handlers_initialized()
                        old_content = self.utility_handler.extract_diff_content(
                            operation.value
                        )

                        # Only include if there's meaningful content
                        if (
                            old_content
                            and old_content.strip()
                            and old_content != "No content"
                        ):
                            changes.append(
                                {
                                    "path": path,
                                    "type": "deleted",
                                    "old_content": old_content,
                                }
                            )
                        else:
                            print(
                                f"🔍 Skipping empty/meaningless removed content for key: {path}"
                            )
                    elif operation_type == "Modified":
                        # Extract readable content from both old and new values
                        self._ensure_handlers_initialized()
                        old_content = self.utility_handler.extract_diff_content(
                            operation.old_value
                        )
                        self._ensure_handlers_initialized()
                        new_content = self.utility_handler.extract_diff_content(
                            operation.new_value
                        )

                        # Only include if the content actually changed and is meaningful
                        if (
                            old_content != new_content
                            and old_content
                            and new_content
                            and old_content.strip()
                            and new_content.strip()
                        ):
                            changes.append(
                                {
                                    "path": path,
                                    "type": "modified",
                                    "old_content": old_content,
                                    "new_content": new_content,
                                }
                            )
                        elif old_content == new_content:
                            print(f"🔍 Skipping identical content for key: {path}")
                            print(
                                f"    Content: {old_content[:100]}{'...' if len(old_content) > 100 else ''}"
                            )
                        else:
                            print(
                                f"🔍 Skipping empty/meaningless modified content for key: {path}"
                            )
                            print(f"    Old: '{old_content}', New: '{new_content}'")

            # Calculate stats
            stats = {"added": 0, "modified": 0, "deleted": 0}
            for change in changes:
                change_type = change["type"]
                if change_type in stats:
                    stats[change_type] += 1

            print(f"📈 Statistics: {stats}")

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
                    "from_ref": from_ref,
                    "to_ref": to_ref,
                    "total_changes": len(changes),
                },
            }

        except Exception as e:
            print(f"Error generating real diff: {e}")
            import traceback

            traceback.print_exc()

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

    def handle_statistics_api(self, parsed_path):
        """Handle statistics API requests."""
        try:
            query_params = parse_qs(parsed_path.query)
            store_path = query_params.get("path", [""])[0]

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

            # Initialize store
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Gather comprehensive statistics
            stats = {}

            # 1. Storage metrics
            stats["storage"] = self._get_storage_statistics(store, store_path)

            # 2. Tree structure analysis
            stats["tree_structure"] = self._analyze_tree_structure(store)

            # 3. Versioning information
            stats["versioning"] = self._get_versioning_statistics(store_path)

            # 4. Store metadata
            stats["metadata"] = self._get_store_metadata(store_path)

            # 5. Performance metrics (if available)
            stats["performance"] = self._get_performance_metrics(store)

            # 6. Taxonomy statistics
            stats["taxonomy"] = self._get_taxonomy_statistics(store)

            # 7. Content analysis
            stats["content"] = self._analyze_content_statistics(store)

            # 8. System information
            import platform

            stats["system"] = {
                "python_version": sys.version.split()[0],
                "platform": platform.system(),
                "platform_version": platform.version()[
                    :50
                ],  # Truncate long version strings
                "memoir_version": "1.0.0",  # You might want to get this from a version file
            }

            from memoir.ui.schemas import StatisticsResponse

            body = StatisticsResponse.model_validate(
                {
                    "success": True,
                    "statistics": stats,
                    "generated_at": self._get_current_timestamp(),
                    "store_path": store_path,
                }
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body.model_dump(mode="json")).encode())

        except Exception as e:
            error_msg = f"Error getting statistics: {e!s}"
            print(f"Statistics API error: {e}")
            import traceback

            traceback.print_exc()

            response_data = {"success": False, "error": error_msg}
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode())

    def _get_storage_statistics(self, store, store_path):
        """Get storage-related statistics."""
        try:
            # Get all keys
            all_keys = []
            namespaces = set()

            # Try to list all keys if method exists
            if hasattr(store.tree, "list_keys"):
                keys_bytes = store.tree.list_keys()
                for key_bytes in keys_bytes:
                    key_str = (
                        key_bytes.decode("utf-8")
                        if isinstance(key_bytes, bytes)
                        else str(key_bytes)
                    )
                    all_keys.append(key_str)
                    # Extract namespace
                    if ":" in key_str:
                        namespace = key_str.split(":")[0]
                        namespaces.add(namespace)

            # Calculate store size
            store_size_mb = 0
            try:
                import os

                total_size = 0
                for dirpath, _dirnames, filenames in os.walk(store_path):
                    for filename in filenames:
                        filepath = os.path.join(dirpath, filename)
                        if os.path.exists(filepath):
                            total_size += os.path.getsize(filepath)
                store_size_mb = round(total_size / (1024 * 1024), 2)
            except Exception:
                pass

            return {
                "total_keys": len(all_keys),
                "total_namespaces": len(namespaces),
                "namespaces": list(namespaces),
                "store_size_mb": store_size_mb,
                "average_key_length": (
                    round(sum(len(k) for k in all_keys) / len(all_keys), 1)
                    if all_keys
                    else 0
                ),
            }
        except Exception as e:
            print(f"Error getting storage statistics: {e}")
            return {
                "total_keys": 0,
                "total_namespaces": 0,
                "store_size_mb": 0,
                "error": str(e),
            }

    def _analyze_tree_structure(self, store):
        """Analyze memory tree structure."""
        try:
            all_keys = []
            if hasattr(store.tree, "list_keys"):
                keys_bytes = store.tree.list_keys()
                for key_bytes in keys_bytes:
                    key_str = (
                        key_bytes.decode("utf-8")
                        if isinstance(key_bytes, bytes)
                        else str(key_bytes)
                    )
                    all_keys.append(key_str)

            levels = {}
            paths_by_depth = {}
            categories = {}

            for key in all_keys:
                # Remove namespace if present
                path = key.split(":", 1)[1] if ":" in key else key

                parts = path.split(".")
                depth = len(parts)

                # Count nodes per level
                if depth not in levels:
                    levels[depth] = 0
                levels[depth] += 1

                # Track paths by depth
                if depth not in paths_by_depth:
                    paths_by_depth[depth] = []
                paths_by_depth[depth].append(path)

                # Count by root category
                if parts:
                    root = parts[0]
                    categories[root] = categories.get(root, 0) + 1

            # Find deepest and widest paths
            deepest_path = ""
            if paths_by_depth:
                max_depth = max(paths_by_depth.keys())
                if paths_by_depth[max_depth]:
                    deepest_path = max(paths_by_depth[max_depth], key=len)

            widest_category = ""
            widest_count = 0
            if categories:
                widest_category = max(categories.items(), key=lambda x: x[1])[0]
                widest_count = categories[widest_category]

            return {
                "total_levels": max(levels.keys()) if levels else 0,
                "nodes_per_level": {f"level_{k}": v for k, v in sorted(levels.items())},
                "deepest_path": deepest_path,
                "widest_branch": (
                    f"{widest_category} ({widest_count} nodes)"
                    if widest_category
                    else ""
                ),
                "categories": categories,
                "total_nodes": len(all_keys),
            }
        except Exception as e:
            print(f"Error analyzing tree structure: {e}")
            return {"total_levels": 0, "total_nodes": 0, "error": str(e)}

    def _get_versioning_statistics(self, store_path):
        """Get git versioning statistics."""
        try:
            import subprocess

            stats = {}

            # Get current branch
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            stats["current_branch"] = (
                result.stdout.strip() if result.returncode == 0 else "unknown"
            )

            # Get current commit
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            stats["current_commit"] = (
                result.stdout.strip() if result.returncode == 0 else "unknown"
            )

            # Count commits
            result = subprocess.run(
                ["git", "rev-list", "--count", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            stats["total_commits"] = (
                int(result.stdout.strip())
                if result.returncode == 0 and result.stdout.strip()
                else 0
            )

            # Get all branches
            result = subprocess.run(
                ["git", "branch", "-a"], cwd=store_path, capture_output=True, text=True
            )
            if result.returncode == 0:
                branches = [
                    b.strip().replace("* ", "")
                    for b in result.stdout.strip().split("\n")
                    if b.strip()
                ]
                stats["branches"] = branches
                stats["total_branches"] = len(branches)
            else:
                stats["branches"] = []
                stats["total_branches"] = 0

            # Get last commit info
            result = subprocess.run(
                ["git", "log", "-1", "--format=%ci|%s"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split("|", 1)
                if len(parts) == 2:
                    stats["last_commit_date"] = parts[0].split()[
                        0
                    ]  # Just the date part
                    stats["last_commit_message"] = parts[1][
                        :100
                    ]  # Truncate long messages

            # Count commits this week
            result = subprocess.run(
                ["git", "rev-list", "--count", "--since=1.week.ago", "HEAD"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            stats["commits_this_week"] = (
                int(result.stdout.strip())
                if result.returncode == 0 and result.stdout.strip()
                else 0
            )

            # Check for uncommitted changes
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                changes = [line for line in result.stdout.strip().split("\n") if line]
                stats["uncommitted_changes"] = len(changes)
            else:
                stats["uncommitted_changes"] = 0

            return stats

        except Exception as e:
            print(f"Error getting versioning statistics: {e}")
            return {
                "current_branch": "unknown",
                "current_commit": "unknown",
                "total_commits": 0,
                "total_branches": 0,
                "error": str(e),
            }

    def _get_store_metadata(self, store_path):
        """Get store metadata."""
        try:
            import os
            from datetime import datetime

            path_obj = Path(store_path)

            # Get creation and modification times
            stat = os.stat(store_path)
            creation_time = datetime.fromtimestamp(stat.st_ctime).isoformat()
            last_access_time = datetime.fromtimestamp(stat.st_atime).isoformat()

            # Calculate age in days
            age_days = (datetime.now() - datetime.fromtimestamp(stat.st_ctime)).days

            # Check if git initialized
            git_dir = path_obj / ".git"
            git_initialized = git_dir.exists() and git_dir.is_dir()

            return {
                "store_path": str(store_path),
                "store_type": "ProllyTreeStore",
                "creation_time": creation_time,
                "last_access_time": last_access_time,
                "store_age_days": age_days,
                "versioning_enabled": True,
                "auto_commit": False,
                "cache_size": 10000,
                "git_initialized": git_initialized,
                "store_format_version": "1.0",
            }

        except Exception as e:
            print(f"Error getting store metadata: {e}")
            return {"store_path": str(store_path), "error": str(e)}

    def _get_performance_metrics(self, store):
        """Get performance metrics if available."""
        try:
            # These would typically come from the store's internal metrics
            # For now, return placeholder data
            return {
                "operations": {
                    "reads": 0,
                    "writes": 0,
                    "searches": 0,
                    "classifications": 0,
                },
                "timing_averages": {
                    "avg_read_ms": 0.8,
                    "avg_write_ms": 12.4,
                    "avg_search_ms": 5.2,
                    "avg_classification_ms": 850.3,
                },
                "memory_usage": {
                    "cache_hit_ratio": 0.89,
                    "cache_size_mb": 45.2,
                    "active_connections": 1,
                },
            }
        except Exception as e:
            print(f"Error getting performance metrics: {e}")
            return {"error": str(e)}

    def _get_taxonomy_statistics(self, store):
        """Get taxonomy and classification statistics."""
        try:
            # Count paths by category
            all_keys = []
            if hasattr(store.tree, "list_keys"):
                keys_bytes = store.tree.list_keys()
                for key_bytes in keys_bytes:
                    key_str = (
                        key_bytes.decode("utf-8")
                        if isinstance(key_bytes, bytes)
                        else str(key_bytes)
                    )
                    all_keys.append(key_str)

            paths_by_category = {}
            for key in all_keys:
                path = key.split(":", 1)[1] if ":" in key else key

                parts = path.split(".")
                if parts:
                    root = parts[0]
                    paths_by_category[root] = paths_by_category.get(root, 0) + 1

            return {
                "total_paths": len(all_keys),
                "categories": len(paths_by_category),
                "paths_by_category": paths_by_category,
                "confidence_thresholds": {"high": 0.8, "medium": 0.5, "low": 0.0},
                "classification_accuracy": 0.91,  # Placeholder
            }
        except Exception as e:
            print(f"Error getting taxonomy statistics: {e}")
            return {"error": str(e)}

    def _analyze_content_statistics(self, store):
        """Analyze content patterns and types."""
        try:
            # Get sample of memories for analysis
            memory_types = {}
            total_chars = 0
            memory_count = 0

            if hasattr(store.tree, "list_keys"):
                keys_bytes = store.tree.list_keys()
                for key_bytes in keys_bytes[:100]:  # Sample first 100 for performance
                    try:
                        value_bytes = store.tree.get(key_bytes)
                        if value_bytes:
                            # Try to decode and analyze
                            if isinstance(value_bytes, bytes):
                                content = value_bytes.decode("utf-8")
                            else:
                                content = str(value_bytes)

                            total_chars += len(content)
                            memory_count += 1

                            # Try to determine memory type from path
                            key_str = (
                                key_bytes.decode("utf-8")
                                if isinstance(key_bytes, bytes)
                                else str(key_bytes)
                            )
                            if "conversation" in key_str.lower():
                                memory_type = "conversation_memory"
                            elif "profile" in key_str.lower():
                                memory_type = "profile_update"
                            elif "timeline" in key_str.lower():
                                memory_type = "timeline_event"
                            elif "location" in key_str.lower():
                                memory_type = "location_event"
                            elif "preference" in key_str.lower():
                                memory_type = "preference_setting"
                            else:
                                memory_type = "other"

                            memory_types[memory_type] = (
                                memory_types.get(memory_type, 0) + 1
                            )

                    except (UnicodeDecodeError, ValueError, TypeError) as e:
                        print(f"Warning: Error processing memory content: {e}")
                        continue

            return {
                "memory_types": memory_types,
                "total_memories_sampled": memory_count,
                "average_content_length": (
                    round(total_chars / memory_count, 1) if memory_count else 0
                ),
                "total_characters": total_chars,
            }
        except Exception as e:
            print(f"Error analyzing content statistics: {e}")
            return {"error": str(e)}

    def _get_current_timestamp(self):
        """Get current timestamp in ISO format."""
        from datetime import datetime

        return datetime.now().isoformat()


def run_server(port: int = 0, on_ready=None, idle_timeout: int = 300):
    """Run the Memoir UI HTTP server.

    ``port=0`` (the default) asks the OS for a free ephemeral port; pass an
    explicit port to pin it. Binds the socket first so port-conflict errors
    surface before any startup output. ``on_ready`` is called with the bound
    port after a successful bind but before ``serve_forever`` — use it to open
    a browser tab, etc.

    ``idle_timeout`` (seconds, default 300) auto-shuts-down the server when
    no HTTP request has arrived for that long. Pass ``0`` (or any non-positive
    value) to disable the watchdog and run indefinitely.

    Raises :class:`FileNotFoundError` if the webapp bundle hasn't been built
    yet (hint: run ``make ui-build``). Blocks until the server is shut down
    (Ctrl+C or the idle watchdog).
    """
    index = _WEBAPP_DIST / "index.html"
    if not index.is_file():
        raise FileNotFoundError(
            f"webapp bundle not found at {_WEBAPP_DIST}/index.html. "
            f"Run 'make ui-build' (or 'cd src/memoir/ui/webapp && pnpm run build') "
            f"to produce it, then retry."
        )

    # Bind first; this raises OSError (EADDRINUSE) before we print anything.
    with ReusableTCPServer(("", port), MemoryStoreHandler) as httpd:
        bound_port = httpd.server_address[1]
        print(f"Starting Memoir UI server on http://localhost:{bound_port}")
        print(f"Open http://localhost:{bound_port} in your browser")
        print("\nTo connect to a memory store, use the command in the UI:")
        print("  /connect /tmp/memoir_ui_store")
        if idle_timeout and idle_timeout > 0:
            print(f"\nServer will auto-stop after {idle_timeout}s of inactivity.")
        print("Press Ctrl+C to stop the server")

        # Seed the activity timestamp so the watchdog measures from startup.
        httpd.last_activity = time.monotonic()

        idle_stop_event = threading.Event()

        def _idle_watchdog():
            # Poll at a coarse but responsive interval (min 1s, max 5s).
            interval = max(1.0, min(5.0, idle_timeout / 10.0))
            while not idle_stop_event.wait(interval):
                if time.monotonic() - httpd.last_activity >= idle_timeout:
                    print(f"\nServer idle for {idle_timeout}s — shutting down.")
                    # serve_forever() is running on the main thread; shutdown()
                    # MUST be called from a different thread (this one).
                    threading.Thread(target=httpd.shutdown, daemon=True).start()
                    return

        watchdog_thread = None
        if idle_timeout and idle_timeout > 0:
            watchdog_thread = threading.Thread(
                target=_idle_watchdog, daemon=True, name="memoir-ui-idle-watchdog"
            )
            watchdog_thread.start()

        if on_ready is not None:
            try:
                on_ready(bound_port)
            except Exception as e:
                print(f"on_ready callback failed: {e}")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.shutdown()
        finally:
            # Ensure the watchdog exits cleanly so Python can shut down.
            idle_stop_event.set()


def main():
    run_server(PORT)  # python -m invocation keeps the historical 8080 default


if __name__ == "__main__":
    main()

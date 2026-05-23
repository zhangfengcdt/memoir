# SPDX-License-Identifier: Apache-2.0
"""HTTP handlers for the watch + search view in the memoir web UI.

Three endpoints:

- ``GET /api/watch/list?path=<store>``                     — registered watched paths
- ``GET /api/watch/files?path=<store>&watched=<root>``     — indexed files under a watched root
- ``GET /api/watch/stats?path=<store>&namespace=watch``    — proximity-tree stats
- ``GET /api/watch/search?path=<store>&query=...&namespace=watch&k=5``
"""

import logging
import os
from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler

logger = logging.getLogger(__name__)


class WatchHandler(BaseAPIHandler):
    """List watched paths, surface proximity-tree stats, and run vector
    search from the web UI."""

    def handle_list_api(self, parsed_path):
        from memoir.services.watch_service import WatchService

        store_path = self._require_store_path(parsed_path)
        if store_path is None:
            return
        try:
            result = WatchService(store_path).list()
            self.send_json_response(result.to_dict())
        except Exception as e:
            logger.exception("watch list failed")
            self.send_error_response(str(e))

    def handle_files_api(self, parsed_path):
        from memoir.services.watch_service import WatchService

        store_path = self._require_store_path(parsed_path)
        if store_path is None:
            return
        params = parse_qs(parsed_path.query)
        watched = params.get("watched", [None])[0]
        if not watched:
            self.send_error_response("Missing 'watched' parameter", 400)
            return
        try:
            result = WatchService(store_path).files(watched)
            self.send_json_response(result.to_dict())
        except Exception as e:
            logger.exception("watch files failed")
            self.send_error_response(str(e))

    def handle_stats_api(self, parsed_path):
        from memoir.services.vector_service import INDEX_NAME, VectorService

        store_path = self._require_store_path(parsed_path)
        if store_path is None:
            return
        params = parse_qs(parsed_path.query)
        namespace = params.get("namespace", ["watch"])[0]

        if not VectorService.feature_available():
            self.send_json_response(
                {
                    "available": False,
                    "namespace": namespace,
                    "reason": (
                        "prollytree was built without the proximity_text "
                        "feature; vector index is unavailable."
                    ),
                }
            )
            return

        try:
            svc = VectorService(store_path)
            ns_store = svc._get_ns_store()
            idx = INDEX_NAME

            # Opening is required before len/chunk_count/audit work — but
            # only if the index has been created (a fresh store with no
            # `memoir watch add` runs has no index yet).
            try:
                svc.open(namespace, idx)
            except Exception as open_err:
                self.send_json_response(
                    {
                        "available": True,
                        "namespace": namespace,
                        "index_name": idx,
                        "opened": False,
                        "doc_count": 0,
                        "chunk_count": 0,
                        "orphans": 0,
                        "missing": 0,
                        "in_sync": True,
                        "note": (
                            f"Index not yet initialized for namespace "
                            f"{namespace!r} ({open_err})."
                        ),
                    }
                )
                return

            doc_count = ns_store.text_index_len(namespace, idx)
            chunk_count = ns_store.text_index_chunk_count(namespace, idx)
            audit = ns_store.audit_text_index(namespace, idx)
            self.send_json_response(
                {
                    "available": True,
                    "namespace": namespace,
                    "index_name": idx,
                    "opened": True,
                    "doc_count": doc_count,
                    "chunk_count": chunk_count,
                    "orphans": len(audit.get("orphans_in_index", []) or []),
                    "missing": len(audit.get("missing_from_index", []) or []),
                    "in_sync": bool(audit.get("is_in_sync", True)),
                }
            )
        except Exception as e:
            logger.exception("watch stats failed")
            self.send_error_response(str(e))

    def handle_search_api(self, parsed_path):
        from memoir.services.search_service import SearchService

        store_path = self._require_store_path(parsed_path)
        if store_path is None:
            return
        params = parse_qs(parsed_path.query)
        query = params.get("query", [""])[0]
        namespace = params.get("namespace", ["watch"])[0]
        try:
            k = int(params.get("k", ["5"])[0])
        except ValueError:
            self.send_error_response("Invalid 'k' parameter (expected int)", 400)
            return

        if not query.strip():
            self.send_error_response("Missing 'query' parameter", 400)
            return
        # Bound k server-side so a malicious / fat-fingered client can't
        # ask for 100k hits.
        k = max(1, min(k, 100))

        # Suppress the onnxruntime native-stderr warning the same way the
        # CLI entry point does — the UI's HTTP server doesn't go through
        # `cli/main.py`.
        os.environ.setdefault("_MEMOIR_SUPPRESS_NATIVE_IMPORT_STDERR", "1")
        try:
            result = SearchService(store_path).search(query, namespace=namespace, k=k)
            self.send_json_response(result.to_dict())
        except Exception as e:
            logger.exception("watch search failed")
            self.send_error_response(str(e))

    def _require_store_path(self, parsed_path) -> str | None:
        params = parse_qs(parsed_path.query)
        store_path = params.get("path", [None])[0]
        if not store_path:
            self.send_error_response("Missing 'path' parameter", 400)
            return None
        if not Path(store_path).exists():
            self.send_error_response(f"Store path does not exist: {store_path}", 404)
            return None
        return store_path

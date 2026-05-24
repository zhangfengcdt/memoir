# SPDX-License-Identifier: Apache-2.0
"""HTTP handlers for the watch + search view in the memoir web UI.

Endpoints:

- ``GET  /api/watch/list?path=<store>``                     — registered watched paths
- ``GET  /api/watch/files?path=<store>&watched=<root>``     — indexed files under a watched root
- ``GET  /api/watch/stats?path=<store>&namespace=watch``    — proximity-tree stats
- ``GET  /api/watch/search?path=<store>&query=...&namespace=watch&k=5``
- ``POST /api/watch/add  {path, namespace?, model?}``       — kicks off indexing in a background
                                                              thread; the list endpoint surfaces
                                                              ``indexing: true`` until it finishes.
- ``POST /api/watch/remove {store, file}``                  — unregister + purge all of the file's
                                                              raw.<file>.* keys (KV + vector).
- ``POST /api/watch/scan {store, file, model?}``            — re-scan a registered file in a
                                                              background thread; uses the same
                                                              ``indexing: true`` flag as add.
- ``POST /api/watch/scan-all {store, model?}``              — re-scan every registered file in
                                                              one background thread, one file
                                                              at a time. Each file's row lights
                                                              up ``indexing: true`` while it's
                                                              being processed.
"""

import asyncio
import logging
import os
import threading
from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler

logger = logging.getLogger(__name__)


# Process-wide in-memory tracker for paths currently being indexed.
#
# Maps abs_path -> {"started_at": iso, "namespace": str, "error": str | None}.
# Removed when indexing completes (success or failure). The list endpoint
# joins this dict with the persisted ``watch:paths`` registry so the UI
# can show a transient "indexing…" badge.
#
# Process-local on purpose: a server restart loses the flag, which is
# fine — at worst the UI sees the row as "complete" until next refresh,
# and the underlying watch state is already committed.
_INDEXING: dict[str, dict] = {}
_INDEXING_LOCK = threading.Lock()

# Serialize concurrent watch.add calls so two background threads can't
# race on the single-writer prollytree store.
_ADD_LOCK = threading.Lock()


def _indexing_snapshot() -> dict[str, dict]:
    """Thread-safe read of ``_INDEXING`` for the list endpoint."""
    with _INDEXING_LOCK:
        return {k: dict(v) for k, v in _INDEXING.items()}


def _run_index_in_background(
    store_path: str,
    abs_path: str,
    action: str,  # "add" | "scan"
    namespace: str,
    model: str | None,
) -> None:
    """Background-thread worker for both ``watch add`` and ``watch scan``.

    Calls into ``WatchService`` under ``_ADD_LOCK`` (prollytree is a
    single-writer store, so we serialize). Clears the in-progress flag
    on success; on failure, stores the error on the flag entry and
    schedules a 30 s timer to drop the marker so the UI doesn't keep a
    stale "indexing failed" badge forever.
    """
    from memoir.services.watch_service import WatchService

    err: str | None = None
    try:
        with _ADD_LOCK:
            svc = WatchService(store_path, llm_model=model)
            if action == "add":
                result = asyncio.run(svc.add(abs_path, namespace=namespace))
                if not result.success:
                    err = result.error or "watch add failed"
            elif action == "scan":
                results = asyncio.run(svc.scan(path=abs_path, namespace=namespace))
                # ``scan`` returns a list of per-path results; the single-
                # file form always has 0 or 1 entries.
                if not results:
                    err = "no result from watch scan"
                elif not results[0].success:
                    err = results[0].error or "watch scan failed"
            else:
                err = f"unknown action: {action!r}"
    except Exception as e:
        logger.exception("watch %s background thread failed: %s", action, abs_path)
        err = f"{type(e).__name__}: {e}"
    finally:
        with _INDEXING_LOCK:
            if err is None:
                _INDEXING.pop(abs_path, None)
            else:
                entry = _INDEXING.get(abs_path, {})
                entry["error"] = err
                _INDEXING[abs_path] = entry
                # Best-effort: drop the error marker after 30s so the
                # UI doesn't show a stale "indexing failed" badge forever.
                threading.Timer(
                    30.0, lambda: _INDEXING.pop(abs_path, None)
                ).start()


def _run_scan_all_in_background(
    store_path: str,
    paths: list[str],
    model: str | None,
) -> None:
    """Background worker for ``POST /api/watch/scan-all``.

    Walks the list of registered paths and re-scans each via
    ``_run_index_in_background`` (the per-file worker), in order. We mark
    each path in ``_INDEXING`` *before* its scan starts and let the
    per-file worker pop it on completion, so only one row at a time
    shows the ``indexing…`` badge as the work progresses. Failures on
    one file don't stop the loop — the per-file worker stores the error
    on its ``_INDEXING`` entry, schedules cleanup, and we move on.
    """
    import datetime as _dt

    for path in paths:
        with _INDEXING_LOCK:
            # If something else is already indexing this path, skip it.
            existing = _INDEXING.get(path)
            if existing and existing.get("error") is None:
                logger.info(
                    "scan-all: skipping %s (already in-flight)", path
                )
                continue
            _INDEXING[path] = {
                "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "namespace": "watch",
                "error": None,
            }
        # _run_index_in_background takes the lock internally, runs the
        # scan, and pops the entry (or stamps an error). Call it inline
        # rather than spawning a new thread per file so the user sees
        # one-row-at-a-time progress through the registry.
        _run_index_in_background(store_path, path, "scan", "watch", model)


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
            data = result.to_dict()
            # Join in-flight indexing state so the UI can render a
            # transient "indexing…" badge per row. Paths in _INDEXING
            # that aren't yet in the persisted registry (the register
            # write happens inside _scan_path, mid-thread) get added as
            # synthetic entries so the row appears immediately.
            in_flight = _indexing_snapshot()
            persisted_paths = {e["path"] for e in data.get("entries") or []}
            for entry in data.get("entries") or []:
                state = in_flight.get(entry["path"])
                entry["indexing"] = state is not None and state.get("error") is None
                entry["indexing_error"] = (
                    state.get("error") if state else None
                )
            for path, state in in_flight.items():
                if path in persisted_paths:
                    continue
                data.setdefault("entries", []).append(
                    {
                        "path": path,
                        "kind": "file",
                        "namespace": state.get("namespace", "watch"),
                        "added_at": state.get("started_at", ""),
                        "last_scan": None,
                        "indexed_count": 0,
                        "indexing": state.get("error") is None,
                        "indexing_error": state.get("error"),
                    }
                )
                data["count"] = len(data["entries"])
            self.send_json_response(data)
        except Exception as e:
            logger.exception("watch list failed")
            self.send_error_response(str(e))

    def handle_add_api(self):
        """POST /api/watch/add — kicks off WatchService.add in the
        background; the list endpoint surfaces ``indexing: true`` until
        completion."""
        try:
            body = self.get_post_data()
        except ValueError as e:
            self.send_error_response(str(e), 400)
            return
        store_path = body.get("store")
        file_path = body.get("file")
        namespace = body.get("namespace") or "watch"
        model = body.get("model")
        if not store_path:
            self.send_error_response("Missing 'store' parameter", 400)
            return
        if not file_path:
            self.send_error_response("Missing 'file' parameter", 400)
            return
        if not Path(store_path).exists():
            self.send_error_response(
                f"Store path does not exist: {store_path}", 404
            )
            return
        abs_file = Path(file_path).expanduser().resolve()
        if not abs_file.exists():
            self.send_error_response(f"File does not exist: {abs_file}", 404)
            return
        if abs_file.is_dir():
            self.send_error_response(
                f"Folders are not supported: {abs_file}. "
                f"Add each file individually.",
                400,
            )
            return

        # Check if already in flight.
        with _INDEXING_LOCK:
            if str(abs_file) in _INDEXING and _INDEXING[str(abs_file)].get("error") is None:
                self.send_json_response(
                    {
                        "success": True,
                        "path": str(abs_file),
                        "indexing": True,
                        "already_in_flight": True,
                    },
                    status_code=200,
                )
                return
            import datetime as _dt

            _INDEXING[str(abs_file)] = {
                "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "namespace": namespace,
                "error": None,
            }

        threading.Thread(
            target=_run_index_in_background,
            args=(store_path, str(abs_file), "add", namespace, model),
            daemon=True,
            name=f"watch-add:{abs_file.name}",
        ).start()

        self.send_json_response(
            {
                "success": True,
                "path": str(abs_file),
                "indexing": True,
            },
            status_code=202,
        )

    def handle_scan_api(self):
        """POST /api/watch/scan — re-scan a registered watched file in a
        background thread. Uses the same ``_INDEXING`` tracker so the UI
        renders the same ``indexing: true`` badge during the re-scan."""
        try:
            body = self.get_post_data()
        except ValueError as e:
            self.send_error_response(str(e), 400)
            return
        store_path = body.get("store")
        file_path = body.get("file")
        namespace = body.get("namespace") or "watch"
        model = body.get("model")
        if not store_path:
            self.send_error_response("Missing 'store' parameter", 400)
            return
        if not file_path:
            self.send_error_response("Missing 'file' parameter", 400)
            return
        if not Path(store_path).exists():
            self.send_error_response(
                f"Store path does not exist: {store_path}", 404
            )
            return
        abs_file = str(Path(file_path).expanduser().resolve())

        with _INDEXING_LOCK:
            if abs_file in _INDEXING and _INDEXING[abs_file].get("error") is None:
                self.send_json_response(
                    {
                        "success": True,
                        "path": abs_file,
                        "indexing": True,
                        "already_in_flight": True,
                    },
                    status_code=200,
                )
                return
            import datetime as _dt

            _INDEXING[abs_file] = {
                "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(
                    timespec="seconds"
                ),
                "namespace": namespace,
                "error": None,
            }

        threading.Thread(
            target=_run_index_in_background,
            args=(store_path, abs_file, "scan", namespace, model),
            daemon=True,
            name=f"watch-scan:{Path(abs_file).name}",
        ).start()

        self.send_json_response(
            {
                "success": True,
                "path": abs_file,
                "indexing": True,
            },
            status_code=202,
        )

    def handle_scan_all_api(self):
        """POST /api/watch/scan-all — re-scan every registered file in
        the background. Iterates the registry, scanning one file at a
        time so each file's row lights up the ``indexing: true`` badge
        only while it's actually being processed. Returns 202 immediately
        with the list of paths queued."""
        try:
            body = self.get_post_data()
        except ValueError as e:
            self.send_error_response(str(e), 400)
            return
        store_path = body.get("store")
        model = body.get("model")
        if not store_path:
            self.send_error_response("Missing 'store' parameter", 400)
            return
        if not Path(store_path).exists():
            self.send_error_response(
                f"Store path does not exist: {store_path}", 404
            )
            return

        from memoir.services.watch_service import WatchService

        try:
            listing = WatchService(store_path).list()
        except Exception as e:
            logger.exception("scan-all: failed to read registry")
            self.send_error_response(str(e))
            return
        paths = [e.path for e in listing.entries] if listing.success else []
        if not paths:
            self.send_json_response(
                {"success": True, "scheduled": 0, "paths": [], "indexing": False},
                status_code=200,
            )
            return

        threading.Thread(
            target=_run_scan_all_in_background,
            args=(store_path, paths, model),
            daemon=True,
            name=f"watch-scan-all:{len(paths)}",
        ).start()

        self.send_json_response(
            {
                "success": True,
                "scheduled": len(paths),
                "paths": paths,
                "indexing": True,
            },
            status_code=202,
        )

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

    def handle_remove_api(self):
        """POST /api/watch/remove — unregister a watched file and tear down
        every ``raw.<file>.*`` key from both the KV store and the vector
        index. Behavior is always full cleanup (the service's ``remove``
        method ignores its purge flag and always purges)."""
        from memoir.services.watch_service import WatchService

        try:
            body = self.get_post_data()
        except ValueError as e:
            self.send_error_response(str(e), 400)
            return
        store_path = body.get("store")
        file_path = body.get("file")
        if not store_path:
            self.send_error_response("Missing 'store' parameter", 400)
            return
        if not file_path:
            self.send_error_response("Missing 'file' parameter", 400)
            return
        if not Path(store_path).exists():
            self.send_error_response(
                f"Store path does not exist: {store_path}", 404
            )
            return
        # ``WatchService.remove`` resolves the path itself, but we also clear
        # any in-flight indexing tracker so a removed file doesn't surface as
        # "indexing…" forever if the user cancels a slow add.
        abs_file = str(Path(file_path).expanduser().resolve())
        with _INDEXING_LOCK:
            _INDEXING.pop(abs_file, None)
        try:
            result = WatchService(store_path).remove(file_path)
            self.send_json_response(result.to_dict())
        except Exception as e:
            logger.exception("watch remove failed")
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

"""
Store handler for memory store operations.

Delegates to StoreService for business logic.
"""

import asyncio
import json
from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler


def _extract_content(value: object) -> object:
    """Pull the inner stored payload out of memoir's value envelope.

    `memoir remember` wraps writes as ``{"content": <payload>, "key": ..., "namespace": ..., ...}``.
    Callers want the payload itself. For metrics, the payload is a JSON
    string (we store ``json.dumps(accumulator)``); we return it parsed when
    possible so the UI can render structured fields without re-parsing.
    """
    if isinstance(value, dict) and "content" in value:
        inner = value["content"]
        if isinstance(inner, str):
            stripped = inner.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except (TypeError, ValueError):
                    return inner
        return inner
    return value


class StoreHandler(BaseAPIHandler):
    """Handler for memory store operations."""

    def handle_store_api(self, parsed_path):
        """Handle API requests for memory store data."""
        from memoir.services.store_service import StoreService
        from memoir.ui.schemas import StoreResponse

        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]

        if not store_path:
            self.send_error_response("Missing 'path' parameter", 400)
            return

        if not Path(store_path).exists():
            self.send_error_response(f"Store path does not exist: {store_path}", 404)
            return

        try:
            service = StoreService(store_path)
            data = service.read_store()
            # Round-trip through the schema to enforce required fields, then
            # emit the validated dict (which keeps any extra legacy keys —
            # ``extra='allow'`` on the model — so the old UI keeps working).
            body = StoreResponse.model_validate(data)
            self.send_json_response(body.model_dump(mode="json"))
        except Exception as e:
            self.send_error_response(str(e))

    def handle_onboard_api(self, parsed_path):
        """Return the codebase:onboard namespace as raw key/value pairs.

        No LLM. The UI renders the same compact view that SessionStart
        injects, so the structure is whatever the /memoir-onboard skill
        wrote — top-level roots like ``goal``, ``structure``, ``rules``,
        ``lessons``, ``_meta``.
        """
        from memoir.store.prolly_adapter import ProllyTreeStore

        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        if not store_path:
            self.send_error_response("Missing 'path' parameter", 400)
            return
        if not Path(store_path).exists():
            self.send_error_response(f"Store path does not exist: {store_path}", 404)
            return

        try:
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(store.asearch("codebase:onboard", ""))
            finally:
                loop.close()

            items = [
                {"key": key, "value": _extract_content(data)}
                for key, data in sorted(results, key=lambda kv: kv[0])
            ]
            self.send_json_response({"success": True, "items": items})
        except Exception as e:
            self.send_error_response(str(e))

    def handle_metrics_api(self, parsed_path):
        """Return all `metrics.*` keys in the default namespace on the
        current branch. Each value is the parsed accumulator JSON.

        After a /memoir-sync-branch, promoted branches' metrics ride
        along on the target, so when the caller is on main this returns
        every promoted branch's accumulator.
        """
        from memoir.store.prolly_adapter import ProllyTreeStore

        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        if not store_path:
            self.send_error_response("Missing 'path' parameter", 400)
            return
        if not Path(store_path).exists():
            self.send_error_response(f"Store path does not exist: {store_path}", 404)
            return

        try:
            store = ProllyTreeStore(
                path=store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                results = loop.run_until_complete(store.asearch("default", "metrics."))
            finally:
                loop.close()

            items = []
            for key, data in sorted(results, key=lambda kv: kv[0]):
                value = _extract_content(data)
                # Each metrics.turn.<branch> key encodes the branch name in
                # the path fragment — surface it explicitly so the UI can
                # group/render without re-parsing the key.
                branch = None
                if key.startswith("metrics.turn."):
                    branch = key[len("metrics.turn.") :]
                items.append({"key": key, "branch": branch, "value": value})

            self.send_json_response({"success": True, "items": items})
        except Exception as e:
            self.send_error_response(str(e))

    def handle_new_api(self):
        """Handle /new command to create a new git repository and initialize memory store."""
        from memoir.services.store_service import StoreService

        try:
            data = self.get_post_data()

            store_path = data.get("path")
            if not store_path:
                self.send_error_response("Missing 'path' parameter", 400)
                return

            service = StoreService()
            result = service.create_store(store_path)

            if result.success:
                self.send_json_response(
                    {
                        "success": True,
                        "path": result.path,
                        "message": result.message,
                    }
                )
            else:
                self.send_error_response(result.error or "Failed to create store", 400)

        except Exception as e:
            self.send_error_response(f"Error creating memory store: {e!s}")

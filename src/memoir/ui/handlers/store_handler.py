"""
Store handler for memory store operations.

Delegates to StoreService for business logic.
"""

from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler


class StoreHandler(BaseAPIHandler):
    """Handler for memory store operations."""

    def handle_store_api(self, parsed_path):
        """Handle API requests for memory store data."""
        from memoir.services.store_service import StoreService

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
            self.send_json_response(data)
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

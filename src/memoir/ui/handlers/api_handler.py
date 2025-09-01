"""
Base API handler class with common functionality.
"""

import json


class BaseAPIHandler:
    """Base class for API handlers with common utilities."""

    def __init__(self, request_handler):
        """Initialize with reference to the main request handler."""
        self.handler = request_handler

    def send_json_response(self, data, status_code=200):
        """Send JSON response with proper error handling for broken pipes."""
        try:
            self.handler.send_response(status_code)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(data, indent=2).encode())
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected - this is normal, don't log as error
            pass

    def send_error_response(self, message, status_code=500):
        """Send error response."""
        self.send_json_response({"error": message}, status_code)

    def get_post_data(self):
        """Get and parse POST data."""
        try:
            content_length = int(self.handler.headers.get("Content-Length", 0))
            if content_length > 0:
                post_data = self.handler.rfile.read(content_length)
                return json.loads(post_data.decode("utf-8"))
            return {}
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Invalid JSON data: {e}")

#!/usr/bin/env python3
"""
Simple HTTP server to serve the Memoir UI and handle memory store data.
"""

import http.server
import json
import os
import socketserver
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from memoir.store.prolly_adapter import ProllyTreeStore

PORT = 8080

class MemoryStoreHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Set the directory to serve from
        super().__init__(*args, directory=str(Path(__file__).parent), **kwargs)
    
    def do_GET(self):
        parsed_path = urlparse(self.path)
        
        # Handle API endpoints
        if parsed_path.path == '/api/store':
            self.handle_store_api(parsed_path)
        elif parsed_path.path == '/':
            # Serve the visualization HTML
            self.path = '/visualization_mockup.html'
            super().do_GET()
        else:
            # Default file serving
            super().do_GET()
    
    def handle_store_api(self, parsed_path):
        """Handle API requests for memory store data."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get('path', [None])[0]
        
        if not store_path:
            self.send_error(400, "Missing 'path' parameter")
            return
        
        if not Path(store_path).exists():
            self.send_error(404, f"Store path does not exist: {store_path}")
            return
        
        try:
            # Use the memory_store_reader to get complete data
            from memory_store_reader import read_store_data
            data_json = read_store_data(store_path)
            data = json.loads(data_json)
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode())
            
        except Exception as e:
            self.send_error(500, str(e))
    
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
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
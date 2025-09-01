"""
Store handler for memory store operations.
"""

import sys
from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from memoir.store.prolly_adapter import ProllyTreeStore


class StoreHandler(BaseAPIHandler):
    """Handler for memory store operations."""
    
    def handle_store_api(self, parsed_path):
        """Handle API requests for memory store data."""
        import sys
        import json
        from pathlib import Path
        from urllib.parse import parse_qs
        
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]

        if not store_path:
            self.send_error_response("Missing 'path' parameter", 400)
            return

        if not Path(store_path).exists():
            self.send_error_response(f"Store path does not exist: {store_path}", 404)
            return

        try:
            # Use the memory_store_reader to get complete data
            sys.path.append(str(Path(__file__).parent.parent))
            from reader import read_store_data

            data_json = read_store_data(store_path)
            data = json.loads(data_json)

            # Send response using base handler utility
            self.send_json_response(data)

        except Exception as e:
            self.send_error_response(str(e))
    
    def handle_new_api(self):
        """Handle /new command to create a new git repository and initialize memory store."""
        import json
        import subprocess
        from pathlib import Path
        
        try:
            # Get POST data using base handler utility
            data = self.get_post_data()

            store_path = data.get("path")
            if not store_path:
                self.send_error_response("Missing 'path' parameter", 400)
                return

            # Validate and normalize the path
            path = Path(store_path).expanduser().resolve()

            # Check if path is writable by trying to create parent directories
            try:
                path.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                self.send_error_response(
                    f"Permission denied: Cannot create directory at {path}", 400
                )
                return
            except OSError as e:
                self.send_error_response(f"Invalid path: {e}", 400)
                return

            # Verify we can write to this directory
            try:
                test_file = path / ".write_test"
                test_file.touch()
                test_file.unlink()
            except (PermissionError, OSError) as e:
                self.send_error_response(f"Directory not writable: {path} - {e}", 400)
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

            # Send response using base handler utility
            self.send_json_response(result)

        except Exception as e:
            self.send_error_response(f"Error creating memory store: {e!s}")
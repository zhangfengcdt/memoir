"""
Branch handler for git operations and version control.
"""

import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class BranchHandler(BaseAPIHandler):
    """Handler for git branch and version control operations."""

    def handle_branches_api(self, parsed_path):
        """Get list of branches in the store."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]

        if not store_path:
            self.handler.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.handler.send_error(404, f"Store path does not exist: {store_path}")
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

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error getting branches: {e!s}")

    def handle_commits_api(self, parsed_path):
        """Get commit history for the store."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]
        branch = query_params.get("branch", ["HEAD"])[0]
        limit = int(query_params.get("limit", [20])[0])

        if not store_path:
            self.handler.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.handler.send_error(404, f"Store path does not exist: {store_path}")
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

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error getting commits: {e!s}")

    def handle_current_branch_api(self, parsed_path):
        """Get the current branch of the store."""
        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]

        if not store_path:
            self.handler.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.handler.send_error(404, f"Store path does not exist: {store_path}")
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

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error getting current branch: {e!s}")

    def handle_checkout_api(self):
        """Checkout a specific commit or branch."""
        try:
            # Read POST data
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            target = data.get("target")  # Can be commit hash or branch name
            create_branch = data.get(
                "create_branch"
            )  # Optional: create new branch from commit

            if not store_path:
                self.handler.send_error(400, "Missing 'path' parameter")
                return

            if not target:
                self.handler.send_error(400, "Missing 'target' parameter")
                return

            if not Path(store_path).exists():
                self.handler.send_error(404, f"Store path does not exist: {store_path}")
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

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode("utf-8") if e.stderr else str(e)
            self.handler.send_error(500, f"Git checkout failed: {error_msg}")
        except Exception as e:
            self.handler.send_error(500, f"Error during checkout: {e!s}")

    def handle_create_branch_api(self):
        """Create a new branch."""
        try:
            # Read POST data
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            branch_name = data.get("branch")
            from_ref = data.get("from", "HEAD")  # Create from specific ref

            if not store_path:
                self.handler.send_error(400, "Missing 'path' parameter")
                return

            if not branch_name:
                self.handler.send_error(400, "Missing 'branch' parameter")
                return

            if not Path(store_path).exists():
                self.handler.send_error(404, f"Store path does not exist: {store_path}")
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

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode("utf-8") if e.stderr else str(e)
            self.handler.send_error(500, f"Failed to create branch: {error_msg}")
        except Exception as e:
            self.handler.send_error(500, f"Error creating branch: {e!s}")

    def handle_merge_branch_api(self):
        """Merge a branch into current branch."""
        try:
            # Read POST data
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            source_branch = data.get("source")

            if not store_path:
                self.handler.send_error(400, "Missing 'path' parameter")
                return

            if not source_branch:
                self.handler.send_error(400, "Missing 'source' parameter")
                return

            if not Path(store_path).exists():
                self.handler.send_error(404, f"Store path does not exist: {store_path}")
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
                    self.handler.send_error(
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

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode("utf-8") if e.stderr else str(e)
            self.handler.send_error(500, f"Merge failed: {error_msg}")
        except Exception as e:
            self.handler.send_error(500, f"Error during merge: {e!s}")

    def handle_delete_branch_api(self):
        """Delete a branch."""
        try:
            # Read POST data
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            branch_name = data.get("branch")
            force = data.get("force", False)

            if not store_path:
                self.handler.send_error(400, "Missing 'path' parameter")
                return

            if not branch_name:
                self.handler.send_error(400, "Missing 'branch' parameter")
                return

            if not Path(store_path).exists():
                self.handler.send_error(404, f"Store path does not exist: {store_path}")
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
                self.handler.send_error(
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

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode("utf-8") if e.stderr else str(e)
            if "not fully merged" in error_msg:
                self.handler.send_error(
                    400,
                    f"Branch '{branch_name}' is not fully merged. Use force=true to delete anyway.",
                )
            else:
                self.handler.send_error(500, f"Failed to delete branch: {error_msg}")
        except Exception as e:
            self.handler.send_error(500, f"Error deleting branch: {e!s}")

    def end_headers(self):
        # Add CORS headers
        self.handler.send_header("Access-Control-Allow-Origin", "*")
        self.handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.handler.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

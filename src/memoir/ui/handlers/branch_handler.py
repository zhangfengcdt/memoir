"""
Branch handler for git operations and version control.

Delegates to BranchService for business logic.
"""

import json
from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler


class BranchHandler(BaseAPIHandler):
    """Handler for git branch and version control operations."""

    def handle_branches_api(self, parsed_path):
        """Get list of branches in the store."""
        from memoir.services.branch_service import BranchService
        from memoir.ui.schemas import BranchesResponse

        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]

        if not store_path:
            self.handler.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.handler.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            service = BranchService(store_path)
            info = service.list_branches()

            body = BranchesResponse(
                success=True,
                branches=info.branches,
                current=info.current,
            )

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(
                json.dumps(body.model_dump(mode="json"), indent=2).encode()
            )

        except Exception as e:
            self.handler.send_error(500, f"Error getting branches: {e!s}")

    def handle_commits_api(self, parsed_path):
        """Get commit history for the store."""
        from memoir.services.branch_service import BranchService
        from memoir.ui.schemas import CommitsResponse

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
            service = BranchService(store_path)
            commits = service.get_commits(branch, limit=limit)

            body = CommitsResponse.model_validate(
                {
                    "success": True,
                    "commits": [c.to_dict() for c in commits],
                    "branch": branch,
                }
            )

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(
                json.dumps(body.model_dump(mode="json"), indent=2).encode()
            )

        except Exception as e:
            self.handler.send_error(500, f"Error getting commits: {e!s}")

    def handle_current_branch_api(self, parsed_path):
        """Get the current branch of the store."""
        from memoir.services.branch_service import BranchService
        from memoir.ui.schemas import CurrentBranchResponse

        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]

        if not store_path:
            self.handler.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.handler.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            service = BranchService(store_path)
            branch, commit = service.get_current_branch()

            body = CurrentBranchResponse(
                success=True,
                branch=branch,
                commit=commit,
            )

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(
                json.dumps(body.model_dump(mode="json"), indent=2).encode()
            )

        except Exception as e:
            self.handler.send_error(500, f"Error getting current branch: {e!s}")

    def handle_checkout_api(self):
        """Checkout a specific commit or branch."""
        from memoir.services.branch_service import BranchService

        try:
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            target = data.get("target")
            create_branch = data.get("create_branch")

            if not store_path:
                self.handler.send_error(400, "Missing 'path' parameter")
                return

            if not target:
                self.handler.send_error(400, "Missing 'target' parameter")
                return

            if not Path(store_path).exists():
                self.handler.send_error(404, f"Store path does not exist: {store_path}")
                return

            service = BranchService(store_path)

            if create_branch:
                # Create and checkout new branch from target
                create_result = service.create_branch(create_branch, from_ref=target)
                if not create_result.success:
                    self.handler.send_error(
                        500, create_result.error or "Failed to create branch"
                    )
                    return
                checkout_result = service.checkout(create_branch)
                message = f"Created and switched to new branch '{create_branch}' from {target[:8]}"
            else:
                checkout_result = service.checkout(target)
                message = f"Switched to {target}"

            if not checkout_result.success:
                self.handler.send_error(500, checkout_result.error or "Checkout failed")
                return

            result = {
                "success": True,
                "message": message,
                "current_branch": checkout_result.current_branch,
                "target": target,
            }

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(result, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error during checkout: {e!s}")

    def handle_create_branch_api(self):
        """Create a new branch."""
        from memoir.services.branch_service import BranchService

        try:
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            branch_name = data.get("branch")
            from_ref = data.get("from", "HEAD")

            if not store_path:
                self.handler.send_error(400, "Missing 'path' parameter")
                return

            if not branch_name:
                self.handler.send_error(400, "Missing 'branch' parameter")
                return

            if not Path(store_path).exists():
                self.handler.send_error(404, f"Store path does not exist: {store_path}")
                return

            service = BranchService(store_path)
            create_result = service.create_branch(branch_name, from_ref=from_ref)

            if create_result.success:
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
            else:
                self.handler.send_error(
                    500, create_result.error or "Failed to create branch"
                )

        except Exception as e:
            self.handler.send_error(500, f"Error creating branch: {e!s}")

    def handle_merge_branch_api(self):
        """Merge a branch into current branch."""
        from memoir.services.branch_service import BranchService

        try:
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

            service = BranchService(store_path)
            merge_result = service.merge(source_branch)

            if merge_result.success:
                result = {
                    "success": True,
                    "message": merge_result.message,
                    "target_branch": merge_result.target_branch,
                    "source_branch": merge_result.source_branch,
                }

                self.handler.send_response(200)
                self.handler.send_header("Content-Type", "application/json")
                self.handler.send_header("Access-Control-Allow-Origin", "*")
                self.handler.end_headers()
                self.handler.wfile.write(json.dumps(result, indent=2).encode())
            else:
                if merge_result.conflicts:
                    self.handler.send_error(
                        409, "Merge conflict detected. Please resolve manually."
                    )
                else:
                    self.handler.send_error(500, merge_result.error or "Merge failed")

        except Exception as e:
            self.handler.send_error(500, f"Error during merge: {e!s}")

    def handle_branches_status_api(self, parsed_path):
        """Get per-branch ahead/behind counts vs the default branch."""
        from memoir.services.branch_service import BranchService

        query_params = parse_qs(parsed_path.query)
        store_path = query_params.get("path", [None])[0]

        if not store_path:
            self.handler.send_error(400, "Missing 'path' parameter")
            return

        if not Path(store_path).exists():
            self.handler.send_error(404, f"Store path does not exist: {store_path}")
            return

        try:
            service = BranchService(store_path)
            status = service.get_branches_status()

            data = {
                "success": True,
                "default": status["default"],
                "current": status["current"],
                "branches": status["branches"],
            }

            self.handler.send_response(200)
            self.handler.send_header("Content-Type", "application/json")
            self.handler.send_header("Access-Control-Allow-Origin", "*")
            self.handler.end_headers()
            self.handler.wfile.write(json.dumps(data, indent=2).encode())

        except Exception as e:
            self.handler.send_error(500, f"Error getting branches status: {e!s}")

    def handle_sync_branches_api(self):
        """Merge `source` into `target` while preserving current branch."""
        from memoir.services.branch_service import BranchService, MergeStrategy

        try:
            content_length = int(self.handler.headers["Content-Length"])
            post_data = self.handler.rfile.read(content_length)
            data = json.loads(post_data.decode("utf-8"))

            store_path = data.get("path")
            source = data.get("source")
            target = data.get("target")
            strategy_raw = data.get("strategy", "skip")

            if not store_path:
                self.handler.send_error(400, "Missing 'path' parameter")
                return

            if not source:
                self.handler.send_error(400, "Missing 'source' parameter")
                return

            if not target:
                self.handler.send_error(400, "Missing 'target' parameter")
                return

            if not Path(store_path).exists():
                self.handler.send_error(404, f"Store path does not exist: {store_path}")
                return

            try:
                strategy = MergeStrategy(strategy_raw)
            except ValueError:
                self.handler.send_error(
                    400,
                    f"Invalid strategy '{strategy_raw}'. Expected one of: ours, theirs, skip",
                )
                return

            service = BranchService(store_path)
            result = service.sync_branch(source, target, strategy=strategy)

            if result.success:
                payload = result.to_dict()
                payload["success"] = True
                self.handler.send_response(200)
                self.handler.send_header("Content-Type", "application/json")
                self.handler.send_header("Access-Control-Allow-Origin", "*")
                self.handler.end_headers()
                self.handler.wfile.write(json.dumps(payload, indent=2).encode())
            else:
                # Conflict (unresolved) → 409 with the conflict list so the UI
                # can prompt for a strategy and retry. Any other error → 500.
                if result.conflicts:
                    payload = result.to_dict()
                    payload["strategy_required"] = True
                    self.handler.send_response(409)
                    self.handler.send_header("Content-Type", "application/json")
                    self.handler.send_header("Access-Control-Allow-Origin", "*")
                    self.handler.end_headers()
                    self.handler.wfile.write(json.dumps(payload, indent=2).encode())
                else:
                    self.handler.send_error(500, result.error or "Sync failed")

        except Exception as e:
            self.handler.send_error(500, f"Error syncing branches: {e!s}")

    def handle_delete_branch_api(self):
        """Delete a branch."""
        from memoir.services.branch_service import BranchService

        try:
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

            service = BranchService(store_path)
            delete_result = service.delete_branch(branch_name, force=force)

            if delete_result.success:
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
            else:
                if "not fully merged" in (delete_result.error or ""):
                    self.handler.send_error(
                        400,
                        f"Branch '{branch_name}' is not fully merged. Use force=true to delete anyway.",
                    )
                else:
                    self.handler.send_error(
                        500, delete_result.error or "Failed to delete branch"
                    )

        except Exception as e:
            self.handler.send_error(500, f"Error deleting branch: {e!s}")

    def end_headers(self):
        # Add CORS headers
        self.handler.send_header("Access-Control-Allow-Origin", "*")
        self.handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.handler.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

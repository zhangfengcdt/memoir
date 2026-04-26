"""
Store handler for memory store operations.

Delegates to StoreService for business logic.
"""

import asyncio
import json
import subprocess
from pathlib import Path
from urllib.parse import parse_qs

from .api_handler import BaseAPIHandler


def _resolve_code_repo_path(store_path: str, items: list[dict]) -> str | None:
    """Pick the on-disk path of the code repo this memoir store was created
    against, so we can compare its HEAD to the snapshot's stamped commit.

    Tries (in order):
      1. `_meta.last_onboard.code_repo_path` from the snapshot (future-proof —
         the /memoir-onboard skill is the right place to start writing this).
      2. Reverse-derive from the store slug under `~/.memoir/<slug>` —
         convention is the absolute path with `/` and `.` replaced by `-`.

    Returns None if neither yields a directory that's actually a git repo.
    """
    for item in items:
        if item.get("key") == "_meta.last_onboard.code_repo_path":
            stored = item.get("value")
            if isinstance(stored, str) and stored:
                p = Path(stored)
                if p.is_dir() and (p / ".git").exists():
                    return str(p)
                # Stored path no longer valid — fall through to slug-derive.
                break

    home = Path.home() / ".memoir"
    try:
        store_p = Path(store_path).resolve()
    except OSError:
        return None
    try:
        rel = store_p.relative_to(home.resolve())
    except ValueError:
        return None
    slug = str(rel)
    if not slug.startswith("-"):
        return None
    candidate = Path("/" + slug[1:].replace("-", "/"))
    if candidate.is_dir() and (candidate / ".git").exists():
        return str(candidate)
    return None


def _git_head_info(repo_path: str) -> tuple[str | None, str | None]:
    """Return (full_commit_sha, branch_name) for a git repo, or (None, None)
    if either lookup fails. We don't raise — the indicator is best-effort.
    """
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=2,
        )
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None, None
    sha_out = sha.stdout.strip() if sha.returncode == 0 else None
    branch_out = branch.stdout.strip() if branch.returncode == 0 else None
    return sha_out, branch_out


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

            # Best-effort live HEAD lookup so the UI can render an
            # "out of sync" indicator when the user's code branch has
            # advanced past the snapshot's stamped commit. Failures are
            # swallowed — the indicator is purely advisory.
            code_repo_path = _resolve_code_repo_path(store_path, items)
            current_code_commit, current_code_branch = (
                _git_head_info(code_repo_path) if code_repo_path else (None, None)
            )

            self.send_json_response(
                {
                    "success": True,
                    "items": items,
                    "code_repo_path": code_repo_path,
                    "current_code_commit": current_code_commit,
                    "current_code_branch": current_code_branch,
                }
            )
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

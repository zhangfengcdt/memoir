# SPDX-License-Identifier: Apache-2.0
"""
Cloud sync service: round-trip a local memoir store with memoir-cloud.

A memoir store is a non-bare git repo whose commits track
``data/prolly_config_tree_config`` (the ProllyTree root config). The memory
data itself lives in the untracked node files under
``.git/prolly/nodes/files/<hash>``. Sync therefore has two halves, and the
cloud serves both:

1. **Git half** — standard smart-HTTP with the ``git`` binary memoir already
   requires. The remote is an ordinary git remote named ``memoir-cloud``
   whose URL is ``<gateway>/sync/<store_id>``.
2. **Chunk half** — a small HTTP protocol for the node files, keyed by
   filename (negotiate → PUT missing → GET missing). Filenames are opaque
   prollytree node hashes; nothing is re-hashed.

Push ordering is mandatory: every chunk PUT must succeed before ``git push``
runs, because the server refuses to advance a ref whose root chunk is not
resident.

The API key is read from ``MEMOIR_API_KEY`` only. It is never written to
``.git/config`` or any other file; git receives it per invocation via
``-c http.extraHeader=...`` and it is redacted from any surfaced output.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from memoir.services.base import BaseService, GitOperationError, ServiceError
from memoir.services.models import (
    CloneResult,
    FetchResult,
    PullResult,
    PushResult,
    RemoteInfo,
)

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)

API_KEY_ENV = "MEMOIR_API_KEY"
GATEWAY_ENV = "MEMOIR_CLOUD_URL"
DEFAULT_GATEWAY = "https://api-gateway-production-ab56.up.railway.app"
REMOTE_NAME = "memoir-cloud"
CLOUD_BRANCH_PREFIX = "cloud/"
EXIT_NON_FF = 6

CHUNK_HASH_RE = re.compile(r"^[0-9a-f]{16,128}$")
NEGOTIATE_BATCH = 500
LIST_PAGE = 1000
CHUNK_CONCURRENCY = 8
DEFAULT_TIMEOUT = 10.0
CHUNK_TIMEOUT = 60.0
RETRIES = 3

PRO_REQUIRED_MESSAGE = f"Cloud sync requires {API_KEY_ENV} (PRO)"
BAD_KEY_MESSAGE = f"{API_KEY_ENV} is missing or invalid"


# --------------------------------------------------------------------------
# Tier gating / configuration
# --------------------------------------------------------------------------


def cloud_enabled() -> bool:
    """True iff ``MEMOIR_API_KEY`` is set (PRO tier). Nothing else is checked."""
    return bool(os.environ.get(API_KEY_ENV, "").strip())


def api_key() -> str:
    return os.environ.get(API_KEY_ENV, "").strip()


def resolve_gateway(url: str | None = None) -> str:
    """``--url`` flag → ``MEMOIR_CLOUD_URL`` env → production default."""
    return (url or os.environ.get(GATEWAY_ENV) or DEFAULT_GATEWAY).rstrip("/")


def remote_url(gateway: str, store_id: str) -> str:
    return f"{gateway.rstrip('/')}/sync/{store_id}"


def parse_remote_url(url: str) -> tuple[str, str]:
    """Split ``<gateway>/sync/<store_id>`` back into ``(gateway, store_id)``."""
    gateway, sep, store_id = url.rstrip("/").rpartition("/sync/")
    if not sep or not store_id or "/" in store_id:
        raise ServiceError(
            f"remote '{REMOTE_NAME}' has an unexpected URL (expected "
            f"<gateway>/sync/<store_id>): {url}"
        )
    return gateway, store_id


def redact(text: str, key: str | None = None) -> str:
    """Strip the API key from anything that may be shown to the user."""
    key = key if key is not None else api_key()
    return text.replace(key, "***") if key else text


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class CloudError(ServiceError):
    """An HTTP-level failure talking to memoir-cloud (exit code 1)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message, code=1)
        self.status = status


class CloudAuthError(CloudError):
    def __init__(self, status: int = 401):
        super().__init__(BAD_KEY_MESSAGE, status=status)


class NonFastForwardError(ServiceError):
    """Local and cloud histories disagree (exit code 6)."""

    def __init__(self, message: str):
        super().__init__(message, code=EXIT_NON_FF)


# --------------------------------------------------------------------------
# HTTP client
# --------------------------------------------------------------------------


class CloudClient:
    """Thin httpx wrapper over the memoir-cloud gateway.

    4xx auth/ownership failures raise immediately; 5xx and connection
    errors are retried a few times with a short backoff. The shared
    ``httpx.Client`` is thread-safe, so chunk transfers can fan out.
    """

    def __init__(self, gateway: str, key: str):
        import httpx

        self.gateway = gateway.rstrip("/")
        self._key = key
        self._client = httpx.Client(
            base_url=self.gateway,
            headers={"Authorization": f"Bearer {key}"},
            timeout=DEFAULT_TIMEOUT,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CloudClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- low level ---------------------------------------------------------

    def _request(
        self, method: str, path: str, *, ok: tuple[int, ...], **kw: Any
    ) -> httpx.Response:
        import httpx

        last_error: Exception | None = None
        for attempt in range(RETRIES):
            try:
                resp = self._client.request(method, path, **kw)
            except httpx.HTTPError as e:
                last_error = e
                logger.debug(
                    "cloud %s %s attempt %d failed: %s", method, path, attempt, e
                )
            else:
                if resp.status_code in ok:
                    return resp
                if resp.status_code in (401,):
                    raise CloudAuthError(resp.status_code)
                if resp.status_code in (403, 404, 400, 413):
                    raise CloudError(
                        f"{method} {path} → {resp.status_code}: {_detail(resp)}",
                        status=resp.status_code,
                    )
                if resp.status_code < 500:
                    raise CloudError(
                        f"{method} {path} → {resp.status_code}: {_detail(resp)}",
                        status=resp.status_code,
                    )
                last_error = CloudError(
                    f"{method} {path} → {resp.status_code}: {_detail(resp)}",
                    status=resp.status_code,
                )
            if attempt + 1 < RETRIES:
                time.sleep(0.2 * (attempt + 1))
        if isinstance(last_error, CloudError):
            raise last_error
        raise CloudError(
            f"{method} {path} failed: {redact(str(last_error), self._key)}"
        )

    # -- auth / stores -------------------------------------------------------

    def whoami(self) -> dict[str, Any]:
        return dict(self._request("GET", "/auth/whoami", ok=(200,)).json())

    def get_store(self, store_id: str) -> dict[str, Any]:
        return dict(self._request("GET", f"/stores/{store_id}", ok=(200,)).json())

    def create_store(self, name: str) -> dict[str, Any]:
        return dict(
            self._request("POST", "/stores", ok=(200, 201), json={"name": name}).json()
        )

    # -- chunks ------------------------------------------------------------

    def negotiate(
        self, store_id: str, have: list[str], want: list[str] | None = None
    ) -> dict[str, list[str]]:
        return dict(
            self._request(
                "POST",
                f"/sync/{store_id}/chunks/negotiate",
                ok=(200,),
                json={"have": have, "want": want or []},
            ).json()
        )

    def missing_on_server(self, store_id: str, hashes: list[str]) -> list[str]:
        missing: list[str] = []
        for i in range(0, len(hashes), NEGOTIATE_BATCH):
            batch = hashes[i : i + NEGOTIATE_BATCH]
            missing.extend(self.negotiate(store_id, batch)["missing_on_server"])
        return missing

    def put_chunk(self, store_id: str, chunk_hash: str, data: bytes) -> bool:
        """Upload one chunk. Returns True if newly created, False if present."""
        resp = self._request(
            "PUT",
            f"/sync/{store_id}/chunks/{chunk_hash}",
            ok=(200, 201),
            content=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=CHUNK_TIMEOUT,
        )
        return bool(resp.status_code == 201)

    def get_chunk(self, store_id: str, chunk_hash: str) -> bytes:
        return bytes(
            self._request(
                "GET",
                f"/sync/{store_id}/chunks/{chunk_hash}",
                ok=(200,),
                timeout=CHUNK_TIMEOUT,
            ).content
        )

    def list_chunks(self, store_id: str) -> list[str]:
        hashes: list[str] = []
        after: str | None = None
        while True:
            params: dict[str, Any] = {"limit": LIST_PAGE}
            if after:
                params["after"] = after
            page = self._request(
                "GET", f"/sync/{store_id}/chunks", ok=(200,), params=params
            ).json()
            hashes.extend(page.get("hashes", []))
            after = page.get("next")
            if not after:
                return hashes


def _detail(resp) -> str:
    try:
        return str(resp.json().get("detail", resp.text))
    except Exception:
        return str(resp.text[:200])


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------


class SyncService(BaseService):
    """Cloud sync operations for one local store.

    All methods raise ``ServiceError`` subclasses on failure; callers map
    ``.code`` to the process exit code.
    """

    def __init__(self, store_path: str):
        super().__init__(store_path)
        self._key = api_key()

    # -- git helpers -------------------------------------------------------

    def _git(
        self, args: list[str], *, auth: bool = False, check: bool = True
    ) -> subprocess.CompletedProcess:
        cmd = ["git"]
        if auth:
            cmd += ["-c", f"http.extraHeader=Authorization: Bearer {self._key}"]
        cmd += args
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        logger.debug("git %s", " ".join(redact(a, self._key) for a in args))
        result = subprocess.run(
            cmd,
            cwd=self.store_path,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if check and result.returncode != 0:
            raise GitOperationError(
                f"git {' '.join(args[:2])} failed: "
                f"{redact(result.stderr.strip() or result.stdout.strip(), self._key)}"
            )
        return result

    def _nodes_dir(self) -> Path:
        return Path(self.store_path) / ".git" / "prolly" / "nodes" / "files"

    def _current_branch(self) -> str:
        result = self._git(["rev-parse", "--abbrev-ref", "HEAD"])
        return str(result.stdout.strip())

    def _ref_exists(self, ref: str) -> bool:
        return (
            self._git(["rev-parse", "--verify", "--quiet", ref], check=False).returncode
            == 0
        )

    # -- remote configuration --------------------------------------------

    def _remote(self) -> tuple[str, str]:
        """``(gateway, store_id)`` of the configured remote, or raise."""
        result = self._git(["remote", "get-url", REMOTE_NAME], check=False)
        if result.returncode != 0:
            raise ServiceError(
                "no cloud remote configured; run `memoir remote add <store_id>` "
                "or `memoir remote add --create`"
            )
        return parse_remote_url(result.stdout.strip())

    def _client(self, gateway: str) -> CloudClient:
        return CloudClient(gateway, self._key)

    def _set_remote(self, url: str, force: bool) -> None:
        exists = (
            self._git(["remote", "get-url", REMOTE_NAME], check=False).returncode == 0
        )
        if exists and not force:
            raise ServiceError(
                f"remote '{REMOTE_NAME}' already exists; pass --force to replace it"
            )
        if exists:
            self._git(["remote", "set-url", REMOTE_NAME, url])
        else:
            self._git(["remote", "add", REMOTE_NAME, url])
        self._ensure_cloud_refspec()

    def _ensure_cloud_refspec(self) -> None:
        """Fetch ``refs/cloud/*`` (cloud-owned proposal branches) too."""
        cloud_spec = f"+refs/cloud/*:refs/remotes/{REMOTE_NAME}/cloud/*"
        current = self._git(
            ["config", "--get-all", f"remote.{REMOTE_NAME}.fetch"], check=False
        ).stdout.split()
        if cloud_spec not in current:
            self._git(["config", "--add", f"remote.{REMOTE_NAME}.fetch", cloud_spec])

    def remote_add(
        self, store_id: str, gateway: str | None = None, force: bool = False
    ) -> RemoteInfo:
        gateway = resolve_gateway(gateway)
        with self._client(gateway) as client:
            client.whoami()
            store = client.get_store(store_id)
        self._set_remote(remote_url(gateway, store_id), force)
        return RemoteInfo(
            gateway=gateway,
            store_id=store_id,
            branch=self._current_branch(),
            store=store,
        )

    def remote_create(
        self, name: str | None = None, gateway: str | None = None, force: bool = False
    ) -> RemoteInfo:
        gateway = resolve_gateway(gateway)
        name = name or Path(self.store_path).name
        with self._client(gateway) as client:
            client.whoami()
            store = client.create_store(name)
        store_id = store["id"]
        self._set_remote(remote_url(gateway, store_id), force)
        return RemoteInfo(
            gateway=gateway,
            store_id=store_id,
            branch=self._current_branch(),
            store=store,
        )

    def remote_show(self) -> RemoteInfo:
        gateway, store_id = self._remote()
        with self._client(gateway) as client:
            store = client.get_store(store_id)
        return RemoteInfo(
            gateway=gateway,
            store_id=store_id,
            branch=self._current_branch(),
            store=store,
        )

    def remote_remove(self) -> str:
        _, store_id = self._remote()
        self._git(["remote", "remove", REMOTE_NAME])
        return store_id

    # -- chunks ------------------------------------------------------------

    def local_chunks(self) -> set[str]:
        nodes = self._nodes_dir()
        if not nodes.is_dir():
            return set()
        return {
            p.name
            for p in nodes.iterdir()
            if p.is_file() and CHUNK_HASH_RE.match(p.name)
        }

    def _upload_chunks(self, client: CloudClient, store_id: str) -> tuple[int, int]:
        local = sorted(self.local_chunks())
        missing = client.missing_on_server(store_id, local)
        nodes = self._nodes_dir()

        def upload(chunk_hash: str) -> bool:
            return client.put_chunk(
                store_id, chunk_hash, (nodes / chunk_hash).read_bytes()
            )

        created = 0
        if missing:
            with ThreadPoolExecutor(max_workers=CHUNK_CONCURRENCY) as pool:
                # list() re-raises the first worker exception, so a single
                # failed PUT aborts the push before any git activity.
                created = sum(1 for ok in pool.map(upload, missing) if ok)
        return created, len(local) - len(missing)

    def _download_chunks(self, client: CloudClient, store_id: str) -> int:
        remote = set(client.list_chunks(store_id))
        wanted = sorted(remote - self.local_chunks())
        nodes = self._nodes_dir()
        nodes.mkdir(parents=True, exist_ok=True)

        def download(chunk_hash: str) -> None:
            data = client.get_chunk(store_id, chunk_hash)
            tmp = nodes / f"{chunk_hash}.partial.{os.getpid()}"
            tmp.write_bytes(data)
            os.replace(tmp, nodes / chunk_hash)

        if wanted:
            with ThreadPoolExecutor(max_workers=CHUNK_CONCURRENCY) as pool:
                list(pool.map(download, wanted))
        return len(wanted)

    def root_hash(self) -> str | None:
        """Hex root hash from the tracked ``data/prolly_config_tree_config``."""
        config = Path(self.store_path) / "data" / "prolly_config_tree_config"
        if not config.exists():
            return None
        root = json.loads(config.read_text()).get("root_hash")
        return bytes(root).hex() if root else None

    def _verify_root_chunk(self) -> None:
        root = self.root_hash()
        if root and not (self._nodes_dir() / root).exists():
            raise ServiceError(
                f"root chunk {root[:12]}… is missing locally after sync; "
                f"the store is incomplete — run `memoir fetch` again"
            )

    # -- verbs --------------------------------------------------------------

    def push(self, branch: str | None = None) -> PushResult:
        gateway, store_id = self._remote()
        branch = branch or self._current_branch()
        if branch.startswith(CLOUD_BRANCH_PREFIX):
            raise ServiceError(
                f"'{branch}' is a cloud-owned proposal branch and cannot be pushed"
            )
        if not self._ref_exists(f"refs/heads/{branch}"):
            raise ServiceError(f"branch '{branch}' does not exist locally", code=2)

        with self._client(gateway) as client:
            uploaded, present = self._upload_chunks(client, store_id)

        # Only after every chunk is resident on the server.
        result = self._git(
            ["push", REMOTE_NAME, f"{branch}:{branch}"], auth=True, check=False
        )
        if result.returncode != 0:
            stderr = redact(result.stderr, self._key)
            if "non-fast-forward" in stderr or "fetch first" in stderr:
                raise NonFastForwardError(
                    "remote has commits you don't have; run `memoir pull` first"
                )
            raise GitOperationError(f"git push failed: {stderr.strip()}")
        return PushResult(
            branch=branch, chunks_uploaded=uploaded, chunks_present=present, pushed=True
        )

    def fetch(self) -> FetchResult:
        gateway, store_id = self._remote()
        self._git(["fetch", "--tags", REMOTE_NAME], auth=True)
        with self._client(gateway) as client:
            downloaded = self._download_chunks(client, store_id)
        refs = self._git(
            [
                "for-each-ref",
                "--format=%(refname:short)",
                f"refs/remotes/{REMOTE_NAME}/",
            ]
        ).stdout.split()
        return FetchResult(chunks_downloaded=downloaded, remote_refs=refs)

    def _raise_pull_failure(self, result: subprocess.CompletedProcess, op: str) -> None:
        if result.returncode == 0:
            return
        stderr = redact(result.stderr, self._key)
        if "fast-forward" in stderr or "rejected" in stderr:
            raise NonFastForwardError(
                "local and cloud histories have diverged; "
                "cloud merge is not available yet"
            )
        raise GitOperationError(f"{op} failed: {stderr.strip()}")

    def pull(self, branch: str | None = None) -> PullResult:
        fetched = self.fetch()
        current = self._current_branch()
        branch = branch or current
        remote_ref = f"refs/remotes/{REMOTE_NAME}/{branch}"
        if not self._ref_exists(remote_ref):
            raise ServiceError(f"cloud has no branch '{branch}'", code=2)

        created = False
        if not self._ref_exists(f"refs/heads/{branch}"):
            self._git(["branch", branch, remote_ref])
            created = True
        elif branch == current:
            result = self._git(["merge", "--ff-only", remote_ref], check=False)
            self._raise_pull_failure(result, "git merge --ff-only")
        else:
            # Fast-forward a non-checked-out branch; a plain (non-`+`) refspec
            # is rejected by git unless the update is a fast-forward.
            result = self._git(
                ["fetch", ".", f"{remote_ref}:refs/heads/{branch}"], check=False
            )
            self._raise_pull_failure(result, "git fetch")

        if branch == current:
            # Same pattern BranchService uses: make the working tree match HEAD
            # so prollytree opens at the new root.
            self._git(["checkout", "HEAD", "--", "data/"], check=False)
            self._verify_root_chunk()

        tip = self._git(["rev-parse", "--short", f"refs/heads/{branch}"]).stdout.strip()
        return PullResult(
            branch=branch,
            chunks_downloaded=fetched.chunks_downloaded,
            created=created,
            tip=tip,
        )


def clone(store_id: str, path: str, gateway: str | None = None) -> CloneResult:
    """Clone a cloud store into ``path`` and make it a usable memoir store."""
    gateway = resolve_gateway(gateway)
    key = api_key()
    target = Path(path).expanduser().resolve()
    if target.exists() and any(target.iterdir()):
        raise ServiceError(f"destination already exists and is not empty: {target}")

    # Validate key + ownership up front so auth failures get the standard
    # message instead of whatever git prints for an HTTP 401/404.
    with CloudClient(gateway, key) as client:
        client.whoami()
        client.get_store(store_id)

    url = remote_url(gateway, store_id)
    result = subprocess.run(
        [
            "git",
            "-c",
            f"http.extraHeader=Authorization: Bearer {key}",
            "clone",
            "--origin",
            REMOTE_NAME,
            url,
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode != 0:
        raise GitOperationError(
            f"git clone failed: {redact(result.stderr.strip(), key)}"
        )

    (target / ".git" / "memoir-backend").write_text("file\n")
    service = SyncService(str(target))
    service._nodes_dir().mkdir(parents=True, exist_ok=True)
    service._ensure_cloud_refspec()
    with service._client(gateway) as client:
        downloaded = service._download_chunks(client, store_id)
    service._verify_root_chunk()
    return CloneResult(
        path=str(target),
        store_id=store_id,
        branch=service._current_branch(),
        chunks_downloaded=downloaded,
    )

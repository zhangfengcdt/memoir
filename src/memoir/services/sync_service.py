# SPDX-License-Identifier: Apache-2.0
"""
Cloud sync service: round-trip a local memoir store with memoir-cloud.

A memoir store is a non-bare git repo whose commits track
``data/prolly_config_tree_config`` (the ProllyTree root config). The memory
data itself lives in the untracked node files under
``.git/prolly/nodes/files/<hash>``. Sync therefore has two halves, and the
cloud serves both:

1. **Git half** — standard smart-HTTP with the ``git`` binary memoir already
   requires. The remote is the ordinary git remote ``origin`` whose URL is
   the store's GitHub-style address, ``https://<gateway>/<owner>/<store>``.
2. **Chunk half** — a small HTTP protocol for the node files, keyed by
   filename, under the same address (``.../chunks/negotiate``, ``PUT``/``GET``
   ``.../chunks/<hash>``, paginated ``GET .../chunks``). Filenames are opaque
   prollytree node hashes; nothing is re-hashed.

Cloud stores are addressed as ``<owner>/<store>`` everywhere a user types or
reads something. There is deliberately no ``clone``: local stores are created
automatically (plugin SessionStart, or the first memoir command), so the
second-machine flow is ``memoir remote add <owner>/<store>`` then
``memoir pull``, and ``pull`` adopts the cloud history when the local store
is still pristine. The server's opaque ``str_…`` id is never printed, stored
in user-visible config, or accepted as input.

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
from urllib.parse import urlsplit

from memoir.services.base import BaseService, GitOperationError, ServiceError
from memoir.services.models import (
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
REMOTE_NAME = "origin"
BACKUP_REF_PREFIX = "refs/memoir/backup/"  # where `pull --force` parks the old tip
CLOUD_BRANCH_PREFIX = "cloud/"
EXIT_NON_FF = 6

CHUNK_HASH_RE = re.compile(r"^[0-9a-f]{16,128}$")
DEFAULT_BRANCH = "main"  # what prollytree creates on a store's first open
NEGOTIATE_BATCH = 500
LIST_PAGE = 1000
CHUNK_CONCURRENCY = 8
DEFAULT_TIMEOUT = 10.0
CHUNK_TIMEOUT = 60.0
RETRIES = 3

PRO_REQUIRED_MESSAGE = f"Cloud sync requires {API_KEY_ENV} (PRO)"
NOT_SIGNED_IN_MESSAGE = f"not signed in: set {API_KEY_ENV}"

# GitHub-shaped naming rules, mirrored from memoir-cloud ``shared/naming.py``.
HANDLE_RE = re.compile(r"^(?!-)(?!.*--)[A-Za-z0-9-]{1,39}(?<!-)$")
STORE_NAME_RE = re.compile(r"^(?!\.)[A-Za-z0-9._-]{1,100}$")
HANDLE_RULES = "1-39 letters, digits or hyphens; no leading, trailing or double hyphen"
STORE_NAME_RULES = (
    "1-100 letters, digits, '.', '_' or '-'; not starting with '.'; not ending in .git"
)
ADDRESS_FORM = "<owner>/<store>, e.g. feng-zhang/demo"


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


def redact(text: str, key: str | None = None) -> str:
    """Strip the API key from anything that may be shown to the user."""
    key = key if key is not None else api_key()
    return text.replace(key, "***") if key else text


# --------------------------------------------------------------------------
# Addresses
# --------------------------------------------------------------------------


def validate_handle(handle: str) -> str | None:
    """Return an error message, or None when ``handle`` is acceptable."""
    if not HANDLE_RE.match(handle):
        return f"handles are {HANDLE_RULES}"
    return None


def validate_store_name(name: str) -> str | None:
    """Return an error message, or None when ``name`` is acceptable."""
    if (
        name in (".", "..")
        or name.lower().endswith(".git")
        or not STORE_NAME_RE.match(name)
    ):
        return f"store names are {STORE_NAME_RULES}"
    return None


def parse_address(text: str) -> tuple[str, str]:
    """Parse ``<owner>/<store>`` (or ``https://<host>/<owner>/<store>``).

    Validates both halves locally before any network call. Opaque ids
    (``str_…``) and the legacy ``/sync/<id>`` URL form are rejected with a
    message pointing at the address form.
    """
    raw = text.strip()
    if raw.startswith("str_") or "/sync/" in raw:
        raise ServiceError(
            f'"{raw}" is a store id; cloud stores are addressed as {ADDRESS_FORM}'
        )
    candidate = raw
    if "://" in raw:
        path = urlsplit(raw).path.strip("/")
        if path.endswith(".git"):
            path = path[:-4]
        candidate = path
    parts = candidate.strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise ServiceError(f'"{raw}" is not a valid address: expected {ADDRESS_FORM}')
    owner, store = parts
    error = validate_handle(owner) or validate_store_name(store)
    if error:
        raise ServiceError(f'"{raw}" is not a valid address: {error}')
    return owner, store


def format_address(owner: str, store: str) -> str:
    return f"{owner}/{store}"


def remote_url(gateway: str, owner: str, store: str) -> str:
    return f"{gateway.rstrip('/')}/{owner}/{store}"


def parse_remote_url(url: str) -> tuple[str, str, str]:
    """Split ``https://<gateway>/<owner>/<store>`` into its three parts."""
    if "/sync/" in url:
        raise ServiceError(
            f"remote '{REMOTE_NAME}' uses the legacy id-based URL ({url}); "
            f"run `memoir remote add {ADDRESS_FORM} --force` to relink"
        )
    parts = urlsplit(url.rstrip("/"))
    segments = parts.path.strip("/").split("/")
    if len(segments) < 2 or not parts.scheme or not parts.netloc:
        raise ServiceError(
            f"remote '{REMOTE_NAME}' has an unexpected URL (expected "
            f"https://<gateway>/<owner>/<store>): {url}"
        )
    owner, store = segments[-2], segments[-1]
    gateway_path = "/".join(segments[:-2])
    gateway = f"{parts.scheme}://{parts.netloc}" + (
        f"/{gateway_path}" if gateway_path else ""
    )
    return gateway, owner, store


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
        super().__init__(NOT_SIGNED_IN_MESSAGE, status=status)


class StoreNotFound(CloudError):
    def __init__(self, address: str):
        super().__init__(f"store {address} not found (or you don't own it)", status=404)


class NonFastForwardError(ServiceError):
    """Local and cloud histories disagree (exit code 6)."""

    def __init__(self, message: str):
        super().__init__(message, code=EXIT_NON_FF)


# --------------------------------------------------------------------------
# HTTP client
# --------------------------------------------------------------------------


class CloudClient:
    """Thin httpx wrapper over the memoir-cloud gateway.

    4xx failures raise immediately; 5xx and connection errors are retried a
    few times with a short backoff. The shared ``httpx.Client`` is
    thread-safe, so chunk transfers can fan out.
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
        """Issue a request; return the response if its status is in ``ok``.

        Raises ``CloudAuthError`` on 401 and ``CloudError`` on any other 4xx
        (never retried). 5xx and connection errors are retried.
        """
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
                if resp.status_code == 401:
                    raise CloudAuthError()
                error = CloudError(
                    f"{method} {path} → {resp.status_code}: {_detail(resp)}",
                    status=resp.status_code,
                )
                if resp.status_code < 500:
                    raise error
                last_error = error
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

    def handle(self) -> str:
        """The signed-in user's handle; error if none has been chosen yet."""
        handle = self.whoami().get("handle")
        if not handle:
            raise ServiceError(
                f"your account has no handle yet; open {self.gateway}/app in a "
                f"browser and choose one, then retry"
            )
        return str(handle)

    def resolve(self, owner: str, store: str) -> dict[str, Any]:
        """Resolve an address; 404 covers both unknown and not-owned."""
        try:
            resp = self._request("GET", f"/stores/by-name/{owner}/{store}", ok=(200,))
        except CloudError as e:
            if e.status == 404:
                raise StoreNotFound(format_address(owner, store)) from None
            raise
        return dict(resp.json())

    def create_store(self, name: str) -> dict[str, Any]:
        try:
            resp = self._request("POST", "/stores", ok=(200, 201), json={"name": name})
        except CloudError as e:
            if e.status == 409:
                raise CloudError("store name already exists", status=409) from None
            if e.status == 422:
                raise CloudError(e.message.split(": ", 1)[-1], status=422) from None
            raise
        return dict(resp.json())

    # -- chunks (address-based routes) -------------------------------------

    def negotiate(
        self, address: str, have: list[str], want: list[str] | None = None
    ) -> dict[str, list[str]]:
        return dict(
            self._request(
                "POST",
                f"/{address}/chunks/negotiate",
                ok=(200,),
                json={"have": have, "want": want or []},
            ).json()
        )

    def missing_on_server(self, address: str, hashes: list[str]) -> list[str]:
        missing: list[str] = []
        for i in range(0, len(hashes), NEGOTIATE_BATCH):
            batch = hashes[i : i + NEGOTIATE_BATCH]
            missing.extend(self.negotiate(address, batch)["missing_on_server"])
        return missing

    def put_chunk(self, address: str, chunk_hash: str, data: bytes) -> bool:
        """Upload one chunk. Returns True if newly created, False if present."""
        resp = self._request(
            "PUT",
            f"/{address}/chunks/{chunk_hash}",
            ok=(200, 201),
            content=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=CHUNK_TIMEOUT,
        )
        return bool(resp.status_code == 201)

    def get_chunk(self, address: str, chunk_hash: str) -> bytes:
        return bytes(
            self._request(
                "GET",
                f"/{address}/chunks/{chunk_hash}",
                ok=(200,),
                timeout=CHUNK_TIMEOUT,
            ).content
        )

    def list_chunks(self, address: str) -> list[str]:
        hashes: list[str] = []
        after: str | None = None
        while True:
            params: dict[str, Any] = {"limit": LIST_PAGE}
            if after:
                params["after"] = after
            page = self._request(
                "GET", f"/{address}/chunks", ok=(200,), params=params
            ).json()
            hashes.extend(page.get("hashes", []))
            after = page.get("next")
            if not after:
                return hashes


def _detail(resp) -> str:
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        return str(resp.text[:200])
    if isinstance(detail, list):  # FastAPI validation errors
        msgs = [str(d.get("msg", d)) for d in detail if isinstance(d, dict)]
        detail = "; ".join(m.removeprefix("Value error, ") for m in msgs) or detail
    return str(detail)


def public_store(store: dict[str, Any]) -> dict[str, Any]:
    """The user-facing subset of a store object: never the opaque id."""
    return {
        k: v
        for k, v in store.items()
        if k not in ("id", "owner_user_id") and v is not None
    }


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
        # symbolic-ref works on an unborn branch (fresh `memoir new`, no
        # commit yet); rev-parse covers a detached HEAD.
        result = self._git(["symbolic-ref", "--short", "-q", "HEAD"], check=False)
        if result.returncode == 0 and result.stdout.strip():
            return str(result.stdout.strip())
        result = self._git(["rev-parse", "--abbrev-ref", "HEAD"])
        return str(result.stdout.strip())

    def _ref_exists(self, ref: str) -> bool:
        return (
            self._git(["rev-parse", "--verify", "--quiet", ref], check=False).returncode
            == 0
        )

    # -- remote configuration --------------------------------------------

    def remote_address(self) -> str | None:
        """``owner/store`` of the configured remote, or None. No network."""
        result = self._git(["remote", "get-url", REMOTE_NAME], check=False)
        if result.returncode != 0:
            return None
        try:
            _, owner, store = parse_remote_url(result.stdout.strip())
        except ServiceError:
            return None
        return format_address(owner, store)

    def _remote(self) -> tuple[str, str, str]:
        """``(gateway, owner, store)`` of the configured remote, or raise."""
        result = self._git(["remote", "get-url", REMOTE_NAME], check=False)
        if result.returncode != 0:
            raise ServiceError(
                f"no cloud remote configured; run `memoir remote add {ADDRESS_FORM}` "
                f"or `memoir push --create <store>`"
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
                f"remote '{REMOTE_NAME}' already exists "
                f"({self.remote_address() or 'non-cloud URL'}); "
                f"pass --force to replace it"
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

    def default_address(self, gateway: str | None = None) -> str:
        """``<handle>/<directory name>`` for `remote add` with no argument.

        The directory is the current working directory (the project the
        user is in), not the store directory: plugin-managed stores live
        under ``~/.memoir/<path-slug>`` and that slug is not a useful name.
        """
        gateway = resolve_gateway(gateway)
        name = Path.cwd().name
        error = validate_store_name(name)
        if error:
            raise ServiceError(
                f'directory name "{name}" is not usable as a store name ({error}); '
                f"pass an explicit address"
            )
        with self._client(gateway) as client:
            handle = client.handle()
        return format_address(handle, name)

    def remote_add(
        self, address: str, gateway: str | None = None, force: bool = False
    ) -> RemoteInfo:
        gateway = resolve_gateway(gateway)
        owner, store_name = parse_address(address)
        with self._client(gateway) as client:
            client.handle()
            store = client.resolve(owner, store_name)
        self._set_remote(remote_url(gateway, owner, store_name), force)
        return RemoteInfo(
            address=format_address(owner, store_name),
            gateway=gateway,
            branch=self._current_branch(),
            store=public_store(store),
        )

    def remote_show(self) -> RemoteInfo:
        gateway, owner, store_name = self._remote()
        with self._client(gateway) as client:
            store = client.resolve(owner, store_name)
        return RemoteInfo(
            address=format_address(owner, store_name),
            gateway=gateway,
            branch=self._current_branch(),
            store=public_store(store),
        )

    def remote_remove(self) -> str:
        _, owner, store_name = self._remote()
        self._git(["remote", "remove", REMOTE_NAME])
        return format_address(owner, store_name)

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

    def _upload_chunks(self, client: CloudClient, address: str) -> tuple[int, int]:
        local = sorted(self.local_chunks())
        missing = client.missing_on_server(address, local)
        nodes = self._nodes_dir()

        def upload(chunk_hash: str) -> bool:
            return client.put_chunk(
                address, chunk_hash, (nodes / chunk_hash).read_bytes()
            )

        created = 0
        if missing:
            with ThreadPoolExecutor(max_workers=CHUNK_CONCURRENCY) as pool:
                # Iterating the map re-raises the first worker exception, so a
                # single failed PUT aborts the push before any git activity.
                created = sum(1 for ok in pool.map(upload, missing) if ok)
        return created, len(local) - len(missing)

    def _download_chunks(self, client: CloudClient, address: str) -> int:
        remote = set(client.list_chunks(address))
        wanted = sorted(remote - self.local_chunks())
        nodes = self._nodes_dir()
        nodes.mkdir(parents=True, exist_ok=True)

        def download(chunk_hash: str) -> None:
            data = client.get_chunk(address, chunk_hash)
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

    def push(
        self,
        branch: str | None = None,
        create: str | None = None,
        gateway: str | None = None,
    ) -> PushResult:
        if create is not None:
            self._create_and_link(create, gateway)
        gateway, owner, store_name = self._remote()
        address = format_address(owner, store_name)
        if not self._ref_exists("HEAD") and branch is None:
            raise ServiceError(
                "this store has no memories yet; nothing to push", code=2
            )
        branch = branch or self._current_branch()
        if branch.startswith(CLOUD_BRANCH_PREFIX):
            raise ServiceError(
                f"'{branch}' is a cloud-owned proposal branch and cannot be pushed"
            )
        if not self._ref_exists(f"refs/heads/{branch}"):
            raise ServiceError(f"branch '{branch}' does not exist locally", code=2)

        with self._client(gateway) as client:
            client.handle()
            uploaded, present = self._upload_chunks(client, address)

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
            branch=branch,
            address=address,
            chunks_uploaded=uploaded,
            chunks_present=present,
            pushed=True,
        )

    def _create_and_link(self, name: str, gateway: str | None) -> None:
        """``push --create <store>``: validate locally, create, set origin."""
        error = validate_store_name(name)
        if error:
            raise ServiceError(f'"{name}" is not a valid store name: {error}')
        existing = self.remote_address()
        if existing:
            raise ServiceError(
                f"this store is already linked to {existing}; "
                f"run `memoir remote remove` first to relink"
            )
        gateway = resolve_gateway(gateway)
        with self._client(gateway) as client:
            handle = client.handle()
            try:
                store = client.create_store(name)
            except CloudError as e:
                if e.status == 409:
                    raise ServiceError(
                        f"store name already exists; pick another or run "
                        f"`memoir remote add {handle}/{name}`"
                    ) from None
                raise
        owner = store.get("owner_handle") or handle
        self._set_remote(remote_url(gateway, owner, store["name"]), force=False)

    def fetch(self) -> FetchResult:
        gateway, owner, store_name = self._remote()
        address = format_address(owner, store_name)
        with self._client(gateway) as client:
            client.handle()
            self._git(["fetch", "--tags", REMOTE_NAME], auth=True)
            downloaded = self._download_chunks(client, address)
        refs = self._git(
            [
                "for-each-ref",
                "--format=%(refname:short)",
                f"refs/remotes/{REMOTE_NAME}/",
            ]
        ).stdout.split()
        return FetchResult(
            address=address, chunks_downloaded=downloaded, remote_refs=refs
        )

    @staticmethod
    def _diverged_message(branch: str) -> str:
        """Both the "grew its own memories before linking" case and the
        "both machines committed since the last sync" case end here: the
        local branch has commits the cloud does not, and vice versa."""
        return (
            "local and cloud histories have diverged; cloud merge is not "
            "available yet. To discard the local memories on this branch and "
            f"adopt the cloud copy: memoir pull --force --branch {branch}"
        )

    def _raise_pull_failure(
        self, result: subprocess.CompletedProcess, op: str, branch: str
    ) -> None:
        if result.returncode == 0:
            return
        stderr = redact(result.stderr, self._key)
        if "fast-forward" in stderr or "rejected" in stderr:
            raise NonFastForwardError(self._diverged_message(branch))
        raise GitOperationError(f"{op} failed: {stderr.strip()}")

    def _shares_history(self, branch: str, remote_ref: str) -> bool:
        """False when the two refs have no common ancestor (unrelated
        histories): a store that grew its own memories before being linked."""
        result = self._git(
            ["merge-base", f"refs/heads/{branch}", remote_ref], check=False
        )
        return result.returncode == 0

    def _is_pristine(self, branch: str) -> bool:
        """True iff ``branch`` holds only prollytree's auto-generated
        "Initial commit" and the working tree has nothing uncommitted.

        Local stores are created automatically (by the plugin on
        SessionStart, or by the first memoir command), so a never-used
        store already has one commit by the time it is linked. Pulling
        into it must adopt the cloud history rather than refuse to merge
        unrelated histories.

        Every memory write is auto-committed, so "exactly one commit" means
        "no memories". This deliberately does not look at the root hash:
        the empty-tree hash differs between prollytree versions.
        """
        log = self._git(
            ["log", "--format=%s", f"refs/heads/{branch}"], check=False
        ).stdout.splitlines()
        if len(log) != 1 or not log[0].startswith("Initial commit"):
            return False
        dirty = self._git(["status", "--porcelain", "--", "data/"]).stdout.strip()
        return not dirty

    def pull(self, branch: str | None = None, force: bool = False) -> PullResult:
        """Fetch, then move ``branch`` to the cloud tip.

        Fast-forward only, with two exceptions: a branch that does not exist
        locally is created, and a pristine local store (only prollytree's
        initial commit) adopts the cloud history. Anything else that is not
        a fast-forward is rejected unless ``force`` is set, in which case the
        local branch is replaced by the cloud copy; the previous tip is
        kept under ``refs/memoir/backup/<branch>`` and reported so it can be
        recovered (``git branch <name> refs/memoir/backup/<branch>``).
        """
        fetched = self.fetch()
        unborn = not self._ref_exists("HEAD")
        # A never-opened store has an unborn HEAD named by git's default
        # (often `master`); prollytree would create `main` on first open,
        # so that is the branch a bare `memoir pull` means.
        current = DEFAULT_BRANCH if unborn else self._current_branch()
        branch = branch or current
        remote_ref = f"refs/remotes/{REMOTE_NAME}/{branch}"
        if not self._ref_exists(remote_ref):
            raise ServiceError(f"cloud has no branch '{branch}'", code=2)

        created = False
        forced = False
        previous_tip: str | None = None
        backup_ref: str | None = None
        if unborn and branch == current:
            # Nothing local yet: make `branch` the checked-out branch.
            self._git(["checkout", "-q", "-f", "-B", branch, remote_ref])
            created = True
        elif not self._ref_exists(f"refs/heads/{branch}"):
            self._git(["branch", branch, remote_ref])
            created = True
        elif self._is_pristine(branch):
            # Never-used local store: adopt the cloud history outright.
            self._replace_branch(branch, remote_ref, current)
            created = True
        elif force:
            previous_tip = self._git(
                ["rev-parse", "--short", f"refs/heads/{branch}"]
            ).stdout.strip()
            # prollytree writes commits without touching git's reflog, so
            # the old tip would otherwise be unreferenced. Keep it under a
            # hidden ref (not a branch, so it never shows up in listings).
            backup_ref = f"{BACKUP_REF_PREFIX}{branch}"
            self._git(["update-ref", backup_ref, f"refs/heads/{branch}"])
            self._replace_branch(branch, remote_ref, current)
            forced = True
        elif not self._shares_history(branch, remote_ref):
            raise NonFastForwardError(self._diverged_message(branch))
        elif branch == current:
            result = self._git(["merge", "--ff-only", remote_ref], check=False)
            self._raise_pull_failure(result, "git merge --ff-only", branch)
        else:
            # Fast-forward a non-checked-out branch; a plain (non-`+`) refspec
            # is rejected by git unless the update is a fast-forward.
            result = self._git(
                ["fetch", ".", f"{remote_ref}:refs/heads/{branch}"], check=False
            )
            self._raise_pull_failure(result, "git fetch", branch)

        if branch == current:
            # Same pattern BranchService uses: make the working tree match HEAD
            # so prollytree opens at the new root.
            self._git(["checkout", "HEAD", "--", "data/"], check=False)
            self._verify_root_chunk()

        tip = self._git(["rev-parse", "--short", f"refs/heads/{branch}"]).stdout.strip()
        return PullResult(
            branch=branch,
            address=fetched.address,
            chunks_downloaded=fetched.chunks_downloaded,
            created=created,
            tip=tip,
            forced=forced,
            previous_tip=previous_tip,
            backup_ref=backup_ref,
        )

    def _replace_branch(self, branch: str, remote_ref: str, current: str) -> None:
        """Point ``branch`` at ``remote_ref``, updating the working tree when
        it is the checked-out branch."""
        if branch == current:
            self._git(["reset", "-q", "--hard", remote_ref])
        else:
            self._git(["branch", "-f", branch, remote_ref])

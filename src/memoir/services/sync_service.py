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
import threading
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
NEGOTIATE_BATCH = 1000
LIST_PAGE = 1000
CHUNK_CONCURRENCY = 8  # parallel chunk downloads (fetch / pull)
# Push uploads go through POST .../chunks/batch (multipart, many chunks per
# request). Server limits: 500 parts, 32 MiB per request; stay under both.
BATCH_MAX_PARTS = 500
BATCH_MAX_BYTES = 24 * 1024 * 1024
BATCH_WORKERS = 4  # more buys little: the bucket's write bandwidth is the ceiling
BATCH_TIMEOUT = 300.0
BATCH_BACKOFF = (1.0, 2.0, 4.0)
# Servers that inflate gzip batch bodies say so on every chunk route.
GZIP_ADVERT_HEADER = "Memoir-Accept-Encoding"
GZIP_LEVEL = 6
# Hashes the server has confirmed (stored or existing) are recorded per remote
# in .git/memoir-cloud/pushed-<remote>, so the next push needs no negotiate.
DEFAULT_TIMEOUT = 10.0
CHUNK_TIMEOUT = 60.0
RETRIES = 3

PRO_REQUIRED_MESSAGE = (
    f"Cloud sync requires a login: run `memoir login` (or set {API_KEY_ENV})"
)
NOT_SIGNED_IN_MESSAGE = f"not signed in: run `memoir login` (or set {API_KEY_ENV})"

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
    """True when some key is available: ``MEMOIR_API_KEY`` or any saved login.

    Whether one applies to a particular gateway is decided later by
    ``api_key(gateway)``; this only gates the cloud commands as a whole.
    """
    from memoir.services import cloud_auth

    return bool(_env_key()) or bool(cloud_auth.load_all()["gateways"])


def _env_key() -> str:
    return os.environ.get(API_KEY_ENV, "").strip()


def same_gateway(a: str, b: str) -> bool:
    """Same gateway: scheme + host[:port], case-insensitive, path ignored."""
    from memoir.services.cloud_auth import normalize_gateway

    return normalize_gateway(a) == normalize_gateway(b)


def api_key(gateway: str | None = None) -> str:
    """The key to send to ``gateway``.

    ``MEMOIR_API_KEY`` wins, for any gateway (as it always has). Otherwise
    the login saved for exactly that gateway (``memoir login --url G``),
    like ``gh`` scopes tokens per host. A saved key is never sent to any
    other gateway; with no ``gateway`` there is no saved-key fallback.
    """
    env = _env_key()
    if env:
        return env
    if not gateway:
        return ""
    from memoir.services import cloud_auth

    found = cloud_auth.entry(gateway)
    return str(found["api_key"]) if found else ""


def resolve_gateway(url: str | None = None) -> str:
    """For commands without a remote yet: ``--url`` → ``MEMOIR_CLOUD_URL`` →
    the saved default gateway → production.

    The saved default only applies while saved logins are in use: with
    ``MEMOIR_API_KEY`` set, its own default (production, or
    ``MEMOIR_CLOUD_URL``) applies, so an env key is never aimed at the
    gateway of an unrelated saved login.
    """
    if url or os.environ.get(GATEWAY_ENV):
        return (url or os.environ[GATEWAY_ENV]).rstrip("/")
    if not _env_key():
        from memoir.services import cloud_auth

        default = cloud_auth.default_gateway()
        if default:
            return default
    return DEFAULT_GATEWAY


def redact(text: str, key: str | None = None) -> str:
    """Strip API keys from anything that may be shown to the user: the given
    one, or the env key and every saved key when none is given."""
    if key is not None:
        keys = [key]
    else:
        from memoir.services import cloud_auth

        keys = [_env_key(), *cloud_auth.saved_keys()]
    for k in keys:
        if k:
            text = text.replace(k, "***")
    return text


class NotLoggedInTo(ServiceError):
    """No key applies to the target gateway (and MEMOIR_API_KEY is unset)."""

    def __init__(self, gateway: str):
        super().__init__(
            f"not logged in to {gateway}: run `memoir login --url {gateway}` "
            f"(or set {API_KEY_ENV})",
            code=1,
        )


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


REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def validate_remote_name(name: str) -> str | None:
    """Remote names are git-ref safe: letters, digits, '.', '_', '-'."""
    if not REMOTE_NAME_RE.match(name) or name.endswith((".", ".lock")) or ".." in name:
        return (
            f'"{name}" is not a valid remote name: use 1-64 letters, digits, '
            "'.', '_' or '-', starting with a letter or digit"
        )
    return None


def parse_remote_url(url: str, remote: str = REMOTE_NAME) -> tuple[str, str, str]:
    """Split ``https://<gateway>/<owner>/<store>`` into its three parts."""
    if "/sync/" in url:
        raise ServiceError(
            f"remote '{remote}' uses the legacy id-based URL ({url}); "
            f"run `memoir remote add {ADDRESS_FORM} --force` to relink"
        )
    parts = urlsplit(url.rstrip("/"))
    segments = parts.path.strip("/").split("/")
    if len(segments) < 2 or not parts.scheme or not parts.netloc:
        raise ServiceError(
            f"remote '{remote}' has an unexpected URL (expected "
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


class BatchTooLarge(CloudError):
    """413 from the batch endpoint: split the batch and retry both halves."""

    def __init__(self) -> None:
        super().__init__("batch too large", status=413)


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
        # Set once any response advertises ``Memoir-Accept-Encoding: gzip``;
        # cleared for the rest of the run if a server answers 415 anyway.
        self.gzip_ok = False
        self._gzip_refused = False
        # Bytes of batch bodies actually put on the wire (compressed or not).
        self.bytes_sent = 0
        self._lock = threading.Lock()

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
                self._note_encoding(resp)
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

    def _note_encoding(self, resp: httpx.Response) -> None:
        advert = resp.headers.get(GZIP_ADVERT_HEADER, "")
        if "gzip" in [t.strip().lower() for t in advert.split(",")]:
            self.gzip_ok = True

    def probe_gzip(self, address: str) -> bool:
        """Learn whether the server inflates gzip batch bodies, via the cheapest
        chunk route (a one-entry listing). Used when a push skipped negotiate
        (the pushed record made it unnecessary) and so has seen no chunk-route
        response yet. Any failure just means "send raw"."""
        if not self.gzip_ok:
            try:
                self._request(
                    "GET", f"/{address}/chunks", ok=(200,), params={"limit": 1}
                )
            except ServiceError as e:
                logger.debug("gzip probe failed: %s", e)
        return self.gzip_ok

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

    def set_repo_meta(
        self, owner: str, store: str, repo: dict[str, Any] | None
    ) -> None:
        """``PATCH /stores/by-name/<owner>/<store>`` with the code repo's
        metadata (replaces the whole document; ``None`` clears it)."""
        self._request(
            "PATCH", f"/stores/by-name/{owner}/{store}", ok=(200,), json={"repo": repo}
        )

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

    def upload_batch(
        self, address: str, parts: list[tuple[str, bytes]]
    ) -> dict[str, Any]:
        """``POST .../chunks/batch``: one multipart request, many chunks.

        Returns ``{"stored": [...], "existing": [...], "rejected": {...}}``.
        502 and connection errors are retried with 1/2/4 s backoff (the
        server is idempotent: a retried batch reports already-written chunks
        as ``existing``). 413 raises ``BatchTooLarge`` so the caller can
        split. Other 4xx raise ``CloudError`` with the server's detail.
        """
        import gzip

        import httpx

        files = [(h, (h, data, "application/octet-stream")) for h, data in parts]
        # Build the multipart body once; the same bytes (or their gzip) go out
        # on every attempt, with an explicit Content-Length.
        req = self._client.build_request(
            "POST", f"/{address}/chunks/batch", files=files
        )
        raw = req.read()
        ctype = req.headers["Content-Type"]
        compressed: bytes | None = None
        for attempt, backoff in enumerate((*BATCH_BACKOFF, None)):
            use_gzip = self.gzip_ok and not self._gzip_refused
            if use_gzip and compressed is None:
                compressed = gzip.compress(raw, compresslevel=GZIP_LEVEL)
            body = compressed if use_gzip and compressed is not None else raw
            headers = {"Content-Type": ctype}
            if use_gzip:
                headers["Content-Encoding"] = "gzip"
            try:
                resp = self._client.post(
                    f"/{address}/chunks/batch",
                    content=body,
                    headers=headers,
                    timeout=BATCH_TIMEOUT,
                )
            except httpx.HTTPError as e:
                logger.debug("batch upload attempt %d failed: %s", attempt, e)
            else:
                self._note_encoding(resp)
                if resp.status_code == 415 and use_gzip:
                    # Defensive: a server that advertised gzip never says this.
                    # Resend raw now and for the rest of the run.
                    logger.debug("server refused gzip batch; sending raw from now on")
                    self._gzip_refused = True
                    continue
                if resp.status_code == 200:
                    with self._lock:
                        self.bytes_sent += len(body)
                    return dict(resp.json())
                if resp.status_code == 401:
                    raise CloudAuthError()
                if resp.status_code == 413:
                    raise BatchTooLarge()
                if resp.status_code < 500:
                    raise CloudError(
                        f"POST /{address}/chunks/batch → {resp.status_code}: "
                        f"{_detail(resp)}",
                        status=resp.status_code,
                    )
                logger.debug("batch upload attempt %d → %s", attempt, resp.status_code)
            if backoff is None:
                break
            time.sleep(backoff)
        raise CloudError("object store unavailable, retry later", status=502)

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

    def __init__(self, store_path: str, remote: str = REMOTE_NAME):
        super().__init__(store_path)
        error = validate_remote_name(remote)
        if error:
            raise ServiceError(error)
        # Which git remote this instance syncs with; ``origin`` by default.
        self.remote = remote
        # Bound per target gateway in ``_client``; git calls that need auth
        # always run after a ``_client`` for the same gateway.
        self._key = ""

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
        result = self._git(["remote", "get-url", self.remote], check=False)
        if result.returncode != 0:
            return None
        try:
            _, owner, store = parse_remote_url(result.stdout.strip(), self.remote)
        except ServiceError:
            return None
        return format_address(owner, store)

    def _remote(self) -> tuple[str, str, str]:
        """``(gateway, owner, store)`` of the configured remote, or raise."""
        result = self._git(["remote", "get-url", self.remote], check=False)
        if result.returncode != 0:
            if self.remote == REMOTE_NAME:
                raise ServiceError(
                    f"no cloud remote configured; run `memoir remote add {ADDRESS_FORM}` "
                    f"or `memoir push --create <store>`"
                )
            raise ServiceError(
                f"no remote named '{self.remote}'; run "
                f"`memoir remote add <owner>/<store> --name {self.remote}` "
                "(`memoir remote list` shows the configured ones)"
            )
        return parse_remote_url(result.stdout.strip(), self.remote)

    def list_remotes(self) -> list[dict[str, Any]]:
        """Every cloud remote of this store: name, address, gateway, and
        whether a key applies to that gateway. Non-cloud remotes (URLs that
        aren't ``<gateway>/<owner>/<store>``) are skipped."""
        result = self._git(
            ["config", "--get-regexp", r"^remote\..*\.url$"], check=False
        )
        rows: list[dict[str, Any]] = []
        for line in result.stdout.splitlines():
            key, _, url = line.partition(" ")
            name = key[len("remote.") : -len(".url")]
            try:
                gateway, owner, store = parse_remote_url(url.strip(), name)
            except ServiceError:
                continue
            rows.append(
                {
                    "name": name,
                    "address": format_address(owner, store),
                    "gateway": gateway,
                    "logged_in": bool(api_key(gateway)),
                }
            )
        rows.sort(key=lambda r: (r["name"] != REMOTE_NAME, r["name"]))
        return rows

    def _client(self, gateway: str) -> CloudClient:
        """A client for ``gateway`` carrying the key that applies to it (see
        ``api_key``); also sets the key the authenticated git calls use."""
        self._key = api_key(gateway)
        if not self._key:
            raise NotLoggedInTo(gateway)
        return CloudClient(gateway, self._key)

    def _set_remote(self, url: str, force: bool) -> None:
        exists = (
            self._git(["remote", "get-url", self.remote], check=False).returncode == 0
        )
        if exists and not force:
            raise ServiceError(
                f"remote '{self.remote}' already exists "
                f"({self.remote_address() or 'non-cloud URL'}); "
                f"pass --force to replace it"
            )
        if exists:
            self._git(["remote", "set-url", self.remote, url])
        else:
            self._git(["remote", "add", self.remote, url])
        self._ensure_cloud_refspec()

    def _ensure_cloud_refspec(self) -> None:
        """Fetch ``refs/cloud/*`` (cloud-owned proposal branches) too."""
        cloud_spec = f"+refs/cloud/*:refs/remotes/{self.remote}/cloud/*"
        current = self._git(
            ["config", "--get-all", f"remote.{self.remote}.fetch"], check=False
        ).stdout.split()
        if cloud_spec not in current:
            self._git(["config", "--add", f"remote.{self.remote}.fetch", cloud_spec])

    def default_address(
        self, gateway: str | None = None, name: str | None = None
    ) -> str:
        """``<handle>/<directory name>`` for `remote add` with no argument.

        The directory is the current working directory (the project the
        user is in), not the store directory: plugin-managed stores live
        under ``~/.memoir/<path-slug>`` and that slug is not a useful name.
        """
        gateway = resolve_gateway(gateway)
        name = name or Path.cwd().name
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
        self._report_repo_meta(gateway, owner, store_name)
        return RemoteInfo(
            address=format_address(owner, store_name),
            gateway=gateway,
            branch=self._current_branch(),
            store=public_store(store),
        )

    def _report_repo_meta(self, gateway: str, owner: str, store_name: str) -> None:
        """Send the code repo's metadata to the cloud (issue #164).

        Best-effort by design: a store that maps to no code repo sends
        nothing; an unchanged document is not resent; any failure while
        collecting or sending is logged at debug and never fails the verb.
        """
        try:
            from memoir.services import repo_meta

            doc = repo_meta.collect(self.store_path)
            if doc is None:
                logger.debug(
                    "no code repo for %s; not reporting metadata", self.store_path
                )
                return
            if repo_meta.unchanged(self.store_path, self.remote, doc):
                logger.debug("repo metadata unchanged; not resending")
                return
            with self._client(gateway) as client:
                client.set_repo_meta(owner, store_name, doc)
            repo_meta.record_sent(self.store_path, self.remote, doc)
        except Exception as e:
            logger.debug("repo metadata not reported: %s", redact(str(e), self._key))

    def ensure_linked(self, address: str, gateway: str | None = None) -> bool:
        """Make this remote point at ``address`` (``pull <address>``).

        - remote missing: link it exactly as ``remote_add`` does (key check,
          address resolution, refspecs); returns True.
        - remote already at the same address on the same gateway: no-op;
          returns False, so repeating the command is harmless.
        - remote at a different store or gateway: raise with nothing changed;
          a pull must never relink silently, or the next push would go to a
          different cloud store.

        ``gateway`` (``--url``) only matters when the remote is created; when
        it exists, a disagreeing ``--url`` counts as "different".
        """
        owner, store_name = parse_address(address)  # local validation first
        wanted = format_address(owner, store_name)
        exists = self._git(["remote", "get-url", self.remote], check=False)
        if exists.returncode != 0:
            self.remote_add(wanted, gateway)
            return True
        current_gw, cur_owner, cur_store = self._remote()
        same_address = format_address(cur_owner, cur_store).lower() == wanted.lower()
        same_gw = gateway is None or same_gateway(current_gw, gateway)
        if same_address and same_gw:
            return False
        current = format_address(cur_owner, cur_store)
        raise ServiceError(
            f"{self.remote} is {current} @ {current_gw}; use --remote <other name> "
            f"to add a second store, or `memoir remote add {wanted} "
            f"{'' if self.remote == REMOTE_NAME else f'--name {self.remote} '}--force` "
            "to switch"
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
        self._git(["remote", "remove", self.remote])
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

    # -- pushed record (what the server has confirmed) ----------------------

    def _pushed_record_path(self) -> Path:
        return Path(self.store_path) / ".git" / "memoir-cloud" / f"pushed-{self.remote}"

    def _read_pushed(self) -> set[str] | None:
        """Hashes the server is known to hold, or None if never recorded."""
        path = self._pushed_record_path()
        if not path.exists():
            return None
        return {line.strip() for line in path.read_text().splitlines() if line.strip()}

    def _write_pushed(self, hashes: set[str]) -> None:
        path = self._pushed_record_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text("".join(f"{h}\n" for h in sorted(hashes)))
        os.replace(tmp, path)

    def _remember_pushed(self, hashes: set[str]) -> None:
        self._write_pushed((self._read_pushed() or set()) | hashes)

    # -- upload --------------------------------------------------------------

    def _upload_chunks(
        self, client: CloudClient, address: str, *, negotiate: bool | None = None
    ) -> tuple[int, int]:
        """Upload every local chunk the server lacks, in multipart batches.

        Returns ``(uploaded, already_present)``. ``negotiate`` defaults to
        "only if there is no pushed record": with a record, ``missing`` is
        computed locally and no negotiate round trip happens at all.
        """
        nodes = self._nodes_dir()
        local = {h: (nodes / h).stat().st_size for h in self.local_chunks()}
        pushed = self._read_pushed()
        if negotiate is None:
            negotiate = pushed is None
        if negotiate:
            missing = set(client.missing_on_server(address, sorted(local)))
        else:
            missing = set(local) - (pushed or set())

        # Biggest first so one large chunk never strands a batch.
        batches: list[list[str]] = []
        batch: list[str] = []
        size = 0
        for h in sorted(missing, key=lambda h: -local[h]):
            if batch and (
                len(batch) >= BATCH_MAX_PARTS or size + local[h] > BATCH_MAX_BYTES
            ):
                batches.append(batch)
                batch, size = [], 0
            batch.append(h)
            size += local[h]
        if batch:
            batches.append(batch)

        stored: set[str] = set()
        existing: set[str] = set()
        rejected: dict[str, str] = {}

        def send(hashes: list[str]) -> None:
            parts = [(h, (nodes / h).read_bytes()) for h in hashes]
            try:
                body = client.upload_batch(address, parts)
            except BatchTooLarge:
                if len(hashes) == 1:
                    raise CloudError(
                        f"chunk {hashes[0][:12]}… is too large for the server"
                    ) from None
                half = len(hashes) // 2
                send(hashes[:half])
                send(hashes[half:])
                return
            stored.update(body.get("stored", []))
            existing.update(body.get("existing", []))
            rejected.update(body.get("rejected", {}))

        if batches:
            # Learn whether the server inflates gzip bodies before the first
            # batch, if no chunk-route response has told us yet.
            client.probe_gzip(address)
            with ThreadPoolExecutor(max_workers=BATCH_WORKERS) as pool:
                # Iterating re-raises the first worker exception, so an
                # unavailable object store aborts before any git activity.
                list(pool.map(send, batches))

        confirmed = (set(local) - missing) | stored | existing
        self._remember_pushed(confirmed)
        if rejected:
            listed = "; ".join(
                f"{h[:12]}…: {why}" for h, why in sorted(rejected.items())
            )
            raise CloudError(
                f"server rejected {len(rejected)} chunk(s), the root may be "
                f"unreachable there: {listed}"
            )
        return len(stored), len(local) - len(stored)

    def _download_chunks(self, client: CloudClient, address: str) -> int:
        remote = set(client.list_chunks(address))
        self._remember_pushed(remote)  # the server has these; no need to re-send
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

        started = time.monotonic()
        git_seconds = 0.0
        with self._client(gateway) as client:
            client.handle()
            uploaded, present = self._upload_chunks(client, address)
            chunk_seconds = time.monotonic() - started

            # Only after every chunk is resident on the server.
            t_git = time.monotonic()
            result = self._git(
                ["push", self.remote, f"{branch}:{branch}"], auth=True, check=False
            )
            git_seconds += time.monotonic() - t_git
            if result.returncode != 0 and "missing chunk" in result.stderr:
                # The pushed record disagreed with the server (e.g. it was
                # written on another machine, or the server lost objects):
                # negotiate everything, rebuild the record, push once more.
                t_more = time.monotonic()
                more, _ = self._upload_chunks(client, address, negotiate=True)
                chunk_seconds += time.monotonic() - t_more
                uploaded += more
                present -= more
                t_git = time.monotonic()
                result = self._git(
                    ["push", self.remote, f"{branch}:{branch}"], auth=True, check=False
                )
                git_seconds += time.monotonic() - t_git
            bytes_sent = client.bytes_sent
            compressed = client.gzip_ok and not client._gzip_refused and bytes_sent > 0
        if result.returncode != 0:
            stderr = redact(result.stderr, self._key)
            if "non-fast-forward" in stderr or "fetch first" in stderr:
                raise NonFastForwardError(
                    "remote has commits you don't have; run `memoir pull` first"
                )
            raise GitOperationError(f"git push failed: {stderr.strip()}")
        self._report_repo_meta(gateway, owner, store_name)
        return PushResult(
            branch=branch,
            address=address,
            chunks_uploaded=uploaded,
            chunks_present=present,
            pushed=True,
            seconds=time.monotonic() - started,
            chunk_seconds=chunk_seconds,
            git_seconds=git_seconds,
            bytes_sent=bytes_sent,
            compressed=compressed,
        )

    def _create_and_link(self, name: str, gateway: str | None) -> None:
        """``push --create <store>``: validate locally, create, set origin."""
        error = validate_store_name(name)
        if error:
            raise ServiceError(f'"{name}" is not a valid store name: {error}')
        existing = self.remote_address()
        if existing:
            raise ServiceError(
                f"remote '{self.remote}' already links this store to {existing}; "
                f"run `memoir remote remove {self.remote}` first, or use "
                "`--remote <other-name>`"
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
            self._git(["fetch", "--tags", self.remote], auth=True)
            downloaded = self._download_chunks(client, address)
        refs = self._git(
            [
                "for-each-ref",
                "--format=%(refname:short)",
                f"refs/remotes/{self.remote}/",
            ]
        ).stdout.split()
        return FetchResult(
            address=address, chunks_downloaded=downloaded, remote_refs=refs
        )

    def _diverged_message(self, branch: str) -> str:
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
        remote_ref = f"refs/remotes/{self.remote}/{branch}"
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

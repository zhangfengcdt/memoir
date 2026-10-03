# SPDX-License-Identifier: Apache-2.0
"""In-process fake of the memoir-cloud api-gateway for cloud-sync tests.

Implements the subset of the gateway contract that ``SyncService`` talks to,
with GitHub-style ``<owner>/<store>`` addressing:

- ``GET  /auth/whoami`` (``handle`` configurable, ``None`` → ``null``)
- ``POST /stores`` (422 on an invalid name, 409 on a duplicate),
  ``GET /stores``, ``GET /stores/by-name/{owner}/{store}`` (404 for unknown
  **or** not-owned)
- ``POST /{owner}/{store}/chunks/negotiate``, ``GET /{owner}/{store}/chunks``,
  ``PUT|GET /{owner}/{store}/chunks/{hash}``
- ``GET /{owner}/{store}/info/refs``, ``POST .../git-receive-pack``,
  ``POST .../git-upload-pack`` — delegated to the real ``git http-backend``
  CGI over a bare repo, so the git half of push/fetch/clone is exercised with
  the real ``git`` binary and no network.

Every request is recorded (method, path, headers, body) so tests can assert
on ordering (chunk PUTs before receive-pack), batching, and that the bearer
header actually arrives. Fault injection: ``fail_puts`` (always 500 for
those hashes), ``flaky_puts`` (500 once, then succeed), ``page_size`` (cap on
chunk-listing pages, to exercise pagination).
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:
    from pathlib import Path

API_KEY = "mck_test_secret_key_DO_NOT_LEAK"
HANDLE = "feng-zhang"
OTHER_HANDLE = "someone-else"

_STORE_NAME_RE = re.compile(r"^(?!\.)[A-Za-z0-9._-]{1,100}$")
_STORE_NAME_RULES = (
    "store names are 1-100 letters, digits, '.', '_' or '-'; "
    "not starting with '.'; not ending in .git"
)


@dataclass
class Recorded:
    method: str
    path: str
    headers: dict[str, str]
    body: bytes = b""


@dataclass
class FakeCloudState:
    repos_root: Path
    api_key: str = API_KEY
    handle: str | None = HANDLE
    # store_id -> store object (incl. owner_handle)
    stores: dict[str, dict] = field(default_factory=dict)
    # store_id -> {hash: bytes}
    chunks: dict[str, dict[str, bytes]] = field(default_factory=dict)
    requests: list[Recorded] = field(default_factory=list)
    fail_puts: set[str] = field(default_factory=set)
    flaky_puts: set[str] = field(default_factory=set)
    page_size: int | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def create_store(self, name: str, owner_handle: str | None = None) -> dict:
        owner_handle = owner_handle or self.handle or HANDLE
        store_id = f"str_{len(self.stores) + 1:04d}"
        repo = self.repos_root / store_id
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "init", "--bare", "-q", str(repo)], check=True, capture_output=True
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "http.receivepack", "true"],
            check=True,
            capture_output=True,
        )
        # Worst case for clients: the advertised HEAD names a branch that
        # does not exist (what an unset init.defaultBranch gives on CI). A
        # plain `git clone` then lands on an unborn branch; the client must
        # recover by checking out `main` itself.
        subprocess.run(
            ["git", "-C", str(repo), "symbolic-ref", "HEAD", "refs/heads/master"],
            check=True,
            capture_output=True,
        )
        store = {
            "id": store_id,
            "name": name,
            "owner_user_id": f"usr_{owner_handle}",
            "owner_handle": owner_handle,
            "created_at": "2026-10-03T00:00:00Z",
        }
        self.stores[store_id] = store
        self.chunks.setdefault(store_id, {})
        return store

    def lookup(self, owner: str, name: str) -> dict | None:
        """Owner-scoped, case-insensitive resolution (None if not yours)."""
        for s in self.stores.values():
            if (
                s["owner_handle"].lower() == owner.lower()
                and s["name"].lower() == name.lower()
                and s["owner_handle"] == self.handle
            ):
                return s
        return None

    def repo_for(self, owner: str, name: str) -> Path:
        store = self.lookup(owner, name)
        assert store is not None
        return self.repos_root / store["id"]

    def chunks_for(self, owner: str, name: str) -> dict[str, bytes]:
        store = self.lookup(owner, name)
        assert store is not None
        return self.chunks[store["id"]]

    def paths(self, method: str | None = None) -> list[str]:
        return [r.path for r in self.requests if method is None or r.method == method]


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: FakeCloudState  # set by the server factory

    def log_message(self, *_args):  # silence the default access log
        pass

    # ---- helpers -------------------------------------------------------
    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _send(self, status: int, body: bytes = b"", ctype: str = "application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, status: int, obj) -> None:
        self._send(status, json.dumps(obj).encode())

    def _authed(self) -> bool:
        return self.headers.get("Authorization") == f"Bearer {self.state.api_key}"

    def _record(self, body: bytes) -> None:
        with self.state.lock:
            self.state.requests.append(
                Recorded(self.command, self.path, dict(self.headers.items()), body)
            )

    # ---- dispatch ------------------------------------------------------
    def do_GET(self):
        self._dispatch(b"")

    def do_POST(self):
        self._dispatch(self._read_body())

    def do_PUT(self):
        self._dispatch(self._read_body())

    def _dispatch(self, body: bytes) -> None:
        self._record(body)
        parts = urlsplit(self.path)
        path = parts.path
        query = parse_qs(parts.query)

        if not self._authed():
            self._json(401, {"detail": "invalid or missing API key"})
            return

        if path == "/auth/whoami":
            self._json(
                200,
                {
                    "user_id": "usr_test",
                    "key_id": "k_test",
                    "scopes": ["read", "write"],
                    "expires_at": None,
                    "tier": "PRO",
                    "handle": self.state.handle,
                },
            )
            return

        if path == "/stores":
            if self.command == "POST":
                name = json.loads(body or b"{}").get("name", "")
                if (
                    not _STORE_NAME_RE.match(name)
                    or name.lower().endswith(".git")
                    or name in (".", "..")
                ):
                    self._json(
                        422,
                        {
                            "detail": [
                                {
                                    "type": "value_error",
                                    "loc": ["body", "name"],
                                    "msg": f"Value error, {_STORE_NAME_RULES}",
                                }
                            ]
                        },
                    )
                    return
                if any(
                    s["owner_handle"] == self.state.handle
                    and s["name"].lower() == name.lower()
                    for s in self.state.stores.values()
                ):
                    self._json(409, {"detail": "store name already exists"})
                    return
                self._json(201, self.state.create_store(name))
            else:
                self._json(
                    200,
                    [
                        s
                        for s in self.state.stores.values()
                        if s["owner_handle"] == self.state.handle
                    ],
                )
            return

        if path.startswith("/stores/by-name/"):
            segs = path[len("/stores/by-name/") :].split("/")
            store = self.state.lookup(*segs) if len(segs) == 2 else None
            if store is None:
                self._json(404, {"detail": "store not found"})
            else:
                self._json(200, store)
            return

        # /{owner}/{store}/...
        segs = path.strip("/").split("/", 2)
        if len(segs) == 3:
            owner, name, tail = segs
            if self.state.lookup(owner, name) is None:
                self._json(404, {"detail": "store not found"})
                return
            if tail.startswith("chunks"):
                self._chunks(owner, name, tail, query, body)
            elif tail in ("info/refs", "git-receive-pack", "git-upload-pack"):
                self._git_cgi(owner, name, tail, parts.query, body)
            else:
                self._json(404, {"detail": "unknown route"})
            return

        self._json(404, {"detail": "not found"})

    # ---- chunk protocol ------------------------------------------------
    def _chunks(
        self, owner: str, name: str, tail: str, query: dict, body: bytes
    ) -> None:
        store_chunks = self.state.chunks_for(owner, name)
        if tail == "chunks/negotiate" and self.command == "POST":
            req = json.loads(body or b"{}")
            have = req.get("have", [])
            want = req.get("want", [])
            if len(have) + len(want) > 500:
                self._json(400, {"detail": "batch too large"})
                return
            self._json(
                200,
                {
                    "missing_on_server": [h for h in have if h not in store_chunks],
                    "present_on_server": [h for h in want if h in store_chunks],
                },
            )
            return
        if tail == "chunks" and self.command == "GET":
            limit = int(query.get("limit", ["1000"])[0])
            if self.state.page_size:
                limit = min(limit, self.state.page_size)
            after = query.get("after", [None])[0]
            keys = sorted(store_chunks)
            if after:
                keys = [k for k in keys if k > after]
            page = keys[:limit]
            self._json(
                200,
                {"hashes": page, "next": page[-1] if len(page) == limit else None},
            )
            return
        if tail.startswith("chunks/"):
            chunk_hash = tail[len("chunks/") :]
            if self.command == "PUT":
                if chunk_hash in self.state.fail_puts:
                    self._json(500, {"detail": "injected failure"})
                    return
                if chunk_hash in self.state.flaky_puts:
                    with self.state.lock:
                        self.state.flaky_puts.discard(chunk_hash)
                    self._json(503, {"detail": "injected transient failure"})
                    return
                if len(body) > 8 * 1024 * 1024:
                    self._json(413, {"detail": "too large"})
                    return
                with self.state.lock:
                    existed = chunk_hash in store_chunks
                    store_chunks[chunk_hash] = body
                self._send(200 if existed else 201)
                return
            if self.command == "GET":
                data = store_chunks.get(chunk_hash)
                if data is None:
                    self._json(404, {"detail": "chunk not found"})
                else:
                    self._send(200, data, "application/octet-stream")
                return
        self._json(404, {"detail": "unknown chunk route"})

    # ---- git smart-HTTP via git http-backend ---------------------------
    def _git_cgi(
        self, owner: str, name: str, tail: str, query: str, body: bytes
    ) -> None:
        repo = self.state.repo_for(owner, name)
        env = {
            **os.environ,
            "GIT_PROJECT_ROOT": str(repo.parent),
            "GIT_HTTP_EXPORT_ALL": "1",
            "PATH_INFO": f"/{repo.name}/{tail}",
            "REQUEST_METHOD": self.command,
            "QUERY_STRING": query,
            "CONTENT_TYPE": self.headers.get("Content-Type", ""),
            "CONTENT_LENGTH": str(len(body)),
            "REMOTE_ADDR": "127.0.0.1",
            "SERVER_PROTOCOL": "HTTP/1.1",
            "GATEWAY_INTERFACE": "CGI/1.1",
        }
        enc = self.headers.get("Content-Encoding")
        if enc:
            env["HTTP_CONTENT_ENCODING"] = enc
        proc = subprocess.run(
            ["git", "http-backend"],
            input=body,
            env=env,
            capture_output=True,
            check=False,
        )
        head, _, payload = proc.stdout.partition(b"\r\n\r\n")
        status = 200
        headers: list[tuple[str, str]] = []
        for line in head.decode("latin-1").splitlines():
            key, _, value = line.partition(":")
            value = value.strip()
            if key.lower() == "status":
                status = int(value.split()[0])
            else:
                headers.append((key, value))
        self.send_response(status)
        for key, value in headers:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)


class FakeCloud:
    """Context manager: starts the fake gateway on a free localhost port."""

    def __init__(self, repos_root: Path):
        self.state = FakeCloudState(repos_root=repos_root)
        handler = type("BoundHandler", (_Handler,), {"state": self.state})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    def __enter__(self) -> FakeCloud:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._server.shutdown()
        self._server.server_close()

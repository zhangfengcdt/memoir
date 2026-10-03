# SPDX-License-Identifier: Apache-2.0
"""In-process fake of the memoir-cloud api-gateway for cloud-sync tests.

Implements the subset of the gateway contract that ``SyncService`` talks to:

- ``GET  /auth/whoami``
- ``GET|POST /stores``, ``GET /stores/{id}``
- ``POST /sync/{id}/chunks/negotiate``, ``GET /sync/{id}/chunks``,
  ``PUT|GET /sync/{id}/chunks/{hash}``
- ``GET /sync/{id}/info/refs``, ``POST /sync/{id}/git-receive-pack``,
  ``POST /sync/{id}/git-upload-pack`` — delegated to the real
  ``git http-backend`` CGI over a bare repo at ``<repos>/<id>``, so the git
  half of push/fetch/clone is exercised with the real ``git`` binary and no
  network.

Every request is recorded (method, path, headers) so tests can assert on
ordering (chunk PUTs before receive-pack), batching, and that the bearer
header actually arrives. Fault injection: ``fail_puts`` (always 500 for
those hashes), ``flaky_puts`` (500 once, then succeed), ``page_size``
(cap on chunk-listing pages, to exercise pagination).
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

if TYPE_CHECKING:
    from pathlib import Path

API_KEY = "mk_test_secret_key_DO_NOT_LEAK"


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
    stores: dict[str, dict] = field(default_factory=dict)
    chunks: dict[str, dict[str, bytes]] = field(default_factory=dict)
    requests: list[Recorded] = field(default_factory=list)
    fail_puts: set[str] = field(default_factory=set)
    flaky_puts: set[str] = field(default_factory=set)
    page_size: int | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def create_store(self, store_id: str, name: str = "test") -> dict:
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
        store = {
            "id": store_id,
            "name": name,
            "owner_user_id": "usr_test",
            "created_at": "2026-10-03T00:00:00Z",
        }
        self.stores[store_id] = store
        self.chunks.setdefault(store_id, {})
        return store

    def paths(self, method: str | None = None) -> list[str]:
        return [r.path for r in self.requests if method is None or r.method == method]


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: FakeCloudState  # set by the server factory

    # Silence the default stderr access log.
    def log_message(self, *_args):
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
                Recorded(
                    self.command,
                    self.path,
                    dict(self.headers.items()),
                    body,
                )
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
                    "scopes": ["stores:rw"],
                    "expires_at": None,
                    "tier": "PRO",
                },
            )
            return

        if path == "/stores":
            if self.command == "POST":
                payload = json.loads(body or b"{}")
                store_id = f"str_{len(self.state.stores) + 1:04d}"
                store = self.state.create_store(store_id, payload.get("name", ""))
                self._json(201, store)
            else:
                self._json(200, list(self.state.stores.values()))
            return

        if path.startswith("/stores/"):
            store_id = path.split("/", 2)[2]
            store = self.state.stores.get(store_id)
            if store is None:
                self._json(404, {"detail": "store not found"})
            else:
                self._json(200, store)
            return

        if path.startswith("/sync/"):
            rest = path[len("/sync/") :]
            store_id, _, tail = rest.partition("/")
            if store_id not in self.state.stores:
                self._json(404, {"detail": "store not found"})
                return
            if tail.startswith("chunks"):
                self._chunks(store_id, tail, query, body)
            elif tail in ("info/refs", "git-receive-pack", "git-upload-pack"):
                self._git_cgi(store_id, tail, parts.query, body)
            else:
                self._json(404, {"detail": "unknown sync route"})
            return

        self._json(404, {"detail": "not found"})

    # ---- chunk protocol ------------------------------------------------
    def _chunks(self, store_id: str, tail: str, query: dict, body: bytes) -> None:
        store_chunks = self.state.chunks.setdefault(store_id, {})
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
    def _git_cgi(self, store_id: str, tail: str, query: str, body: bytes) -> None:
        env = {
            **os.environ,
            "GIT_PROJECT_ROOT": str(self.state.repos_root),
            "GIT_HTTP_EXPORT_ALL": "1",
            "PATH_INFO": f"/{store_id}/{tail}",
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
            name, _, value = line.partition(":")
            value = value.strip()
            if name.lower() == "status":
                status = int(value.split()[0])
            else:
                headers.append((name, value))
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
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

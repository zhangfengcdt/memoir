# SPDX-License-Identifier: Apache-2.0
"""
Background lifecycle control for the memoir UI server.

Tracks running `memoir ui` processes via small JSON pidfiles under
~/.memoir/ui-servers/, one per store, keyed by a short hash of the store's
absolute path. This lets independent callers (hooks, skills, a terminal)
start, query, and stop a per-store UI server without stepping on each
other or on servers started for other stores.

This module is intentionally host-agnostic: it has no notion of Claude
Code, Codex, or any other integration. The CLI commands in
`memoir.cli.commands.ui` (ui-start / ui-status / ui-stop) are the thin
wrapper around it; every host plugin now delegates to those commands
instead of carrying its own copy of this logic.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path
from typing import Any

PIDFILE_DIR = Path.home() / ".memoir" / "ui-servers"

_READY_URL_RE = re.compile(r"http://localhost:\d+/\?store=\S+")
_START_TIMEOUT_SECONDS = 3.0
_START_POLL_INTERVAL_SECONDS = 0.2
_STOP_GRACE_ATTEMPTS = 5
_STOP_GRACE_INTERVAL_SECONDS = 0.2


class ServerStartError(RuntimeError):
    """Raised when a background UI server fails to reach ready state."""


def _pidfile_for(store: str) -> Path:
    """Pidfile path for a store, keyed by the first 8 hex chars of its sha256.

    Hashing (rather than a sanitized path) keeps the filename short and
    avoids collisions between stores whose paths differ only in characters
    that would otherwise need escaping.
    """
    digest = hashlib.sha256(store.encode()).hexdigest()[:8]
    return PIDFILE_DIR / f"{digest}.json"


def _read_record(pidfile: Path) -> dict[str, Any] | None:
    try:
        with pidfile.open() as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_record(pidfile: Path, record: dict[str, Any]) -> None:
    PIDFILE_DIR.mkdir(parents=True, exist_ok=True)
    with pidfile.open("w") as f:
        json.dump(record, f)


def _process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def _server_alive(record: dict[str, Any]) -> bool:
    """A tracked server counts as alive only when both a pid and a url were
    recorded and the pid is still running. A record with no url means the
    server never reached ready state; a dead pid means it crashed or was
    killed outside memoir. Either way it should be reported as stale, not
    running.
    """
    return bool(record.get("url")) and _process_alive(record.get("pid"))


def _open_in_browser(url: str) -> None:
    # Best-effort only — a missing/broken browser launcher shouldn't fail
    # the start/reuse call itself.
    with contextlib.suppress(Exception):
        webbrowser.open(url)


def _tail(path: Path, lines: int) -> str:
    try:
        content = path.read_text(errors="ignore").splitlines()
    except OSError:
        return ""
    return "\n".join(content[-lines:])


def _wait_for_ready_url(log_path: Path, pid: int) -> str | None:
    """Poll the launch log for the "Opening ... at http://localhost:<port>/?store=..."
    line the CLI prints once the server has bound successfully, bailing out
    early if the process dies first.
    """
    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        text = log_path.read_text(errors="ignore") if log_path.exists() else ""
        match = _READY_URL_RE.search(text)
        if match:
            return match.group(0)
        if not _process_alive(pid):
            break
        time.sleep(_START_POLL_INTERVAL_SECONDS)
    return None


def start(store: str, *, open_browser: bool = True) -> tuple[dict[str, Any], bool]:
    """Start a background UI server for `store`, or reuse one already running.

    Returns (record, reused). `record` always contains pid, port, url,
    store, started, and log.

    Raises ServerStartError if a fresh launch doesn't reach ready state
    within the startup window.
    """
    store = str(Path(store).resolve())
    pidfile = _pidfile_for(store)

    existing = _read_record(pidfile)
    if existing and _server_alive(existing):
        if open_browser:
            _open_in_browser(existing["url"])
        return {**existing, "reused": True}, True
    if existing:
        # Stale pidfile from a crashed or killed process — clear it before
        # launching a replacement.
        pidfile.unlink(missing_ok=True)

    log_fd, log_name = tempfile.mkstemp(prefix="memoir-ui.", suffix=".log")
    log_path = Path(log_name)
    with os.fdopen(log_fd, "w") as log_file:
        # A fully detached child (new session, stdio redirected to the log
        # file) so it survives the caller's process exiting — mirrors the
        # `nohup ... &` launch the plugin scripts used before this moved
        # into core.
        process = subprocess.Popen(
            [sys.executable, sys.argv[0], "ui", store],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    url = _wait_for_ready_url(log_path, process.pid)
    if not url or not _process_alive(process.pid):
        tail = _tail(log_path, 40)
        log_path.unlink(missing_ok=True)
        raise ServerStartError(f"memoir ui failed to start. Log tail:\n{tail}")

    port_match = re.search(r"localhost:(\d+)", url)
    port = int(port_match.group(1)) if port_match else 0
    record = {
        "pid": process.pid,
        "port": port,
        "url": url,
        "store": store,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "log": str(log_path),
    }
    _write_record(pidfile, record)

    if open_browser:
        _open_in_browser(url)

    return {**record, "reused": False}, False


def status_one(store: str) -> dict[str, Any] | None:
    """Status for a single store's tracked server, or None if untracked."""
    record = _read_record(_pidfile_for(str(Path(store).resolve())))
    if not record:
        return None
    return {**record, "state": "running" if _server_alive(record) else "stale"}


def status_all() -> list[dict[str, Any]]:
    """Status for every server memoir is currently tracking, across all stores."""
    entries: list[dict[str, Any]] = []
    if not PIDFILE_DIR.is_dir():
        return entries
    for pidfile in sorted(PIDFILE_DIR.glob("*.json")):
        record = _read_record(pidfile)
        if record:
            entries.append(
                {**record, "state": "running" if _server_alive(record) else "stale"}
            )
    return entries


def _stop_pidfile(pidfile: Path) -> dict[str, Any]:
    record = _read_record(pidfile) or {}
    pid = record.get("pid")
    if isinstance(pid, int) and _process_alive(pid):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
        for _ in range(_STOP_GRACE_ATTEMPTS):
            if not _process_alive(pid):
                break
            time.sleep(_STOP_GRACE_INTERVAL_SECONDS)
        if _process_alive(pid):
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)
        outcome = "stopped"
    else:
        outcome = "already gone"
    pidfile.unlink(missing_ok=True)
    return {"pid": pid, "url": record.get("url"), "outcome": outcome}


def stop_one(store: str) -> dict[str, Any] | None:
    """Stop a single store's tracked server. Returns None (no-op, no output)
    when the store has no tracked server at all.
    """
    pidfile = _pidfile_for(str(Path(store).resolve()))
    if not pidfile.exists():
        return None
    return _stop_pidfile(pidfile)


def stop_all() -> list[dict[str, Any]]:
    """Stop every server memoir is currently tracking, across all stores."""
    results: list[dict[str, Any]] = []
    if not PIDFILE_DIR.is_dir():
        return results
    for pidfile in sorted(PIDFILE_DIR.glob("*.json")):
        results.append(_stop_pidfile(pidfile))
    return results

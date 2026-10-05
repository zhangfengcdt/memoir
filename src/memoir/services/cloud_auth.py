# SPDX-License-Identifier: Apache-2.0
"""
memoir-cloud credentials on this machine (issue #168).

``memoir login`` runs a device-approval flow (like ``gh auth login``): the CLI
asks the gateway for a short user code, the user approves it in a browser that
is already signed in, and the gateway hands back an API key exactly once. The
key, its gateway and the user's handle are saved to
``$XDG_CONFIG_HOME/memoir/cloud.json`` (default ``~/.config/memoir/cloud.json``)
with mode 0600 in a 0700 directory.

Resolution used by every cloud command:

- key: ``MEMOIR_API_KEY`` env (wins) → ``cloud.json``
- gateway: ``--url`` → ``MEMOIR_CLOUD_URL`` → ``cloud.json`` → production

The key is never printed; callers keep redacting it from error text.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

POLL_TIMEOUT = 10.0
CLIENT_NAME_MAX = 64


class LoginError(Exception):
    """The device flow ended without a key (denied, expired, network)."""


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "memoir"


def config_path() -> Path:
    return config_dir() / "cloud.json"


def load() -> dict[str, Any] | None:
    """The saved login, or ``None`` when absent or unreadable."""
    try:
        data = json.loads(config_path().read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("api_key"), str):
        return None
    return data


def save(gateway: str, api_key: str, handle: str | None) -> Path:
    """Write the login atomically: directory 0700, file 0600 from creation."""
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    path = config_path()
    tmp = directory / f".cloud.json.tmp.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(
                {"gateway": gateway, "api_key": api_key, "handle": handle}, f, indent=2
            )
            f.write("\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def delete() -> bool:
    """Remove the saved login. True when a file was removed."""
    try:
        config_path().unlink()
        return True
    except FileNotFoundError:
        return False


def saved_key() -> str:
    data = load()
    return str(data["api_key"]).strip() if data else ""


def saved_gateway() -> str | None:
    data = load()
    gw = data.get("gateway") if data else None
    return gw.rstrip("/") if isinstance(gw, str) and gw else None


def client_name() -> str:
    return (socket.gethostname() or "memoir-cli")[:CLIENT_NAME_MAX]


# --------------------------------------------------------------------------
# Device flow
# --------------------------------------------------------------------------


def device_login(
    gateway: str,
    *,
    on_code: Callable[[dict[str, Any]], None],
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Run start → (user approves in a browser) → poll. Returns
    ``{"api_key", "handle", "gateway"}`` or raises ``LoginError``.

    ``on_code`` receives the ``start`` response so the caller can show the
    code and open the browser. Polls no faster than the server's interval.
    """
    import httpx

    with httpx.Client(base_url=gateway, timeout=POLL_TIMEOUT) as client:
        try:
            resp = client.post("/auth/cli/start", json={"client_name": client_name()})
        except httpx.HTTPError as e:
            raise LoginError(f"cannot reach {gateway}: {e}") from None
        if resp.status_code != 200:
            raise LoginError(
                f"login is not available on {gateway} ({resp.status_code})"
            )
        start = resp.json()
        on_code(start)
        interval = max(1.0, float(start.get("interval", 3)))
        deadline = now() + float(start.get("expires_in", 600))
        while now() < deadline:
            sleep(interval)
            try:
                poll = client.post(
                    "/auth/cli/poll", json={"device_code": start["device_code"]}
                )
            except httpx.HTTPError as e:
                logger.debug("login poll failed, retrying: %s", e)
                continue
            if poll.status_code == 404:
                raise LoginError(
                    "the login code is no longer known; run `memoir login` again"
                )
            if poll.status_code != 200:
                logger.debug("login poll → %s", poll.status_code)
                continue
            body = poll.json()
            status = body.get("status")
            if status == "approved" and body.get("api_key"):
                return {
                    "api_key": body["api_key"],
                    "handle": body.get("handle"),
                    "gateway": (body.get("gateway") or gateway).rstrip("/"),
                }
            if status == "denied":
                raise LoginError("the login was denied in the browser")
            if status == "expired":
                raise LoginError("the login code expired; run `memoir login` again")
        raise LoginError("the login code expired; run `memoir login` again")


def revoke(gateway: str, api_key: str) -> bool:
    """Best-effort ``POST /auth/keys/self/revoke``. True when the server said OK."""
    import httpx

    try:
        resp = httpx.post(
            f"{gateway.rstrip('/')}/auth/keys/self/revoke",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=POLL_TIMEOUT,
        )
    except httpx.HTTPError as e:
        logger.debug("key revoke failed: %s", e)
        return False
    return resp.status_code in (200, 204)

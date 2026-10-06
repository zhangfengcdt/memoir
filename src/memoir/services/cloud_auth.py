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

- key for gateway G: ``MEMOIR_API_KEY`` env (wins) → the entry saved for G;
  a saved key is never sent to any other gateway
- gateway (when no remote decides it): ``--url`` → ``MEMOIR_CLOUD_URL`` →
  the saved default → production

The file holds one login per gateway, like ``gh``'s ``hosts.yml``:
``{"default": "<gw>", "gateways": {"<gw>": {"api_key", "handle"}}}``.

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


def normalize_gateway(gateway: str) -> str:
    """``scheme://host[:port]``, lowercase, no path or trailing slash — the key
    credentials are stored and matched under (like ``gh``'s hosts)."""
    from urllib.parse import urlsplit

    parts = urlsplit(gateway.strip())
    if not parts.scheme or not parts.netloc:
        return gateway.strip().rstrip("/").lower()
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def _empty() -> dict[str, Any]:
    return {"default": None, "gateways": {}}


def load_all() -> dict[str, Any]:
    """All saved logins: ``{"default": <gw>|None, "gateways": {<gw>: {"api_key",
    "handle"}}}``. Reads the single-login format of #169 as one entry (it is
    rewritten in the new shape on the next save). Missing / unreadable → empty.
    """
    try:
        data = json.loads(config_path().read_text())
    except (OSError, ValueError):
        return _empty()
    if not isinstance(data, dict):
        return _empty()
    if "gateways" not in data and isinstance(data.get("api_key"), str):
        # #169 format: {"gateway", "api_key", "handle"}
        gw = data.get("gateway")
        if not isinstance(gw, str) or not gw:
            return _empty()
        key = normalize_gateway(gw)
        return {
            "default": key,
            "gateways": {
                key: {"api_key": data["api_key"], "handle": data.get("handle")}
            },
        }
    gateways: dict[str, Any] = {}
    raw = data.get("gateways")
    if isinstance(raw, dict):
        for gw, entry in raw.items():
            if isinstance(entry, dict) and isinstance(entry.get("api_key"), str):
                gateways[normalize_gateway(gw)] = {
                    "api_key": entry["api_key"],
                    "handle": entry.get("handle"),
                }
    default = data.get("default")
    default = (
        normalize_gateway(default) if isinstance(default, str) and default else None
    )
    if default not in gateways:
        default = next(iter(gateways), None)
    return {"default": default, "gateways": gateways}


def _write(data: dict[str, Any]) -> Path:
    """Write atomically: directory 0700, file 0600 from creation."""
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    path = config_path()
    tmp = directory / f".cloud.json.tmp.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return path


def save(
    gateway: str, api_key: str, handle: str | None, *, make_default: bool = False
) -> Path:
    """Add or replace the login for ``gateway``. The first login (or
    ``make_default``) becomes the default gateway."""
    data = load_all()
    key = normalize_gateway(gateway)
    data["gateways"][key] = {"api_key": api_key, "handle": handle}
    if make_default or not data["default"]:
        data["default"] = key
    return _write(data)


def remove(gateway: str) -> dict[str, Any] | None:
    """Drop the login for ``gateway``; returns the removed entry. When the
    default goes, another saved gateway (if any) becomes the default; the
    file is deleted when nothing is left."""
    data = load_all()
    key = normalize_gateway(gateway)
    entry = data["gateways"].pop(key, None)
    if entry is None:
        return None
    if data["default"] == key:
        data["default"] = next(iter(data["gateways"]), None)
    if data["gateways"]:
        _write(data)
    else:
        config_path().unlink(missing_ok=True)
    return dict(entry)


def entry(gateway: str) -> dict[str, Any] | None:
    """The saved login for exactly this gateway (normalised), or None."""
    found = load_all()["gateways"].get(normalize_gateway(gateway))
    return dict(found) if found else None


def default_gateway() -> str | None:
    default = load_all()["default"]
    return str(default) if default else None


def saved_keys() -> list[str]:
    """Every saved key — for redaction only."""
    return [e["api_key"] for e in load_all()["gateways"].values() if e.get("api_key")]


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

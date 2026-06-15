# SPDX-License-Identifier: Apache-2.0
"""``hermes memoir`` CLI subcommands: status | ui.

Loaded independently of the provider by Hermes's
``discover_plugin_cli_commands`` (it imports only this module during argparse
setup), so this file stays lightweight and self-contained. The loader wires
``register_cli`` as the parser builder and ``memoir_command`` as the handler.
"""

from __future__ import annotations

import json
import os
import sys

try:  # Loaded as a package submodule inside the Hermes host.
    from .bridge import INSTALL_HINT, MemoirBridge
except ImportError:  # Direct/flat import (tests).
    from bridge import INSTALL_HINT, MemoirBridge  # type: ignore


def _hermes_home() -> str:
    try:
        from hermes_constants import get_hermes_home  # type: ignore

        return str(get_hermes_home())
    except Exception:
        return os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")


def _store_path() -> str:
    """Resolve the memoir store path: config override → <hermes_home>/memoir-store."""
    home = _hermes_home()
    cfg_path = os.path.join(home, "memoir.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8") as f:
                cfg = json.load(f) or {}
            if cfg.get("store_path"):
                return cfg["store_path"]
        except Exception:
            pass
    return os.path.join(home, "memoir-store")


def register_cli(subparser) -> None:
    """Build the ``hermes memoir`` argparse subcommand tree."""
    subs = subparser.add_subparsers(dest="memoir_command")
    subs.add_parser("status", help="Show memoir store status")
    subs.add_parser("ui", help="Launch the memoir web UI for this store")
    subparser.set_defaults(func=memoir_command)


def memoir_command(args) -> None:
    store = _store_path()
    bridge = MemoirBridge(store)

    if not bridge.available():
        print(INSTALL_HINT, file=sys.stderr)
        sys.exit(127)

    cmd = getattr(args, "memoir_command", None)

    if cmd == "ui":
        # Long-running web server — hand stdio over to the memoir UI.
        base = bridge._cli()  # resolved argv
        if not base:
            print(INSTALL_HINT, file=sys.stderr)
            sys.exit(127)
        os.execvp(base[0], [*base, "-s", store, "ui"])
        return

    # Default: status.
    if not os.path.isdir(os.path.join(store, ".git")):
        print(f"No memoir store at {store}. It is created on first agent run.")
        return
    ok, payload = bridge.status()
    if not ok:
        print(
            f"memoir status failed: {payload.get('error', 'unknown error')}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"Store:  {store}")
    if isinstance(payload, dict):
        for label, key in (
            ("Branch", "branch"),
            ("Commits", "commit_count"),
            ("Memories", "memory_count"),
        ):
            if key in payload:
                print(f"{label}: {payload[key]}")

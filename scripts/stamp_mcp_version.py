#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stamp a version into the MCP distribution metadata.

Sets ``version`` in ``packaging/mcp/manifest.json`` (the Claude Desktop .mcpb
manifest) and ``packaging/mcp/server.json`` (the official MCP Registry entry,
including each package's version). Used by the MCP release pipeline so the
shipped artifacts always carry the released version.

Usage:
    python scripts/stamp_mcp_version.py 0.2.4
    python scripts/stamp_mcp_version.py --check 0.2.4   # verify, don't write
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

MCP_DIR = Path(__file__).resolve().parent.parent / "packaging" / "mcp"


def _apply(version: str, *, check: bool) -> bool:
    ok = True
    manifest = MCP_DIR / "manifest.json"
    server = MCP_DIR / "server.json"

    m = json.loads(manifest.read_text())
    if check:
        ok &= m.get("version") == version
    else:
        m["version"] = version
        manifest.write_text(json.dumps(m, indent=2) + "\n")

    s = json.loads(server.read_text())
    if check:
        ok &= s.get("version") == version
        ok &= all(p.get("version") == version for p in s.get("packages", []))
    else:
        s["version"] = version
        for pkg in s.get("packages", []):
            pkg["version"] = version
        server.write_text(json.dumps(s, indent=2) + "\n")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Stamp the MCP distribution metadata version.")
    parser.add_argument("--check", action="store_true", help="Verify the version matches; do not write.")
    parser.add_argument("version", help="Version to stamp (e.g. 0.2.4).")
    args = parser.parse_args()

    if args.check:
        if _apply(args.version, check=True):
            print(f"MCP metadata version == {args.version}")
            return 0
        print(f"ERROR: MCP metadata does not match {args.version}", file=sys.stderr)
        return 1

    _apply(args.version, check=False)
    print(f"stamped MCP metadata -> {args.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

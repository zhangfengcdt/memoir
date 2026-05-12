#!/usr/bin/env python3
"""Version consistency check for memoir release surfaces.

Memoir has three independently versioned products:

  * The Python package ``memoir-ai`` (source of truth: ``src/memoir/__init__.py``).
  * The Claude Code plugin ``memoir`` (source of truth: the plugin manifest).
  * The Codex plugin ``memoir`` (source of truth: the plugin manifest).

The three products may legitimately track different version numbers, but within
each group every file that declares a version must agree. This script enforces
that invariant so a release bump that forgets to touch one file fails fast in
CI.

Exit codes: 0 if every group is internally consistent, 1 otherwise.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class VersionSource:
    label: str
    path: Path
    version: str


def _read_python_version(path: Path) -> str:
    text = path.read_text()
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"{path}: could not find __version__ assignment")
    return match.group(1)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def collect_sources() -> dict[str, list[VersionSource]]:
    """Return version sources grouped by product."""

    pkg_init = REPO_ROOT / "src" / "memoir" / "__init__.py"
    claude_plugin_manifest = REPO_ROOT / "plugins" / "claude-code" / ".claude-plugin" / "plugin.json"
    codex_plugin_manifest = REPO_ROOT / "plugins" / "codex" / ".codex-plugin" / "plugin.json"
    claude_marketplace = REPO_ROOT / ".claude-plugin" / "marketplace.json"

    python_group: list[VersionSource] = [
        VersionSource(
            label="src/memoir/__init__.py:__version__",
            path=pkg_init,
            version=_read_python_version(pkg_init),
        ),
    ]

    claude_plugin_group: list[VersionSource] = []
    codex_plugin_group: list[VersionSource] = []

    plugin_json = _read_json(claude_plugin_manifest)
    plugin_name = plugin_json.get("name", "memoir")
    claude_plugin_group.append(
        VersionSource(
            label=f"{claude_plugin_manifest.relative_to(REPO_ROOT)}:version",
            path=claude_plugin_manifest,
            version=plugin_json["version"],
        )
    )

    marketplace_json = _read_json(claude_marketplace)
    claude_plugin_group.append(
        VersionSource(
            label=f"{claude_marketplace.relative_to(REPO_ROOT)}:metadata.version",
            path=claude_marketplace,
            version=marketplace_json["metadata"]["version"],
        )
    )

    for entry in marketplace_json.get("plugins", []):
        if entry.get("name") == plugin_name:
            claude_plugin_group.append(
                VersionSource(
                    label=f"{claude_marketplace.relative_to(REPO_ROOT)}:plugins[{plugin_name}].version",
                    path=claude_marketplace,
                    version=entry["version"],
                )
            )
            break
    else:
        raise RuntimeError(
            f"{claude_marketplace}: no plugin entry named {plugin_name!r} — update this script "
            f"if the plugin was renamed."
        )

    codex_plugin_json = _read_json(codex_plugin_manifest)
    codex_plugin_group.append(
        VersionSource(
            label=f"{codex_plugin_manifest.relative_to(REPO_ROOT)}:version",
            path=codex_plugin_manifest,
            version=codex_plugin_json["version"],
        )
    )

    return {
        "Python package (memoir-ai)": python_group,
        "Claude Code plugin (memoir)": claude_plugin_group,
        "Codex plugin (memoir)": codex_plugin_group,
    }


def check_group(name: str, sources: list[VersionSource]) -> bool:
    versions = {s.version for s in sources}
    width = max(len(s.label) for s in sources)
    print(f"{name}:")
    for src in sources:
        print(f"  {src.label.ljust(width)}  {src.version}")
    if len(versions) == 1:
        print("  ✓ consistent\n")
        return True
    print(f"  ✗ MISMATCH: expected one version, found {sorted(versions)}\n")
    return False


def main() -> int:
    try:
        groups = collect_sources()
    except (FileNotFoundError, KeyError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("Version consistency check")
    print("=" * 25)
    print()

    ok = True
    for name, sources in groups.items():
        if not check_group(name, sources):
            ok = False

    if ok:
        print("All version groups consistent.")
        return 0
    print("Version consistency check FAILED.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())

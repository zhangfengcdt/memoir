# SPDX-License-Identifier: Apache-2.0
"""Garbage collection for the prolly node store.

Every write saves fresh node files under ``.git/prolly/nodes/files/<hash>``
(content-addressed), and nothing removes the ones no commit refers to any
more: each ``put`` before a commit, each checkout, each merge leaves the
previous nodes behind. A store with a few dozen memories can carry hundreds
of thousands of dead nodes (one pane bug wrote 470,000 in a day).

A node is live when some commit's root reaches it. Each commit's
``data/prolly_config_tree_config`` names its root hash; a node names its
children by their raw 32-byte hashes. ``reachable_nodes`` walks from every
root of every ref (branches, remotes, tags, backups) plus the working
config, and ``collect_garbage`` reports or deletes the rest. ``push`` uses the
same walk so dead nodes never travel to the cloud.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from memoir.store.gitcmd import run_git

if TYPE_CHECKING:
    import subprocess

logger = logging.getLogger(__name__)

NODE_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
CONFIG_PATH = "data/prolly_config_tree_config"


def nodes_dir(store_path: str | Path) -> Path:
    return Path(store_path) / ".git" / "prolly" / "nodes" / "files"


def _git(store_path: str | Path, *args: str) -> subprocess.CompletedProcess:
    # Shared helper so UTF-8 decoding lives in one place (review #9a).
    return run_git(store_path, *args)


def _root_from_config(text: str) -> str | None:
    try:
        root = json.loads(text).get("root_hash")
    except (ValueError, AttributeError):
        return None
    if isinstance(root, list) and all(isinstance(b, int) for b in root):
        return bytes(root).hex()
    if isinstance(root, str) and NODE_HASH_RE.match(root):
        return root
    return None


def node_roots(store_path: str | Path) -> set[str]:
    """The root hash of every commit on every ref, and of the working tree."""
    roots: set[str] = set()
    revs = _git(store_path, "rev-list", "--all")
    if revs.returncode == 0:
        for sha in revs.stdout.split():
            blob = _git(store_path, "show", f"{sha}:{CONFIG_PATH}")
            if blob.returncode == 0:
                root = _root_from_config(blob.stdout)
                if root:
                    roots.add(root)
    working = Path(store_path) / CONFIG_PATH
    if working.is_file():
        root = _root_from_config(working.read_text(encoding="utf-8", errors="replace"))
        if root:
            roots.add(root)
    return roots


def local_nodes(store_path: str | Path) -> set[str]:
    """Every node file on disk, by hash."""
    nodes = nodes_dir(store_path)
    if not nodes.is_dir():
        return set()
    return {
        p.name for p in nodes.iterdir() if p.is_file() and NODE_HASH_RE.match(p.name)
    }


def reachable_nodes(
    store_path: str | Path, present: set[str] | None = None
) -> set[str]:
    """The node files some commit's root reaches. Children are found as raw
    32-byte windows of a node's bytes that name a file on disk; a chance
    match of 32 bytes against a real hash is as likely as a hash collision."""
    files = local_nodes(store_path) if present is None else present
    nodes = nodes_dir(store_path)
    seen: set[str] = set()
    stack = [root for root in node_roots(store_path) if root in files]
    while stack:
        h = stack.pop()
        if h in seen:
            continue
        seen.add(h)
        try:
            data = (nodes / h).read_bytes()
        except OSError:
            continue
        for i in range(len(data) - 31):
            child = data[i : i + 32].hex()
            if child in files and child not in seen:
                stack.append(child)
    return seen


@dataclass
class GcResult:
    reachable: int
    orphans: int
    bytes_orphaned: int
    deleted: int = 0
    applied: bool = False
    roots: int = 0
    orphan_hashes: list[str] = field(default_factory=list, repr=False)

    def to_dict(self) -> dict:
        return {
            "reachable": self.reachable,
            "orphans": self.orphans,
            "bytes_orphaned": self.bytes_orphaned,
            "deleted": self.deleted,
            "applied": self.applied,
            "roots": self.roots,
        }


def collect_garbage(store_path: str | Path, apply: bool = False) -> GcResult:
    """Report the dead node files, and delete them with ``apply``."""
    files = local_nodes(store_path)
    roots = node_roots(store_path)
    live = reachable_nodes(store_path, files)
    nodes = nodes_dir(store_path)
    orphans = sorted(files - live)
    size = 0
    for h in orphans:
        with contextlib.suppress(OSError):
            size += (nodes / h).stat().st_size
    deleted = 0
    if apply:
        for h in orphans:
            try:
                (nodes / h).unlink()
                deleted += 1
            except OSError as e:
                logger.warning("gc: could not delete %s: %s", h, e)
    return GcResult(
        reachable=len(live),
        orphans=len(orphans),
        bytes_orphaned=size,
        deleted=deleted,
        applied=apply,
        roots=len(roots),
        orphan_hashes=orphans,
    )

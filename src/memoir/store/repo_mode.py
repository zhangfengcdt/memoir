# SPDX-License-Identifier: Apache-2.0
"""
Repo mode: infer the memoir store from the code repo you're standing in (#168).

Store resolution is ``-s`` → ``MEMOIR_STORE`` → repo mode → cwd. Repo mode
applies when the current directory is inside a git work tree that is not
itself a memoir store. The store is ``~/.memoir/<slug>``, where ``<slug>`` is
the main worktree root with ``/`` and ``.`` replaced by ``-`` — the same
derivation as the Claude Code plugin's ``derive-store-path.sh``, so the CLI
and Claude Code sessions in that repo share one store.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from memoir.store.backend import is_memoir_store

GIT_TIMEOUT = 5.0


@dataclass(frozen=True)
class RepoContext:
    root: Path  # main worktree root of the code repo
    store: Path  # ~/.memoir/<slug>

    @property
    def name(self) -> str:
        return self.root.name


def _git(cwd: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    out = result.stdout.strip()
    return out if result.returncode == 0 and out else None


def main_worktree_root(cwd: Path) -> Path | None:
    """Root of the main worktree (linked worktrees share their main's store)."""
    porcelain = _git(cwd, "worktree", "list", "--porcelain")
    if porcelain:
        for line in porcelain.splitlines():
            if line.startswith("worktree "):
                candidate = Path(line[len("worktree ") :])
                if candidate.is_dir():
                    return candidate.resolve()
                break
    top = _git(cwd, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else None


def slug(path: Path) -> str:
    return str(path).replace("/", "-").replace(".", "-")


def store_for_repo(root: Path, home: Path | None = None) -> Path:
    return (home or Path.home()) / ".memoir" / slug(root.resolve())


def detect(cwd: Path | None = None, home: Path | None = None) -> RepoContext | None:
    """The repo context for ``cwd``, or ``None`` when repo mode doesn't apply
    (not in a git work tree, or the work tree is itself a memoir store)."""
    cwd = (cwd or Path.cwd()).resolve()
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return None
    if is_memoir_store(Path(top)):
        return None
    root = main_worktree_root(cwd) or Path(top).resolve()
    return RepoContext(root=root, store=store_for_repo(root, home))


def display(path: Path, home: Path | None = None) -> str:
    """``~/.memoir/<slug>`` rather than the absolute home path."""
    home = (home or Path.home()).resolve()
    try:
        return "~/" + str(path.resolve().relative_to(home))
    except ValueError:
        return str(path)

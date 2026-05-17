"""Git-config hardening for memoir stores.

prollytree's Git backend stores tree nodes as *dangling* git blob objects:
present in ``.git/objects/`` but not reachable from any branch or tag. Git's
default garbage collector is free to delete dangling objects when it runs,
which would silently corrupt memoir's memory data.

``harden_git_config`` applies two configs to every memoir store git repo:

- ``gc.auto = 0`` disables automatic gc triggered by routine git operations
  and by the "too many loose objects" heuristic.
- ``gc.pruneExpire = never`` keeps dangling objects even when ``git gc`` is
  invoked with its default config.

Called from the store-create paths and on every store open (idempotent), so
the retrofit reaches every existing memoir store the first time the new
memoir version opens it.

This protects against silent / automatic gc only. An explicit
``git gc --prune=now`` overrides the config and can still prune. The File
backend (chunks outside ``.git/objects/``) is the only fully bulletproof
option against that case.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


_HARDENING_CONFIGS: tuple[tuple[str, str], ...] = (
    ("gc.auto", "0"),
    ("gc.pruneExpire", "never"),
)


def harden_git_config(store_path: Path | str) -> None:
    """Apply gc-safety configs to the git repo at ``store_path``.

    Idempotent: safe to call on every store open. Existing values are
    overwritten unconditionally so legacy stores get retrofitted on first
    open by a memoir version that includes this helper.

    Args:
        store_path: Directory containing a ``.git`` subdirectory.

    Raises:
        FileNotFoundError: ``store_path`` has no ``.git`` directory.
        subprocess.CalledProcessError: a ``git config`` invocation failed.
    """
    path = Path(store_path)
    if not (path / ".git").exists():
        raise FileNotFoundError(f"Not a git repository (no .git): {path}")

    for key, value in _HARDENING_CONFIGS:
        subprocess.run(
            ["git", "-C", str(path), "config", key, value],
            check=True,
            capture_output=True,
        )

    logger.debug("gc-safety configs applied to %s", path)

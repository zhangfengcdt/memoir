# SPDX-License-Identifier: Apache-2.0
"""Backend resolution + per-store lock for memoir.

Resolves which ``prollytree.StorageBackend`` to use when opening or creating
a memoir store. Precedence rules (highest first):

1. **Per-store lock** at ``<store>/.git/memoir-backend``. A one-line file
   holding ``git`` / ``file`` / ``rocksdb``. Written by the store-create
   code path. Fixed for the life of the store — a store's backend cannot
   change after creation. ``memory`` is *not* a valid persisted value:
   the InMemory backend is volatile and locking a store to it would lose
   all data on next reopen.

2. **Legacy on-disk detection.** For stores that exist on disk but have no
   lock (created by a pre-this-change memoir version), the backend is
   inferred from the on-disk structure: a memoir store is recognized by
   the prollytree config file at ``data/prolly_config_tree_config`` (a
   plain top-level ``data/`` directory is *not* sufficient — random
   project repos can have one). Within a recognized memoir store,
   presence of ``.git/prolly/nodes/files/`` ⇒ File backend; otherwise
   ⇒ Git (the historic default).

3. **Env var** ``MEMOIR_PROLLY_BACKEND``. Case-insensitive, whitespace
   trimmed. Useful for power-users opting new stores into a non-default
   backend; cannot override a per-store lock or an existing store's
   detected backend.

4. **Default: File.** Brand-new stores with no env override are File-backed.
"""

import logging
import os
from pathlib import Path

from prollytree import StorageBackend

logger = logging.getLogger(__name__)

_ENV_VAR = "MEMOIR_PROLLY_BACKEND"

_NAME_TO_BACKEND: dict[str, StorageBackend] = {
    "git": StorageBackend.Git,
    "file": StorageBackend.File,
    "rocksdb": StorageBackend.RocksDB,
    # NOTE: ``memory`` (StorageBackend.InMemory) is deliberately absent.
    # Persisting it would create a store that loses all data on next
    # reopen, which is incoherent. ``parse_backend_name`` rejects it at
    # parse time so the failure surfaces before any partial init runs.
}


def _backend_to_name(backend: StorageBackend) -> str:
    """Reverse lookup. ``StorageBackend`` is a pyo3-bound class and is
    unhashable, so we can't use it as a dict key — linear search instead.
    """
    for name, candidate in _NAME_TO_BACKEND.items():
        if candidate == backend:
            return name
    raise ValueError(f"Unsupported backend: {backend!r}")


def parse_backend_name(value: str) -> StorageBackend:
    """Convert a backend name string to the ``StorageBackend`` enum value.

    Accepts ``git``, ``file``, ``rocksdb`` (case-insensitive, whitespace
    trimmed). ``memory`` is rejected here rather than later in
    ``write_backend_lock`` so the failure surfaces before partial init.
    Raises ``ValueError`` for unknown names.
    """
    return _parse_name(value, "backend name")


def _parse_name(value: str, source: str) -> StorageBackend:
    """Map a string like 'file' to ``StorageBackend.File``.

    ``source`` is woven into the error message so a bad lock-file value
    points at the lock path and a bad env-var points at the var name.
    """
    norm = value.strip().lower()
    if not norm:
        raise ValueError(f"{source}: empty backend name")
    if norm not in _NAME_TO_BACKEND:
        valid = ", ".join(sorted(_NAME_TO_BACKEND))
        raise ValueError(
            f"{source}: unknown backend {value!r}. Expected one of: {valid}"
        )
    return _NAME_TO_BACKEND[norm]


def _lock_path(store_path: Path) -> Path:
    return store_path / ".git" / "memoir-backend"


def _read_lock(store_path: Path) -> StorageBackend | None:
    lock = _lock_path(store_path)
    if not lock.exists():
        return None
    return _parse_name(lock.read_text(), f"{lock} (memoir-backend lock)")


def is_memoir_store(store_path: Path | str) -> bool:
    """Return True iff the given path is a memoir store.

    Memoir-specific markers (any one suffices):

    - ``.git/memoir-backend`` — the per-store backend lock, written by
      ``StoreService.create_store`` before any prollytree code runs. This
      is the earliest marker available.
    - ``.git/prolly/`` — prollytree's node-storage scratch directory.
    - ``data/prolly_config_tree_config`` — prollytree's tree config file,
      created on first ``VersionedKvStore`` init.

    A plain top-level ``data/`` directory is *not* sufficient — many
    project repos have one, and accepting it would let ``memoir status``
    (or any other read-side caller) lazy-materialize a fresh prolly tree
    inside an unrelated project's working copy.
    """
    path = Path(store_path)
    return (
        (path / ".git" / "memoir-backend").exists()
        or (path / ".git" / "prolly").exists()
        or (path / "data" / "prolly_config_tree_config").exists()
    )


def _detect_legacy_backend(store_path: Path) -> StorageBackend | None:
    """Infer the backend of an existing store that has no lock file.

    Returns ``None`` if ``store_path`` doesn't look like an existing memoir
    store, so the caller falls through to the env var / default for
    brand-new stores. Recognition requires a prollytree-specific marker
    (``data/prolly_config_tree_config`` or ``.git/prolly/``) — a plain
    ``data/`` directory in a random project repo is *not* enough.
    """
    if not (store_path / ".git").exists():
        return None
    has_prolly_config = (store_path / "data" / "prolly_config_tree_config").exists()
    has_prolly_dir = (store_path / ".git" / "prolly").exists()
    if not (has_prolly_config or has_prolly_dir):
        return None
    if (store_path / ".git" / "prolly" / "nodes" / "files").exists():
        return StorageBackend.File
    return StorageBackend.Git


def resolve_backend(store_path: Path | str | None = None) -> StorageBackend:
    """Resolve the storage backend for a memoir store.

    Args:
        store_path: Path to a memoir store. If omitted, only the env var
            and default are consulted (useful at create time before the
            directory exists).

    Returns:
        The chosen ``StorageBackend``.

    Raises:
        ValueError: a per-store lock or env var holds an unrecognized
            backend name.
    """
    if store_path is not None:
        path = Path(store_path)
        from_lock = _read_lock(path)
        if from_lock is not None:
            return from_lock
        from_disk = _detect_legacy_backend(path)
        if from_disk is not None:
            return from_disk

    env_value = os.environ.get(_ENV_VAR, "")
    if env_value.strip():
        return _parse_name(env_value, _ENV_VAR)

    return StorageBackend.File


def write_backend_lock(store_path: Path | str, backend: StorageBackend) -> None:
    """Persist the chosen backend at ``<store>/.git/memoir-backend``.

    The lock is the authoritative record of an existing store's backend;
    ``resolve_backend`` reads it on every open. Written once at store
    creation. A store's backend never changes after creation.

    Raises ``ValueError`` if ``backend`` is ``InMemory``: persisting a
    volatile backend is incoherent (the next reopen would see an empty
    store), so we refuse to lock a store to it.
    """
    if backend == StorageBackend.InMemory:
        raise ValueError(
            "Cannot lock a store to the InMemory backend: it is volatile "
            "and would lose all data across reopen."
        )
    name = _backend_to_name(backend)
    lock = _lock_path(Path(store_path))
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(name + "\n")
    logger.debug("wrote backend lock %s ⇒ %s", lock, name)

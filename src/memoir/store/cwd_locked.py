# SPDX-License-Identifier: Apache-2.0
"""Shared helper: a proxy that chdir's into the store path before any
underlying tree method call.

Workaround for prollytree's Rust binding, which uses cwd (not the absolute
path passed to its constructor) to locate the enclosing git repo on every
operation — not just at construction. Without this wrapper, callers in
non-git cwds hit "Not in a git repository" on `.put()`/`.insert()`/`.commit()`
even when the tree was constructed successfully via the in-init chdir.

Used by both ``ProllyTreeStore`` (the existing VersionedKvStore-backed adapter)
and ``VectorService`` (the new NamespacedKvStore-backed adapter for vector
indexing). Lift to a shared module so neither needs to know about the other.
"""

import os
from pathlib import Path
from typing import Any


class CwdLockedTree:
    """Proxy that chdir's into ``store_path`` before any callable attribute
    access and restores the caller's cwd on the way out.

    Wrapping once at construction is uniformly cheaper than annotating every
    public method that touches the underlying tree (28+ call sites in the
    existing adapter).
    """

    def __init__(self, tree: Any, store_path: Path | str):
        # Underscore prefix on the inner attrs so __getattr__ never recurses
        # into them (it only fires for missing names).
        object.__setattr__(self, "_tree", tree)
        object.__setattr__(self, "_store_path", str(store_path))

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._tree, name)
        if not callable(attr):
            return attr
        store_path = self._store_path

        def _wrapped(*args, **kwargs):
            saved = os.getcwd()
            try:
                os.chdir(store_path)
                return attr(*args, **kwargs)
            finally:
                os.chdir(saved)

        return _wrapped

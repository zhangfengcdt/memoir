# SPDX-License-Identifier: Apache-2.0
"""Watch service: ingest files / folders into memoir.

Provides the pipeline behind ``memoir watch``. For each file:

1. ``markitdown`` extracts plaintext.
2. ``IntelligentClassifier.classify_slices_async`` runs a single LLM call
   that segments the document at semantic boundaries and classifies each
   slice independently. Inputs longer than ``summarize_max_chars`` are
   windowed and re-stitched into global offsets.
3. Each slice is stored as its own memoir memory under its classified
   taxonomy path (via ``MemoryService.remember``) and vector-indexed
   independently (via ``VectorService``), so semantic search returns
   slice-level hits rather than whole-file hits. When two slices in the
   same file classify to the same taxonomy path, the second (and later)
   pick up a numeric suffix — ``<path>``, ``<path>.2``, ``<path>.3`` — so
   they don't overwrite each other.

State lives in the ``watch`` namespace alongside the indexed file content:

- ``watch:config`` — config dict (max size, slice window cap, embedder name)
- ``watch:paths``  — registry of watched paths
- ``watch:files``  — per-file state (content hash, slice memory keys, mtime, ...)
                     kept as a single dict; read once per scan,
                     mutated in memory, written once at end.
"""

import contextlib
import hashlib
import logging
import os
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memoir.classifier.intelligent import SliceClassification
from memoir.services.base import BaseService, ServiceError, StoreNotFoundError
from memoir.services.memory_service import MemoryService
from memoir.services.models import (
    WatchAddResult,
    WatchEntry,
    WatchFileEntry,
    WatchFilesResult,
    WatchListResult,
    WatchRemoveResult,
    WatchScanResult,
    WatchStatusResult,
)
from memoir.services.vector_service import VectorService

logger = logging.getLogger(__name__)


DEFAULT_CONFIG = {
    "max_size_mb": 100,
    # ``summarize_max_chars`` is the slice-classification window. The LLM
    # classifies the whole document in one call when it fits; for longer
    # inputs the watch pipeline windows the text into non-overlapping
    # chunks of this size, classifies each window, then re-stitches the
    # slice offsets back into global file coordinates.
    "summarize_max_chars": 100_000,
    # Cap how many files a single ``scan`` will index (new or changed).
    # Unchanged files (hash match) don't count — they're cheap. When the
    # cap is hit the scan prints a warning naming the remaining count so
    # the user can re-run; the deletion sweep is skipped too (we haven't
    # visited every file, so we can't tell what's truly gone).
    "max_files_per_scan": 100,
    "embedder": "MiniLmEmbedder",
}

# Matched against any path component (so `.git/objects/...` is also filtered).
EXCLUDE_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        ".DS_Store",
        ".idea",
        ".vscode",
    }
)

# Text-based formats only at this stage. Markitdown's registry includes image,
# audio, video, and archive types — we intentionally exclude them: their
# extracted text content is empty (or unreliable OCR) and they don't add
# value to a semantic memory store. Expand here when use cases justify it.
SUPPORTED_EXTENSIONS = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".text",
        ".csv",
        ".docx",
        ".pdf",
    }
)


_WATCH_NS: tuple[str, ...] = ("watch",)
_CONFIG_KEY = "config"
_PATHS_KEY = "paths"
_FILES_KEY = "files"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sanitize_path_component(s: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", s)
    return cleaned or "untitled"


def _abs_path_hash(p: Path) -> str:
    return hashlib.sha256(str(p).encode("utf-8")).hexdigest()


def _content_hash(data: bytes) -> str:
    # Algorithm prefix means swapping blake3/sha256 forces a re-index since
    # comparison includes it.
    try:
        import blake3

        return f"blake3:{blake3.blake3(data).hexdigest()}"
    except ImportError:
        return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _is_excluded(p: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in p.parts)


@contextlib.contextmanager
def _maybe_suppress_native_stderr():
    """FD-level stderr redirect around blocks that trigger native lib loads
    (markitdown → magika → onnxruntime), so the onnxruntime GPU-probe
    warning emitted by native code via ``fprintf(stderr)`` doesn't escape.

    Active only when ``_MEMOIR_SUPPRESS_NATIVE_IMPORT_STDERR=1`` (set by
    the CLI entry point). Library callers get a pass-through.
    """
    if os.environ.get("_MEMOIR_SUPPRESS_NATIVE_IMPORT_STDERR") != "1":
        yield
        return
    saved_fd = os.dup(2)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, 2)
        yield
    finally:
        os.dup2(saved_fd, 2)
        os.close(devnull_fd)
        os.close(saved_fd)


_MARKITDOWN_CLS = None


def _load_markitdown():
    """Import and return ``markitdown.MarkItDown``. Cached."""
    global _MARKITDOWN_CLS
    if _MARKITDOWN_CLS is not None:
        return _MARKITDOWN_CLS
    with _maybe_suppress_native_stderr():
        from markitdown import MarkItDown as _MD
    _MARKITDOWN_CLS = _MD
    return _MARKITDOWN_CLS


def supported_extensions() -> set[str]:
    """File extensions the watch pipeline can ingest. Text-based formats
    only (see ``SUPPORTED_EXTENSIONS``)."""
    return set(SUPPORTED_EXTENSIONS)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class WatchService(BaseService):
    """Orchestrates the per-scan pipeline. Owns ``watch:{config,paths,files}`` reads/writes.

    Heavy collaborators (markitdown, MemoryService, VectorService,
    IntelligentClassifier) are lazy-initialized so commands that don't touch
    the pipeline (e.g. ``watch list``) stay cheap.
    """

    def __init__(
        self,
        store_path: str,
        llm_model: str | None = None,
        progress: Callable[[str], None] | None = None,
        verbose: bool = False,
    ):
        super().__init__(store_path)
        self.llm_model = llm_model
        self._memory_service: MemoryService | None = None
        self._vector_service: VectorService | None = None
        self._classifier = None
        # Test seam: returns an object with ``.convert(path).text_content``.
        self._markitdown_factory: Callable[[], Any] | None = None
        self._progress = progress or (lambda _msg: None)
        self._verbose = verbose

    def _vprogress(self, msg: str) -> None:
        """Emit a sub-step message only in verbose mode."""
        if self._verbose:
            self._progress(msg)

    def _get_memory_service(self) -> MemoryService:
        if self._memory_service is None:
            self._memory_service = MemoryService(
                self.store_path, llm_model=self.llm_model
            )
            # Share the store handle so per-file writes don't reopen the tree.
            self._memory_service._store = self._get_store()
        return self._memory_service

    def _get_vector_service(self) -> VectorService:
        if self._vector_service is None:
            self._vector_service = VectorService(self.store_path)
        return self._vector_service

    def _get_classifier(self):
        # Reuse MemoryService's wiring so the watch classifier and
        # `memoir remember` see the same taxonomy.
        if self._classifier is None:
            self._classifier = self._get_memory_service()._get_classifier()
        return self._classifier

    def _read_meta(self, key: str) -> Any:
        try:
            return self._get_store().get(_WATCH_NS, key)
        except Exception as e:
            logger.debug("read watch:%s failed (%s); treating as missing", key, e)
            return None

    def _write_meta(self, key: str, value: Any) -> None:
        self._get_store().put(_WATCH_NS, key, value)

    def _read_config(self) -> dict:
        existing = self._read_meta(_CONFIG_KEY)
        if isinstance(existing, dict):
            # Merge so user-set keys aren't clobbered by defaults.
            merged = dict(DEFAULT_CONFIG)
            merged.update(existing)
            return merged
        self._write_meta(_CONFIG_KEY, dict(DEFAULT_CONFIG))
        return dict(DEFAULT_CONFIG)

    def _read_paths(self) -> list[dict]:
        existing = self._read_meta(_PATHS_KEY)
        if isinstance(existing, dict) and isinstance(existing.get("paths"), list):
            return list(existing["paths"])
        return []

    def _write_paths(self, paths: list[dict]) -> None:
        self._write_meta(_PATHS_KEY, {"paths": paths})

    def _read_files(self) -> dict:
        existing = self._read_meta(_FILES_KEY)
        if isinstance(existing, dict):
            return existing
        return {}

    def _write_files(self, files: dict) -> None:
        self._write_meta(_FILES_KEY, files)

    async def add(
        self,
        path: str,
        namespace: str = "watch",
    ) -> WatchAddResult:
        """Register a single file and run the initial scan.

        Folders are rejected — only single-file watches are supported.
        """
        abs_path = Path(path).expanduser().resolve()
        if not abs_path.exists():
            return WatchAddResult(
                success=False,
                path=str(abs_path),
                error=f"Path does not exist: {abs_path}",
            )

        if abs_path.is_dir():
            return WatchAddResult(
                success=False,
                path=str(abs_path),
                error=(
                    f"Folders are not supported: {abs_path}. "
                    f"Run `memoir watch add` on each file individually."
                ),
            )

        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        # `already_registered` flag for the caller — checked BEFORE the scan
        # so `add()`'s contract ("returns whether this path was already
        # watched") still holds. The actual write of the path entry is
        # batched inside ``_scan_path`` so it lands in the same data commit
        # as the slice writes (one commit per file, not three).
        paths = self._read_paths()
        already = any(p.get("path") == str(abs_path) for p in paths)

        scan = await self._scan_path(abs_path, namespace=namespace)

        return WatchAddResult(
            success=scan.success,
            path=str(abs_path),
            scan=scan,
            already_registered=already,
            error=scan.error,
        )

    async def scan(
        self,
        path: str | None = None,
        namespace: str | None = None,
    ) -> list[WatchScanResult]:
        """Re-scan a previously registered path (or all of them if ``path``
        is None)."""
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        registered = self._read_paths()
        if path is None:
            targets = list(registered)
        else:
            abs_target_path = Path(path).expanduser().resolve()
            abs_target = str(abs_target_path)
            if abs_target_path.is_dir():
                return [
                    WatchScanResult(
                        success=False,
                        path=abs_target,
                        error=(
                            f"Folders are not supported: {abs_target}. "
                            f"Run `memoir watch scan` on each file individually."
                        ),
                    )
                ]
            targets = [p for p in registered if p.get("path") == abs_target]
            if not targets:
                return [
                    WatchScanResult(
                        success=False,
                        path=abs_target,
                        error=(
                            f"Path is not registered: {abs_target}. "
                            f"Run `memoir watch add {abs_target}` first."
                        ),
                    )
                ]

        results: list[WatchScanResult] = []
        for entry in targets:
            ns = namespace or entry.get("namespace", "watch")
            res = await self._scan_path(Path(entry["path"]), namespace=ns)
            results.append(res)
            # last_scan update is batched inside _scan_path itself so it
            # lands in the same commit as the slice writes.
            if res.aborted:
                raise KeyboardInterrupt
        return results

    def list(self) -> WatchListResult:
        """Show all registered paths + a per-path file count."""
        entries: list[WatchEntry] = []
        try:
            files = self._read_files()
            count_by_root: dict[str, int] = {}
            for state in files.values():
                root = state.get("watched_path")
                if isinstance(root, str):
                    count_by_root[root] = count_by_root.get(root, 0) + 1

            for entry in self._read_paths():
                entries.append(
                    WatchEntry(
                        path=entry.get("path", ""),
                        kind=entry.get("kind", "folder"),
                        namespace=entry.get("namespace", "watch"),
                        added_at=entry.get("added_at", ""),
                        last_scan=entry.get("last_scan"),
                        indexed_count=count_by_root.get(entry.get("path", ""), 0),
                    )
                )
        except Exception as e:
            return WatchListResult(success=False, error=str(e))
        return WatchListResult(success=True, entries=entries)

    def files(self, path: str) -> WatchFilesResult:
        """List every indexed file under ``path`` (the watched root).

        Unlike ``status()`` which caps at the 20 most-recent, this returns
        every file the watch service has on record for the root.
        """
        abs_target = str(Path(path).expanduser().resolve())
        try:
            files_state = self._read_files()
            entries: list[WatchFileEntry] = []
            for state in files_state.values():
                if state.get("watched_path") != abs_target:
                    continue
                chash = state.get("content_hash") or ""
                entries.append(
                    WatchFileEntry(
                        abs_path=state.get("abs_path", ""),
                        size=int(state.get("size") or 0),
                        indexed_at=state.get("indexed_at", ""),
                        mtime=state.get("mtime"),
                        summary_chars=int(state.get("summary_chars") or 0),
                        content_hash=chash[:12] if isinstance(chash, str) else "",
                    )
                )
            entries.sort(key=lambda e: e.abs_path)
            return WatchFilesResult(
                success=True, watched_path=abs_target, files=entries
            )
        except Exception as e:
            return WatchFilesResult(
                success=False, watched_path=abs_target, error=str(e)
            )

    def status(self, path: str) -> WatchStatusResult:
        """Per-path status. Includes recently-changed files (up to 20)."""
        abs_target = str(Path(path).expanduser().resolve())
        try:
            entry = next(
                (p for p in self._read_paths() if p.get("path") == abs_target), None
            )
            if entry is None:
                return WatchStatusResult(
                    success=False,
                    path=abs_target,
                    error=f"Path is not registered: {abs_target}",
                )
            files = self._read_files()
            states = [s for s in files.values() if s.get("watched_path") == abs_target]
            states.sort(key=lambda s: s.get("indexed_at", ""), reverse=True)
            recent = [s.get("abs_path", "") for s in states[:20]]
            return WatchStatusResult(
                success=True,
                path=abs_target,
                kind=entry.get("kind"),
                namespace=entry.get("namespace"),
                added_at=entry.get("added_at"),
                last_scan=entry.get("last_scan"),
                files_indexed=len(states),
                recently_changed=recent,
            )
        except Exception as e:
            return WatchStatusResult(success=False, path=abs_target, error=str(e))

    def remove(self, path: str, purge: bool = False) -> WatchRemoveResult:
        """Unregister a watched path. With ``purge=True``, also deletes every
        memory + vector-index entry that came from this path."""
        abs_target = str(Path(path).expanduser().resolve())
        try:
            paths = self._read_paths()
            remaining = [p for p in paths if p.get("path") != abs_target]
            if len(remaining) == len(paths):
                return WatchRemoveResult(
                    success=False,
                    path=abs_target,
                    purge=purge,
                    error=f"Path is not registered: {abs_target}",
                )

            files_removed = 0
            files = self._read_files()
            if purge:
                store = self._get_store()
                vector = (
                    self._get_vector_service()
                    if VectorService.feature_available()
                    else None
                )
                surviving_files = {}
                for path_hash, state in files.items():
                    if state.get("watched_path") != abs_target:
                        surviving_files[path_hash] = state
                        continue
                    ns_tuple = self.namespace_to_tuple(state.get("namespace", "watch"))
                    memory_keys = state.get("memory_keys") or []
                    for k in memory_keys:
                        try:
                            store.delete(ns_tuple, k)
                        except Exception as e:
                            logger.warning(
                                "purge: delete %s/%s failed: %s", ns_tuple, k, e
                            )
                    if vector and memory_keys:
                        # Only the primary path is indexed; siblings share the
                        # same vector via related_keys.
                        try:
                            vector.delete(
                                state.get("namespace", "watch"),
                                memory_keys[0].encode("utf-8"),
                            )
                        except Exception as e:
                            logger.warning("purge: vector delete failed: %s", e)
                    files_removed += 1
                self._write_files(surviving_files)
                if vector:
                    try:
                        vector.commit(f"watch purge {abs_target}")
                    except Exception as e:
                        logger.warning("purge: vector commit failed: %s", e)
            # Soft remove (purge=False) just drops the registry entry; file
            # state under watch:files stays so future re-adds are idempotent.

            self._write_paths(remaining)
            with contextlib.suppress(Exception):
                self._get_store().commit(f"watch remove {abs_target}")

            return WatchRemoveResult(
                success=True, path=abs_target, files_removed=files_removed, purge=purge
            )
        except Exception as e:
            return WatchRemoveResult(
                success=False, path=abs_target, purge=purge, error=str(e)
            )

    async def _scan_path(
        self,
        target: Path,
        namespace: str,
    ) -> WatchScanResult:
        """Walk a target, index changed files, return aggregated stats."""
        start = time.time()

        config = self._read_config()
        max_bytes = int(config.get("max_size_mb", 100)) * 1024 * 1024
        summarize_max = int(config.get("summarize_max_chars", 100_000))
        max_files_per_scan = int(config.get("max_files_per_scan", 100))

        # Embedder identity guard: prollytree rejects reopen with a different
        # embedder than the one persisted at first open.
        if (
            VectorService.feature_available()
            and os.environ.get("MEMOIR_TEST_USE_HASH_EMBEDDER") != "1"
            and config.get("embedder")
            and config.get("embedder") != "MiniLmEmbedder"
        ):
            return WatchScanResult(
                success=False,
                path=str(target),
                namespace=namespace,
                error=(
                    f"watch:config.embedder is set to "
                    f"{config.get('embedder')!r}, but this build only supports "
                    f"MiniLmEmbedder. Reset it with "
                    f"`memoir forget config -n watch --force` (the next scan "
                    f"will regenerate the config with the default embedder)."
                ),
            )

        if target.is_file():
            candidates: list[Path] = [target]
        else:
            candidates = [
                p for p in target.rglob("*") if p.is_file() and not _is_excluded(p)
            ]

        exts = supported_extensions()
        files_seen = len(candidates)
        candidates = [p for p in candidates if p.suffix.lower() in exts]
        skipped_unsupported = files_seen - len(candidates)

        stats = {
            "files_indexed": 0,
            "files_unchanged": 0,
            "files_deleted": 0,
            "files_skipped_size": 0,
            "files_skipped_parse_error": 0,
            "index_failures": 0,
            "slices_indexed": 0,
        }

        files_state = self._read_files()
        store = self._get_store()
        memory_service = self._get_memory_service()
        vector = (
            self._get_vector_service() if VectorService.feature_available() else None
        )

        # Track every path-hash we visit so we can detect files that were
        # indexed in a previous scan but no longer exist on disk.
        seen_path_keys: set[str] = set()
        target_str = str(target)

        total = len(candidates)
        # Track whether we processed every candidate. If the per-scan cap
        # cuts the loop short, we skip the deletion sweep — incomplete
        # seen_path_keys would otherwise mis-classify unvisited files as
        # deletions and tear them down.
        scan_complete = True
        remaining_after_cap = 0
        aborted = False
        # Batch all per-slice and metadata writes into a single commit at
        # end of scan. Without this, ``ProllyTreeStore.put`` auto-commits
        # on every key — a 10-slice file would otherwise land ~12+ commits
        # in git log (one per slice + metadata + deletion-sweep + ...).
        # The vector tree is already batched via vector.commit() below;
        # this brings the data tree to the same cadence.
        saved_auto_commit = getattr(store, "auto_commit", True)
        store.auto_commit = False
        try:
            for idx, p in enumerate(candidates, start=1):
                # Cap fires BEFORE this file would be processed, so the warning
                # at end-of-scan can report the exact remaining count.
                if stats["files_indexed"] >= max_files_per_scan:
                    scan_complete = False
                    # Everything from this point onward — even unchanged files —
                    # is unvisited from the deletion-sweep's perspective.
                    remaining_after_cap = total - idx + 1
                    break
                seen_path_keys.add(_abs_path_hash(p))
                try:
                    size = p.stat().st_size
                except OSError as e:
                    logger.warning("stat failed for %s: %s", p, e)
                    stats["files_skipped_parse_error"] += 1
                    continue
                if size > max_bytes:
                    self._progress(
                        f"[{idx}/{total}] skip (size > {config['max_size_mb']}MB): {p}"
                    )
                    stats["files_skipped_size"] += 1
                    continue

                try:
                    data = p.read_bytes()
                except OSError as e:
                    logger.warning("read failed for %s: %s", p, e)
                    stats["files_skipped_parse_error"] += 1
                    continue

                chash = _content_hash(data)
                path_key = _abs_path_hash(p)
                prev = files_state.get(path_key)
                if isinstance(prev, dict) and prev.get("content_hash") == chash:
                    self._progress(f"[{idx}/{total}] unchanged: {p}")
                    stats["files_unchanged"] += 1
                    continue

                self._vprogress(f"[{idx}/{total}] processing: {p}")

                text = self._extract_text(p)
                if text is None:
                    self._progress(f"[{idx}/{total}] parse error: {p}")
                    stats["files_skipped_parse_error"] += 1
                    continue
                self._vprogress(f"  → extract: markitdown produced {len(text):,} chars")

                model_label = self.llm_model or "default model"
                self._vprogress(
                    f"  → slice+classify: 1 LLM call ({model_label}) on "
                    f"{len(text):,} chars (window cap {summarize_max:,})"
                )

                try:
                    classifier = self._get_classifier()
                    slices = await classifier.classify_slices_async(
                        text, window_chars=summarize_max
                    )
                except Exception as e:
                    logger.warning("slice+classify failed for %s: %s", p, e)
                    stats["files_skipped_parse_error"] += 1
                    continue

                if not slices:
                    # LLM produced no usable slices — fall back to a single
                    # whole-file slice classified to a synthetic path. Keeps
                    # the file searchable rather than silently dropping it.
                    fallback_path = "knowledge.files." + _sanitize_path_component(
                        p.stem
                    )
                    slices = [
                        SliceClassification(
                            start=0,
                            end=len(text),
                            paths=[fallback_path],
                            confidence=0.3,
                            reasoning="slice classifier returned no slices; fallback",
                        )
                    ]
                    self._vprogress(
                        f"  → fallback: 1 slice under {fallback_path} (no LLM slices)"
                    )

                # Tear down the file's previous slice keys before re-indexing.
                # The collision-suffix scheme is per-file so a re-scan that
                # produces different paths or counts would otherwise leave
                # orphan memories.
                prev_keys = list((prev or {}).get("memory_keys") or [])
                if prev_keys:
                    prev_ns_tuple = self.namespace_to_tuple(
                        (prev or {}).get("namespace", namespace)
                    )
                    for k in prev_keys:
                        with contextlib.suppress(Exception):
                            store.delete(prev_ns_tuple, k)
                    if vector is not None:
                        for k in prev_keys:
                            with contextlib.suppress(Exception):
                                vector.delete(namespace, k.encode("utf-8"))

                source_meta_base = {
                    "kind": "watch",
                    "abs_path": str(p),
                    "content_hash": chash,
                    "extracted_text_chars": len(text),
                    "slice_count": len(slices),
                }
                new_keys: list[str] = []
                slice_summary: list[str] = []
                file_index_failures = 0
                # Per-file collision counter: first slice at a given taxonomy
                # path uses the bare path as its key; subsequent slices that
                # also classify to that path get a numeric suffix (`.2`, `.3`).
                # Most files end up with clean unsuffixed keys; only genuine
                # repeated classifications within one file pick up the suffix.
                # Inlined below rather than wrapped in a closure to satisfy
                # ruff's B023 (closure-over-loop-variable) — the dict lives
                # inside this for-iter so a closure would technically be
                # late-bound to whichever ``path_usage`` exists at call time.
                path_usage: dict[str, int] = {}

                # Each slice is stored under both its classified taxonomy
                # path(s) AND a per-file ``raw.<filename>.sNNN`` key — the
                # raw key gives a stable filename-based lookup independent
                # of how the LLM classified the content. Both keys hold the
                # same slice text.
                file_token = _sanitize_path_component(p.name)

                for s_idx, sl in enumerate(slices):
                    slice_text = text[sl.start : sl.end]
                    if not slice_text.strip():
                        continue
                    primary = sl.paths[0]
                    classified_paths: list[str] = []
                    for pp in sl.paths:
                        n = path_usage.get(pp, 0) + 1
                        path_usage[pp] = n
                        classified_paths.append(pp if n == 1 else f"{pp}.{n}")
                    raw_key = f"raw.{file_token}.s{s_idx + 1:03d}"
                    # Same content is written under classified + raw keys.
                    # MemoryService.remember(paths=[...]) records each as a
                    # sibling of the others via ``related_keys``, so the UI
                    # can navigate raw ↔ classified for any slice.
                    all_keys = [*classified_paths, raw_key]
                    primary_key = classified_paths[0]

                    self._vprogress(
                        f"  → slice {s_idx}: chars [{sl.start},{sl.end}) → "
                        f"{all_keys} conf={sl.confidence:.2f}"
                    )

                    try:
                        await memory_service.remember(
                            content=slice_text,
                            paths=all_keys,
                            namespace=namespace,
                            replace=True,
                            extra_metadata={
                                "source": {
                                    **source_meta_base,
                                    "slice_index": s_idx,
                                    "slice_start": sl.start,
                                    "slice_end": sl.end,
                                    "slice_primary_path": primary,
                                    "raw_key": raw_key,
                                }
                            },
                        )
                    except Exception as e:
                        logger.warning(
                            "remember failed for %s slice %d: %s", p, s_idx, e
                        )
                        continue
                    new_keys.extend(all_keys)

                    # Vector index — one doc per slice, best-effort.
                    if vector is not None:
                        try:
                            vector.index(
                                namespace, primary_key.encode("utf-8"), slice_text
                            )
                        except Exception as e:
                            logger.warning(
                                "vector index failed for %s slice %d: %s",
                                p,
                                s_idx,
                                e,
                            )
                            file_index_failures += 1
                    slice_summary.append(primary)

                if not new_keys:
                    # Every slice's write failed.
                    stats["files_skipped_parse_error"] += 1
                    continue

                stats["index_failures"] += file_index_failures
                stats["files_indexed"] += 1
                stats["slices_indexed"] += len(slice_summary)
                files_state[path_key] = {
                    "abs_path": str(p),
                    "watched_path": str(target),
                    "namespace": namespace,
                    "memory_keys": new_keys,
                    "content_hash": chash,
                    "size": size,
                    "mtime": p.stat().st_mtime,
                    "indexed_at": _now_iso(),
                    "summary_chars": len(text),
                    "slice_count": len(slice_summary),
                }
                self._progress(
                    f"[{idx}/{total}] indexed: {p} → {len(slice_summary)} slice(s) "
                    f"(paths: {', '.join(slice_summary[:5])}"
                    + (", ..." if len(slice_summary) > 5 else "")
                    + ")"
                )
        except KeyboardInterrupt:
            aborted = True
            scan_complete = False
            self._progress(
                f"⚠ scan interrupted: indexed {stats['files_indexed']} file(s) "
                f"so far — saving progress. Re-run `memoir watch scan` to continue."
            )

        # Detect deletions: entries whose watched_path matches this target
        # but whose path-hash wasn't seen on disk this scan. We additionally
        # confirm the file is genuinely missing (not just filtered out by
        # exclude/extension/oversize rules) before tearing down the entry.
        # Skipped when the per-scan cap fired or the scan was interrupted —
        # seen_path_keys is partial, so any unvisited file would be wrongly
        # treated as deleted.
        if scan_complete:
            for path_key, state in list(files_state.items()):
                if state.get("watched_path") != target_str:
                    continue
                if path_key in seen_path_keys:
                    continue
                abs_path_str = state.get("abs_path", "")
                if abs_path_str and Path(abs_path_str).exists():
                    continue
                ns = state.get("namespace", "watch")
                ns_tuple = self.namespace_to_tuple(ns)
                for k in state.get("memory_keys") or []:
                    try:
                        store.delete(ns_tuple, k)
                    except Exception as e:
                        logger.warning("scan: delete %s/%s failed: %s", ns_tuple, k, e)
                if vector and (state.get("memory_keys") or []):
                    with contextlib.suppress(Exception):
                        vector.delete(ns, state["memory_keys"][0].encode("utf-8"))
                files_state.pop(path_key, None)
                stats["files_deleted"] += 1
                self._progress(f"deleted: {abs_path_str}")

        if not scan_complete and not aborted:
            self._progress(
                f"⚠ scan cap reached: indexed {stats['files_indexed']} files "
                f"(max_files_per_scan={max_files_per_scan}); "
                f"{remaining_after_cap} file(s) remain — re-run `memoir watch scan` "
                f"to continue. Deletion detection skipped on this partial scan."
            )

        # Always flush files_state so progress from a partial/interrupted scan
        # is not lost on the next run. With auto_commit disabled this is just
        # a buffered put — the explicit commit below flushes everything.
        self._write_files(files_state)

        # Register the path entry (first scan) or refresh its last_scan
        # (re-scan). Both code paths buffer through the same commit batch
        # below so we don't pay a separate commit for path bookkeeping.
        paths_meta = self._read_paths()
        entry = next((p for p in paths_meta if p.get("path") == target_str), None)
        if entry is None:
            paths_meta.append(
                {
                    "path": target_str,
                    "kind": "file",
                    "namespace": namespace,
                    "added_at": _now_iso(),
                    "last_scan": _now_iso(),
                }
            )
        else:
            entry["last_scan"] = _now_iso()
            entry["namespace"] = namespace
            entry["kind"] = "file"
        self._write_paths(paths_meta)

        # Single batched data-tree commit for the whole scan: slice writes,
        # deletion-sweep deletes, files_state flush, path-registry update —
        # all roll up into one git commit. Restore auto_commit before
        # raising so callers that reuse the service handle aren't left with
        # a half-detached store.
        try:
            commit_msg = (
                f"watch index {target} "
                f"({stats['slices_indexed']} slices "
                f"from {stats['files_indexed']} file(s))"
            )
            store.commit(commit_msg)
        except Exception as e:
            logger.warning("watch: data commit failed: %s", e)
        finally:
            store.auto_commit = saved_auto_commit

        if vector is not None:
            try:
                vector.commit(f"watch index {target}")
            except Exception as e:
                logger.warning("vector commit failed: %s", e)

        commit_hash = self._get_current_commit_info()[0]

        return WatchScanResult(
            success=True,
            path=str(target),
            namespace=namespace,
            files_seen=files_seen,
            files_indexed=stats["files_indexed"],
            slices_indexed=stats["slices_indexed"],
            files_unchanged=stats["files_unchanged"],
            files_deleted=stats["files_deleted"],
            files_skipped_size=stats["files_skipped_size"],
            files_skipped_unsupported=skipped_unsupported,
            files_skipped_parse_error=stats["files_skipped_parse_error"],
            index_failures=stats["index_failures"],
            commit_hash=commit_hash,
            timing_ms=(time.time() - start) * 1000.0,
            aborted=aborted,
        )

    def _extract_text(self, p: Path) -> str | None:
        """markitdown wrapper. Returns ``None`` on any failure."""
        try:
            if self._markitdown_factory is not None:
                md = self._markitdown_factory()
            else:
                MarkItDown = _load_markitdown()
                md = MarkItDown()
            res = md.convert(str(p))
            text = getattr(res, "text_content", None)
            if not isinstance(text, str):
                return None
            return text
        except ImportError:
            raise ServiceError(
                "markitdown is required for `memoir watch`. Install it with "
                "`pip install 'memoir-ai[watch]'`.",
                code=7,
            )
        except Exception as e:
            logger.warning("markitdown.convert failed on %s: %s", p, e)
            return None

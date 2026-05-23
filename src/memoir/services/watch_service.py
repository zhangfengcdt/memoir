# SPDX-License-Identifier: Apache-2.0
"""Watch service: ingest files / folders into memoir.

Provides the pipeline behind ``memoir watch``. For each file:

1. ``markitdown`` extracts plaintext.
2. Docs ≤ ``summarize_max_chars`` pass through verbatim. Larger docs are
   reduced to a deterministic head+tail+titles summary — no LLM.
3. The result is classified by the existing intelligent classifier (one LLM
   call), stored via ``MemoryService.remember`` with ``extra_metadata={"source":
   ...}``, and indexed for vector search via ``VectorService``.

State lives in the ``watch`` namespace alongside the indexed file content:

- ``watch:config`` — config dict (max size, summarize threshold, embedder name)
- ``watch:paths``  — registry of watched paths
- ``watch:files``  — per-file state (content hash, memory keys, mtime, ...)
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
    # Three-tier per-file pipeline:
    #   text ≤ summarize_min_chars (small):    full text → classifier
    #   between min and max     (medium):      LLM-summarize text down to
    #                                          ≤ min chars → classifier
    #   text > summarize_max_chars (long):     deterministic head+tail+titles
    #                                          summary capped at min chars
    #                                          (no LLM for summarize) → classifier
    # Summary outputs are always capped at ``summarize_min_chars`` so the
    # classifier never sees more than that — keeps token costs bounded
    # regardless of input doc size.
    "summarize_min_chars": 1_000,
    "summarize_max_chars": 10_000,
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


def _extract_titles(text: str, max_titles: int = 30) -> list[str]:
    """Pull ``#``-style headings out of markitdown's output."""
    titles: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line.startswith("#"):
            continue
        stripped = line.lstrip("#").strip()
        if stripped and stripped not in seen:
            seen.add(stripped)
            titles.append(stripped)
        if len(titles) >= max_titles:
            break
    return titles


def _deterministic_summary(
    text: str,
    max_summary_chars: int,
    source_name: str | None = None,
    head_chars: int | None = None,
    tail_chars: int | None = None,
) -> str:
    """Build a head + tail + titles summary without calling an LLM.

    Used for long documents so the watch pipeline only spends one LLM call
    (classification) per file. ``max_summary_chars`` caps the output size;
    head + tail are sized to 60/30 of that cap.
    """
    head_chars = head_chars if head_chars is not None else int(max_summary_chars * 0.6)
    tail_chars = tail_chars if tail_chars is not None else int(max_summary_chars * 0.3)

    head = text[:head_chars]
    tail = text[-tail_chars:] if len(text) > head_chars + tail_chars else ""

    titles = _extract_titles(text)

    parts: list[str] = []
    if source_name:
        parts.append(f"# {source_name}")
    if titles:
        parts.append("## Headings")
        parts.extend(f"- {t}" for t in titles)
    parts.append("")
    parts.append("## Beginning")
    parts.append(head.strip())
    if tail:
        parts.append("")
        parts.append("## End")
        parts.append(tail.strip())

    summary = "\n".join(parts)
    if len(summary) > max_summary_chars:
        summary = summary[:max_summary_chars]
    return summary


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
        """Register a file or folder and run the initial scan."""
        abs_path = Path(path).expanduser().resolve()
        if not abs_path.exists():
            return WatchAddResult(
                success=False,
                path=str(abs_path),
                error=f"Path does not exist: {abs_path}",
            )

        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        kind = "folder" if abs_path.is_dir() else "file"
        paths = self._read_paths()
        already = any(p.get("path") == str(abs_path) for p in paths)
        if not already:
            paths.append(
                {
                    "path": str(abs_path),
                    "kind": kind,
                    "namespace": namespace,
                    "added_at": _now_iso(),
                    "last_scan": None,
                }
            )
            self._write_paths(paths)

        scan = await self._scan_path(abs_path, namespace=namespace)
        if scan.success:
            paths = self._read_paths()
            for entry in paths:
                if entry.get("path") == str(abs_path):
                    entry["last_scan"] = _now_iso()
                    entry["namespace"] = namespace
                    entry["kind"] = kind
                    break
            self._write_paths(paths)

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
            abs_target = str(Path(path).expanduser().resolve())
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
            if res.success:
                paths = self._read_paths()
                for p in paths:
                    if p.get("path") == entry["path"]:
                        p["last_scan"] = _now_iso()
                        break
                self._write_paths(paths)
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
        summarize_min = int(config.get("summarize_min_chars", 1_000))
        summarize_max = int(config.get("summarize_max_chars", 10_000))
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
            if len(text) <= summarize_min:
                self._vprogress(
                    f"  → summary: skipped (small doc, {len(text):,} ≤ "
                    f"{summarize_min:,} chars; full text passed to classifier)"
                )
                self._vprogress(f"  → classify: 1 LLM call ({model_label})")
            elif len(text) <= summarize_max:
                self._vprogress(
                    f"  → summary: LLM-summarize "
                    f"(medium doc, {summarize_min:,} < {len(text):,} ≤ "
                    f"{summarize_max:,} chars; target ≤ {summarize_min:,} chars)"
                )
                self._vprogress(
                    f"  → classify: 2 LLM calls ({model_label}; "
                    f"1 summarize + 1 classify)"
                )
            else:
                self._vprogress(
                    f"  → summary: deterministic head+tail+titles "
                    f"(long doc, {len(text):,} > {summarize_max:,} chars; "
                    f"capped at {summarize_min:,} chars; no LLM for summarize)"
                )
                self._vprogress(f"  → classify: 1 LLM call ({model_label})")

            try:
                cls_result, content_to_store = await self._build_content_and_classify(
                    text,
                    summarize_min=summarize_min,
                    summarize_max=summarize_max,
                    p=p,
                )
            except Exception as e:
                logger.warning("classify failed for %s: %s", p, e)
                stats["files_skipped_parse_error"] += 1
                continue

            paths_for_remember = cls_result.paths or (
                [cls_result.path] if cls_result.path else None
            )
            if not paths_for_remember:
                paths_for_remember = [
                    "knowledge.files." + _sanitize_path_component(p.stem)
                ]
            self._vprogress(
                f"  → classify: confidence={cls_result.confidence:.2f}, "
                f"paths={paths_for_remember}"
            )

            source_meta = {
                "kind": "watch",
                "abs_path": str(p),
                "content_hash": chash,
                "extracted_text_chars": len(text),
            }
            self._vprogress(
                f"  → store: writing {len(content_to_store):,} chars to "
                f"{len(paths_for_remember)} memory key(s) (replace=True)"
            )
            try:
                remember_result = await memory_service.remember(
                    content=content_to_store,
                    paths=paths_for_remember,
                    namespace=namespace,
                    replace=True,
                    extra_metadata={"source": source_meta},
                )
            except Exception as e:
                logger.warning("remember failed for %s: %s", p, e)
                stats["files_skipped_parse_error"] += 1
                continue

            # Vector index — best-effort. Data is already committed, so an
            # index failure only means search won't surface this file.
            if vector is not None:
                doc_id = paths_for_remember[0].encode("utf-8")
                try:
                    prev_primary = (
                        (prev or {}).get("memory_keys", [None])[0]
                        if isinstance(prev, dict)
                        else None
                    )
                    if prev_primary and prev_primary != paths_for_remember[0]:
                        # Primary path changed; drop the stale vector.
                        with contextlib.suppress(Exception):
                            vector.delete(namespace, prev_primary.encode("utf-8"))
                    vector.index(namespace, doc_id, content_to_store)
                    self._vprogress(
                        f"  → vector: indexed under {paths_for_remember[0]}"
                    )
                except Exception as e:
                    logger.warning("vector index failed for %s: %s", p, e)
                    stats["index_failures"] += 1
                    self._vprogress(f"  → vector: FAILED ({e})")
            else:
                self._vprogress("  → vector: skipped (proximity_text not available)")

            stats["files_indexed"] += 1
            files_state[path_key] = {
                "abs_path": str(p),
                "watched_path": str(target),
                "namespace": namespace,
                "memory_keys": list(remember_result.keys),
                "content_hash": chash,
                "size": size,
                "mtime": p.stat().st_mtime,
                "indexed_at": _now_iso(),
                "summary_chars": len(content_to_store),
            }
            self._progress(f"[{idx}/{total}] indexed: {p} → {paths_for_remember[0]}")

        # Detect deletions: entries whose watched_path matches this target
        # but whose path-hash wasn't seen on disk this scan. We additionally
        # confirm the file is genuinely missing (not just filtered out by
        # exclude/extension/oversize rules) before tearing down the entry.
        # Skipped when the per-scan cap fired — seen_path_keys is partial,
        # so any unvisited file would be wrongly treated as deleted.
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

        if not scan_complete:
            self._progress(
                f"⚠ scan cap reached: indexed {stats['files_indexed']} files "
                f"(max_files_per_scan={max_files_per_scan}); "
                f"{remaining_after_cap} file(s) remain — re-run `memoir watch scan` "
                f"to continue. Deletion detection skipped on this partial scan."
            )

        self._write_files(files_state)

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
            files_unchanged=stats["files_unchanged"],
            files_deleted=stats["files_deleted"],
            files_skipped_size=stats["files_skipped_size"],
            files_skipped_unsupported=skipped_unsupported,
            files_skipped_parse_error=stats["files_skipped_parse_error"],
            index_failures=stats["index_failures"],
            commit_hash=commit_hash,
            timing_ms=(time.time() - start) * 1000.0,
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

    async def _llm_summarize(self, text: str, max_chars: int) -> str | None:
        """Single LLM call to summarize ``text`` down to ``max_chars``.

        Returns the summary (truncated to ``max_chars`` if the model went
        over) or ``None`` on any error so the caller can fall back to the
        deterministic summary path.
        """
        try:
            llm = self._get_memory_service()._get_llm()
            prompt = (
                f"Summarize the following document in {max_chars} characters or "
                f"fewer. Preserve key topics, named entities, conclusions, and "
                f"any actionable details. Output the summary only — no preamble.\n\n"
                f"{text}"
            )
            response = await llm.ainvoke(prompt)
            summary = (
                response.content if hasattr(response, "content") else str(response)
            )
            if not isinstance(summary, str):
                return None
            if len(summary) > max_chars:
                summary = summary[:max_chars]
            return summary
        except Exception as e:
            logger.warning("LLM summarize failed: %s", e)
            return None

    async def _build_content_and_classify(
        self,
        text: str,
        summarize_min: int,
        summarize_max: int,
        p: Path,
    ):
        """Three-tier pipeline:

        - small (``len(text) <= summarize_min``): full text → classifier
          (1 LLM call).
        - medium (``summarize_min < len(text) <= summarize_max``):
          LLM-summarize down to ``summarize_min`` chars → classifier
          (2 LLM calls). Falls back to the deterministic summary if the
          LLM summarize call fails.
        - long (``len(text) > summarize_max``): deterministic head+tail+titles
          summary capped at ``summarize_min`` chars → classifier
          (1 LLM call).

        Returns ``(ClassificationResult, content_to_store)`` — ``content_to_store``
        is what gets persisted as the memoir memory and indexed for search.
        """
        classifier = self._get_classifier()
        if len(text) <= summarize_min:
            cls = await classifier.classify_input(text)
            return cls, text
        if len(text) <= summarize_max:
            summary = await self._llm_summarize(text, max_chars=summarize_min)
            if summary is None:
                # LLM unavailable / failed — degrade to deterministic so the
                # scan still makes progress.
                summary = _deterministic_summary(
                    text, max_summary_chars=summarize_min, source_name=p.name
                )
        else:
            summary = _deterministic_summary(
                text, max_summary_chars=summarize_min, source_name=p.name
            )
        cls = await classifier.classify_input(summary)
        return cls, summary

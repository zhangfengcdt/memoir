# SPDX-License-Identifier: Apache-2.0
"""Watch service: ingest files / folders into memoir.

Provides the pipeline behind ``memoir watch``. For each file:

1. ``markitdown`` extracts plaintext.
2. Short docs (``len(text) <= summarize_min_chars``) are passed through verbatim.
   Long docs are reduced to a deterministic head+tail+titles summary — no LLM.
3. The result is classified by the existing intelligent classifier (one LLM
   call), stored via ``MemoryService.remember`` with ``extra_metadata={"source":
   ...}``, and indexed for vector search via ``VectorService``.

State lives in the ``_meta`` namespace alongside ``_meta.last_onboard.*``:

- ``_meta.watch.config`` — config dict (max size, summarize threshold, embedder name)
- ``_meta.watch.paths``  — registry of watched paths
- ``_meta.watch.files``  — per-file state (content hash, memory keys, mtime, ...)
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
    WatchListResult,
    WatchRemoveResult,
    WatchScanResult,
    WatchStatusResult,
)
from memoir.services.vector_service import VectorService, versioned_config_preserved

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config + constants
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "max_size_mb": 100,
    "summarize_min_chars": 10_000,
    "embedder": "MiniLmEmbedder",
}

# Directories never walked into. Matched against any path component, so
# ``/repo/.git/objects/...`` is filtered the same way ``/.git/...`` is.
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

# Hardcoded markitdown-supported extension fallback. Mirrors the
# ``ACCEPTED_FILE_EXTENSIONS`` declared in markitdown's per-converter modules
# (csv, docx, epub, html, ipynb, msg, pdf, pptx, txt, markdown, json, ...).
# Image and audio formats are intentionally excluded — markitdown supports
# them but typically returns empty / OCR-only text and they balloon the LLM
# bill for low signal.
SUPPORTED_EXTENSIONS = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".text",
        ".pdf",
        ".docx",
        ".pptx",
        ".xlsx",
        ".html",
        ".htm",
        ".csv",
        ".epub",
        ".ipynb",
        ".json",
        ".jsonl",
        ".msg",
    }
)


# Reserved per-file path-state keys live under the namespace tuple ``("_meta",)``
# with these scalar string keys (mirrors the ``_meta.last_onboard.*`` style).
_META_NS: tuple[str, ...] = ("_meta",)
_META_CONFIG_KEY = "watch.config"
_META_PATHS_KEY = "watch.paths"
_META_FILES_KEY = "watch.files"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sanitize_path_component(s: str) -> str:
    """Make a file basename safe to embed in a taxonomy path."""
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", s)
    return cleaned or "untitled"


def _abs_path_hash(p: Path) -> str:
    """Stable hash of an absolute path string — used as the key in
    ``_meta.watch.files``. SHA-256 hex digest."""
    return hashlib.sha256(str(p).encode("utf-8")).hexdigest()


def _content_hash(data: bytes) -> str:
    """Hash file bytes. Prefers blake3 (faster) but falls back to sha256.
    The result is prefixed with the algorithm name so a swap re-triggers
    indexing on next scan (the comparison string includes the prefix)."""
    try:
        import blake3

        return f"blake3:{blake3.blake3(data).hexdigest()}"
    except ImportError:
        return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _is_excluded(p: Path) -> bool:
    """True if any path component is in EXCLUDE_DIRS."""
    return any(part in EXCLUDE_DIRS for part in p.parts)


def _extract_titles(text: str, max_titles: int = 30) -> list[str]:
    """Pull ``#``-style headings from markitdown's output.

    markitdown emits markdown for the formats it understands (PDFs, docx,
    pptx, html), so leading-``#`` runs are the reliable signal. Plaintext
    sources without explicit headings simply yield nothing — the head/tail
    of the document still carry the topic.
    """
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
    threshold: int,
    source_name: str | None = None,
    head_chars: int | None = None,
    tail_chars: int | None = None,
    max_summary_chars: int | None = None,
) -> str:
    """Build a deterministic head+tail+titles summary, no LLM.

    Used when ``len(text) > summarize_min_chars`` so the watch pipeline can
    keep the LLM call count to one (classification only). The summary is the
    content actually stored in memoir and the input handed to the classifier
    — so it should preserve enough surface-form signal that classification
    quality doesn't fall off a cliff.

    Layout (Markdown):
        # <source_name>           # only when source_name is provided
        ## Headings               # extracted titles (≤ 30)
        - Heading 1
        - Heading 2

        ## Beginning
        <first head_chars chars of text>

        ## End
        <last tail_chars chars of text>

    Defaults scale with ``threshold``: head = 60% of threshold, tail = 30%,
    leaving slack for headings + structural overhead. Caller can override
    for tests.
    """
    # 60/30/10 split: most of the budget goes to the head (intros tend to
    # set the topic), a third to the tail (conclusions / TOC at-end PDFs),
    # the rest for headings.
    head_chars = head_chars if head_chars is not None else int(threshold * 0.6)
    tail_chars = tail_chars if tail_chars is not None else int(threshold * 0.3)
    max_summary_chars = (
        max_summary_chars if max_summary_chars is not None else threshold
    )

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


def supported_extensions() -> set[str]:
    """Returns the set of file extensions the watch pipeline can ingest.

    Tries to derive the set from the markitdown converter registry at runtime
    so a markitdown upgrade picks up new formats automatically. Falls back to
    the hardcoded ``SUPPORTED_EXTENSIONS`` set if introspection fails (which
    happens with the markitdown 0.1.x line; converters declare a private
    ``accepts(stream)`` method, not an ``accepted_file_extensions`` attribute).
    """
    exts: set[str] = set(SUPPORTED_EXTENSIONS)
    try:
        import importlib
        import pkgutil

        import markitdown.converters as conv_pkg

        for mod_info in pkgutil.iter_modules(conv_pkg.__path__):
            try:
                mod = importlib.import_module(f"markitdown.converters.{mod_info.name}")
            except Exception:
                continue
            for attr in dir(mod):
                if attr == "ACCEPTED_FILE_EXTENSIONS":
                    val = getattr(mod, attr)
                    if isinstance(val, (list, tuple, set)):
                        for e in val:
                            if isinstance(e, str) and e.startswith("."):
                                exts.add(e.lower())
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(
            "supported_extensions: introspection failed (%s); using fallback", e
        )
    return exts


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class WatchService(BaseService):
    """Orchestrates the per-scan pipeline. Owns ``_meta.watch.*`` reads/writes.

    Heavy collaborators (markitdown, MemoryService, VectorService,
    IntelligentClassifier) are lazy-initialized so commands that don't touch
    the pipeline (e.g. ``watch list``) stay cheap.
    """

    def __init__(
        self,
        store_path: str,
        llm_model: str | None = None,
        progress: Callable[[str], None] | None = None,
    ):
        super().__init__(store_path)
        self.llm_model = llm_model
        self._memory_service: MemoryService | None = None
        self._vector_service: VectorService | None = None
        self._classifier = None
        # Test seam: tests inject a stub that mimics
        # ``MarkItDown().convert(path).text_content`` semantics.
        self._markitdown_factory: Callable[[], Any] | None = None
        # Hook for per-file progress output (suppressed under --json).
        self._progress = progress or (lambda _msg: None)

    # ----- lazy collaborators ------------------------------------------------

    def _get_memory_service(self) -> MemoryService:
        if self._memory_service is None:
            self._memory_service = MemoryService(
                self.store_path, llm_model=self.llm_model
            )
            # Share the same store handle so per-file writes don't reopen the
            # tree. Important under auto_commit=False (set during scans).
            self._memory_service._store = self._get_store()
        return self._memory_service

    def _get_vector_service(self) -> VectorService:
        if self._vector_service is None:
            self._vector_service = VectorService(self.store_path)
        return self._vector_service

    def _get_classifier(self):
        if self._classifier is None:
            # Reuse MemoryService's wiring (LLM + taxonomy loader + thresholds)
            # so the watch classifier sees the same paths the user's existing
            # ``memoir remember`` writes do. Pulling the classifier through
            # MemoryService also means tests that swap the classifier on the
            # MemoryService instance flow through to here.
            self._classifier = self._get_memory_service()._get_classifier()
        return self._classifier

    # ----- _meta helpers -----------------------------------------------------

    def _read_meta(self, key: str) -> Any:
        try:
            return self._get_store().get(_META_NS, key)
        except Exception as e:
            logger.debug("read _meta.%s failed (%s); treating as missing", key, e)
            return None

    def _write_meta(self, key: str, value: Any) -> None:
        self._get_store().put(_META_NS, key, value)

    def _read_config(self) -> dict:
        existing = self._read_meta(_META_CONFIG_KEY)
        if isinstance(existing, dict):
            # Fill in any missing keys without clobbering user-set ones.
            merged = dict(DEFAULT_CONFIG)
            merged.update(existing)
            return merged
        # First touch: seed defaults.
        self._write_meta(_META_CONFIG_KEY, dict(DEFAULT_CONFIG))
        return dict(DEFAULT_CONFIG)

    def _read_paths(self) -> list[dict]:
        existing = self._read_meta(_META_PATHS_KEY)
        if isinstance(existing, dict) and isinstance(existing.get("paths"), list):
            return list(existing["paths"])
        return []

    def _write_paths(self, paths: list[dict]) -> None:
        self._write_meta(_META_PATHS_KEY, {"paths": paths})

    def _read_files(self) -> dict:
        existing = self._read_meta(_META_FILES_KEY)
        if isinstance(existing, dict):
            return existing
        return {}

    def _write_files(self, files: dict) -> None:
        self._write_meta(_META_FILES_KEY, files)

    # ----- public commands ---------------------------------------------------

    async def add(
        self,
        path: str,
        namespace: str = "default",
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
        # Stamp last_scan.
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
            ns = namespace or entry.get("namespace", "default")
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
                        namespace=entry.get("namespace", "default"),
                        added_at=entry.get("added_at", ""),
                        last_scan=entry.get("last_scan"),
                        indexed_count=count_by_root.get(entry.get("path", ""), 0),
                    )
                )
        except Exception as e:
            return WatchListResult(success=False, error=str(e))
        return WatchListResult(success=True, entries=entries)

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
                # Wrap all namespace-store operations in the config-preserve
                # context so the data tree's root hash survives the purge.
                with versioned_config_preserved(self.store_path):
                    for path_hash, state in files.items():
                        if state.get("watched_path") != abs_target:
                            surviving_files[path_hash] = state
                            continue
                        # Delete every memory key written for this file plus
                        # the vector-index entry (single doc_id = primary path).
                        ns_tuple = self.namespace_to_tuple(
                            state.get("namespace", "default")
                        )
                        memory_keys = state.get("memory_keys") or []
                        for k in memory_keys:
                            try:
                                store.delete(ns_tuple, k)
                            except Exception as e:
                                logger.warning(
                                    "purge: delete %s/%s failed: %s", ns_tuple, k, e
                                )
                        if vector and memory_keys:
                            try:
                                vector.delete(
                                    state.get("namespace", "default"),
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
            else:
                # Soft remove: just drop the registry entry. File state lives
                # on under _meta.watch.files so future re-adds skip re-indexing.
                pass

            self._write_paths(remaining)
            with contextlib.suppress(Exception):
                # auto_commit may already have handled the commit; tolerate
                # both cases.
                self._get_store().commit(f"watch remove {abs_target}")

            return WatchRemoveResult(
                success=True, path=abs_target, files_removed=files_removed, purge=purge
            )
        except Exception as e:
            return WatchRemoveResult(
                success=False, path=abs_target, purge=purge, error=str(e)
            )

    # ----- scan pipeline -----------------------------------------------------

    async def _scan_path(
        self,
        target: Path,
        namespace: str,
    ) -> WatchScanResult:
        """Walk a target, index changed files, return aggregated stats."""
        start = time.time()

        config = self._read_config()
        max_bytes = int(config.get("max_size_mb", 100)) * 1024 * 1024
        summarize_min = int(config.get("summarize_min_chars", 10_000))

        # Embedder identity guard: refuse cleanly when the stored config
        # references a different embedder than VectorService can produce.
        # In v1 we only ship MiniLmEmbedder; in tests, MEMOIR_TEST_USE_HASH_EMBEDDER
        # swaps in HashEmbedder, in which case we relax the guard.
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
                    f"_meta.watch.config.embedder is set to "
                    f"{config.get('embedder')!r}, but this build only supports "
                    f"MiniLmEmbedder. Either reset it via "
                    f"`memoir put _meta.watch.config ...` or drop the index "
                    f"and re-scan."
                ),
            )

        # Enumerate candidate files.
        if target.is_file():
            candidates: list[Path] = [target]
        else:
            candidates = [
                p for p in target.rglob("*") if p.is_file() and not _is_excluded(p)
            ]

        # Filter by extension.
        exts = supported_extensions()
        files_seen = len(candidates)
        candidates = [p for p in candidates if p.suffix.lower() in exts]
        skipped_unsupported = files_seen - len(candidates)

        # Stat-and-hash pass.
        stats = {
            "files_indexed": 0,
            "files_unchanged": 0,
            "files_skipped_size": 0,
            "files_skipped_parse_error": 0,
            "index_failures": 0,
        }

        files_state = self._read_files()
        # Open the data store BEFORE the namespace store opens during the
        # scan — keeps the in-process VersionedKvStore handle cached so
        # per-file remember() writes work even after the namespace store
        # has touched prolly_config_tree_config.
        self._get_store()
        memory_service = self._get_memory_service()
        vector = (
            self._get_vector_service() if VectorService.feature_available() else None
        )

        total = len(candidates)
        for idx, p in enumerate(candidates, start=1):
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

            # Parse with markitdown.
            text = self._extract_text(p)
            if text is None:
                self._progress(f"[{idx}/{total}] parse error: {p}")
                stats["files_skipped_parse_error"] += 1
                continue

            # Build content + classify. Long documents are reduced to a
            # deterministic head+tail+titles summary (no LLM); only the
            # classifier touches an LLM. Short documents pass through
            # verbatim — content stored is the original text, classified
            # whole.
            try:
                cls_result, content_to_store = await self._build_content_and_classify(
                    text, threshold=summarize_min, p=p
                )
            except Exception as e:
                logger.warning("classify failed for %s: %s", p, e)
                stats["files_skipped_parse_error"] += 1
                continue

            # Persist via MemoryService.
            paths_for_remember = cls_result.paths or (
                [cls_result.path] if cls_result.path else None
            )
            if not paths_for_remember:
                # Classifier returned nothing usable; fall back to a deterministic path.
                paths_for_remember = [
                    "knowledge.files." + _sanitize_path_component(p.stem)
                ]

            source_meta = {
                "kind": "watch",
                "abs_path": str(p),
                "content_hash": chash,
                "extracted_text_chars": len(text),
            }
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

            # Vector index — best-effort. Data is already committed, so a
            # failure here only means search won't surface this file; recall
            # / get still work.
            if vector is not None:
                doc_id = paths_for_remember[0].encode("utf-8")
                try:
                    # Pre-delete prior doc_id when the primary path changed,
                    # so old vectors don't linger.
                    prev_primary = (
                        (prev or {}).get("memory_keys", [None])[0]
                        if isinstance(prev, dict)
                        else None
                    )
                    if prev_primary and prev_primary != paths_for_remember[0]:
                        with contextlib.suppress(Exception):
                            vector.delete(namespace, prev_primary.encode("utf-8"))
                    vector.index(namespace, doc_id, content_to_store)
                except Exception as e:
                    logger.warning("vector index failed for %s: %s", p, e)
                    stats["index_failures"] += 1

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

        # Flush per-file state once.
        self._write_files(files_state)

        # End-of-scan: persist the vector index, but preserve the data
        # tree's root hash in ``data/prolly_config_tree_config``. Both
        # stores share that file; if we let the namespace tree's commit
        # be the last write, the next process's ``VersionedKvStore.open()``
        # silently falls back to an empty tree and every memory we just
        # wrote becomes unreadable. ``versioned_config_preserved`` snapshots
        # the file bytes on entry and writes them back on exit — no extra
        # git commit needed (see vector_service.py for the full rationale).
        if vector is not None:
            with versioned_config_preserved(self.store_path):
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
                from markitdown import MarkItDown

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

    async def _build_content_and_classify(
        self,
        text: str,
        threshold: int,
        p: Path,
    ):
        """Build the content to store and classify it.

        - ``len(text) <= threshold``: send the full raw text to the
          classifier and store it verbatim. One LLM call.
        - ``len(text) > threshold``: build a deterministic summary
          (head + tail + extracted titles/headings) without touching an LLM,
          send the summary to the classifier, store the summary. One LLM
          call.

        Returns ``(ClassificationResult, content_to_store)``.
        """
        classifier = self._get_classifier()
        if len(text) <= threshold:
            cls = await classifier.classify_input(text)
            return cls, text
        summary = _deterministic_summary(text, threshold=threshold, source_name=p.name)
        cls = await classifier.classify_input(summary)
        return cls, summary

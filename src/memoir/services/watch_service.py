# SPDX-License-Identifier: Apache-2.0
"""Watch service: ingest single files into memoir.

Provides the pipeline behind ``memoir watch``. For each file:

1. **Size check.** Reject files larger than ``max_size_bytes`` (default
   100 KB). The whole pipeline is sized for short documents.
2. **Extract.** ``markitdown`` extracts plaintext.
3. **Chunk + summarize.** One LLM call (see ``_chunk_and_summarize_async``)
   asks for a one-paragraph summary plus a list of chunk boundaries
   reported as verbatim anchor strings. The pipeline locates anchors in
   the source text via ``str.find`` to recover real char offsets.
4. **Store.** The summary lands at ``raw.<file>.summary`` and each chunk
   at ``raw.<file>.chunk.NNN``, all under the ``watch`` namespace via
   ``MemoryService.remember``.
5. **Vector index.** Every memory key (summary + chunks) is vector-indexed
   so semantic search returns chunk-level hits.

State lives in the ``watch`` namespace alongside the indexed file content:

- ``watch:config`` — config dict (max size, embedder name)
- ``watch:paths``  — registry of watched paths
- ``watch:files``  — per-file state (content hash, chunk memory keys, mtime, ...)
                     kept as a single dict; read once per scan,
                     mutated in memory, written once at end.
"""

import contextlib
import hashlib
import json
import logging
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
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
    # Hard reject above this size on disk. The chunk+summarize pipeline is
    # built for short documents — bigger files would also push the LLM call
    # toward output-token limits and slow re-scans considerably.
    "max_size_bytes": 100_000,
    # Cap how many files a single ``scan`` will index (new or changed).
    # Unchanged files (hash match) don't count — they're cheap. When the
    # cap is hit the scan prints a warning naming the remaining count so
    # the user can re-run; the deletion sweep is skipped too (we haven't
    # visited every file, so we can't tell what's truly gone).
    "max_files_per_scan": 100,
    "embedder": "MiniLmEmbedder",
}

# Hard cap on chunks the LLM may produce per file. The prompt nudges
# toward many fewer (1-6 typical), but a defensive cap protects against
# a runaway response.
MAX_CHUNKS_PER_FILE = 10


@dataclass
class WatchChunk:
    """One chunk of the watched document. Half-open ``[start, end)`` over
    the extracted text. The watch pipeline never echoes verbatim text back
    from the LLM — only anchor strings — and recovers offsets locally via
    ``str.find``."""

    start: int
    end: int


@dataclass
class ChunkPlan:
    """LLM output: a one-paragraph summary plus the list of chunk
    boundaries to store under ``raw.<file>.chunk.NNN`` keys. The summary
    is written under ``raw.<file>.summary`` and also vector-indexed.

    ``error`` carries a short reason when the LLM call or its JSON
    response couldn't be parsed; the watch pipeline forwards it to its
    progress callback so the user sees *why* the fallback fired instead
    of just the placeholder summary in the store.
    """

    summary: str
    chunks: list[WatchChunk] = field(default_factory=list)
    error: str | None = None


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
        # HTML is allowed because ``markitdown.convert(path).text_content``
        # returns the *extracted Markdown*, not the raw HTML — so the
        # stored chunks under ``raw.<file>.chunk.NNN`` end up as clean
        # Markdown text (headings, bold/italic, links, lists), with
        # ``<script>`` / ``<style>`` / nav boilerplate stripped by
        # markitdown's html converter. The whole pipeline (chunk
        # boundaries, summary, vector index) operates on that
        # post-conversion text.
        ".html",
        ".htm",
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


def _build_chunk_summarize_prompt(text: str, *, max_chunks: int) -> str:
    """Build the chunk-and-summarize prompt with the same
    ``[STATIC_SECTION_START]...[STATIC_SECTION_END]`` cache-friendly
    discipline used by the classifier prompts. The dynamic section is
    just the document text + a closing instruction."""
    parts = [
        "[STATIC_SECTION_START]",
        "",
        "You are a document chunking and summarization system. Given a document, you will:",
        "  1. Write a concise one-paragraph SUMMARY of the whole document (2-4 sentences).",
        "  2. Segment the document into chunks sized for vector search.",
        "  3. Report each chunk's location by QUOTING short anchor strings — the first ~40 chars and last ~40 chars of the chunk (verbatim, taken from the document).",
        "",
        "CHUNKING RULES:",
        "  - Each chunk is a coherent block of content (a section, a tight cluster of related lines, a topic).",
        "  - Target chunk size: 500-2000 chars. Avoid tiny chunks (<200 chars) unless the document is itself short.",
        "  - Chunks MUST be non-overlapping and follow the document order.",
        "  - Prefer FEWER, LARGER chunks. Most documents need 1-5 chunks. Hard maximum: "
        + str(max_chunks)
        + " chunks total.",
        "  - Repetitive lists / tables / log lines belong in ONE chunk, not many.",
        "  - You may omit boilerplate / navigation / repeated material that has no useful retrieval content.",
        "",
        "ANCHOR RULES (CRITICAL):",
        "  - ``start_anchor`` = the first 30-60 chars of the chunk, copied EXACTLY from the document (preserve case, whitespace, punctuation).",
        "  - ``end_anchor``   = the last  30-60 chars of the chunk, copied EXACTLY from the document.",
        "  - Pick anchors that appear ONLY ONCE in the document — long enough to be unique.",
        "  - If a chunk is shorter than 60 chars in total, set start_anchor = end_anchor = the entire chunk text.",
        "  - DO NOT paraphrase, summarize, or normalize whitespace inside anchors. Copy verbatim.",
        "",
        "JSON RESPONSE FORMAT (return a single object, no prose, no preamble):",
        "{",
        '  "summary": "<one-paragraph summary>",',
        '  "chunks": [',
        "    {",
        '      "start_anchor": "<verbatim first 30-60 chars of the chunk>",',
        '      "end_anchor":   "<verbatim last  30-60 chars of the chunk>"',
        "    }",
        "  ]",
        "}",
        "",
        "[STATIC_SECTION_END]",
        "",
        "[DYNAMIC_SECTION_START]",
        "",
        "DOCUMENT TO CHUNK AND SUMMARIZE (length: " + str(len(text)) + " chars):",
        "",
        text,
        "",
        "Return only the JSON object.",
        "[DYNAMIC_SECTION_END]",
    ]
    return "\n".join(parts)


def _parse_chunk_summarize_response(response: Any, *, source_text: str) -> ChunkPlan:
    """Extract ``summary`` + ``chunks`` from the LLM response. Anchors
    are resolved against ``source_text`` via ``str.find`` from a monotonic
    cursor so later chunks can't locate their anchor before earlier ones.
    Chunks whose anchors fail to locate (in order) are dropped silently.
    """
    content = response.content if hasattr(response, "content") else str(response)
    start_idx = content.find("{")
    if start_idx == -1:
        logger.warning("chunk+summarize response has no JSON: %r", content[:200])
        return ChunkPlan(summary="", chunks=[])

    # Brace-match to find the closing brace.
    brace = 0
    end_idx = -1
    for i in range(start_idx, len(content)):
        if content[i] == "{":
            brace += 1
        elif content[i] == "}":
            brace -= 1
            if brace == 0:
                end_idx = i + 1
                break
    if end_idx == -1:
        logger.warning("chunk+summarize response has unbalanced braces")
        return ChunkPlan(summary="", chunks=[])

    json_str = content[start_idx:end_idx]
    data = json.loads(json_str)

    summary = data.get("summary")
    if not isinstance(summary, str):
        summary = ""
    summary = summary.strip()

    raw_chunks = data.get("chunks") or []
    out: list[WatchChunk] = []
    cursor = 0
    src_len = len(source_text)
    for ch in raw_chunks:
        if not isinstance(ch, dict):
            continue
        start_anchor = ch.get("start_anchor")
        end_anchor = ch.get("end_anchor")
        if not isinstance(start_anchor, str) or not isinstance(end_anchor, str):
            continue
        sa = start_anchor.strip()
        ea = end_anchor.strip()
        if not sa or not ea:
            continue
        start = source_text.find(sa, cursor)
        if start < 0:
            logger.debug("chunk start_anchor not found: %r", sa[:80])
            continue
        end_match = source_text.find(ea, start)
        if end_match < 0:
            logger.debug("chunk end_anchor not found after start: %r", ea[:80])
            continue
        end = end_match + len(ea)
        if end <= start or end > src_len:
            continue
        out.append(WatchChunk(start=start, end=end))
        cursor = end
    if len(out) > MAX_CHUNKS_PER_FILE:
        logger.info(
            "chunk+summarize returned %d chunks; capping at %d",
            len(out),
            MAX_CHUNKS_PER_FILE,
        )
        out = out[:MAX_CHUNKS_PER_FILE]
    return ChunkPlan(summary=summary, chunks=out)


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

    def remove(self, path: str, purge: bool = True) -> WatchRemoveResult:
        """Unregister a watched path and delete its indexed memories.

        Tears down (1) all ``raw.<file>.*`` memory keys in the watch
        namespace, (2) every matching vector index entry, (3) the per-file
        state under ``watch:files``, and (4) the path entry under
        ``watch:paths``. All buffered into a single batched data commit
        plus one vector commit per call.

        The ``purge`` parameter is retained for API back-compat: it now
        defaults to True and is the only supported value. Passing
        ``purge=False`` is silently treated as True — "remove without
        cleanup" was confusing (the file looked unwatched but its
        ``raw.*`` keys and vector hits stayed in the namespace), so the
        soft-remove path was dropped.
        """
        del purge  # back-compat shim; behavior is always full cleanup now.
        abs_target = str(Path(path).expanduser().resolve())
        try:
            paths = self._read_paths()
            remaining = [p for p in paths if p.get("path") != abs_target]
            if len(remaining) == len(paths):
                return WatchRemoveResult(
                    success=False,
                    path=abs_target,
                    purge=True,
                    error=f"Path is not registered: {abs_target}",
                )

            store = self._get_store()
            vector = (
                self._get_vector_service()
                if VectorService.feature_available()
                else None
            )
            files = self._read_files()

            # Batch every delete + the path-registry update + the
            # files_state flush into one data commit. Same auto_commit-off
            # pattern the scan loop uses.
            saved_auto_commit = getattr(store, "auto_commit", True)
            store.auto_commit = False
            files_removed = 0
            try:
                surviving_files: dict[str, Any] = {}
                for path_hash, state in files.items():
                    if state.get("watched_path") != abs_target:
                        surviving_files[path_hash] = state
                        continue
                    ns = state.get("namespace", "watch")
                    ns_tuple = self.namespace_to_tuple(ns)
                    memory_keys = list(state.get("memory_keys") or [])
                    for k in memory_keys:
                        try:
                            store.delete(ns_tuple, k)
                        except Exception as e:
                            logger.warning(
                                "remove: kv delete %s/%s failed: %s", ns_tuple, k, e
                            )
                    # Chunk-mode vector-indexes every key (summary + every
                    # chunk), so the vector teardown must iterate all of
                    # them — not just memory_keys[0] as the old slice-mode
                    # code assumed.
                    if vector:
                        for k in memory_keys:
                            with contextlib.suppress(Exception):
                                vector.delete(ns, k.encode("utf-8"))
                    files_removed += 1
                self._write_files(surviving_files)
                self._write_paths(remaining)
                with contextlib.suppress(Exception):
                    store.commit(
                        f"watch remove {abs_target} ({files_removed} file(s) purged)"
                    )
            finally:
                store.auto_commit = saved_auto_commit

            if vector:
                try:
                    vector.commit(f"watch remove {abs_target}")
                except Exception as e:
                    logger.warning("remove: vector commit failed: %s", e)

            return WatchRemoveResult(
                success=True,
                path=abs_target,
                files_removed=files_removed,
                purge=True,
            )
        except Exception as e:
            return WatchRemoveResult(
                success=False, path=abs_target, purge=True, error=str(e)
            )

    async def _scan_path(
        self,
        target: Path,
        namespace: str,
    ) -> WatchScanResult:
        """Walk a target, index changed files, return aggregated stats."""
        start = time.time()

        config = self._read_config()
        max_bytes = int(config.get("max_size_bytes", 100_000))
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
            "chunks_indexed": 0,
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
                        f"[{idx}/{total}] skip "
                        f"(size {size:,} bytes > cap {max_bytes:,} bytes): {p}"
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
                    f"  → chunk+summarize: 1 LLM call ({model_label}) on "
                    f"{len(text):,} chars"
                )

                plan = await self._chunk_and_summarize_async(text)

                # Fallback: if the LLM returns nothing useful, store the
                # whole document as a single chunk so the file is still
                # searchable rather than silently dropped. Surface the
                # actual error reason via _progress (not _vprogress) so
                # the user sees what failed without having to enable -v.
                fallback = False
                if not plan.summary and not plan.chunks:
                    fallback = True
                    reason = plan.error or "unknown (no summary, no chunks)"
                    plan = ChunkPlan(
                        summary="(no summary; LLM call failed or returned empty)",
                        chunks=[WatchChunk(start=0, end=len(text))],
                    )
                    self._progress(
                        f"  ⚠ chunk+summarize fell back to whole-file chunk: {reason}"
                    )
                elif not plan.chunks:
                    # Summary present but no chunks — single chunk over the
                    # full document so search still has something to hit.
                    plan = ChunkPlan(
                        summary=plan.summary,
                        chunks=[WatchChunk(start=0, end=len(text))],
                    )

                # Tear down the file's previous keys before re-indexing.
                # ``state["memory_keys"]`` is just a list of key strings;
                # the new chunk-keyed shape and the legacy slice-keyed
                # shape both delete cleanly through this same loop.
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

                file_token = _sanitize_path_component(p.name)
                summary_key = f"raw.{file_token}.summary"
                source_meta_base = {
                    "kind": "watch",
                    "abs_path": str(p),
                    "content_hash": chash,
                    "extracted_text_chars": len(text),
                    "chunk_count": len(plan.chunks),
                    "fallback_indexed": fallback,
                }

                new_keys: list[str] = []
                file_index_failures = 0

                # 1) Summary.
                try:
                    await memory_service.remember(
                        content=plan.summary,
                        paths=[summary_key],
                        namespace=namespace,
                        replace=True,
                        extra_metadata={
                            "source": {**source_meta_base, "kind_detail": "summary"}
                        },
                    )
                    new_keys.append(summary_key)
                    if vector is not None:
                        try:
                            vector.index(
                                namespace, summary_key.encode("utf-8"), plan.summary
                            )
                        except Exception as e:
                            logger.warning(
                                "vector index failed for %s summary: %s", p, e
                            )
                            file_index_failures += 1
                    self._vprogress(
                        f"  → summary: {len(plan.summary):,} chars → {summary_key}"
                    )
                except Exception as e:
                    logger.warning("remember failed for %s summary: %s", p, e)

                # 2) Chunks.
                for c_idx, ch in enumerate(plan.chunks):
                    chunk_text = text[ch.start : ch.end]
                    if not chunk_text.strip():
                        continue
                    chunk_key = f"raw.{file_token}.chunk.{c_idx + 1:03d}"
                    self._vprogress(
                        f"  → chunk {c_idx + 1}: chars [{ch.start},{ch.end}) "
                        f"({len(chunk_text):,}) → {chunk_key}"
                    )
                    try:
                        await memory_service.remember(
                            content=chunk_text,
                            paths=[chunk_key],
                            namespace=namespace,
                            replace=True,
                            extra_metadata={
                                "source": {
                                    **source_meta_base,
                                    "kind_detail": "chunk",
                                    "chunk_index": c_idx + 1,
                                    "chunk_start": ch.start,
                                    "chunk_end": ch.end,
                                }
                            },
                        )
                    except Exception as e:
                        logger.warning(
                            "remember failed for %s chunk %d: %s", p, c_idx + 1, e
                        )
                        continue
                    new_keys.append(chunk_key)

                    if vector is not None:
                        try:
                            vector.index(
                                namespace, chunk_key.encode("utf-8"), chunk_text
                            )
                        except Exception as e:
                            logger.warning(
                                "vector index failed for %s chunk %d: %s",
                                p,
                                c_idx + 1,
                                e,
                            )
                            file_index_failures += 1

                if not new_keys:
                    # Every write failed (very unusual).
                    stats["files_skipped_parse_error"] += 1
                    continue

                stats["index_failures"] += file_index_failures
                stats["files_indexed"] += 1
                stats["chunks_indexed"] += len(plan.chunks)
                files_state[path_key] = {
                    "abs_path": str(p),
                    "watched_path": str(target),
                    "namespace": namespace,
                    "memory_keys": new_keys,
                    "content_hash": chash,
                    "size": size,
                    "mtime": p.stat().st_mtime,
                    "indexed_at": _now_iso(),
                    "extracted_text_chars": len(text),
                    "chunk_count": len(plan.chunks),
                }
                self._progress(
                    f"[{idx}/{total}] indexed: {p} → "
                    f"summary + {len(plan.chunks)} chunk(s)"
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
                state_keys = list(state.get("memory_keys") or [])
                for k in state_keys:
                    try:
                        store.delete(ns_tuple, k)
                    except Exception as e:
                        logger.warning("scan: delete %s/%s failed: %s", ns_tuple, k, e)
                # Chunk-mode vector-indexes every key (summary + each chunk),
                # not just the primary. Delete all of them or stragglers
                # surface as "(memory no longer present)" stubs in search.
                if vector and state_keys:
                    for k in state_keys:
                        with contextlib.suppress(Exception):
                            vector.delete(ns, k.encode("utf-8"))
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
                f"({stats['chunks_indexed']} chunks "
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
            chunks_indexed=stats["chunks_indexed"],
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

    async def _chunk_and_summarize_async(self, text: str) -> ChunkPlan:
        """Single LLM call that returns a paragraph summary + chunk
        boundaries (as verbatim anchor strings) for ``text``.

        Anchor protocol: LLMs reliably quote text they see but reliably
        miscount character offsets. We ask the LLM for the first 30-60
        chars and last 30-60 chars of each chunk, then locate them in
        the source text via ``str.find`` with a monotonic cursor.
        Chunks whose anchors don't appear (in order) are dropped — the
        LLM hallucinated them and we'd rather lose that chunk than
        produce a mid-character cut.

        Returns ``ChunkPlan(summary="", chunks=[])`` on any failure so
        the watch pipeline can fall back without crashing the scan.
        """
        if not text:
            return ChunkPlan(summary="", chunks=[], error="empty input text")

        prompt = _build_chunk_summarize_prompt(text, max_chunks=MAX_CHUNKS_PER_FILE)
        try:
            llm = self._get_memory_service()._get_llm()
            response = await llm.ainvoke(prompt)
        except Exception as e:
            err = f"LLM call: {type(e).__name__}: {e}"
            logger.warning("chunk+summarize %s", err)
            return ChunkPlan(summary="", chunks=[], error=err)

        try:
            plan = _parse_chunk_summarize_response(response, source_text=text)
        except Exception as e:
            raw = response.content if hasattr(response, "content") else str(response)
            err = f"parse: {type(e).__name__}: {e}; raw[:160]={raw[:160]!r}"
            logger.warning("chunk+summarize %s", err)
            return ChunkPlan(summary="", chunks=[], error=err)

        # If the parser couldn't find any usable JSON, treat that as a
        # parse failure too — surface a useful excerpt of the raw response.
        if not plan.summary and not plan.chunks:
            raw = response.content if hasattr(response, "content") else str(response)
            plan.error = f"empty parse result; raw[:160]={raw[:160]!r}"
            logger.warning("chunk+summarize %s", plan.error)
        return plan

#!/usr/bin/env python3
"""Deterministic, stdlib-only extractors for the project:onboard skill.

The skill walks a non-git folder and dispatches each file to the matching
extractor based on its file extension. Every extractor returns a small
structured blob (key=value lines plus a JSON-encoded composite where useful)
that is written verbatim into the memoir store under
`project:onboard/files.<sanitized_path>.summary`.

No LLM calls happen here. Everything is bounded reads + zero-network parsing.

The module also exposes a pluggable tool registry: per `kind`, a stdlib
extractor always runs first; optional external tools (vision LLMs,
ffprobe, whisper, exiftool, …) declared in `~/.memoir/onboard-tools.yaml`
or `<project>/.memoir/onboard-tools.yaml` may run afterwards and merge their
output under `extractor.<tool_name>.<field>` keys. v1 ships with zero tool
entries; the registry skeleton exists so v2 is a config edit, not a code
change.

CLI:
    python3 extractors.py walk <root>           # list files + kinds + meta
    python3 extractors.py extract <path>        # one-file structured blob
    python3 extractors.py snapshot-hash <root>  # sha256 over (path, size, mtime_ns)
    python3 extractors.py tree <root>           # pruned dir tree (depth ≤ 3)
    python3 extractors.py shape <root>          # writing/bookkeeping/video-editing/mixed

All commands print a single JSON object to stdout (except `tree`, which
prints plain text — it's meant to be embedded directly in a memory value).
"""

from __future__ import annotations

import csv
import fnmatch
import hashlib
import io
import json
import os
import re
import struct
import subprocess
import sys
import time
import wave
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_FILE = "/tmp/memoir-hook.log"


def _log(msg: str) -> None:
    """Best-effort log to /tmp/memoir-hook.log; never raises."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[extractors {datetime.now(timezone.utc).isoformat()}] {msg}\n")
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Kind classification
# ---------------------------------------------------------------------------

# Map extension (lowercased, no leading dot) → kind. Extensions not listed fall
# through to default classification (text vs. binary by sniffing the first
# bytes); see _classify_kind below.
EXT_KIND: dict[str, str] = {
    # prose
    "txt": "prose",
    "rst": "prose",
    "org": "prose",
    "tex": "prose",
    # markdown is a separate kind so the consumer LLM sees the heading outline
    "md": "markdown",
    "markdown": "markdown",
    # tabular
    "csv": "csv",
    "tsv": "tsv",
    # data
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    # office
    "docx": "office-doc",
    "pptx": "office-slides",
    "xlsx": "office-sheet",
    "epub": "epub",
    # pdf
    "pdf": "pdf",
    # video projects
    "fcpxml": "video-project",
    "kdenlive": "video-project",
    "prproj": "video-project",
    "aep": "video-project",
    # subtitles
    "srt": "srt",
    "vtt": "vtt",
    # images
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "gif": "image",
    "webp": "image",
    "bmp": "image",
    "tif": "image",
    "tiff": "image",
    "heic": "image",
    # audio
    "mp3": "audio",
    "wav": "audio",
    "flac": "audio",
    "aac": "audio",
    "ogg": "audio",
    "m4a": "audio",
    # video
    "mp4": "video",
    "mov": "video",
    "mkv": "video",
    "avi": "video",
    "webm": "video",
    "m4v": "video",
    # archives
    "zip": "archive",
    "tar": "archive",
    "gz": "archive",
    "tgz": "archive",
    "7z": "archive",
    "bz2": "archive",
    "xz": "archive",
    # code-text (still possible in mixed folders; we treat it as prose-lite)
    "py": "code-text",
    "js": "code-text",
    "ts": "code-text",
    "go": "code-text",
    "rs": "code-text",
    "java": "code-text",
    "c": "code-text",
    "cpp": "code-text",
    "h": "code-text",
    "sh": "code-text",
    "bash": "code-text",
    "html": "code-text",
    "css": "code-text",
    "sql": "code-text",
    "toml": "code-text",
    "ini": "code-text",
    "cfg": "code-text",
}

# Default exclusion globs. Covers OS/editor cruft, code build artifacts, and
# video/audio editor caches (the issue's three target project types). Users
# extend via `<project>/.memoir/onboard-excludes.txt` (gitignore syntax).
DEFAULT_EXCLUDES: list[str] = [
    # OS / editor
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "~$*",
    "*.tmp",
    "*.bak",
    "*~",
    # version control / package managers
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".venv",
    "venv",
    "target",
    ".next",
    ".cache",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    # video / audio editor caches
    "Adobe Premiere Pro Auto-Save",
    "*.fcpcache",
    "*.proxy",
    "Render Files",
    "Audio Files",
    "Backup",
    # memoir's own state
    ".memoir",
]

# Files larger than this get metadata-only treatment regardless of kind, so we
# never read raw video/audio into the snapshot.
SIZE_CAP_BYTES: int = 50 * 1024 * 1024


def _classify_kind(path: Path, size: int) -> str:
    """Return the kind token for a file, sniffing when the extension lies."""
    ext = path.suffix.lower().lstrip(".")
    if ext in EXT_KIND:
        return EXT_KIND[ext]
    # Sniff: read first 1 KB and look at byte distribution. Mostly-printable
    # ASCII → "prose"; otherwise "binary".
    try:
        with open(path, "rb") as f:
            sample = f.read(1024)
        if not sample:
            return "unknown"
        printable = sum(1 for b in sample if 0x20 <= b < 0x7F or b in (0x09, 0x0A, 0x0D))
        if printable / len(sample) > 0.85:
            return "prose"
        return "binary"
    except OSError:
        return "unknown"


# ---------------------------------------------------------------------------
# Walk + excludes
# ---------------------------------------------------------------------------


def _load_user_excludes(root: Path) -> list[str]:
    """Read project-local `.memoir/onboard-excludes.txt`; return glob list."""
    f = root / ".memoir" / "onboard-excludes.txt"
    if not f.is_file():
        return []
    out = []
    try:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.append(line)
    except OSError:
        pass
    return out


def _is_excluded(rel: str, name: str, excludes: list[str]) -> bool:
    """Match `name` against any exclude glob; also match the relative path."""
    for pat in excludes:
        if fnmatch.fnmatch(name, pat):
            return True
        if fnmatch.fnmatch(rel, pat):
            return True
    return False


def walk_files(root: Path, extra_excludes: list[str] | None = None) -> list[dict]:
    """Walk `root` and emit one entry per surviving file.

    Each entry is a dict with `path` (relative), `size`, `mtime_ns`, `kind`.
    Directories matching any exclude glob are pruned from the descent (cheap
    and matches gitignore semantics for the `node_modules/` style entries).
    """
    excludes = list(DEFAULT_EXCLUDES)
    excludes.extend(_load_user_excludes(root))
    if extra_excludes:
        excludes.extend(extra_excludes)

    files: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        # Prune directories in-place (os.walk respects this on subsequent yields).
        dirnames[:] = [
            d for d in dirnames if not _is_excluded(os.path.join(rel_dir, d), d, excludes)
        ]
        for fname in filenames:
            rel = os.path.normpath(os.path.join(rel_dir, fname))
            if rel.startswith("./"):
                rel = rel[2:]
            if _is_excluded(rel, fname, excludes):
                continue
            full = Path(dirpath) / fname
            try:
                st = full.stat()
            except OSError:
                continue
            kind = _classify_kind(full, st.st_size) if st.st_size <= SIZE_CAP_BYTES else "binary"
            files.append(
                {
                    "path": rel,
                    "size": int(st.st_size),
                    "mtime_ns": int(st.st_mtime_ns),
                    "kind": kind,
                }
            )
    files.sort(key=lambda e: e["path"])
    return files


def snapshot_hash(files: list[dict]) -> str:
    """Hash over (path, size, mtime_ns) tuples — the warm-mode change signal."""
    h = hashlib.sha256()
    for entry in files:
        h.update(entry["path"].encode("utf-8", "replace"))
        h.update(b"\0")
        h.update(str(entry["size"]).encode("ascii"))
        h.update(b"\0")
        h.update(str(entry["mtime_ns"]).encode("ascii"))
        h.update(b"\n")
    return h.hexdigest()


def sanitize_path(rel: str) -> str:
    """Mirror the existing `structure.modules.<fs_path>` convention: '/' and
    '.' both become '_'. The result is a single semantic-path leaf segment."""
    return rel.replace("/", "_").replace(".", "_")


def render_tree(root: Path, max_depth: int = 3, max_entries_per_dir: int = 40) -> str:
    """Pruned directory tree, depth ≤ `max_depth`, sorted entries.

    Hidden + huge dirs collapse to `<dirname>/ (…)` so the output stays short.
    """
    excludes = list(DEFAULT_EXCLUDES)
    excludes.extend(_load_user_excludes(root))
    lines: list[str] = [f"{root.name}/"]

    def _walk(path: Path, depth: int, prefix: str) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(
                path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except OSError:
            return
        kept = [
            e
            for e in entries
            if not _is_excluded(str(e.relative_to(root)), e.name, excludes)
        ]
        if len(kept) > max_entries_per_dir:
            head = kept[:max_entries_per_dir]
            elided = len(kept) - len(head)
            kept = head
        else:
            elided = 0
        for i, e in enumerate(kept):
            last = (i == len(kept) - 1) and elided == 0
            connector = "└── " if last else "├── "
            display = e.name + ("/" if e.is_dir() else "")
            lines.append(prefix + connector + display)
            if e.is_dir() and depth + 1 <= max_depth:
                ext = "    " if last else "│   "
                _walk(e, depth + 1, prefix + ext)
        if elided:
            lines.append(prefix + f"└── … (+{elided} more)")

    _walk(root, 1, "")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Per-kind extractors
# ---------------------------------------------------------------------------


def _read_bounded(path: Path, head_bytes: int = 8192, tail_bytes: int = 2048) -> tuple[str, str]:
    """Return (head_text, tail_text). Both decoded with replacement."""
    try:
        size = path.stat().st_size
    except OSError:
        return "", ""
    try:
        with open(path, "rb") as f:
            head = f.read(head_bytes)
            tail = b""
            if size > head_bytes + tail_bytes:
                f.seek(max(0, size - tail_bytes))
                tail = f.read(tail_bytes)
    except OSError:
        return "", ""
    return head.decode("utf-8", "replace"), tail.decode("utf-8", "replace")


_STOPWORDS = set(
    """a an and are as at be but by for from has have he her his i in is it its
    of on or that the their them they this to was were will with you your me my
    we us our she him not no do does did so if then than which who whom what
    when where why how all any some such can could would should may might""".split()
)


def _top_terms(text: str, n: int = 10) -> list[str]:
    counts: dict[str, int] = {}
    for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text):
        wl = w.lower()
        if wl in _STOPWORDS:
            continue
        counts[wl] = counts.get(wl, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _first_words(text: str, n: int) -> str:
    words = re.findall(r"\S+", text.strip())
    return " ".join(words[:n])


def _last_words(text: str, n: int) -> str:
    words = re.findall(r"\S+", text.strip())
    return " ".join(words[-n:]) if len(words) >= n else " ".join(words)


def extract_prose(path: Path) -> dict:
    head, tail = _read_bounded(path)
    full = head + ("\n…\n" + tail if tail else "")
    title = _detect_title(path, head)
    return {
        "kind": "prose",
        "title": title,
        "first_50w": _first_words(full, 50),
        "last_20w": _last_words(full, 20),
        "word_count": _word_count(full),
        "top_terms": _top_terms(full),
    }


def _detect_title(path: Path, head: str) -> str:
    """Frontmatter `title:` → first H1 → first non-empty line → filename stem."""
    fm_match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", head, flags=re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            m = re.match(r"\s*title\s*:\s*(.+?)\s*$", line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    for line in head.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return m.group(1).strip()
    for line in head.splitlines():
        s = line.strip()
        if s and not s.startswith("---"):
            return s[:120]
    return path.stem


def extract_markdown(path: Path) -> dict:
    head, tail = _read_bounded(path)
    full = head + ("\n…\n" + tail if tail else "")
    headings = []
    for line in head.splitlines():
        m = re.match(r"^#{1,3}\s+(.+?)\s*$", line)
        if m:
            headings.append(m.group(1).strip())
        if len(headings) >= 12:
            break
    return {
        "kind": "markdown",
        "title": _detect_title(path, head),
        "headings": headings,
        "first_50w": _first_words(full, 50),
        "last_20w": _last_words(full, 20),
        "word_count": _word_count(full),
        "top_terms": _top_terms(full),
    }


_LEDGER_DATE = re.compile(r"date|day|time", re.IGNORECASE)
_LEDGER_AMOUNT = re.compile(r"amount|amt|price|total|cost|debit|credit|value", re.IGNORECASE)
_LEDGER_CATEGORY = re.compile(r"categor|cat|type|kind|tag|account", re.IGNORECASE)


def extract_tabular(path: Path, delimiter: str | None = None) -> dict:
    """Both .csv and .tsv. Auto-sniffs delimiter when absent."""
    blob: dict[str, Any] = {"kind": "csv" if path.suffix.lower() == ".csv" else "tsv"}
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            sample = f.read(8192)
    except OSError:
        return blob
    if delimiter is None:
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = "," if blob["kind"] == "csv" else "\t"
    blob["delimiter"] = delimiter

    rows: list[list[str]] = []
    columns: list[str] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f, delimiter=delimiter)
            for i, row in enumerate(reader):
                if i == 0:
                    columns = row
                    continue
                if len(rows) < 16:
                    rows.append(row)
                if i > 100_000:
                    break
            row_count = i  # noqa: F841 — i is the last value seen
    except OSError:
        row_count = 0
    blob["columns"] = columns
    blob["sample_rows"] = rows[:3]
    # Stream a quick row count separately so we don't load the whole file.
    blob["row_count"] = _count_rows(path, delimiter)
    blob["numeric_columns"] = _numeric_columns(columns, rows)
    if _looks_like_ledger(columns):
        blob["shape"] = "ledger"
    return blob


def _count_rows(path: Path, delimiter: str) -> int:
    """Stream-count rows minus header. Bounded by a 10M line cap."""
    n = 0
    try:
        with open(path, "rb") as f:
            for _ in f:
                n += 1
                if n > 10_000_000:
                    break
    except OSError:
        return 0
    return max(0, n - 1)  # subtract header


def _numeric_columns(columns: list[str], sample_rows: list[list[str]]) -> list[str]:
    if not columns or not sample_rows:
        return []
    out = []
    for ci, name in enumerate(columns):
        values = [r[ci] for r in sample_rows if ci < len(r)]
        if not values:
            continue
        if all(_is_numericish(v) for v in values):
            out.append(name)
    return out


def _is_numericish(s: str) -> bool:
    s = s.strip().lstrip("$£€¥").replace(",", "").rstrip("%")
    if not s:
        return False
    try:
        float(s)
        return True
    except ValueError:
        return False


def _looks_like_ledger(columns: list[str]) -> bool:
    has_date = any(_LEDGER_DATE.search(c) for c in columns)
    has_amount = any(_LEDGER_AMOUNT.search(c) for c in columns)
    has_category = any(_LEDGER_CATEGORY.search(c) for c in columns)
    return has_date and has_amount and has_category


def extract_json(path: Path) -> dict:
    blob: dict[str, Any] = {"kind": "json"}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        obj = json.loads(text)
    except (OSError, json.JSONDecodeError) as e:
        blob["error"] = f"parse: {type(e).__name__}"
        return blob
    blob["top_type"] = type(obj).__name__
    if isinstance(obj, dict):
        blob["top_keys"] = list(obj.keys())[:50]
        blob["key_count"] = len(obj)
    elif isinstance(obj, list):
        blob["item_count"] = len(obj)
        if obj:
            blob["first_item_type"] = type(obj[0]).__name__
    blob["max_depth"] = _max_depth(obj)
    return blob


def _max_depth(obj: Any, depth: int = 0, cap: int = 100) -> int:
    if depth >= cap:
        return depth
    if isinstance(obj, dict):
        return max((_max_depth(v, depth + 1, cap) for v in obj.values()), default=depth + 1)
    if isinstance(obj, list):
        return max((_max_depth(v, depth + 1, cap) for v in obj), default=depth + 1)
    return depth


def extract_yaml(path: Path) -> dict:
    """Minimal stdlib-only YAML peek.

    We do NOT reimplement YAML — just sniff top-level keys via the heuristic
    that a top-level key is `^[A-Za-z_][A-Za-z0-9_-]*\\s*:` at column 0. Good
    enough for `summary.overview` template purposes, never used as the
    authoritative parse.
    """
    blob: dict[str, Any] = {"kind": "yaml"}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return blob
    keys: list[str] = []
    for line in text.splitlines()[:500]:
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", line)
        if m:
            keys.append(m.group(1))
        if len(keys) >= 50:
            break
    blob["top_keys"] = keys
    return blob


def extract_office_zip(path: Path) -> dict:
    """docx/pptx/xlsx/epub all share a zip-with-xml structure."""
    ext = path.suffix.lower().lstrip(".")
    blob: dict[str, Any] = {"kind": EXT_KIND.get(ext, "office-doc")}
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            blob["entries"] = len(names)
            # core props (docx, pptx, xlsx)
            if "docProps/core.xml" in names:
                with z.open("docProps/core.xml") as cf:
                    try:
                        tree = ET.parse(cf)
                        for el in tree.iter():
                            tag = el.tag.split("}", 1)[-1]
                            if tag == "title" and el.text:
                                blob["title"] = el.text.strip()
                            elif tag == "creator" and el.text:
                                blob["creator"] = el.text.strip()
                            elif tag == "modified" and el.text:
                                blob["modified"] = el.text.strip()
                    except ET.ParseError:
                        pass
            # xlsx: enumerate sheet names
            if blob["kind"] == "office-sheet" and "xl/workbook.xml" in names:
                with z.open("xl/workbook.xml") as wf:
                    try:
                        tree = ET.parse(wf)
                        sheets = []
                        for el in tree.iter():
                            tag = el.tag.split("}", 1)[-1]
                            if tag == "sheet":
                                name = el.get("name") or ""
                                if name:
                                    sheets.append(name)
                        blob["sheets"] = sheets
                    except ET.ParseError:
                        pass
            # pptx: slide count
            if blob["kind"] == "office-slides":
                slide_count = sum(
                    1 for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")
                )
                if slide_count:
                    blob["slide_count"] = slide_count
            # docx: paragraph count (rough)
            if blob["kind"] == "office-doc" and "word/document.xml" in names:
                with z.open("word/document.xml") as df:
                    try:
                        data = df.read().decode("utf-8", "replace")
                        blob["paragraph_count"] = data.count("<w:p")
                    except OSError:
                        pass
            # epub: opf manifest
            if blob["kind"] == "epub":
                opf = next((n for n in names if n.endswith(".opf")), None)
                if opf:
                    with z.open(opf) as of:
                        try:
                            tree = ET.parse(of)
                            for el in tree.iter():
                                tag = el.tag.split("}", 1)[-1]
                                if tag == "title" and el.text and "title" not in blob:
                                    blob["title"] = el.text.strip()
                            blob["spine_items"] = sum(
                                1 for el in tree.iter() if el.tag.split("}", 1)[-1] == "itemref"
                            )
                        except ET.ParseError:
                            pass
    except (zipfile.BadZipFile, OSError) as e:
        blob["error"] = f"open: {type(e).__name__}"
    return blob


def extract_pdf(path: Path) -> dict:
    """PDFs are metadata-only at v1 — text extraction is a tool entry."""
    blob: dict[str, Any] = {"kind": "pdf"}
    try:
        with open(path, "rb") as f:
            magic = f.read(8)
        blob["valid_magic"] = magic.startswith(b"%PDF-")
        if blob["valid_magic"]:
            blob["pdf_version"] = magic[5:8].decode("ascii", "replace").strip()
    except OSError as e:
        blob["error"] = f"read: {type(e).__name__}"
    return blob


def extract_video_project(path: Path) -> dict:
    """fcpxml / kdenlive / prproj are XML; aep is binary (metadata-only)."""
    ext = path.suffix.lower().lstrip(".")
    blob: dict[str, Any] = {"kind": "video-project", "format": ext}
    if ext == "aep":
        return blob  # binary; nothing more to say without dedicated tool
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as e:
        blob["error"] = f"parse: {type(e).__name__}"
        return blob
    root = tree.getroot()
    name_attr = root.get("name") or root.get("title")
    if name_attr:
        blob["project_name"] = name_attr
    # crude clip count: any element named clip|asset-clip|ref-clip|kdenlivedoc producer
    clip_tags = {"clip", "asset-clip", "ref-clip", "producer"}
    clips = sum(1 for el in tree.iter() if el.tag.split("}", 1)[-1] in clip_tags)
    blob["clip_count"] = clips
    # try to read a `duration` attribute on the root or its sequence child
    for el in tree.iter():
        dur = el.get("duration")
        if dur and "duration" not in blob:
            blob["duration"] = dur
            break
    return blob


def extract_srt(path: Path) -> dict:
    """SRT cue parsing — first cue, last cue, count, total duration."""
    return _extract_subtitles(path, kind="srt")


def extract_vtt(path: Path) -> dict:
    return _extract_subtitles(path, kind="vtt")


_SRT_TIME = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")


def _extract_subtitles(path: Path, kind: str) -> dict:
    blob: dict[str, Any] = {"kind": kind}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        blob["error"] = f"read: {type(e).__name__}"
        return blob
    # Cues separated by blank lines. For VTT, skip the WEBVTT header.
    if kind == "vtt":
        text = re.sub(r"^WEBVTT.*?\n\n", "", text, count=1, flags=re.DOTALL)
    cues = re.split(r"\n\s*\n", text.strip())
    cues = [c for c in cues if c.strip()]
    blob["cue_count"] = len(cues)
    if cues:
        blob["first_cue"] = _strip_cue(cues[0])
        blob["last_cue"] = _strip_cue(cues[-1])
    last_match = None
    for m in _SRT_TIME.finditer(text):
        last_match = m
    if last_match:
        h, mi, s, ms = last_match.groups()
        blob["total_duration_s"] = round(
            int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / (1000 if len(ms) >= 3 else 100), 2
        )
    return blob


def _strip_cue(cue: str) -> str:
    """Drop the index + timing lines, keep the text."""
    lines = [ln for ln in cue.splitlines() if not _SRT_TIME.search(ln)]
    lines = [ln for ln in lines if not re.fullmatch(r"\d+", ln.strip())]
    return " ".join(ln.strip() for ln in lines if ln.strip())[:200]


def extract_image(path: Path) -> dict:
    blob: dict[str, Any] = {"kind": "image", "format": path.suffix.lower().lstrip(".")}
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except OSError:
        return blob
    if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
        # IHDR is the first chunk after the signature.
        w, h = struct.unpack(">II", head[16:24])
        blob["width"], blob["height"] = w, h
    elif head.startswith(b"\xff\xd8"):
        blob["jpeg"] = True  # full size requires marker walking; skip in v1
    elif head.startswith(b"GIF8"):
        if len(head) >= 10:
            w, h = struct.unpack("<HH", head[6:10])
            blob["width"], blob["height"] = w, h
    return blob


def extract_audio(path: Path) -> dict:
    blob: dict[str, Any] = {"kind": "audio", "format": path.suffix.lower().lstrip(".")}
    if blob["format"] == "wav":
        try:
            with wave.open(str(path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate:
                    blob["duration_s"] = round(frames / rate, 2)
                blob["sample_rate"] = rate
                blob["channels"] = wf.getnchannels()
        except (wave.Error, OSError):
            pass
    return blob


def extract_video(path: Path) -> dict:
    return {"kind": "video", "format": path.suffix.lower().lstrip(".")}


def extract_archive(path: Path) -> dict:
    blob: dict[str, Any] = {"kind": "archive", "format": path.suffix.lower().lstrip(".")}
    if blob["format"] == "zip":
        try:
            with zipfile.ZipFile(path) as z:
                blob["entries"] = len(z.namelist())
        except (zipfile.BadZipFile, OSError):
            pass
    return blob


def extract_default(path: Path) -> dict:
    """Fallback for kind=binary/unknown/code-text."""
    return {
        "kind": _classify_kind(path, _safe_size(path)),
        "format": path.suffix.lower().lstrip(".") or "(none)",
    }


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


KIND_DISPATCH = {
    "prose": extract_prose,
    "markdown": extract_markdown,
    "csv": extract_tabular,
    "tsv": extract_tabular,
    "json": extract_json,
    "yaml": extract_yaml,
    "office-doc": extract_office_zip,
    "office-slides": extract_office_zip,
    "office-sheet": extract_office_zip,
    "epub": extract_office_zip,
    "pdf": extract_pdf,
    "video-project": extract_video_project,
    "srt": extract_srt,
    "vtt": extract_vtt,
    "image": extract_image,
    "audio": extract_audio,
    "video": extract_video,
    "archive": extract_archive,
    "code-text": extract_prose,
}


# ---------------------------------------------------------------------------
# Pluggable tool registry (v1 ships empty)
# ---------------------------------------------------------------------------


def _tool_config_paths(root: Path | None = None) -> list[Path]:
    paths = [Path.home() / ".memoir" / "onboard-tools.yaml"]
    if root is not None:
        paths.append(root / ".memoir" / "onboard-tools.yaml")
    return paths


def _load_tool_config(paths: list[Path]) -> dict[str, list[dict]]:
    """Load tool config. Tries PyYAML; if absent, falls back to JSON if the
    file's content parses as JSON. Returns `{kind: [tool_entry, ...]}`."""
    merged: dict[str, list[dict]] = {}
    for p in paths:
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        data = _parse_tool_config_text(text, p)
        if not isinstance(data, dict):
            continue
        for kind, entries in data.items():
            if not isinstance(entries, list):
                continue
            merged.setdefault(kind, [])
            for entry in entries:
                if isinstance(entry, dict) and "command" in entry:
                    merged[kind].append(entry)
    return merged


def _parse_tool_config_text(text: str, source: Path) -> Any:
    try:
        import yaml  # type: ignore[import-not-found]

        return yaml.safe_load(text)
    except ImportError:
        # No PyYAML — accept JSON-shaped content as a fallback.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            _log(
                f"tool config at {source} is YAML-only and PyYAML is unavailable; "
                "skipping. Install PyYAML or rewrite as JSON to enable."
            )
            return None
    except Exception as e:  # yaml.YAMLError subclasses
        _log(f"tool config at {source} failed to parse: {type(e).__name__}")
        return None


def _tool_cache_dir(store_path: str | None) -> Path | None:
    if not store_path:
        return None
    p = Path(store_path) / ".git" / "plugin-extractor-cache"
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return p


def _content_hash(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def run_tools_for_kind(
    kind: str, path: Path, registry: dict[str, list[dict]], cache_dir: Path | None
) -> dict:
    """Run any external tools registered for `kind`. Output is merged under
    `extractor.<tool_name>.<field>` keys. Failures are silent (logged)."""
    out: dict[str, Any] = {}
    entries = registry.get(kind, [])
    if not entries:
        return out
    chash = _content_hash(path)
    for entry in entries:
        name = str(entry.get("name") or entry.get("command", "tool")).split()[0]
        cache_file = None
        if cache_dir and chash:
            cache_file = cache_dir / f"{chash}.{name}.json"
            if cache_file.is_file():
                try:
                    cached = json.loads(cache_file.read_text(encoding="utf-8"))
                    for k, v in cached.items():
                        out[f"extractor.{name}.{k}"] = v
                    continue
                except (OSError, json.JSONDecodeError):
                    pass
        cmd_template = entry.get("command", "")
        timeout_s = float(entry.get("timeout_s", 30))
        try:
            cmd = cmd_template.replace("{path}", str(path))
            res = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                timeout=timeout_s,
                check=False,
            )
            if res.returncode != 0:
                _log(f"tool '{name}' for {path}: rc={res.returncode}; {res.stderr[:200]!r}")
                continue
            try:
                payload = json.loads(res.stdout.decode("utf-8", "replace") or "{}")
            except json.JSONDecodeError:
                payload = {"raw_stdout_first_200": res.stdout[:200].decode("utf-8", "replace")}
            if not isinstance(payload, dict):
                continue
            for k, v in payload.items():
                out[f"extractor.{name}.{k}"] = v
            if cache_file:
                try:
                    cache_file.write_text(json.dumps(payload), encoding="utf-8")
                except OSError:
                    pass
        except subprocess.TimeoutExpired:
            _log(f"tool '{name}' for {path}: timeout after {timeout_s}s")
        except Exception as e:
            _log(f"tool '{name}' for {path}: {type(e).__name__}: {e}")
    return out


# ---------------------------------------------------------------------------
# Top-level extract()
# ---------------------------------------------------------------------------


def extract(path: Path, registry: dict | None = None, cache_dir: Path | None = None) -> dict:
    """Run the stdlib extractor for the file's kind, then merge any tool
    outputs registered for that kind.

    Always emits `kind=` and `extractor.stdlib.fields=[…]` so the consumer
    LLM knows which fields are deterministic vs. tool-derived.
    """
    size = _safe_size(path)
    if size > SIZE_CAP_BYTES:
        return {
            "kind": "binary",
            "format": path.suffix.lower().lstrip(".") or "(none)",
            "note": "size_cap_exceeded",
            "size": size,
        }
    kind = _classify_kind(path, size)
    fn = KIND_DISPATCH.get(kind, extract_default)
    blob = fn(path)
    blob["kind"] = blob.get("kind") or kind
    blob["extractor.stdlib.fields"] = sorted(
        k for k in blob.keys() if not k.startswith("extractor.")
    )
    if registry:
        tool_out = run_tools_for_kind(kind, path, registry, cache_dir)
        blob.update(tool_out)
    return blob


def render_blob(blob: dict) -> str:
    """Render a blob as a `key=value` text body — what the skill writes into
    `files.<sanitized_path>.summary`. JSON-encodes lists/dicts."""
    lines: list[str] = []
    # `kind` first so consumer LLMs see the schema tag immediately.
    if "kind" in blob:
        lines.append(f"kind={blob['kind']}")
    for k in sorted(blob.keys()):
        if k == "kind":
            continue
        v = blob[k]
        if isinstance(v, (dict, list)):
            lines.append(f"{k}={json.dumps(v, ensure_ascii=False)}")
        elif isinstance(v, bool):
            lines.append(f"{k}={'true' if v else 'false'}")
        else:
            lines.append(f"{k}={v}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Project-shape classifier (deterministic; powers summary.overview template)
# ---------------------------------------------------------------------------


def detect_shape(files: list[dict]) -> str:
    """Return one of: writing-shape, bookkeeping-shape, video-editing-shape, mixed."""
    if not files:
        return "mixed"
    total = len(files)
    kinds: dict[str, int] = {}
    has_ledger = False
    has_video_project = False
    for f in files:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
        if f["kind"] == "video-project":
            has_video_project = True
    prose_share = (kinds.get("prose", 0) + kinds.get("markdown", 0)) / total
    csv_share = (kinds.get("csv", 0) + kinds.get("tsv", 0)) / total
    video_share = (
        kinds.get("video", 0) + kinds.get("audio", 0) + kinds.get("video-project", 0)
    ) / total
    binary_share = (kinds.get("binary", 0) + kinds.get("unknown", 0)) / total

    # Ledger detection: peek at any csv/tsv to confirm shape=ledger before
    # committing to a bookkeeping label.
    if csv_share >= 0.3:
        for f in files:
            if f["kind"] in ("csv", "tsv"):
                # We don't have the path here; caller can pass it in. For shape
                # detection we use the heuristic "csv-heavy folder" alone.
                has_ledger = True
                break

    if prose_share > 0.4 and binary_share < 0.4:
        return "writing-shape"
    if csv_share > 0.3 and has_ledger:
        return "bookkeeping-shape"
    if video_share > 0.2 or has_video_project:
        return "video-editing-shape"
    return "mixed"


def shape_overview(root: Path, files: list[dict], shape: str) -> str:
    """Fill the matching template for `summary.overview`."""
    if not files:
        return f"Empty folder at {root.name}."
    file_count = len(files)
    kinds: dict[str, int] = {}
    for f in files:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    top_kinds = ", ".join(
        f"{k}({v})" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])[:3]
    )
    top_titles = _top_level_titles(root, files)
    if shape == "writing-shape":
        wc_total = sum(_word_count_from_meta(f) for f in files if f["kind"] in ("prose", "markdown"))
        wc_k = max(1, wc_total // 1000)
        return (
            f"Writing project. {file_count} files totaling ~{wc_k}k indexed words; "
            f"top-level: {top_titles}."
        )
    if shape == "bookkeeping-shape":
        return (
            f"Bookkeeping / records project. {file_count} files; "
            f"mostly tabular ledgers; top-level: {top_titles}."
        )
    if shape == "video-editing-shape":
        return (
            f"Video editing project. {file_count} media + project files; "
            f"top-level: {top_titles}."
        )
    return f"Folder of {file_count} files; mostly {top_kinds}; top-level: {top_titles}."


def _word_count_from_meta(f: dict) -> int:
    # Caller can attach 'word_count' onto the entry in cold mode; default 0.
    return int(f.get("word_count", 0) or 0)


def _top_level_titles(root: Path, files: list[dict], n: int = 3) -> str:
    top = []
    for f in files:
        if "/" in f["path"]:
            continue
        top.append(f["path"])
        if len(top) >= n:
            break
    return ", ".join(top) if top else "(empty top level)"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli_walk(root: Path) -> int:
    files = walk_files(root)
    out = {"files": files, "snapshot_hash": snapshot_hash(files)}
    print(json.dumps(out, ensure_ascii=False))
    return 0


def _cli_extract(path: Path, store_path: str | None) -> int:
    registry = _load_tool_config(_tool_config_paths())
    cache_dir = _tool_cache_dir(store_path)
    blob = extract(path, registry=registry, cache_dir=cache_dir)
    print(render_blob(blob))
    return 0


def _cli_snapshot_hash(root: Path) -> int:
    files = walk_files(root)
    print(snapshot_hash(files))
    return 0


def _cli_tree(root: Path) -> int:
    print(render_tree(root))
    return 0


def _cli_shape(root: Path) -> int:
    files = walk_files(root)
    shape = detect_shape(files)
    overview = shape_overview(root, files, shape)
    print(json.dumps({"shape": shape, "overview": overview}, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(
            "usage: extractors.py {walk|extract|snapshot-hash|tree|shape} <path>",
            file=sys.stderr,
        )
        return 2
    cmd = argv[1]
    if cmd == "walk":
        return _cli_walk(Path(argv[2]))
    if cmd == "extract":
        store = os.environ.get("MEMOIR_STORE")
        return _cli_extract(Path(argv[2]), store)
    if cmd == "snapshot-hash":
        return _cli_snapshot_hash(Path(argv[2]))
    if cmd == "tree":
        return _cli_tree(Path(argv[2]))
    if cmd == "shape":
        return _cli_shape(Path(argv[2]))
    print(f"unknown subcommand: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))

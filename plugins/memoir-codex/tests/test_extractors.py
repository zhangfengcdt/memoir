"""Unit tests for plugins/memoir-codex/skills/memoir-onboard/extractors.py.

Stdlib-only fixtures — every test creates a tiny synthetic file in a temp
directory and asserts the structured-blob shape. No network, no LLM.
"""

from __future__ import annotations

import importlib.util
import json
import struct
import sys
import zipfile
from pathlib import Path

import pytest

EXTRACTORS_PATH = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "memoir-onboard"
    / "extractors.py"
)


def _load_extractors():
    spec = importlib.util.spec_from_file_location("extractors", EXTRACTORS_PATH)
    assert spec and spec.loader, f"could not load {EXTRACTORS_PATH}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["extractors"] = mod
    spec.loader.exec_module(mod)
    return mod


extractors = _load_extractors()


# ---------------------------------------------------------------------------
# extract_prose / extract_markdown
# ---------------------------------------------------------------------------


def test_extract_markdown_with_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "chapter.md"
    f.write_text(
        """---
title: Chapter 3: The Argument
---

# Chapter 3: The Argument

It started, as most of these did, over coffee and a vague sense that the
mother had been right after all. Sarah opened the door of the apartment
and decided, after some hesitation, to argue.

## Counterpoint

Coffee was the only available weapon.

## Reconciliation

Eventually they decided.
"""
    )
    blob = extractors.extract_markdown(f)
    assert blob["kind"] == "markdown"
    assert blob["title"] == "Chapter 3: The Argument"
    assert "Counterpoint" in blob["headings"]
    assert "Reconciliation" in blob["headings"]
    assert blob["word_count"] > 0
    assert "first_50w" in blob and len(blob["first_50w"].split()) <= 50
    assert isinstance(blob["top_terms"], list)


def test_extract_markdown_first_h1_when_no_frontmatter(tmp_path: Path) -> None:
    f = tmp_path / "chapter.md"
    f.write_text("# Just A Heading\n\nbody text\n")
    assert extractors.extract_markdown(f)["title"] == "Just A Heading"


def test_extract_prose_falls_back_to_filename(tmp_path: Path) -> None:
    f = tmp_path / "essay.txt"
    f.write_text("just some prose, no heading at all\n")
    blob = extractors.extract_prose(f)
    assert blob["kind"] == "prose"
    assert blob["title"]  # non-empty (filename stem or first line)
    assert blob["word_count"] > 0


# ---------------------------------------------------------------------------
# extract_tabular (csv / tsv) + ledger detection
# ---------------------------------------------------------------------------


def test_extract_tabular_csv(tmp_path: Path) -> None:
    f = tmp_path / "data.csv"
    f.write_text("name,age,score\nalice,30,95.5\nbob,25,82.0\ncarol,40,90.0\n")
    blob = extractors.extract_tabular(f)
    assert blob["kind"] == "csv"
    assert blob["columns"] == ["name", "age", "score"]
    assert blob["row_count"] == 3
    assert "age" in blob["numeric_columns"]
    assert "score" in blob["numeric_columns"]
    assert blob.get("shape") != "ledger"


def test_extract_tabular_ledger_shape(tmp_path: Path) -> None:
    f = tmp_path / "ledger.csv"
    rows = ["date,amount,category,note"]
    rows += [f"2026-01-{n:02d},{n*10}.00,groceries,Whole Foods" for n in range(1, 12)]
    f.write_text("\n".join(rows) + "\n")
    blob = extractors.extract_tabular(f)
    assert blob["shape"] == "ledger"
    assert blob["columns"][0] == "date"
    assert "amount" in blob["numeric_columns"]
    assert blob["row_count"] == 11


def test_extract_tabular_caps_sample_rows(tmp_path: Path) -> None:
    f = tmp_path / "many.csv"
    rows = ["a,b"]
    rows += [f"{i},{i*2}" for i in range(50)]
    f.write_text("\n".join(rows) + "\n")
    blob = extractors.extract_tabular(f)
    assert len(blob["sample_rows"]) == 3  # only 3 surface; 16 collected internally
    assert blob["row_count"] == 50


# ---------------------------------------------------------------------------
# extract_json / extract_yaml
# ---------------------------------------------------------------------------


def test_extract_json_dict(tmp_path: Path) -> None:
    f = tmp_path / "data.json"
    f.write_text(json.dumps({"a": 1, "b": [1, 2, 3], "c": {"deep": {"deeper": 1}}}))
    blob = extractors.extract_json(f)
    assert blob["kind"] == "json"
    assert blob["top_type"] == "dict"
    assert set(blob["top_keys"]) == {"a", "b", "c"}
    assert blob["max_depth"] >= 3


def test_extract_json_invalid(tmp_path: Path) -> None:
    f = tmp_path / "bad.json"
    f.write_text("not json at all")
    blob = extractors.extract_json(f)
    assert blob["kind"] == "json"
    assert "error" in blob


def test_extract_yaml_top_keys(tmp_path: Path) -> None:
    f = tmp_path / "config.yaml"
    f.write_text("foo: 1\nbar:\n  - 1\n  - 2\nbaz_qux: hello\n")
    blob = extractors.extract_yaml(f)
    assert blob["kind"] == "yaml"
    assert "foo" in blob["top_keys"]
    assert "bar" in blob["top_keys"]
    assert "baz_qux" in blob["top_keys"]


# ---------------------------------------------------------------------------
# extract_office_zip
# ---------------------------------------------------------------------------


def _make_minimal_xlsx(path: Path, sheets: list[str]) -> None:
    """Hand-roll the minimum xlsx structure needed for our parser."""
    sheet_xml_entries = "\n".join(
        f'<sheet name="{name}" sheetId="{i+1}" r:id="rId{i+1}"/>'
        for i, name in enumerate(sheets)
    )
    workbook_xml = (
        '<?xml version="1.0"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheet_xml_entries}</sheets>"
        "</workbook>"
    )
    core_xml = (
        '<?xml version="1.0"?>'
        '<cp:coreProperties '
        'xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        "<dc:title>Quarterly Numbers</dc:title>"
        "<dc:creator>Feng</dc:creator>"
        "</cp:coreProperties>"
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml", workbook_xml)
        z.writestr("docProps/core.xml", core_xml)


def test_extract_office_zip_xlsx(tmp_path: Path) -> None:
    f = tmp_path / "book.xlsx"
    _make_minimal_xlsx(f, ["Q1", "Q2", "Notes"])
    blob = extractors.extract_office_zip(f)
    assert blob["kind"] == "office-sheet"
    assert blob["sheets"] == ["Q1", "Q2", "Notes"]
    assert blob.get("title") == "Quarterly Numbers"
    assert blob["entries"] == 2


def test_extract_office_zip_corrupt(tmp_path: Path) -> None:
    f = tmp_path / "broken.docx"
    f.write_bytes(b"not a real zip")
    blob = extractors.extract_office_zip(f)
    assert "error" in blob


# ---------------------------------------------------------------------------
# extract_pdf (metadata-only)
# ---------------------------------------------------------------------------


def test_extract_pdf_magic(tmp_path: Path) -> None:
    f = tmp_path / "doc.pdf"
    f.write_bytes(b"%PDF-1.7\n%binary garbage")
    blob = extractors.extract_pdf(f)
    assert blob["kind"] == "pdf"
    assert blob["valid_magic"] is True
    assert blob["pdf_version"].startswith("1.")


def test_extract_pdf_invalid_magic(tmp_path: Path) -> None:
    f = tmp_path / "fake.pdf"
    f.write_bytes(b"not a pdf")
    blob = extractors.extract_pdf(f)
    assert blob["valid_magic"] is False


# ---------------------------------------------------------------------------
# extract_video_project
# ---------------------------------------------------------------------------


def test_extract_video_project_fcpxml(tmp_path: Path) -> None:
    f = tmp_path / "edit.fcpxml"
    f.write_text(
        '<?xml version="1.0"?>'
        '<fcpxml version="1.10" name="Vacation Edit" duration="3600s">'
        '<library><event name="Main">'
        '<asset-clip name="clip1"/><asset-clip name="clip2"/><asset-clip name="clip3"/>'
        "</event></library>"
        "</fcpxml>"
    )
    blob = extractors.extract_video_project(f)
    assert blob["kind"] == "video-project"
    assert blob["format"] == "fcpxml"
    assert blob["project_name"] == "Vacation Edit"
    assert blob["clip_count"] == 3
    assert blob["duration"] == "3600s"


def test_extract_video_project_aep_metadata_only(tmp_path: Path) -> None:
    f = tmp_path / "comp.aep"
    f.write_bytes(b"\x00\x00binary garbage")
    blob = extractors.extract_video_project(f)
    assert blob["kind"] == "video-project"
    assert blob["format"] == "aep"
    # No parse for binary aep.
    assert "clip_count" not in blob
    assert "error" not in blob


# ---------------------------------------------------------------------------
# extract_srt / extract_vtt
# ---------------------------------------------------------------------------


def test_extract_srt(tmp_path: Path) -> None:
    f = tmp_path / "captions.srt"
    f.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nHello, world.\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nMid line.\n\n"
        "3\n00:01:00,500 --> 00:01:02,500\nGoodbye.\n"
    )
    blob = extractors.extract_srt(f)
    assert blob["kind"] == "srt"
    assert blob["cue_count"] == 3
    assert blob["first_cue"].startswith("Hello")
    assert blob["last_cue"].startswith("Goodbye")
    assert blob["total_duration_s"] >= 60


# ---------------------------------------------------------------------------
# extract_image (PNG dimensions from header)
# ---------------------------------------------------------------------------


def _make_png(path: Path, w: int, h: int) -> None:
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"
    path.write_bytes(sig + ihdr)


def test_extract_image_png(tmp_path: Path) -> None:
    f = tmp_path / "tiny.png"
    _make_png(f, 7, 5)
    blob = extractors.extract_image(f)
    assert blob["kind"] == "image"
    assert blob["width"] == 7
    assert blob["height"] == 5


# ---------------------------------------------------------------------------
# walk_files + snapshot_hash + excludes
# ---------------------------------------------------------------------------


def test_walk_files_basic(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("# A\n")
    (tmp_path / "data.csv").write_text("h\n1\n")
    (tmp_path / ".DS_Store").write_text("noise")
    sub = tmp_path / "node_modules"
    sub.mkdir()
    (sub / "x.js").write_text("nope")
    files = extractors.walk_files(tmp_path)
    paths = {f["path"] for f in files}
    assert "a.md" in paths
    assert "data.csv" in paths
    assert ".DS_Store" not in paths
    # node_modules is pruned at the directory level
    assert not any(p.startswith("node_modules") for p in paths)


def test_walk_files_user_excludes(tmp_path: Path) -> None:
    (tmp_path / "keep.md").write_text("y")
    (tmp_path / "drop.log").write_text("n")
    excl_dir = tmp_path / ".memoir"
    excl_dir.mkdir()
    (excl_dir / "onboard-excludes.txt").write_text("*.log\n")
    files = extractors.walk_files(tmp_path)
    paths = {f["path"] for f in files}
    assert "keep.md" in paths
    assert "drop.log" not in paths


def test_snapshot_hash_stable_for_unchanged(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("hello")
    (tmp_path / "b.txt").write_text("world")
    h1 = extractors.snapshot_hash(extractors.walk_files(tmp_path))
    h2 = extractors.snapshot_hash(extractors.walk_files(tmp_path))
    assert h1 == h2


def test_snapshot_hash_changes_on_size_change(tmp_path: Path) -> None:
    f = tmp_path / "a.md"
    f.write_text("hello")
    h1 = extractors.snapshot_hash(extractors.walk_files(tmp_path))
    f.write_text("hello world")
    h2 = extractors.snapshot_hash(extractors.walk_files(tmp_path))
    assert h1 != h2


def test_sanitize_path() -> None:
    assert extractors.sanitize_path("a/b.txt") == "a_b_txt"
    assert extractors.sanitize_path("plain") == "plain"


# ---------------------------------------------------------------------------
# Top-level extract() always emits kind + provenance
# ---------------------------------------------------------------------------


def test_extract_top_level_emits_provenance(tmp_path: Path) -> None:
    f = tmp_path / "story.md"
    f.write_text("# title\n\nbody body body\n")
    blob = extractors.extract(f)
    assert blob["kind"] == "markdown"
    assert "extractor.stdlib.fields" in blob
    # All non-extractor.* fields should be listed in provenance.
    listed = set(blob["extractor.stdlib.fields"])
    for k in blob:
        if k.startswith("extractor."):
            continue
        assert k in listed


def test_extract_size_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "huge.mp4"
    f.write_bytes(b"\x00" * 1024)
    monkeypatch.setattr(extractors, "SIZE_CAP_BYTES", 100)
    blob = extractors.extract(f)
    assert blob["kind"] == "binary"
    assert blob["note"] == "size_cap_exceeded"


# ---------------------------------------------------------------------------
# Shape detection
# ---------------------------------------------------------------------------


def test_detect_shape_writing(tmp_path: Path) -> None:
    files = [
        {"path": "a.md", "kind": "markdown", "size": 100, "mtime_ns": 0},
        {"path": "b.md", "kind": "markdown", "size": 100, "mtime_ns": 0},
        {"path": "c.txt", "kind": "prose", "size": 100, "mtime_ns": 0},
        {"path": "d.png", "kind": "image", "size": 100, "mtime_ns": 0},
    ]
    assert extractors.detect_shape(files) == "writing-shape"


def test_detect_shape_video(tmp_path: Path) -> None:
    files = [
        {"path": "edit.fcpxml", "kind": "video-project", "size": 100, "mtime_ns": 0},
        {"path": "clip1.mp4", "kind": "video", "size": 100, "mtime_ns": 0},
        {"path": "clip2.mp4", "kind": "video", "size": 100, "mtime_ns": 0},
    ]
    assert extractors.detect_shape(files) == "video-editing-shape"


def test_detect_shape_mixed(tmp_path: Path) -> None:
    files = [
        {"path": "a.png", "kind": "image", "size": 100, "mtime_ns": 0},
        {"path": "b.zip", "kind": "archive", "size": 100, "mtime_ns": 0},
        {"path": "c.mp4", "kind": "video", "size": 100, "mtime_ns": 0},
    ]
    # 33% video share, no project file → falls into video-editing because
    # share >= 0.2; if that drifts, the assertion changes — currently 'video-editing-shape'.
    out = extractors.detect_shape(files)
    assert out in {"mixed", "video-editing-shape"}


# ---------------------------------------------------------------------------
# Tool registry skeleton (v1: zero entries unless config exists)
# ---------------------------------------------------------------------------


def test_tool_config_loader_missing_files(tmp_path: Path) -> None:
    # No config files exist → empty registry.
    out = extractors._load_tool_config([tmp_path / "nope.yaml"])
    assert out == {}


def test_tool_config_loader_json_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # PyYAML may or may not be installed; the loader accepts JSON shaped content.
    cfg = tmp_path / "tools.yaml"
    cfg.write_text(json.dumps({"audio": [{"command": "echo {}", "timeout_s": 5}]}))
    out = extractors._load_tool_config([cfg])
    assert "audio" in out
    assert out["audio"][0]["command"] == "echo {}"


def test_run_tools_for_kind_empty_registry(tmp_path: Path) -> None:
    f = tmp_path / "x.md"
    f.write_text("hi")
    out = extractors.run_tools_for_kind("markdown", f, {}, None)
    assert out == {}


def test_run_tools_for_kind_executes_and_caches(tmp_path: Path) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hello")
    cache = tmp_path / "cache"
    cache.mkdir()
    registry = {
        "prose": [
            {
                "name": "echo",
                "command": "printf '%s' '{\"echoed\": \"yes\"}'",
                "timeout_s": 5,
            }
        ]
    }
    out1 = extractors.run_tools_for_kind("prose", f, registry, cache)
    assert out1 == {"extractor.echo.echoed": "yes"}
    # Cache hit: rerun should return the same result without invoking shell.
    cached_files = list(cache.glob("*.json"))
    assert cached_files, "expected a cache file"
    out2 = extractors.run_tools_for_kind("prose", f, registry, cache)
    assert out2 == out1


# ---------------------------------------------------------------------------
# render_blob shape
# ---------------------------------------------------------------------------


def test_render_blob_kind_first(tmp_path: Path) -> None:
    blob = {"kind": "markdown", "title": "X", "headings": ["a", "b"]}
    out = extractors.render_blob(blob)
    assert out.splitlines()[0] == "kind=markdown"
    assert "title=X" in out
    assert 'headings=["a", "b"]' in out

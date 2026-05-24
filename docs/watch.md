# Watch — file & folder ingestion with vector search

`memoir watch` ingests local files (PDFs, Markdown, docx, html, ...) into
memoir and makes them semantically searchable. It complements the existing
`memoir remember` write path: anything you point watch at is parsed,
classified into the same taxonomy, and indexed for vector search.

`memoir search` is the new top-level command that queries the vector index.

## When to use watch vs. remember

- **`memoir remember`** — short, ad-hoc facts and notes you type or paste in.
  Classified by LLM, stored at a taxonomy path. No vector index.
- **`memoir watch`** — bulk ingest of existing files. Each file is parsed
  with markitdown, classified, stored as a memory, *and* indexed for vector
  search by `memoir search`.

## Quick start

```bash
# Create a store (or reuse an existing one)
memoir new ~/.memoir/notes
export MEMOIR_STORE=~/.memoir/notes

# Point watch at a folder of docs
memoir watch add ~/Documents/notes
# → walks the folder, parses each file, classifies, indexes for search

# Or a single file
memoir watch add ~/papers/transformer.pdf -n research

# See what's registered
memoir watch list

# Re-scan (idempotent — only changed files are re-indexed)
memoir watch scan ~/Documents/notes

# Search the indexed content
memoir search "transformer attention mechanism"
memoir search "async patterns" -n research -k 10 --json

# Tear down
memoir watch remove ~/Documents/notes --purge
```

## How it works

For each file under a watched path:

1. **Filter.** Files under `.git`, `node_modules`, `venv`, `__pycache__`,
   `.DS_Store`, `.idea`, `.vscode` are skipped. Unsupported extensions are
   silently skipped (see `memoir watch formats`).
2. **Size guard.** Files larger than `watch:config.max_size_mb` (default
   100 MB) are skipped with a log entry.
3. **Hash.** Content hash (blake3 if installed, otherwise sha256). If the
   hash matches the prior scan, nothing happens — this makes re-scans cheap.
4. **Parse.** `markitdown` extracts plaintext.
5. **Slice + classify.** A single LLM call (`classify_slices_async`) reads
   the document and returns a JSON list of `{start, end, paths, confidence}`
   entries — each is a semantically coherent slice of the file. The pipeline
   does the actual slicing locally using the returned char offsets, so the
   LLM never has to echo verbatim prose. For inputs longer than
   `summarize_max_chars` (default 100 000 chars), the text is windowed into
   non-overlapping chunks; offsets are shifted into global file coordinates
   and re-stitched.
6. **Store per slice.** Each slice is written via `MemoryService.remember`
   under `<primary_path>.s{idx:04d}` (e.g. `knowledge.papers.transformer.s0003`).
   `extra_metadata.source` records `{kind: "watch", abs_path, content_hash,
   slice_index, slice_start, slice_end, slice_primary_path}` so each slice
   is distinguishable from hand-written memories and traces back to the
   original file's exact byte range.
7. **Index per slice.** Each slice is added to the vector index as its own
   prollytree text-index document, keyed by its slice memory key. Semantic
   search therefore returns slice-level hits, not whole-file hits.

Re-scanning a changed file tears down its previous slice keys before
writing the new ones, so the per-slice key namespace never accumulates
orphans across rewrites.

All state (config, registered paths, per-file hashes) lives inside the
memoir store, under the `watch:config`, `watch:paths`, `watch:files` keys
— no sidecar files.

## CLI reference

```
memoir watch add <path> [-n NAMESPACE] [--model MODEL]
memoir watch list
memoir watch scan [path] [-n NAMESPACE] [--model MODEL]
memoir watch remove <path> [--purge]
memoir watch status <path>
memoir watch formats

memoir search <query> [-n NAMESPACE] [-k INT]
```

### Defaults

- **Recursion:** folders are walked recursively.
- **Excludes:** see step 1 above; not user-configurable.
- **Namespace:** `watch` unless `-n` is given.
- **Max file size:** 100 MB (in `watch:config.max_size_mb`). The config
  dict is stored on first scan; to reset to defaults, delete it with
  `memoir forget config -n watch --force` and re-scan.
- **Slice-classify window cap:** 100 000 chars (in
  `watch:config.summarize_max_chars`). Inputs above this are windowed and
  re-stitched, so very long files still go through the single LLM call
  per window without an extra summarize pass.
- **Embedder:** `MiniLmEmbedder` (downloads ~90 MB of model weights on
  first run into `~/.cache/prollytree/embedders/`).
- **LLM model:** resolves via `--model` → `MEMOIR_LLM_MODEL` env →
  `claude-haiku-4-5` default.

## v1 limits

- **Local files only.** No URL / RSS / cloud-storage sources.
- **On-demand scans.** No live filesystem watcher / daemon — re-run
  `memoir watch scan` to pick up changes.
- **Original bytes not stored.** Only the markitdown plaintext (or its
  deterministic summary) is stored. To re-process a file, point watch at
  the original on disk.
- **Vector search is watch-only.** `memoir remember` writes are not added
  to the vector index in v1.
- **Sequential.** Large folders take a while — one LLM classification call
  per changed file. Re-scans skip unchanged files via content hash.

## Installation

Watch requires the `markitdown` extra:

```bash
pip install 'memoir-ai[watch]'
```

The vector index itself comes with the default prollytree wheel — no extra
install needed.

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
5. **Build the content to store.**
    - Short docs (`len(text) ≤ summarize_min_chars`, default 10 000 chars):
      the full plaintext is stored verbatim.
    - Long docs: a **deterministic** summary is built from the document's
      head, tail, and any `#`-style markdown headings. No LLM is involved
      in summarization.
6. **Classify.** The classifier (one LLM call) assigns 1–2 taxonomy paths.
7. **Store.** Via `MemoryService.remember`, with `extra_metadata.source` set
   to `{kind: "watch", abs_path: ..., content_hash: ...}` so the entry is
   distinguishable from hand-written memories.
8. **Index.** The stored content is added to the vector index under the
   primary classified path as the doc id.

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
- **Summarize threshold:** 10 000 chars (in
  `watch:config.summarize_min_chars`).
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

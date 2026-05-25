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

For each watched file:

1. **Size guard.** Files larger than `watch:config.max_size_bytes` (default
   100 000 bytes on disk) are rejected outright. The whole pipeline is
   sized for short documents.
2. **Hash.** Content hash (blake3 if installed, otherwise sha256). If the
   hash matches the prior scan, nothing happens — this makes re-scans cheap.
3. **Parse.** `markitdown` extracts plaintext.
4. **Chunk + summarize.** A single LLM call asks for (a) a one-paragraph
   summary of the whole document, and (b) a list of chunk boundaries sized
   for vector search. Boundaries are reported as verbatim **anchor strings**
   (first / last ~40 chars of each chunk); the pipeline locates them in the
   source text via `str.find` to recover real char offsets. Hard cap of 10
   chunks per file.
5. **Store.** The summary lands at `raw.<file>.summary`; each chunk at
   `raw.<file>.chunk.001`, `.chunk.002`, … under the `watch` namespace via
   `MemoryService.remember`. `extra_metadata.source` records
   `{kind: "watch", abs_path, content_hash, kind_detail, chunk_index,
   chunk_start, chunk_end, ...}` so each entry traces back to its origin.
6. **Index.** Every memory key (summary + chunks) is added to the vector
   index as its own prollytree text-index document. Semantic search returns
   chunk-level hits.

Re-scanning a changed file tears down every previous key — both KV and
vector — before writing the new summary + chunks, so the key namespace
never accumulates orphans across rewrites. The data tree commits once
per file (covering all the puts/deletes + path-registry update); the
vector tree commits once per file as well.

`memoir watch remove --purge <file>` deletes every `raw.<file>.*` key
from both KV and vector and removes the file from the watched-paths
registry.

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

- **Single files only.** Folders are rejected by `watch add` / `watch scan`.
- **Namespace:** `watch` unless `-n` is given.
- **Max file size:** **100 000 bytes** on disk (in
  `watch:config.max_size_bytes`). Files larger than this are rejected.
  The config dict is written on first scan; reset to defaults with
  `memoir forget config -n watch --force` and re-scan.
- **Max chunks per file:** 10 (hard cap in the pipeline; prompt nudges
  toward 1–5).
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

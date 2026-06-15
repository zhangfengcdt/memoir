# Memoir memory provider for Hermes

Give [Hermes](https://github.com/NousResearch/hermes-agent) **versioned,
semantic long-term memory** backed by [memoir](https://github.com/zhangfengcdt/memoir):
a git-like store (branch / commit / merge) over a Prolly-tree, with semantic
paths and cryptographic provenance. Unlike vector-only memory backends, every
write is a commit you can inspect (`memoir log`), attribute (`memoir blame`),
and time-travel.

## How it works

This is a Hermes **memory provider plugin** — a directory under
`$HERMES_HOME/plugins/memoir/`, activated with `memory.provider: memoir`. It
holds no memoir code in-process: it shells out to the `memoir` CLI over a
subprocess bridge, so the plugin is stdlib-only and concurrent captures
self-resolve in the Prolly-tree (no locking).

- **Recall** — `memoir_recall` tool: semantic search over stored facts.
- **Capture** — every turn is auto-extracted (`memoir capture --profile
  assistant`) on a background thread; durable facts (preferences, people,
  schedule, standing instructions) are committed, ephemera are dropped.
- **Remember** — `memoir_remember` tool for explicit, durable facts (with a
  secret-content guard).
- **Mirror** — Hermes's built-in `MEMORY.md` / `USER.md` edits are mirrored
  into versioned memoir paths via `on_memory_write`.
- **Status / UI** — `hermes memoir status`, `hermes memoir ui`.

## Install

1. Install the memoir CLI (the plugin auto-falls back to a pinned `uvx` if
   absent, but a direct install is faster):

   ```bash
   pip install memoir-ai      # or: pipx install memoir-ai / uv tool install memoir-ai
   ```

2. Install the plugin into your Hermes home, then activate it:

   ```bash
   # From a checkout of zhangfengcdt/memoir:
   cp -r plugins/hermes ~/.hermes/plugins/memoir
   # …or via the plugin installer (git subdir):
   hermes plugins install zhangfengcdt/memoir/tree/main/plugins/hermes

   hermes config set memory.provider memoir
   ```

   > Hermes allows **one** external memory provider at a time — activating
   > memoir displaces any other (`mem0`, `honcho`, …). The built-in
   > `MEMORY.md` layer is unaffected.

3. The store is created automatically on first run at
   `<hermes_home>/memoir-store` (override with `store_path` in
   `<hermes_home>/memoir.json`).

## Config (`<hermes_home>/memoir.json`)

| key          | default                      | meaning                              |
|--------------|------------------------------|--------------------------------------|
| `store_path` | `<hermes_home>/memoir-store` | store location                       |
| `capture`    | `true`                       | auto-capture facts from each turn    |
| `model`      | host's selected model        | pin the capture/classification model; empty = follow Hermes `model.default` |

## LLM backend

The plugin drives memoir with its **litellm (direct provider API) backend
only** — it never shells out to the `claude` CLI. All extraction and
classification run on the **host-selected model** (Hermes `model.default`,
tracked across mid-session switches), or an explicit `model` pin. memoir reads
the provider credentials from the Hermes process environment (e.g.
`ANTHROPIC_API_KEY` in `<hermes_home>/.env`); if the selected model's provider
key is missing, capture fails loudly rather than silently switching backends.

## Verify

```bash
hermes memoir status
memoir -s <hermes_home>/memoir-store summarize --depth 3
memoir -s <hermes_home>/memoir-store blame <path>   # provenance
```

## Notes / limits (v1)

- Local store only. Multi-device sync (the merge-based wedge) is future work
  and needs a `memoir remote` story.
- Recall is LLM-free (summarize→get), so it's fast and works even without a
  provider key. Auto-capture and explicit `memoir_remember` classification do
  need the host provider's key in the Hermes env.
- Pinned `memoir-ai` fallback version: see `MEMOIR_AI_PIN` in `bridge.py`.

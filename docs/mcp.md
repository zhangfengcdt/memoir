# MCP Server

Memoir ships an **MCP server** (`memoir-mcp`) built on the official
[Model Context Protocol](https://modelcontextprotocol.io) SDK. Point any MCP host
at it — Claude Desktop, Cursor, Cline, Windsurf, VS Code (Copilot), Zed,
Continue, LibreChat, … — and that agent gains **git-versioned, taxonomy-structured
memory**, including the tools no other memory server has: `memoir_branches`,
`memoir_checkout`, and `memoir_commits` (branch / checkout / provenance over your
memory).

One server, one store, every host: your memory follows you across tools.

## Install & run

The server is an optional extra (it pulls in the MCP SDK):

```bash
pip install "memoir-ai[mcp]"        # or: pipx install "memoir-ai[mcp]"
```

Run it (stdio is the default transport):

```bash
MEMOIR_STORE=~/.memoir/mcp memoir-mcp
```

You don't have to install anything — every config below uses **`uvx`**, which
fetches and runs it on demand:

```bash
uvx --from "memoir-ai[mcp]" memoir-mcp
```

- **Store path** — `MEMOIR_STORE`, or `--store <path>`, defaulting to
  `~/.memoir/mcp`. The store is **created automatically** on first use, so a
  fresh install works with zero setup.
- **Recall is keyless by default** (`mode="lexical"`) — fast LLM-free keyword
  ranking, no API key needed (consistent with the Hermes/OpenClaw plugins). For
  smarter recall on large stores, opt into the LLM modes `single` / `tiered`
  (need a provider key). See [LLM-driven remember & recall](#llm-driven-remember-recall).

## Connect your host

Most hosts use the same `mcpServers` block — only the **file** and a couple of
**key names** differ.

### Claude Desktop, Cursor, Cline, Windsurf

These all use an `mcpServers` map. Add:

```json
{
  "mcpServers": {
    "memoir": {
      "command": "uvx",
      "args": ["--from", "memoir-ai[mcp]", "memoir-mcp"],
      "env": { "MEMOIR_STORE": "~/.memoir/mcp" }
    }
  }
}
```

| Host | Where |
|---|---|
| **Claude Desktop** | `claude_desktop_config.json` (Settings → Developer → Edit Config) — or install the one-click `.mcpb` (see [below](#claude-desktop-one-click-mcpb)) |
| **Cursor** | `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (per-project) |
| **Cline** | Cline panel → **MCP Servers → Configure** (`cline_mcp_settings.json`) |
| **Windsurf** | `~/.codeium/windsurf/mcp_config.json` |

### VS Code (GitHub Copilot)

VS Code uses a top-level **`servers`** key in `.vscode/mcp.json`:

```json
{
  "servers": {
    "memoir": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "memoir-ai[mcp]", "memoir-mcp"],
      "env": { "MEMOIR_STORE": "${userHome}/.memoir/mcp" }
    }
  }
}
```

### Zed

Zed uses **`context_servers`** with a nested `command` in `settings.json`:

```json
{
  "context_servers": {
    "memoir": {
      "command": { "path": "uvx", "args": ["--from", "memoir-ai[mcp]", "memoir-mcp"] }
    }
  }
}
```

### Continue / LibreChat (YAML)

`config.yaml` (Continue) / `librechat.yaml` (LibreChat):

```yaml
mcpServers:
  memoir:
    command: uvx
    args: ["--from", "memoir-ai[mcp]", "memoir-mcp"]
    env:
      MEMOIR_STORE: ~/.memoir/mcp
```

> Schemas drift between releases — if a host rejects the snippet, check its own
> MCP docs for the current shape; the `command` / `args` / `env` triple is the
> constant.

## Remote / web connectors (ChatGPT, Claude.ai)

The hosted web tiers connect over HTTP, not stdio. Run the server with
Streamable HTTP and point the connector at it:

```bash
memoir-mcp --http --host 0.0.0.0 --port 8000     # serves at /mcp
```

Then add it as a custom/remote connector with the URL `http://<host>:8000/mcp`.
(For anything internet-facing, terminate TLS and add auth at your proxy.)

## LLM-driven remember & recall

Memoir's edge is **intelligent** memory: `memoir_remember` classifies each fact
into the right semantic taxonomy path with an LLM, and `memoir_recall` can use
the LLM to navigate that taxonomy — not just keyword matching.

`memoir_remember` is **always** LLM-driven, so it needs a provider key in the
server's `env`. `memoir_recall` defaults to keyless `lexical`; to make the LLM
modes the default, set `MEMOIR_MCP_RECALL_MODE` (or pass `mode` per call):

```json
{
  "mcpServers": {
    "memoir": {
      "command": "uvx",
      "args": ["--from", "memoir-ai[mcp]", "memoir-mcp"],
      "env": {
        "MEMOIR_STORE": "~/.memoir/mcp",
        "ANTHROPIC_API_KEY": "sk-ant-…",
        "MEMOIR_LLM_MODEL": "claude-haiku-4-5",
        "MEMOIR_MCP_RECALL_MODE": "single"
      }
    }
  }
}
```

### Recommended recall flow (caller-driven drill)

The default, most accurate recall lets **the host model pick what to read** — no
extra LLM inside memoir, no API key:

1. `memoir_summarize` → see the stored taxonomy paths (a histogram).
2. The model chooses the paths relevant to the question.
3. `memoir_get` those exact paths → the values.

For a large store, summarize at `depth=1`, pick a top-level prefix, then
`memoir_summarize(prefix="…")` to narrow before getting keys. This mirrors
memoir's `[mode=drill]` and the Hermes/OpenClaw plugins, and the server's
`instructions` steer hosts to it by default.

`memoir_recall` is the one-shot shortcut when you don't want to drill — its modes
are below.

### Recall modes

`memoir_recall` takes a `mode` (the model can pass it per call; the default is
set by `MEMOIR_MCP_RECALL_MODE`):

| `mode` | How it works | Latency | Key? |
|---|---|---|---|
| `lexical` (default) | LLM-free keyword ranking over the structured paths. The calling agent (already an LLM) reasons over the results — same approach as the plugins. | instant | no |
| `single` | One LLM call selects the most relevant taxonomy paths, then fetches them. | ~500–800ms | yes |
| `tiered` | **Multi-level LLM drill-down** (L1 histogram → L1 pick → optional L2 → key pick → fetch). Narrower prompts; scales to large/noisy stores. | ~1–2s | yes |

The two LLM modes mirror the `memoir recall` CLI:

```bash
memoir recall "what's my testing setup?"                # single (default)
memoir recall "what's my testing setup?" --mode tiered  # multi-level drill-down
```

`single`/`tiered` need a provider key; if none is available they **fall back to
`lexical`**, so recall never hard-fails (and a keyless install still works).

### Env vars

| Env var | Effect |
|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / … | Provider key for classification + LLM recall. **`memoir_remember` needs one** to auto-classify (or pass an explicit `path` to skip it, keyless). Routed by model name. |
| `MEMOIR_LLM_MODEL` | Model for classification/recall (default `claude-haiku-4-5` — fast + cheap). |
| `MEMOIR_LLM_BASE_URL` | Route LLM calls through a proxy/gateway. |
| `MEMOIR_MCP_RECALL_MODE` | Default recall mode: `lexical` (default), `single`, or `tiered`. |

> The key lives in your host's MCP config (often plaintext on disk) — use a
> least-privilege key. `claude-haiku-4-5` keeps cost negligible.

## Tools

| Tool | Read-only | Purpose |
|---|---|---|
| `memoir_summarize` | ✓ | List stored paths as a histogram grouped by the first `depth` taxonomy segments. **Step 1 of recall** — the model reads this and picks relevant paths. `prefix` narrows a branch. LLM-free. |
| `memoir_get` | ✓ | Fetch the exact memories at the given paths/keys. **Step 2 of recall** — the model passes the keys it chose. LLM-free. |
| `memoir_recall` | ✓ | One-shot recall shortcut. `mode`: `lexical` (default, keyless keyword ranking) · `single` (LLM path-selection) · `tiered` (multi-level LLM drill-down). |
| `memoir_remember` | | Store a durable fact **verbatim**, committed with versioning. Auto-classified into a semantic path (needs a key), or pass an explicit `path` to skip classification (keyless). Secrets/credentials are refused. |
| `memoir_forget` | | Delete a memory by key (prior versions stay in git history). |
| `memoir_status` | ✓ | Branch, commit count, memory count. |
| `memoir_branches` | ✓ | List branches — **versioned memory**. |
| `memoir_checkout` | | Switch/create a branch or commit. |
| `memoir_commits` | ✓ | Commit history — **provenance / blame**. |

Tools carry MCP annotations (`readOnlyHint` / `destructiveHint`) so hosts can
surface safety hints.

## Claude Desktop one-click (.mcpb)

A Claude Desktop **Desktop Extension** manifest lives at
[`packaging/mcp/manifest.json`](https://github.com/zhangfengcdt/memoir/tree/main/packaging/mcp)
— build it into a `.mcpb` for double-click install (no JSON editing). See that
folder's README for the build/publish steps and the official MCP Registry
`server.json`.

## Notes

- **Versioning is the differentiator.** Unlike vector-only memory servers, every
  write is a commit; `memoir_branches` / `memoir_checkout` / `memoir_commits`
  expose branch/merge and `blame`-style provenance over memory.
- **Bespoke plugins go deeper.** The [Claude Code](claude_code.md),
  [Codex](codex.md), [Hermes](hermes.md), and [OpenClaw](openclaw.md) plugins add
  *automatic* capture + recall via host hooks; MCP is tool-only (the model must
  call the tools) but reaches every host with zero per-host code.

## See also

- [CLI](cli.md) — the underlying `memoir` commands the tools wrap.
- [Architecture](architecture.md) — how memoir is structured under the hood.

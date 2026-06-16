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
- **Recall is LLM-free by default** (fast, no API key). `memoir_remember`
  classifies content with an LLM, so it needs a provider key
  (e.g. `ANTHROPIC_API_KEY`) in the server's environment; `memoir_recall` with
  `semantic=true` also does.

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

Memoir's edge is **intelligent** memory: `remember` classifies content into the
right semantic taxonomy path with an LLM, and recall can do LLM **semantic**
search — not just keyword matching. The MCP server uses these the moment you
give it a model + key in its environment.

**To enable it, add the provider key (and optionally the model) to the server's
`env`** in your host config:

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
        "MEMOIR_MCP_SEMANTIC_RECALL": "1"
      }
    }
  }
}
```

What each does:

| Env var | Effect |
|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / … | The provider key memoir uses for classification + semantic search. **`memoir_remember` requires one** (it classifies into a taxonomy path); without it, remember fails. memoir routes by model name. |
| `MEMOIR_LLM_MODEL` | Which model does the classification/search (default `claude-haiku-4-5` — fast + cheap, ideal for this). |
| `MEMOIR_LLM_BASE_URL` | Route the LLM calls through a proxy/gateway. |
| `MEMOIR_MCP_SEMANTIC_RECALL` | `1` makes `memoir_recall` default to **LLM semantic search**. Otherwise recall is LLM-free (lexical) by default and the model opts in per call with `semantic=true`. |

So:

- **`memoir_remember` is always LLM-driven** — give the server a key and it
  classifies + commits to a semantic path. No key → it errors (by design, rather
  than storing under a guessed path).
- **`memoir_recall` is LLM-free by default** (fast, keyless), and becomes
  LLM-semantic either per-call (`semantic=true`) or globally
  (`MEMOIR_MCP_SEMANTIC_RECALL=1`).

> The key lives in your host's MCP config (often plaintext on disk) — use a
> least-privilege key. The default `claude-haiku-4-5` keeps classification cost
> negligible.

## Tools

| Tool | Read-only | Purpose |
|---|---|---|
| `memoir_recall` | ✓ | Recall stored facts. LLM-free by default (lexical ranking); `semantic=true` for LLM search. |
| `memoir_remember` | | Store a fact; auto-classified into a semantic path and committed. Needs a provider key. |
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

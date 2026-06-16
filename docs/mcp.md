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

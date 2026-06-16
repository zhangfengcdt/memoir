# Memoir MCP — packaging & distribution

Artifacts for distributing the `memoir-mcp` server. **These are drafts** — the
`.mcpb` and registry schemas evolve, so validate each one with its official tool
before submitting. All listings are outward-facing and need maintainer accounts.

Run/connect docs (per host) live in [`docs/mcp.md`](../../docs/mcp.md).

## Files

| File | For | Validate / publish with |
|---|---|---|
| `manifest.json` | Claude Desktop **Desktop Extension** (`.mcpb`, one-click install) | `npx @anthropic-ai/mcpb validate manifest.json` → `npx @anthropic-ai/mcpb pack` |
| `server.json` | **Official MCP Registry** listing | `mcp-publisher validate` → `mcp-publisher publish` |

## Build the `.mcpb` (Claude Desktop)

```bash
cd packaging/mcp
npx @anthropic-ai/mcpb validate manifest.json
npx @anthropic-ai/mcpb pack .            # → memoir.mcpb (double-click to install)
```

The manifest runs the server via `uvx --from "memoir-ai[mcp]" memoir-mcp`, so the
end user needs `uv` on PATH (no Python env to bundle). The store path is a
`user_config` field (`directory`), defaulting to `~/.memoir/mcp`.

## Publish to the MCP Registry

```bash
# authenticate as the io.github.zhangfengcdt namespace owner, then:
mcp-publisher validate    # against server.json
mcp-publisher publish
```

Verify before publishing: that the registry's `pypi` + `runtime_hint: uvx` path
resolves the `[mcp]` extra and the `memoir-mcp` console script (extras handling in
the registry's runtime resolution is the thing most likely to need a tweak).

## Other registries (manual, lower effort)

- **Glama** (glama.ai/mcp) — auto-indexes public GitHub MCP servers; submit the repo.
- **Smithery** (smithery.ai) — add a `smithery.yaml`; supports hosted runs.
- **Cline MCP Marketplace** — PR to `cline/mcp-marketplace`.
- **PulseMCP**, **mcp.so**, **awesome-mcp-servers** — list entries.

Lead every listing with the differentiator: **git-versioned memory**
(`memoir_branches` / `memoir_checkout` / `memoir_commits`) and **one store across
every MCP host** — the wedge vs vector-only memory servers.

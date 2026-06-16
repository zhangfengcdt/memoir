# Plugin Docker smoke tests

Throwaway containers that install each agent host + the memoir plugin from
scratch and verify the integration in a clean environment. **These are test
harnesses, not plugins** — they live outside the plugin directories so they're
never bundled into an install (`hermes plugins install` / the Claude Code /
Codex marketplaces copy the plugin subdir verbatim, with no filtering).

| Host | Folder | Verifies |
|---|---|---|
| Hermes | [`hermes/`](hermes/) | install via `owner/repo/subdir` → provider load → tools → `/memoir` → real auto-capture |
| Claude Code | [`claude-code/`](claude-code/) | CLI + plugin present → memoir CLI resolution → store creation → capture |
| Codex | [`codex/`](codex/) | CLI + plugin present → memoir CLI resolution → store creation → capture |

Each folder has a `Dockerfile`, a `test.sh`, and a `README.md`. General shape:

```bash
docker build -t memoir-<host>-test plugins/docker-tests/<host>
docker run --rm -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
    -v "$PWD/plugins/docker-tests/<host>/test.sh:/test.sh:ro" \
    memoir-<host>-test bash /test.sh
```

Only the capture step calls an LLM (hence `ANTHROPIC_API_KEY`); everything else
runs offline.

**Scope note.** Hermes exposes a programmatic `MemoryProvider`, so its harness
drives the real provider + tools end-to-end. The Claude Code and Codex plugins
are bash hooks/skills that shell out to `memoir` inside an interactive,
auth-gated agent session — so those harnesses verify the *deterministic* memoir
plumbing the plugins depend on (CLI resolution, store creation, capture) rather
than a full live hook-driven turn.

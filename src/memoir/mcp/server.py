# SPDX-License-Identifier: Apache-2.0
"""
Memoir MCP server (built on the official ``mcp`` SDK / FastMCP).

Exposes memoir over the Model Context Protocol so any MCP host — Claude Desktop,
Cursor, Cline, Windsurf, Zed, Continue, LibreChat, … — gets git-versioned,
taxonomy-structured memory, including the differentiating ``memoir_branches`` /
``memoir_checkout`` / ``memoir_commits`` versioning tools.

Install:  pip install "memoir-ai[mcp]"
Run:      MEMOIR_STORE=/path/to/store memoir-mcp          # stdio (default)
          memoir-mcp --http --host 127.0.0.1 --port 8000  # Streamable HTTP

Recall is **LLM-free by default** (enumerate keys → batched direct get →
lexical ranking), so it's fast and needs no API key. ``semantic=true`` opts into
the LLM-backed search. ``memoir_remember`` classifies content with the LLM, so
it needs a provider key (e.g. ``ANTHROPIC_API_KEY``) in the server environment.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Default store when ``MEMOIR_STORE`` is unset — keeps one-click installs zero-config.
DEFAULT_STORE = os.path.join(os.path.expanduser("~"), ".memoir", "mcp")

#: Namespaces excluded from recall (internal, not user facts).
_RECALL_EXCLUDE_NS = {"taxonomy"}


def _version() -> str:
    # ``memoir.__version__`` is the single source of truth (read by hatch for
    # packaging); prefer it over importlib.metadata, which can be stale in
    # editable installs.
    try:
        from memoir import __version__

        return __version__
    except Exception:
        try:
            from importlib.metadata import version

            return version("memoir-ai")
        except Exception:
            return "0"


def resolve_store_path() -> str:
    """Store path: ``MEMOIR_STORE`` env, else the zero-config default."""
    return os.environ.get("MEMOIR_STORE") or DEFAULT_STORE


def ensure_store(store_path: str) -> None:
    """Create the store if it doesn't exist yet (idempotent)."""
    if (Path(store_path) / ".git").exists():
        return
    from memoir.services.store_service import StoreService

    Path(store_path).parent.mkdir(parents=True, exist_ok=True)
    result = StoreService().create_store(store_path)
    if not getattr(result, "success", True):
        raise RuntimeError(
            f"Failed to create store at {store_path}: {getattr(result, 'error', '?')}"
        )


# ---------------------------------------------------------------------------
# Tool logic — pure functions over the service layer. Import-safe (no ``mcp``
# dependency) so they're unit-testable without the SDK installed.
# ---------------------------------------------------------------------------


def _memory_service(store_path: str):
    from memoir.services.memory_service import MemoryService

    return MemoryService(store_path)


def _branch_service(store_path: str):
    from memoir.services.branch_service import BranchService

    return BranchService(store_path)


def _store_service(store_path: str | None = None):
    from memoir.services.store_service import StoreService

    return StoreService(store_path)


def _content_of(value: Any) -> str:
    """Extract the human-readable content from a stored value."""
    if isinstance(value, dict):
        return str(value.get("content", value))
    return str(value)


def recall(
    store_path: str, query: str, limit: int = 10, namespace: str | None = None
) -> dict:
    """LLM-free recall: enumerate keys → batched get → lexical ranking."""
    svc = _store_service(store_path)
    data = svc.read_store()
    all_ns: dict[str, list[str]] = data.get("namespaces", {})
    if namespace:
        targets = {namespace: all_ns.get(namespace, [])}
    else:
        targets = {
            ns: keys for ns, keys in all_ns.items() if ns not in _RECALL_EXCLUDE_NS
        }

    mem = _memory_service(store_path)
    rows: list[dict] = []
    for ns, keys in targets.items():
        keys = [k for k in keys if not k.startswith("metrics.")]
        if not keys:
            continue
        result = mem.get(keys, namespace=ns)
        items = getattr(result, "items", None) or []
        for it in items:
            if not it.get("found"):
                continue
            content = _content_of(it.get("value"))
            rows.append({"key": it["key"], "namespace": ns, "content": content})

    tokens = [t for t in query.lower().split() if t] if query else []
    if tokens:

        def score(row: dict) -> int:
            hay = f"{row['key']} {row['content']}".lower()
            return sum(1 for t in tokens if t in hay)

        ranked = sorted(rows, key=score, reverse=True)
        ranked = [r for r in ranked if score(r) > 0] or rows
    else:
        ranked = rows
    return {
        "success": True,
        "query": query,
        "count": len(ranked[:limit]),
        "memories": ranked[:limit],
    }


async def recall_semantic(
    store_path: str, query: str, limit: int = 10, namespace: str | None = None
) -> dict:
    """LLM-backed semantic recall (opt-in; needs a provider key)."""
    mem = _memory_service(store_path)
    result = await mem.recall(query, limit=limit, namespace=namespace)
    return {
        "success": result.success,
        "memories": result.memories,
        "timing_ms": result.timing_ms,
    }


async def remember(store_path: str, content: str, namespace: str = "default") -> dict:
    """Store content, auto-classified into a semantic path (needs a provider key)."""
    result = await _memory_service(store_path).remember(content, namespace)
    return {
        "success": result.success,
        "key": result.key,
        "confidence": result.confidence,
        "reasoning": result.reasoning,
        "commit": result.commit_hash,
    }


async def forget(store_path: str, key: str, namespace: str = "default") -> dict:
    result = await _memory_service(store_path).forget(key, namespace)
    return {"success": result.success, "key": result.key, "commit": result.commit_hash}


def status(store_path: str) -> dict:
    return _store_service(store_path).get_status().to_dict()


def branches(store_path: str) -> dict:
    info = _branch_service(store_path).list_branches()
    return {"branches": info.branches, "current": info.current}


def checkout(store_path: str, target: str, create: bool = False) -> dict:
    result = _branch_service(store_path).checkout(target, create=create)
    return {
        "success": result.success,
        "branch": result.branch,
        "commit": result.commit,
        "created": result.created,
    }


def commits(store_path: str, limit: int = 10) -> dict:
    items = _branch_service(store_path).get_commits("HEAD", limit=limit)
    return {"commits": [c.to_dict() for c in items]}


# ---------------------------------------------------------------------------
# FastMCP server assembly (lazy ``mcp`` import — only when the server runs).
# ---------------------------------------------------------------------------


def build_server(store_path: str):
    """Construct a FastMCP server exposing the memoir tools for ``store_path``."""
    try:
        from mcp.server.fastmcp import FastMCP
        from mcp.types import ToolAnnotations
    except ModuleNotFoundError as e:  # pragma: no cover - exercised via main()
        raise SystemExit(
            "The MCP SDK is not installed. Install it with:\n"
            '    pip install "memoir-ai[mcp]"\n'
            "or run via uvx:\n"
            '    uvx --from "memoir-ai[mcp]" memoir-mcp'
        ) from e

    server = FastMCP(
        "memoir",
        instructions=(
            "Git-versioned, taxonomy-structured long-term memory. Recall stored facts "
            "before answering when prior context helps; remember durable new facts. "
            "Memory is branchable and every write is a commit (provenance via memoir_commits)."
        ),
    )
    # FastMCP reports the SDK version by default; surface memoir's instead.
    with contextlib.suppress(Exception):  # private attr, best-effort
        server._mcp_server.version = _version()
    ro = ToolAnnotations(readOnlyHint=True)
    destructive = ToolAnnotations(readOnlyHint=False, destructiveHint=True)

    @server.tool(
        name="memoir_recall",
        description=(
            "Recall stored memories. LLM-free by default (fast, no API key): "
            "ranks stored facts by lexical overlap with the query. Set semantic=true "
            "for LLM-backed search."
        ),
        annotations=ro,
    )
    async def memoir_recall(
        query: str,
        limit: int = 10,
        namespace: str | None = None,
        semantic: bool = False,
    ) -> dict:
        if semantic:
            return await recall_semantic(
                store_path, query, limit=limit, namespace=namespace
            )
        return recall(store_path, query, limit=limit, namespace=namespace)

    @server.tool(
        name="memoir_remember",
        description=(
            "Store content in memory. It is auto-classified into a semantic path and "
            "committed with git versioning. Requires a provider API key for classification."
        ),
    )
    async def memoir_remember(content: str, namespace: str = "default") -> dict:
        return await remember(store_path, content, namespace=namespace)

    @server.tool(
        name="memoir_forget",
        description="Delete a memory by its exact key/path. Prior versions remain in git history.",
        annotations=destructive,
    )
    async def memoir_forget(key: str, namespace: str = "default") -> dict:
        return await forget(store_path, key, namespace=namespace)

    @server.tool(
        name="memoir_status",
        description="Status of the connected memory store (branch, commit count, memory count).",
        annotations=ro,
    )
    def memoir_status() -> dict:
        return status(store_path)

    @server.tool(
        name="memoir_branches",
        description="List all branches in the memory store (git-versioned memory).",
        annotations=ro,
    )
    def memoir_branches() -> dict:
        return branches(store_path)

    @server.tool(
        name="memoir_checkout",
        description="Switch to a branch or commit, optionally creating the branch.",
    )
    def memoir_checkout(target: str, create: bool = False) -> dict:
        return checkout(store_path, target, create=create)

    @server.tool(
        name="memoir_commits",
        description="Commit history for the memory store (provenance / blame).",
        annotations=ro,
    )
    def memoir_commits(limit: int = 10) -> dict:
        return commits(store_path, limit=limit)

    return server


def main() -> None:
    """Entry point for the ``memoir-mcp`` console script."""
    parser = argparse.ArgumentParser(
        prog="memoir-mcp", description="Memoir MCP server (versioned semantic memory)."
    )
    parser.add_argument(
        "--store", help="Store path (default: $MEMOIR_STORE or ~/.memoir/mcp)."
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Serve over Streamable HTTP instead of stdio.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP host (with --http).")
    parser.add_argument(
        "--port", type=int, default=8000, help="HTTP port (with --http)."
    )
    parser.add_argument(
        "--version", action="version", version=f"memoir-mcp {_version()}"
    )
    args = parser.parse_args()

    store_path = args.store or resolve_store_path()
    ensure_store(store_path)
    server = build_server(store_path)

    if args.http:
        server.settings.host = args.host
        server.settings.port = args.port
        server.run(transport="streamable-http")
    else:
        server.run()  # stdio


if __name__ == "__main__":
    main()

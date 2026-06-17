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

Recall has three modes: ``lexical`` (default) — LLM-free keyword ranking,
instant and keyless; ``single`` — one LLM call to pick the most relevant
taxonomy paths; ``tiered`` — multi-level LLM drill-down for large stores.
single/tiered use memoir's IntelligentSearchEngine and need a provider key (e.g.
``ANTHROPIC_API_KEY``), falling back to lexical if none is available. Set the
default with ``MEMOIR_MCP_RECALL_MODE``. ``memoir_remember`` always classifies
content with the LLM, so it needs a key.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

#: Default store when ``MEMOIR_STORE`` is unset — keeps one-click installs zero-config.
DEFAULT_STORE = os.path.join(os.path.expanduser("~"), ".memoir", "mcp")

#: Namespaces excluded from recall (internal, not user facts).
_RECALL_EXCLUDE_NS = {"taxonomy"}

#: Secret-content guard for memoir_remember (mirrors the Hermes/OpenClaw plugins).
#: Memory is versioned plaintext — refuse obvious credentials.
_SECRET_PATTERNS = [
    re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9]{16,}\b"),  # OpenAI/Stripe-style keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),  # GitHub tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),  # Slack tokens
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),  # PEM private keys
    re.compile(r"\b\d{13,16}\b"),  # bare long digit runs (card-ish)
    re.compile(r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*\S+"),
]


def _looks_like_secret(content: str) -> bool:
    return any(p.search(content) for p in _SECRET_PATTERNS)


#: Recall modes: lexical (LLM-free), single (one LLM call), tiered (multi-level
#: LLM drill-down). single/tiered map to memoir's IntelligentSearchEngine.
RECALL_MODES = ("lexical", "single", "tiered")


def default_recall_mode() -> str:
    """Default recall mode, from MEMOIR_MCP_RECALL_MODE (else 'lexical').

    Defaults to the LLM-free 'lexical' path — keyless, instant, and consistent
    with the Hermes/OpenClaw plugins (the calling agent is already an LLM, so an
    in-memoir LLM pass is usually redundant). 'single'/'tiered' are opt-in.
    """
    m = os.environ.get("MEMOIR_MCP_RECALL_MODE", "").strip().lower()
    if m in RECALL_MODES:
        return m
    # Back-compat: the earlier boolean knob meant "use LLM semantic recall".
    if os.environ.get("MEMOIR_MCP_SEMANTIC_RECALL", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return "single"
    return "lexical"


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


def summarize(
    store_path: str,
    depth: int = 3,
    namespace: str | None = None,
    prefix: str | None = None,
    include_metrics: bool = False,
) -> dict:
    """Taxonomy histogram for caller-driven drill: keys grouped by the first
    ``depth`` segments. At depth 3 (memoir paths are 3 levels) the groups are the
    full keys, ready to pass to ``memoir_get``. ``prefix`` narrows to one branch
    (e.g. ``"preferences"``). LLM-free.
    """
    svc = _store_service(store_path)
    all_ns: dict[str, list[str]] = svc.read_store().get("namespaces", {})
    targets = (
        {namespace: all_ns.get(namespace, [])}
        if namespace
        else {ns: keys for ns, keys in all_ns.items() if ns not in _RECALL_EXCLUDE_NS}
    )
    out: dict[str, dict[str, int]] = {}
    for ns, keys in targets.items():
        if prefix:
            keys = [k for k in keys if k == prefix or k.startswith(prefix + ".")]
        if not include_metrics:
            keys = [k for k in keys if not k.startswith("metrics.")]
        if not keys:
            continue
        counts: dict[str, int] = {}
        for k in keys:
            segs = k.split(".")
            group = ".".join(segs[:depth]) if len(segs) >= depth else k
            counts[group] = counts.get(group, 0) + 1
        out[ns] = dict(sorted(counts.items()))
    total = sum(sum(c.values()) for c in out.values())
    return {"depth": depth, "prefix": prefix, "total": total, "namespaces": out}


def get_memories(store_path: str, keys: list[str], namespace: str = "default") -> dict:
    """Batched exact-path lookup (LLM-free). Missing keys come back found=False."""
    res = _memory_service(store_path).get(keys, namespace=namespace)
    items = getattr(res, "items", None) or []
    return {
        "items": [
            {
                "key": it["key"],
                "namespace": namespace,
                "found": bool(it.get("found")),
                "content": _content_of(it.get("value")) if it.get("found") else None,
            }
            for it in items
        ]
    }


async def recall_semantic(
    store_path: str,
    query: str,
    limit: int = 10,
    namespace: str | None = None,
    mode: str = "single",
) -> dict:
    """LLM-driven recall via memoir's IntelligentSearchEngine.

    ``mode="single"`` — one LLM call (path discovery → LLM path selection →
    fetch), ~500-800ms. ``mode="tiered"`` — multi-level drill-down (L1 histogram
    → L1 pick → optional L2 → key pick → fetch), narrower prompts, ~1-2s, scales
    to large stores. Both need a provider key in the environment.
    """
    mem = _memory_service(store_path)
    result = await mem.recall(query, limit=limit, namespace=namespace, mode=mode)
    if not result.success:
        # e.g. missing provider key — raise so the caller can fall back to lexical.
        raise RuntimeError(getattr(result, "error", None) or "recall failed")
    return {
        "success": result.success,
        "memories": result.memories,
        "timing_ms": result.timing_ms,
        "mode": mode,
    }


async def remember(
    store_path: str, content: str, namespace: str = "default", path: str | None = None
) -> dict:
    """Store content as a durable fact. Auto-classified into a semantic path
    (needs a provider key) unless an explicit ``path`` is given (no LLM).
    Refuses obvious secrets — memory is versioned plaintext.
    """
    if _looks_like_secret(content):
        return {
            "success": False,
            "error": (
                "Refused: the content looks like a secret/credential. Memory is "
                "versioned and stored in plaintext — use a secrets manager instead."
            ),
        }
    result = await _memory_service(store_path).remember(content, namespace, path=path)
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
            "Git-versioned, taxonomy-structured long-term memory.\n"
            "RECALL — preferred flow (you pick what to read): call memoir_summarize to "
            "see the stored taxonomy paths, choose the ones relevant to the question, then "
            "memoir_get those exact paths. For a large store, summarize at depth 1 first, "
            "pick a top-level prefix, then summarize that prefix before getting keys. "
            "memoir_recall is a one-shot shortcut when you don't want to drill.\n"
            "Remember durable new facts with memoir_remember. Memory is branchable and "
            "every write is a commit (provenance via memoir_commits)."
        ),
    )
    # FastMCP reports the SDK version by default; surface memoir's instead.
    with contextlib.suppress(Exception):  # private attr, best-effort
        server._mcp_server.version = _version()
    ro = ToolAnnotations(readOnlyHint=True)
    destructive = ToolAnnotations(readOnlyHint=False, destructiveHint=True)

    default_mode = default_recall_mode()

    @server.tool(
        name="memoir_recall",
        description=(
            "One-shot recall shortcut. Prefer memoir_summarize → memoir_get (you pick the "
            "paths) for best results; use this when you just want a quick lookup. Modes: "
            "'lexical' (default) — LLM-free keyword ranking, instant, no key; 'single' — one "
            "LLM call picks paths, ~500-800ms; 'tiered' — multi-level LLM drill-down for "
            "large/noisy stores, ~1-2s. single/tiered need a provider key and fall back to "
            "lexical if unavailable. Default settable via MEMOIR_MCP_RECALL_MODE."
        ),
        annotations=ro,
    )
    async def memoir_recall(
        query: str,
        limit: int = 10,
        namespace: str | None = None,
        mode: Literal["lexical", "single", "tiered"] = default_mode,
    ) -> dict:
        if mode == "lexical":
            return recall(store_path, query, limit=limit, namespace=namespace)
        try:
            return await recall_semantic(
                store_path, query, limit=limit, namespace=namespace, mode=mode
            )
        except Exception as e:
            # Graceful degradation (e.g. no provider key): fall back to the
            # LLM-free path so recall always works.
            logger.warning(
                "semantic recall (%s) failed, falling back to lexical: %s", mode, e
            )
            out = recall(store_path, query, limit=limit, namespace=namespace)
            out["mode"] = "lexical"
            out["fellback_from"] = mode
            return out

    @server.tool(
        name="memoir_summarize",
        description=(
            "List stored memory paths as a histogram grouped by the first `depth` "
            "taxonomy segments (LLM-free, instant). Step 1 of the preferred recall flow: "
            "read this, pick the paths relevant to the question, then memoir_get them. "
            "depth=3 returns full keys; for a large store use depth=1, pick a top-level "
            "prefix, then call again with that `prefix` to narrow before getting keys."
        ),
        annotations=ro,
    )
    def memoir_summarize(
        depth: int = 3, namespace: str | None = None, prefix: str | None = None
    ) -> dict:
        return summarize(store_path, depth=depth, namespace=namespace, prefix=prefix)

    @server.tool(
        name="memoir_get",
        description=(
            "Fetch the exact memories at the given taxonomy paths/keys (LLM-free, instant). "
            "Step 2 of the preferred recall flow — pass keys you chose from memoir_summarize. "
            "Missing keys come back found=false."
        ),
        annotations=ro,
    )
    def memoir_get(keys: list[str], namespace: str = "default") -> dict:
        return get_memories(store_path, keys, namespace=namespace)

    @server.tool(
        name="memoir_remember",
        description=(
            "Store a durable fact in memory, committed with git versioning. It is "
            "auto-classified into a semantic path (needs a provider key), or pass an "
            "explicit `path` to skip classification. Secrets/credentials are refused — "
            "do not store passwords, API keys, or tokens."
        ),
    )
    async def memoir_remember(
        content: str, namespace: str = "default", path: str | None = None
    ) -> dict:
        return await remember(store_path, content, namespace=namespace, path=path)

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

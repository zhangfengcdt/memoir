# SPDX-License-Identifier: Apache-2.0
"""Memoir memory provider for Hermes.

Gives Hermes versioned, semantic memory backed by a local memoir store —
git-like branch/commit/merge over a Prolly-tree with cryptographic
provenance. Unlike vector-only providers (Mem0, Zep, Letta), every write is
a commit you can inspect, blame, and (eventually) sync via merge.

This is a Hermes **memory provider plugin**: a directory under
``$HERMES_HOME/plugins/memoir/`` (or installed via
``hermes plugins install``), activated with ``memory.provider: memoir`` in
``~/.hermes/config.yaml``. It is NOT a pip-entry-point package — Hermes loads
memory providers by directory scan (``plugins.memory.load_memory_provider``)
and the general entry-point ``PluginContext`` has no
``register_memory_provider``.

The provider holds no memoir code in-process; it shells out to the ``memoir``
CLI via :mod:`bridge`, so the package is stdlib-only and prollytree
self-resolves concurrent (fire-and-forget) writes.

Lifecycle:
  initialize()        derive + ensure the store, cache an overview
  system_prompt_block() static recall guidance + cached overview
  get_tool_schemas()  memoir_recall / memoir_remember / memoir_status
  sync_turn()         fire-and-forget `memoir capture --profile assistant`
  on_pre_compress / on_session_end  capture the uncaptured message tail
  on_memory_write()   mirror Hermes's built-in MEMORY.md/USER.md edits
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
from typing import Any

try:  # pragma: no cover - exercised only inside a Hermes host
    from .bridge import INSTALL_HINT, MemoirBridge
except ImportError:  # Loaded as a top-level module by some test harnesses.
    from bridge import INSTALL_HINT, MemoirBridge  # type: ignore

logger = logging.getLogger(__name__)

# Subclass the Hermes ABC when available so the instance is a true
# MemoryProvider (and inherits the ABC's no-op defaults for hooks we don't
# override). When hermes-agent isn't importable — this repo's unit tests,
# packaging hygiene checks — fall back to ``object`` so the package still
# imports and the methods stay directly testable.
try:  # pragma: no cover - depends on host environment
    from agent.memory_provider import MemoryProvider as _Base
except Exception:
    _Base = object  # type: ignore[assignment, misc]


# Coarse secret detector — refuse to persist obvious credentials even if the
# model tries to stash them. Mirrors the opencode-memoir guard. Durable memory
# is never the right home for secrets; this is a backstop, not a vault.
_SECRET_PATTERNS = [
    re.compile(r"\b(sk|pk|rk)-[A-Za-z0-9]{16,}\b"),  # OpenAI/Stripe-style keys
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),  # GitHub tokens
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),  # Slack tokens
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),  # PEM private keys
    re.compile(r"\b\d{13,16}\b"),  # bare long digit runs (card-ish)
    re.compile(
        r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*\S+"
    ),  # labelled secrets
]


def _looks_like_secret(content: str) -> bool:
    return any(p.search(content) for p in _SECRET_PATTERNS)


def _slugify(target: str) -> str:
    """Normalize a built-in-memory target into a taxonomy path segment."""
    slug = re.sub(r"[^a-z0-9]+", "_", (target or "").lower()).strip("_")
    return slug or "note"


def _rank_by_query(items: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    """Order recalled items by lexical overlap with the query (no LLM).

    Items matching a query token (in path or content) come first, ranked by
    match count; the rest follow in original order. We never drop non-matching
    items — for a small personal-memory store, surfacing the full profile and
    letting the host model judge relevance beats a brittle keyword cut.
    """
    tokens = {t for t in re.split(r"\W+", query.lower()) if len(t) > 2}
    if not tokens:
        return items

    def score(it: dict[str, Any]) -> int:
        hay = f"{it.get('path', '')} {it.get('content', '')}".lower()
        return sum(1 for t in tokens if t in hay)

    return sorted(items, key=score, reverse=True)


def _messages_to_transcript(messages: list[dict[str, Any]] | None) -> str:
    """Render OpenAI-style messages into the `[Human]/[Assistant]` form
    that ``memoir capture`` expects. System/tool messages are skipped."""
    if not messages:
        return ""
    lines: list[str] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, list):
            # Multimodal content blocks — keep the text parts only.
            content = " ".join(
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        if not isinstance(content, str) or not content.strip():
            continue
        if role == "user":
            lines.append(f"[Human]\n{content.strip()}")
        elif role == "assistant":
            lines.append(f"[Assistant]\n{content.strip()}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

_RECALL_SCHEMA = {
    "name": "memoir_recall",
    "description": (
        "Search the user's long-term memory by meaning. Returns relevant "
        "stored facts about the user — preferences, people, schedule, "
        "standing instructions. Use at the start of a conversation or "
        "whenever past context would help."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to recall."},
            "limit": {
                "type": "integer",
                "description": "Max results (default 10).",
            },
        },
        "required": ["query"],
    },
}

_REMEMBER_SCHEMA = {
    "name": "memoir_remember",
    "description": (
        "Store a durable fact about the user (a stable preference, a "
        "relationship, a recurring commitment, a standing instruction). "
        "memoir classifies it into a semantic path and commits it. Do NOT "
        "store secrets, passwords, or one-off task details."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The fact to store."},
            "path": {
                "type": "string",
                "description": (
                    "Optional explicit 3-level taxonomy path "
                    "(e.g. preferences.food.dietary) to skip classification."
                ),
            },
        },
        "required": ["content"],
    },
}

_FORGET_SCHEMA = {
    "name": "memoir_forget",
    "description": (
        "Delete a stored fact when the user asks to forget or remove "
        "something about them. Takes the exact taxonomy path — first call "
        "memoir_recall to find the path, then forget it. The fact stops "
        "appearing in recall; prior versions remain in the store's git "
        "history (recoverable)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "Exact taxonomy path to delete (e.g. "
                    "profile.personal.pets), as returned by memoir_recall."
                ),
            },
        },
        "required": ["path"],
    },
}

_STATUS_SCHEMA = {
    "name": "memoir_status",
    "description": (
        "Report the memory store status: current branch, commit count, and "
        "number of stored memories."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class MemoirProvider(_Base):  # type: ignore[misc, valid-type]
    """Hermes MemoryProvider backed by a local memoir store via the CLI."""

    def __init__(self) -> None:
        self._bridge: MemoirBridge | None = None
        self._store_path: str = ""
        self._session_id: str = ""
        self._overview: str = ""
        self._capture_enabled: bool = True
        self._capture_profile: str = "assistant"
        # Explicit model pin from memoir.json (if any). When set it always
        # wins; otherwise we follow the host's selected model and track
        # mid-session switches via on_turn_start.
        self._config_model: str | None = None
        # Mirror Hermes session forks onto memoir branches: a /branch fork
        # gets its own ``hermes/<session>`` branch; resuming a non-forked
        # session returns to ``main``.
        self._branching_enabled: bool = True
        self._agent_context: str = "primary"
        # Index into the live `messages` list that we've already captured, so
        # the on_pre_compress / on_session_end boundaries only sweep the tail.
        self._captured_through: int = 0
        self._threads: list[threading.Thread] = []
        self._lock = threading.Lock()

    # -- identity / availability --------------------------------------------

    @property
    def name(self) -> str:
        return "memoir"

    def is_available(self) -> bool:
        # No network — just check that a memoir CLI invocation resolves.
        return MemoirBridge(self._store_path or ".").available()

    # -- config -------------------------------------------------------------

    @staticmethod
    def _config_path(hermes_home: str) -> str:
        return os.path.join(hermes_home, "memoir.json")

    def _load_config(self, hermes_home: str) -> dict:
        cfg: dict = {}
        path = self._config_path(hermes_home)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    cfg = json.load(f) or {}
            except Exception:
                cfg = {}
        return cfg

    @staticmethod
    def _host_model() -> str | None:
        """The model Hermes is configured to use (``model.default``), if
        readable. Lets capture/classification run on the host-selected model
        rather than memoir's built-in default. Best-effort."""
        try:
            from hermes_cli.config import cfg_get, load_config

            return cfg_get(load_config(), "model", "default") or None
        except Exception:
            return None

    def get_config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "store_path",
                "description": (
                    "Memoir store location (default: <hermes_home>/memoir-store)."
                ),
            },
            {
                "key": "capture",
                "description": "Auto-capture facts from each turn.",
                "default": "true",
                "choices": ["true", "false"],
            },
            {
                "key": "model",
                "description": (
                    "Pin the LLM model for capture/classification. Leave "
                    "empty to follow the host's selected model "
                    "(Hermes model.default)."
                ),
            },
            {
                "key": "base_url",
                "description": (
                    "Custom provider endpoint (LLM gateway/proxy) for "
                    "capture/classification. Empty = call the provider "
                    "directly (e.g. api.anthropic.com)."
                ),
            },
            {
                "key": "session_branching",
                "description": (
                    "Mirror Hermes session forks onto memoir branches "
                    "(/branch → hermes/<session>; resume non-fork → main)."
                ),
                "default": "true",
                "choices": ["true", "false"],
            },
        ]

    def save_config(self, values: dict[str, Any], hermes_home: str) -> None:
        path = self._config_path(hermes_home)
        existing = self._load_config(hermes_home)
        existing.update({k: v for k, v in values.items() if v not in (None, "")})
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
        os.replace(tmp, path)

    # -- lifecycle ----------------------------------------------------------

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id or ""
        self._agent_context = kwargs.get("agent_context", "primary")

        hermes_home = kwargs.get("hermes_home") or os.path.expanduser("~/.hermes")
        cfg = self._load_config(hermes_home)

        self._store_path = cfg.get("store_path") or os.path.join(
            hermes_home, "memoir-store"
        )
        self._capture_enabled = str(cfg.get("capture", "true")).lower() != "false"
        self._branching_enabled = (
            str(cfg.get("session_branching", "true")).lower() != "false"
        )

        # Model: explicit memoir.json pin → host-selected model → memoir's
        # own default. memoir is always driven by litellm (direct provider
        # API), never the claude CLI — see MemoirBridge._build_env.
        self._config_model = cfg.get("model") or None
        model = self._config_model or self._host_model()

        # Optional custom provider endpoint (LLM gateway/proxy). Without it
        # memoir calls the provider directly (e.g. api.anthropic.com).
        base_url = cfg.get("base_url") or None

        self._bridge = MemoirBridge(self._store_path, model=model, base_url=base_url)
        self._event(
            f"initialize session={session_id} ctx={self._agent_context} "
            f"avail={self._bridge.available()} branching={self._branching_enabled}"
        )
        if not self._bridge.available():
            logger.warning("memoir provider: %s", INSTALL_HINT)
            return

        if not self._bridge.ensure_store():
            logger.warning(
                "memoir provider: failed to create store at %s", self._store_path
            )
            return

        # Align the store's branch with this session at agent-init time. This
        # is the safety net for the lazy-agent path: Hermes builds the agent
        # (and activates this provider) on the first turn, so a `/resume`
        # issued before any message can't notify us — but when the agent does
        # init, we land on the right branch. A session with its own fork
        # branch → that branch; any other session → main.
        if self._branching_enabled:
            target = self._branch_for_session(session_id)
            try:
                dest = target if self._bridge.has_branch(target) else "main"
                ok, payload = self._bridge.checkout(dest)
                if ok:
                    self._event(f"init checkout → {dest}")
                else:
                    err = payload.get("error") if isinstance(payload, dict) else payload
                    self._event(f"init checkout → {dest} failed: {err}")
            except Exception as e:  # pragma: no cover - defensive
                self._event(f"init checkout error: {e}")

        # Cache a lightweight overview for the system prompt. Best-effort —
        # never let a slow/failed summary block agent startup.
        try:
            ok, payload = self._bridge.summarize(depth=2)
            if ok and isinstance(payload, dict):
                count = payload.get("total_memories") or payload.get("count")
                if count:
                    self._overview = f"{count} memories stored."
        except Exception:
            self._overview = ""

    @staticmethod
    def _branch_for_session(session_id: str) -> str:
        """Deterministic memoir branch name for a Hermes session.

        Sanitized to a git-safe ref under the ``hermes/`` namespace. A
        session that was never forked simply has no such branch, so the
        resume path falls back to ``main``.
        """
        slug = re.sub(r"[^A-Za-z0-9._-]", "-", session_id or "").strip("-./")
        return f"hermes/{slug[:64]}" if slug else "hermes/session"

    def system_prompt_block(self) -> str:
        if not (self._bridge and self._bridge.available()):
            return ""
        block = (
            "# Memoir Memory\n"
            "You have persistent, versioned long-term memory of this user.\n"
            "- Call `memoir_recall` to retrieve preferences, people, schedule, "
            "and standing instructions before answering when past context "
            "could matter.\n"
            "- Call `memoir_remember` to store a NEW durable fact the user "
            "shares (stable preferences, relationships, recurring commitments, "
            "standing instructions). Never store secrets or one-off details — "
            "ordinary turns are also auto-captured.\n"
        )
        if self._overview:
            block += f"- Store: {self._overview}\n"
        return block

    # -- tools --------------------------------------------------------------

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return [_RECALL_SCHEMA, _REMEMBER_SCHEMA, _FORGET_SCHEMA, _STATUS_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs) -> str:
        if not (self._bridge and self._bridge.available()):
            return json.dumps({"error": INSTALL_HINT})

        if tool_name == "memoir_recall":
            query = (args.get("query") or "").strip()
            if not query:
                return json.dumps({"error": "Missing required parameter: query"})
            limit = int(args.get("limit") or 10)
            ok, payload = self._bridge.recall()
            if not ok:
                return json.dumps(payload)
            items = payload.get("items", []) if isinstance(payload, dict) else []
            results = []
            for it in items:
                if not it.get("found"):
                    continue
                value = it.get("value")
                content = value.get("content") if isinstance(value, dict) else value
                results.append({"path": it.get("key"), "content": content})
            results = _rank_by_query(results, query)[:limit]
            return json.dumps({"results": results, "count": len(results)})

        if tool_name == "memoir_remember":
            content = (args.get("content") or "").strip()
            if not content:
                return json.dumps({"error": "Missing required parameter: content"})
            if _looks_like_secret(content):
                return json.dumps(
                    {
                        "error": (
                            "Refused: content looks like a secret/credential. "
                            "Memory is not a secret store."
                        )
                    }
                )
            ok, payload = self._bridge.remember(content, path=args.get("path") or None)
            if not ok:
                return json.dumps(payload)
            key = payload.get("key") if isinstance(payload, dict) else None
            return json.dumps({"stored": True, "key": key})

        if tool_name == "memoir_forget":
            path = (args.get("path") or "").strip()
            if not path:
                return json.dumps({"error": "Missing required parameter: path"})
            ok, payload = self._bridge.forget(path)
            if not ok:
                return json.dumps(payload)
            if isinstance(payload, dict) and payload.get("found") is False:
                return json.dumps(
                    {"forgotten": False, "error": f"No memory found at '{path}'."}
                )
            return json.dumps(
                {
                    "forgotten": True,
                    "key": payload.get("key", path),
                    "commit": payload.get("commit_hash"),
                }
            )

        if tool_name == "memoir_status":
            _ok, payload = self._bridge.status()
            return json.dumps(payload)

        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    # -- capture (write) paths ----------------------------------------------

    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        # Follow the host's live model selection (handles mid-session model
        # switches) unless memoir.json pinned an explicit model.
        if self._config_model or not self._bridge:
            return
        model = kwargs.get("model")
        if model:
            self._bridge.model = model

    def _should_write(self) -> bool:
        # Skip writes for non-primary agent contexts (subagent/cron/flush) —
        # those system prompts would corrupt the user's representation.
        return (
            self._capture_enabled
            and self._agent_context == "primary"
            and bool(self._bridge and self._bridge.available())
        )

    def _spawn_capture(self, transcript: str) -> None:
        if not transcript.strip():
            return

        def _run() -> None:
            try:
                self._bridge.capture(transcript, profile=self._capture_profile)  # type: ignore[union-attr]
            except Exception as e:  # pragma: no cover - defensive
                logger.debug("memoir capture failed: %s", e)

        t = threading.Thread(target=_run, daemon=True, name="memoir-capture")
        with self._lock:
            # Reap finished threads so the list can't grow unbounded over a
            # long session.
            self._threads = [x for x in self._threads if x.is_alive()]
            self._threads.append(t)
        t.start()

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: list[dict[str, Any]] | None = None,
    ) -> None:
        if not self._should_write():
            return
        transcript = (
            f"[Human]\n{(user_content or '').strip()}\n"
            f"[Assistant]\n{(assistant_content or '').strip()}"
        )
        self._spawn_capture(transcript)
        # Mark everything up to now as captured so the compression / session
        # boundaries only sweep messages added after this turn.
        if messages is not None:
            self._captured_through = len(messages)

    def on_pre_compress(self, messages: list[dict[str, Any]]) -> str:
        if self._should_write():
            tail = messages[self._captured_through :]
            self._spawn_capture(_messages_to_transcript(tail))
            self._captured_through = len(messages)
        # We persist independently; nothing to add to the compression summary.
        return ""

    def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        if self._should_write():
            tail = messages[self._captured_through :]
            self._spawn_capture(_messages_to_transcript(tail))
            self._captured_through = len(messages)

    def on_session_switch(
        self, new_session_id: str, *, reset: bool = False, **kwargs
    ) -> None:
        """Route the memoir store's branch to match the session.

        Hermes rotates ``session_id`` on ``/branch`` (fork), ``/resume``,
        ``/reset``/``/new``, and context compression — distinguished by the
        ``reason`` kwarg. We mirror forks onto memoir branches so a forked
        conversation's captures stay isolated, and resuming a non-forked
        session returns to ``main``:

          - ``reason="branch"`` (fork) → create+checkout ``hermes/<id>`` off
            the current branch; the fork's captures land there.
          - ``reason="resume"`` / reset / other → checkout ``hermes/<id>`` if
            that branch exists, else ``main`` (a session that was never
            forked has no branch → main).
          - ``reason="compression"`` → no-op: the logical conversation
            continues, only the id rolled over; keep the current branch.
        """
        # Entry trace — lands in ~/.hermes/logs/agent.log so we can confirm
        # the hook fires and which path it takes, regardless of whether the
        # CLI surfaces stderr.
        logger.info(
            "memoir: on_session_switch new=%s reason=%s reset=%s branching=%s avail=%s",
            new_session_id,
            kwargs.get("reason"),
            reset,
            self._branching_enabled,
            bool(self._bridge and self._bridge.available()),
        )
        self._event(
            f"on_session_switch new={new_session_id} reason={kwargs.get('reason')} "
            f"reset={reset} branching={self._branching_enabled}"
        )

        self._session_id = new_session_id or self._session_id
        if reset:
            # New conversation — reset the per-session capture cursor.
            self._captured_through = 0

        if not (self._branching_enabled and new_session_id):
            return
        if not (self._bridge and self._bridge.available()):
            return

        reason = kwargs.get("reason", "")
        if reason == "compression":
            return  # continuation of the same conversation — keep the branch

        # Let any in-flight fire-and-forget captures from the preceding turns
        # finish before we switch branches — otherwise a background `memoir
        # capture` writing to the current branch can race the checkout (and
        # we'd also want those writes to land pre-fork, not on the new fork).
        self._drain_captures(timeout=10.0)

        # Decide the target branch and whether to create it.
        if reason == "branch" and not reset:
            target, create = self._branch_for_session(new_session_id), True
        elif not reset and self._bridge.has_branch(
            self._branch_for_session(new_session_id)
        ):
            target, create = self._branch_for_session(new_session_id), False
        else:
            # Resume of a never-forked session, or a reset/new → main.
            target, create = "main", False

        try:
            ok, payload = self._bridge.checkout(target, create=create)
        except Exception as e:  # pragma: no cover - defensive
            self._notice(f"branch switch to {target} failed: {e}")
            return
        if ok:
            self._notice(f"memory branch → {target}")
        else:
            err = payload.get("error") if isinstance(payload, dict) else payload
            self._notice(f"branch switch to {target} failed: {err}")

    def _notice(self, msg: str) -> None:
        """Surface a short memoir status line to the user.

        Memory providers have no first-class channel to the chat UI, so we
        write a concise line to stderr (visible in the Hermes CLI terminal)
        and also log it. Used for branch switches so the user can see when
        the memoir store follows a session fork/resume.
        """
        import contextlib

        logger.info("memoir: %s", msg)
        self._event(msg)
        with contextlib.suppress(Exception):
            print(f"  ⑂ memoir: {msg}", file=sys.stderr, flush=True)

    def _event(self, msg: str) -> None:
        """Append a timestamped provider event to a fixed file in the store
        (``<store>/.git/memoir-hermes-events.log``).

        This is a logging-independent diagnostic channel: it does not rely on
        Hermes's log routing, so it reliably records whether the provider's
        hooks fire in the live session.
        """
        if not self._store_path:
            return
        import contextlib
        import time

        path = os.path.join(self._store_path, ".git", "memoir-hermes-events.log")
        with contextlib.suppress(Exception), open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.time():.0f} pid={os.getpid()} {msg}\n")

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mirror Hermes's built-in MEMORY.md / USER.md edits into memoir so
        curated memory is versioned too. Replace-at-path semantics so the
        mirror tracks the canonical built-in entry rather than appending."""
        if not self._should_write():
            return
        if action == "remove" or not (content or "").strip():
            return
        if _looks_like_secret(content):
            return
        path = f"profile.assistant.{_slugify(target)}"

        def _run() -> None:
            try:
                self._bridge.remember(content, path=path, replace=True)  # type: ignore[union-attr]
            except Exception as e:  # pragma: no cover - defensive
                logger.debug("memoir on_memory_write mirror failed: %s", e)

        threading.Thread(target=_run, daemon=True, name="memoir-mirror").start()

    def _drain_captures(self, timeout: float = 5.0) -> None:
        """Block until in-flight fire-and-forget capture threads finish (each
        up to ``timeout`` seconds). Used before a branch switch and at
        shutdown so pending writes land before the store changes underfoot."""
        with self._lock:
            threads = [t for t in self._threads if t.is_alive()]
        for t in threads:
            t.join(timeout=timeout)

    def shutdown(self) -> None:
        # Finish any in-flight captures first so they land on the *current*
        # branch (e.g. the fork being torn down)...
        self._drain_captures(timeout=5.0)
        # ...then leave the store on `main`, so exiting a fork session never
        # strands the store on a fork branch — the next session starts clean.
        # The fork's data stays safe on its own branch and is restored if the
        # fork is resumed. (Reset on exit; initialize() is the restart-side
        # backstop.)
        if self._branching_enabled and self._bridge and self._bridge.available():
            import contextlib

            with contextlib.suppress(Exception):
                ok, payload = self._bridge.checkout("main")
                if ok:
                    self._event("shutdown checkout → main")
                else:
                    err = payload.get("error") if isinstance(payload, dict) else payload
                    self._event(f"shutdown checkout → main failed: {err}")


def register(ctx) -> None:
    """Register memoir as a Hermes memory provider."""
    ctx.register_memory_provider(MemoirProvider())

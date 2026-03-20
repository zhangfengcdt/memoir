"""
Hook System - Event-driven hooks for memoir operations.

Implements the hook patterns from the OpenClaw integration spec:
- memoir-recall: Inject memories at session bootstrap
- memoir-store: Buffer and batch-store conversation turns
- memoir-subagent: Manage branches for parallel sub-agents

Hooks fire on specific events and can:
1. Execute memoir CLI commands
2. Inject context into the agent's system prompt
3. Buffer data for batch processing
"""

import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, ClassVar, Optional

from memoir.simulation.cli_executor import CLIExecutor, CLIResult

logger = logging.getLogger(__name__)


class HookEvent(Enum):
    """Events that can trigger hooks."""

    AGENT_BOOTSTRAP = "agent:bootstrap"  # Session starts
    MESSAGE_RECEIVED = "message:received"  # User message received
    MESSAGE_SENT = "message:sent"  # Agent response sent
    COMMAND_NEW = "command:new"  # New command/session
    SESSION_END = "session:end"  # Session ending


@dataclass
class HookResult:
    """Result from hook execution."""

    hook_name: str
    event: HookEvent
    success: bool
    context_injection: Optional[str] = None  # Text to inject into context
    cli_results: list[CLIResult] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class ConversationTurn:
    """A single conversation turn for buffering."""

    user_message: str
    assistant_message: str
    timestamp: float
    session_key: str


class HookSystem:
    """
    Event-driven hook system for memoir integration.

    Manages hooks that fire on agent events and execute memoir
    operations automatically.

    Example:
        hooks = HookSystem("/path/to/store", user_id="user123")

        # Fire bootstrap hook - injects memories into context
        result = hooks.on_agent_bootstrap(session_key="agent:main:user:123:session:1")
        if result.context_injection:
            system_prompt += result.context_injection

        # Fire message_sent hook - buffers turns for batch storage
        hooks.on_message_sent(
            user_message="How do I debug Python?",
            assistant_message="You can use pdb or print statements...",
            session_key="..."
        )
    """

    # Keywords that trigger semantic recall (expensive)
    RECALL_KEYWORDS = re.compile(
        r"\b(remember|last time|previously|you said|my preference|"
        r"we discussed|earlier|before|mentioned|told you)\b",
        re.IGNORECASE,
    )

    def __init__(
        self,
        store_path: str,
        user_id: str = "default",
        batch_size: int = 10,
        buffer_dir: Optional[str] = None,
    ):
        """
        Initialize hook system.

        Args:
            store_path: Path to memoir store
            user_id: User ID for namespace isolation
            batch_size: Number of turns before batch flush
            buffer_dir: Directory for turn buffers (default: /tmp/memoir-buffer)
        """
        self.store_path = store_path
        self.user_id = user_id
        self.batch_size = batch_size
        self.buffer_dir = Path(buffer_dir or "/tmp/memoir-buffer")
        self.buffer_dir.mkdir(parents=True, exist_ok=True)

        self.executor = CLIExecutor(store_path)

        # Turn buffer (in-memory for simplicity in POC)
        self._turn_buffer: list[ConversationTurn] = []

        # Hook registry
        self._hooks: dict[HookEvent, list[Callable]] = defaultdict(list)

        # Register default hooks
        self._register_default_hooks()

    def _register_default_hooks(self):
        """Register the default memoir hooks."""
        self.register(HookEvent.AGENT_BOOTSTRAP, self._memoir_recall_hook)
        self.register(HookEvent.MESSAGE_RECEIVED, self._keyword_recall_hook)
        self.register(HookEvent.MESSAGE_SENT, self._memoir_store_hook)
        self.register(HookEvent.COMMAND_NEW, self._flush_batch_hook)
        self.register(HookEvent.SESSION_END, self._flush_batch_hook)

    def register(self, event: HookEvent, handler: Callable) -> None:
        """
        Register a hook handler.

        Args:
            event: Event to trigger on
            handler: Function to call
        """
        self._hooks[event].append(handler)

    def fire(self, event: HookEvent, **kwargs) -> list[HookResult]:
        """
        Fire all hooks for an event.

        Args:
            event: Event type
            **kwargs: Event-specific data

        Returns:
            List of HookResults from all handlers
        """
        results = []
        for handler in self._hooks[event]:
            try:
                start = time.time()
                result = handler(event=event, **kwargs)
                if result:
                    result.duration_ms = (time.time() - start) * 1000
                    results.append(result)
            except Exception as e:
                logger.error(f"Hook {handler.__name__} failed: {e}")
                results.append(
                    HookResult(
                        hook_name=handler.__name__,
                        event=event,
                        success=False,
                        error=str(e),
                    )
                )
        return results

    # ==========================================================================
    # Convenience Methods
    # ==========================================================================

    def on_agent_bootstrap(self, session_key: str) -> HookResult:
        """
        Fire bootstrap hooks when agent session starts.

        This triggers memoir-recall to inject relevant memories.

        Args:
            session_key: Session identifier (e.g., "agent:main:user:123:session:1")

        Returns:
            Combined HookResult with context to inject
        """
        results = self.fire(HookEvent.AGENT_BOOTSTRAP, session_key=session_key)

        # Combine context injections and duration
        combined_context = []
        all_cli_results = []
        total_duration_ms = 0.0
        for r in results:
            if r.context_injection:
                combined_context.append(r.context_injection)
            all_cli_results.extend(r.cli_results)
            total_duration_ms += r.duration_ms

        return HookResult(
            hook_name="agent_bootstrap",
            event=HookEvent.AGENT_BOOTSTRAP,
            success=all(r.success for r in results),
            context_injection=(
                "\n\n".join(combined_context) if combined_context else None
            ),
            cli_results=all_cli_results,
            duration_ms=total_duration_ms,
        )

    def on_message_received(
        self,
        message: str,
        session_key: str,
    ) -> HookResult:
        """
        Fire hooks when user message is received.

        Triggers keyword-based recall if memory-related keywords detected.

        Args:
            message: User message content
            session_key: Session identifier

        Returns:
            HookResult with any recalled context
        """
        results = self.fire(
            HookEvent.MESSAGE_RECEIVED,
            message=message,
            session_key=session_key,
        )

        combined_context = []
        merged_data = {}
        total_duration_ms = 0.0
        for r in results:
            if r.context_injection:
                combined_context.append(r.context_injection)
            if r.data:
                merged_data.update(r.data)
            total_duration_ms += r.duration_ms

        return HookResult(
            hook_name="message_received",
            event=HookEvent.MESSAGE_RECEIVED,
            success=all(r.success for r in results),
            context_injection=(
                "\n\n".join(combined_context) if combined_context else None
            ),
            cli_results=[r for res in results for r in res.cli_results],
            data=merged_data,
            duration_ms=total_duration_ms,
        )

    def on_message_sent(
        self,
        user_message: str,
        assistant_message: str,
        session_key: str,
    ) -> HookResult:
        """
        Fire hooks when agent sends response.

        Buffers the conversation turn for batch storage.

        Args:
            user_message: User's message
            assistant_message: Agent's response
            session_key: Session identifier

        Returns:
            HookResult (may include batch flush results)
        """
        results = self.fire(
            HookEvent.MESSAGE_SENT,
            user_message=user_message,
            assistant_message=assistant_message,
            session_key=session_key,
        )

        # Merge data from all results
        merged_data = {"buffer_size": len(self._turn_buffer)}
        total_duration_ms = 0.0
        for r in results:
            if r.data:
                merged_data.update(r.data)
            total_duration_ms += r.duration_ms

        return HookResult(
            hook_name="message_sent",
            event=HookEvent.MESSAGE_SENT,
            success=all(r.success for r in results),
            cli_results=[r for res in results for r in res.cli_results],
            data=merged_data,
            duration_ms=total_duration_ms,
        )

    def flush_buffer(self, session_key: str) -> HookResult:
        """
        Force flush the turn buffer.

        Args:
            session_key: Session identifier

        Returns:
            HookResult with batch storage results
        """
        results = self.fire(HookEvent.SESSION_END, session_key=session_key, force=True)

        # Merge data and duration from all results
        merged_data = {}
        total_duration_ms = 0.0
        for r in results:
            if r.data:
                merged_data.update(r.data)
            total_duration_ms += r.duration_ms

        return HookResult(
            hook_name="flush_buffer",
            event=HookEvent.SESSION_END,
            success=all(r.success for r in results),
            cli_results=[r for res in results for r in res.cli_results],
            data=merged_data,
            duration_ms=total_duration_ms,
        )

    # ==========================================================================
    # Default Hook Implementations
    # ==========================================================================

    # Default identity mappings - empty by default, loaded dynamically from store
    # Add identities via: memoir set "config.identity.<name>" '{"channels": ["channel1"], "description": "..."}' -n agent
    DEFAULT_IDENTITY_MAPPINGS: ClassVar[dict[str, dict[str, Any]]] = {}

    def _ensure_identity_mappings_in_memory(self) -> list[CLIResult]:
        """
        Ensure identity mappings exist in agent memory.

        Uses new format: config.identity.{channel}:{user_id} -> namespace
        Expects external seeding (e.g., from simulation demo).

        Returns:
            List of CLI results from storing mappings (empty if externally seeded)
        """
        # New format expects external seeding via simulation.py or other setup
        # No longer auto-seeds from DEFAULT_IDENTITY_MAPPINGS
        return []

    def _load_identity_mappings_from_memory(
        self, use_defaults: bool = True
    ) -> dict[str, dict[str, Any]]:
        """
        Load identity mappings dynamically from agent memory.

        Note: This method is deprecated. Identity lookups now use direct key access
        via _get_identity_for_channel() with format: config.identity.{channel}:{user_id}

        This method is kept for backward compatibility with _format_identity_mappings().

        Args:
            use_defaults: If True, fall back to DEFAULT_IDENTITY_MAPPINGS on error

        Returns:
            Identity mappings dict {person: {"channels": [...]}} or empty dict
        """
        # New format uses individual keys, not a single JSON blob
        # Return empty dict - callers should use _get_identity_for_channel() instead
        if use_defaults:
            return self.DEFAULT_IDENTITY_MAPPINGS
        return {}

    def _get_identity_for_channel(
        self, channel: str, user_id: Optional[str] = None
    ) -> Optional[str]:
        """Get the person identity for a given channel and optional user_id.

        Uses direct key lookup in the new format:
        - config.identity.{channel}:{user_id} -> namespace (specific user)
        - config.identity.{channel} -> namespace (channel-wide)

        Checks channel:user_id first (more specific), then channel-only.
        """
        # First try exact channel:user_id match (more specific)
        if user_id:
            result = self.executor.get(
                key=f"config.identity.{channel}:{user_id}",
                namespace="agent",
            )
            if result.success and result.data and isinstance(result.data, dict):
                content = result.data.get("content", "")
                if content and isinstance(content, str):
                    return content.strip()

        # Fall back to channel-only match
        result = self.executor.get(
            key=f"config.identity.{channel}",
            namespace="agent",
        )
        if result.success and result.data and isinstance(result.data, dict):
            content = result.data.get("content", "")
            if content and isinstance(content, str):
                return content.strip()

        return None

    def _format_identity_mappings(self) -> str:
        """Format identity mappings for LLM context injection.

        Note: With the new direct-lookup format, identity resolution is done
        via CLI get, not LLM parsing. This method is kept for informational purposes.
        """
        return (
            "Identity resolution uses direct lookup:\n"
            "  memoir get config.identity.{channel}:{user_id} --namespace agent\n"
            "Falls back to: config.identity.{channel} for channel-wide mappings."
        )

    def _memoir_recall_hook(
        self,
        event: HookEvent,
        session_key: str,
        **kwargs,
    ) -> HookResult:
        """
        memoir-recall hook: Inject memories at session bootstrap.

        1. Ensures identity mappings are stored in agent memory
        2. Reads identity mappings to determine current person
        3. Injects context with identity info and relevant memories

        Args:
            event: Hook event
            session_key: Session key for user extraction

        Returns:
            HookResult with context to inject
        """
        cli_results = []
        sections = []

        # Ensure identity mappings are stored in agent memory
        seed_results = self._ensure_identity_mappings_in_memory()
        cli_results.extend(seed_results)

        # Get channel, user_id and determine person identity
        channel = self._extract_channel(session_key)
        user_id = self._extract_user_id(session_key)
        person = self._get_identity_for_channel(channel, user_id)

        # Always inject identity mappings first
        identity_section = (
            "### Identity Mappings\n"
            "Use these to determine which namespace to use for user memories:\n"
            "Format: channel or channel:user_id -> person\n"
            f"{self._format_identity_mappings()}\n\n"
            f"**Current channel:** {channel}\n"
            f"**Current user_id:** {user_id}\n"
            f"**Current person:** {person or 'unknown'}\n"
            f"**Use namespace:** {person or channel} for this user's memories"
        )
        sections.append(identity_section)

        # If we know the person, look up their memories
        if person:
            person_lookups = [
                ("User Preferences", person, "preferences"),
                ("Current Project", person, "projects.current"),
            ]
            for title, namespace, path in person_lookups:
                result = self.executor.get(path, namespace=namespace)
                cli_results.append(result)
                if result.success and result.data:
                    memories = result.data.get("memories", [])
                    if memories:
                        content = self._format_memories(memories)
                        sections.append(f"### {title} ({person})\n{content}")

        # Agent memories (identity mappings + skills)
        agent_lookups = [
            ("Agent Configuration", "agent", "identity"),
            ("Agent Skills", "agent", "skills"),
            ("System Tools", "system", "tools.available"),
        ]
        for title, namespace, path in agent_lookups:
            result = self.executor.get(path, namespace=namespace)
            cli_results.append(result)
            if result.success and result.data:
                memories = result.data.get("memories", [])
                if memories:
                    content = self._format_memories(memories)
                    sections.append(f"### {title}\n{content}")

        context = None
        if sections:
            context = "## Long-Term Memory (from Memoir)\n\n" + "\n\n".join(sections)

        return HookResult(
            hook_name="memoir-recall",
            event=event,
            success=True,
            context_injection=context,
            cli_results=cli_results,
        )

    def _keyword_recall_hook(
        self,
        event: HookEvent,
        message: str,
        session_key: str,
        **kwargs,
    ) -> HookResult:
        """
        Keyword-based recall hook: Search memories when keywords detected.

        Only triggers for messages containing memory-related keywords
        to minimize expensive LLM calls.

        Args:
            event: Hook event
            message: User message
            session_key: Session key

        Returns:
            HookResult with recalled memories
        """
        # Check for recall keywords
        if not self.RECALL_KEYWORDS.search(message):
            return HookResult(
                hook_name="keyword-recall",
                event=event,
                success=True,
                data={"triggered": False},
            )

        user_ns = self._get_user_namespace(session_key)

        # Extract query from message (simplified - just use the message)
        query = self._extract_recall_query(message)

        # Semantic search (expensive - LLM call)
        result = self.executor.recall(query, limit=5, namespace=user_ns)

        context = None
        if result.success and result.data:
            memories = result.data.get("memories", [])
            if memories:
                content = self._format_memories(memories)
                context = f"## Relevant Memories\n\n{content}"

        return HookResult(
            hook_name="keyword-recall",
            event=event,
            success=result.success,
            context_injection=context,
            cli_results=[result],
            data={"triggered": True, "query": query},
        )

    def _memoir_store_hook(
        self,
        event: HookEvent,
        user_message: str,
        assistant_message: str,
        session_key: str,
        **kwargs,
    ) -> HookResult:
        """
        memoir-store hook: Buffer turns for batch storage.

        Buffers conversation turns and flushes when batch size reached.
        Only stores turns with substantial content.

        Args:
            event: Hook event
            user_message: User's message
            assistant_message: Agent's response
            session_key: Session key

        Returns:
            HookResult (may trigger batch flush)
        """
        # Add to buffer
        turn = ConversationTurn(
            user_message=user_message[:2000],  # Truncate for safety
            assistant_message=assistant_message[:2000],
            timestamp=time.time(),
            session_key=session_key,
        )
        self._turn_buffer.append(turn)

        # Check if batch is ready
        if len(self._turn_buffer) >= self.batch_size:
            return self._flush_batch_hook(event, session_key, force=True)

        return HookResult(
            hook_name="memoir-store",
            event=event,
            success=True,
            data={
                "buffered": True,
                "buffer_size": len(self._turn_buffer),
                "batch_size": self.batch_size,
            },
        )

    def _flush_batch_hook(
        self,
        event: HookEvent,
        session_key: str = "",
        force: bool = False,
        **kwargs,
    ) -> HookResult:
        """
        Flush buffered turns to memoir.

        Analyzes buffered conversation turns and stores relevant
        information in memory.

        Args:
            event: Hook event
            session_key: Session key
            force: Force flush even if buffer not full

        Returns:
            HookResult with storage results
        """
        if not self._turn_buffer:
            return HookResult(
                hook_name="flush-batch",
                event=event,
                success=True,
                data={"flushed": False, "reason": "empty_buffer"},
            )

        turns = self._turn_buffer
        self._turn_buffer = []

        # For POC demo, skip automatic conversation storage
        # In production, this would use memoir analyze-batch to extract facts
        # For now, we let the LLM decide what to store via tool calls

        return HookResult(
            hook_name="flush-batch",
            event=event,
            success=True,
            cli_results=[],
            data={
                "flushed": True,
                "turns_processed": len(turns),
                "skipped": True,  # Not storing conversation summaries
            },
        )

    # ==========================================================================
    # Helper Methods
    # ==========================================================================

    def _extract_user_id(self, session_key: str) -> str:
        """Extract user ID from session key."""
        # Pattern: channel:<channel>:user_id:<userId>:session:<sessionId>
        match = re.search(r":user_id:([^:]+)", session_key)
        if match:
            return match.group(1)
        return self.user_id

    def _extract_channel(self, session_key: str) -> str:
        """Extract channel from session key."""
        # Pattern: channel:<channel>:user_id:<userId>:session:<sessionId>
        match = re.search(r"^channel:([^:]+)", session_key)
        if match:
            return match.group(1)
        return "web"

    def _get_user_namespace(self, session_key: str) -> str:
        """Get user namespace from session key (channel:user_id format)."""
        channel = self._extract_channel(session_key)
        user_id = self._extract_user_id(session_key)
        return f"{channel}:{user_id}"

    def _detect_project(self) -> Optional[str]:
        """Detect project from current directory."""
        cwd = Path.cwd()

        # Try package.json
        pkg_json = cwd / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text())
                name = data.get("name", "")
                return re.sub(r"[^a-z0-9-]", "-", name, flags=re.IGNORECASE)
            except Exception:
                pass

        # Try pyproject.toml
        pyproject = cwd / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                match = re.search(r'name\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    return re.sub(
                        r"[^a-z0-9-]", "-", match.group(1), flags=re.IGNORECASE
                    )
            except Exception:
                pass

        # Try git repo name
        git_dir = cwd / ".git"
        if git_dir.exists():
            return cwd.name

        return None

    def _extract_recall_query(self, message: str) -> str:
        """Extract search query from user message."""
        # Remove recall keywords and use remaining content
        cleaned = self.RECALL_KEYWORDS.sub("", message).strip()
        return cleaned if cleaned else message

    def _format_memories(self, memories: list[dict]) -> str:
        """Format memories for context injection."""
        lines = []
        for mem in memories[:5]:  # Limit to 5
            path = mem.get("path", "unknown")
            content = mem.get("content", "")[:200]  # Truncate
            lines.append(f"- **{path}**: {content}")
        return "\n".join(lines)

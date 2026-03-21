"""
LLM Agent - Agent that uses LLM for tool calling decisions.

This agent:
1. Sends messages to an LLM (e.g., claude-haiku-4-5)
2. LLM sees memoir tool definitions
3. LLM decides when to call memoir tools
4. Tool calls execute memoir CLI commands
5. Results are fed back to LLM for final response
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from memoir.simulation.cli_executor import CLIExecutor
from memoir.simulation.hooks import HookSystem
from memoir.simulation.live_tui import (
    EventSource,
    InstrumentedHookSystem,
    InstrumentedSkillInjector,
    LiveSimulationTUI,
    MemoryEvent,
)
from memoir.simulation.session import Session, SessionManager
from memoir.simulation.skill import TOOL_DEFINITIONS, SkillInjector

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    """A tool call from the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""  # Original JSON string


@dataclass
class AgentResponse:
    """Response from the agent."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    thinking: str = ""  # LLM's reasoning before tool calls
    duration_ms: float = 0.0


class LLMAgent:
    """
    Agent that uses LLM for intelligent tool calling.

    Example:
        agent = LLMAgent(
            store_path="/path/to/store",
            model="claude-haiku-4-5",
            user_id="alice",
            tui=tui,  # Optional TUI for visualization
        )

        response = await agent.chat("Remember that I prefer dark mode")
        # LLM decides to call memoir_remember tool
        # Tool executes memoir CLI command
        # LLM provides final response
    """

    # Base system prompt - taxonomy will be injected dynamically
    SYSTEM_PROMPT_TEMPLATE = """You are a helpful AI assistant with persistent memory via the Memoir system.

## Current Session:
- Channel: {channel}
- User Namespace: {user_namespace}

## Memory Tools

### For Storing:
- **memoir_set(key, content)**: Store at exact path - use when you're confident about the path
- **memoir_remember(content)**: Auto-classifies content - use when unsure or content is complex

### For Retrieving:
- **memoir_get(key)**: Get by exact path - fast O(log n) lookup
- **memoir_recall(query)**: Semantic search - finds relevant memories by meaning

**CRITICAL**: When looking up information, if `memoir_get` returns empty/not found,
you MUST immediately call `memoir_recall` with a natural language query before responding.
Never say "I don't have that information" after only trying `memoir_get`.

### Other:
- **memoir_forget(path)**: Delete a memory

{taxonomy_section}

## When to Retrieve Memories

Proactively check memories to help users achieve the best outcomes.
Use memories to inform your reasoning, verify facts, and personalize responses.

### When to retrieve:
- Before answering questions that might relate to stored knowledge
- When reasoning about user preferences, context, or past discussions
- To check if relevant information was previously stored
- To personalize recommendations or suggestions
- When deciding which tools, languages, or approaches to suggest

### Retrieval strategy (MUST FOLLOW):

**Example flow for "how old am I?":**
1. Try `memoir_get("profile.personal.age")` → not found
2. MUST then call `memoir_recall("user age")` → might find it under different path
3. Only after BOTH return nothing, say "I don't have your age stored"

**Rules:**
- Always try `memoir_get` first (fast, exact path)
- If `memoir_get` returns nothing → IMMEDIATELY call `memoir_recall`
- Never respond "not found" until you've tried BOTH tools
- Don't over-retrieve - only check when it genuinely helps

## When to Store Memories

The purpose of storing memories is to enable **easy recall via semantic paths**.
Choose paths that others (or future you) would naturally look up.

### Choosing between memoir_set and memoir_remember:

Use **memoir_set** when:
- Content clearly fits a single category (e.g., "I like Python" → preferences.language)
- You're confident about the path from the taxonomy examples
- Storing simple, atomic facts

Use **memoir_remember** when:
- Content is complex or multi-faceted (e.g., "I'm a senior engineer at Google working on ML")
- Content could fit multiple categories
- You're unsure which path is best - let the classifier decide
- User says "remember this" without being specific

### Store to USER namespace ({user_namespace}) when:
- User shares personal info: name, location, job, preferences
- User mentions their goals, projects, or interests
- User states opinions, likes/dislikes, or habits
- User's tool/technology preferences (e.g., "I prefer pytest", "I use vim")
- User's coding style preferences (e.g., "I like functional programming")
- Any fact ABOUT the user that they might want recalled later

### Store to AGENT namespace (agent) when:
- You (the AI) discover something NEW that you didn't know before
- General facts about tools/systems that apply to everyone (not user preference)
- Meta-learnings about how to be a better assistant
- NOTE: If the USER says "I prefer X" or "I like X", that's USER preference, not agent learning!

### DO NOT store:
- Trivial or temporary information
- Information already stored (check first with memoir_get if unsure)
- Sensitive data (passwords, tokens, secrets)

## Namespaces:
- **agent**: Your own learnings, skills, techniques (shared across all users)
- **{user_namespace}**: This user's memories (private to this user)

IMPORTANT: For this user's memories, ALWAYS use namespace "{user_namespace}".
For your own learnings/skills, use namespace "agent".

Be conversational and acknowledge when you store or find memories.
"""

    def __init__(
        self,
        store_path: str,
        model: str = "claude-haiku-4-5",
        user_id: str = "default",
        channel: str = "web",
        session_manager: Optional[SessionManager] = None,
        tui: Optional[LiveSimulationTUI] = None,
        enable_hooks: bool = True,
    ):
        self.store_path = store_path
        self.model = model
        self.user_id = user_id
        self.channel = channel
        self.tui = tui

        # Session management
        self.session_manager = session_manager or SessionManager()
        self.session: Optional[Session] = None

        # CLI executor for tool execution
        self.cli = CLIExecutor(store_path)

        # Skill injector for tool definitions
        self.skill_injector = SkillInjector(
            user_id=user_id,
            store_path=store_path,
        )

        # Resolved namespace (set at session start)
        self.resolved_namespace: Optional[str] = None

        # Hooks (optional)
        self.hooks: Optional[HookSystem] = None
        if enable_hooks:
            self.hooks = HookSystem(
                store_path=store_path,
                user_id=user_id,
                batch_size=2,  # Flush after 2 turns for demo
            )
            # Wrap with instrumentation if TUI provided
            if tui:
                self.hooks = InstrumentedHookSystem(self.hooks, tui)

        # Wrap skill injector with instrumentation if TUI provided
        if tui:
            self.skill_injector = InstrumentedSkillInjector(self.skill_injector, tui)

        # LLM (lazy loaded)
        self._llm = None

        # Taxonomy (loaded from store, cached)
        self._taxonomy_section: Optional[str] = None
        self._load_taxonomy_from_store()

    @property
    def llm(self):
        """Lazy-load LLM."""
        if self._llm is None:
            from memoir.llm import get_llm

            self._llm = get_llm(
                model=self.model,
                temperature=0.7,
                max_tokens=1000,
            )
        return self._llm

    def _load_taxonomy_from_store(self) -> None:
        """Load taxonomy from the store and cache it for prompt injection.

        Loads classification examples and category descriptions from the store,
        formatting them for the LLM system prompt. This ensures the LLM uses
        the same taxonomy as memoir's classifier.
        """
        try:
            from memoir.store.prolly_adapter import ProllyTreeStore
            from memoir.taxonomy.loader import TaxonomyLoader

            store = ProllyTreeStore(self.store_path)
            loader = TaxonomyLoader(store)

            if not loader.has_taxonomy_in_store():
                logger.warning("No taxonomy in store, using minimal guidance")
                self._taxonomy_section = self._get_fallback_taxonomy_section()
                return

            # Load examples and descriptions from store
            examples = loader.get_examples_from_store(limit=30)
            descriptions = loader.get_descriptions_from_store()

            # Format for prompt
            lines = ["## Taxonomy Guide (from store)"]
            lines.append("")
            lines.append(
                "Use these paths with `memoir_set` when you recognize the pattern:"
            )
            lines.append("")

            # Add category descriptions
            if descriptions:
                lines.append("### Categories:")
                for cat, desc in sorted(descriptions.items()):
                    lines.append(f"- **{cat}**: {desc}")
                lines.append("")

            # Add examples grouped by category
            if examples:
                lines.append("### Examples (input → path):")
                examples_by_cat: dict[str, list[tuple[str, str]]] = {}
                for input_text, path, _reasoning in examples:
                    cat = path.split(".")[0]
                    if cat not in examples_by_cat:
                        examples_by_cat[cat] = []
                    if len(examples_by_cat[cat]) < 4:  # Max 4 per category
                        examples_by_cat[cat].append((input_text, path))

                for cat in sorted(examples_by_cat.keys()):
                    for input_text, path in examples_by_cat[cat]:
                        lines.append(f'- "{input_text}" → `{path}`')
                lines.append("")

            lines.append(
                "**Decision**: If input matches a pattern above, use `memoir_set` with that path."
            )
            lines.append("Otherwise, use `memoir_remember` for auto-classification.")

            self._taxonomy_section = "\n".join(lines)
            logger.info(
                f"Loaded taxonomy from store: {len(examples)} examples, {len(descriptions)} categories"
            )

        except Exception as e:
            logger.warning(f"Failed to load taxonomy from store: {e}")
            self._taxonomy_section = self._get_fallback_taxonomy_section()

    def _get_fallback_taxonomy_section(self) -> str:
        """Return minimal taxonomy guidance when store taxonomy is unavailable."""
        return """## Decision Guide for Storing:
1. **Know the path?** → Use `memoir_set` (fast, no LLM call)
   - User says "I prefer dark mode" → `memoir_set("preferences.theme", "dark mode")`
   - User says "My name is Kevin" → `memoir_set("profile.name", "Kevin")`
   - User says "I use Python" → `memoir_set("preferences.language", "Python")`

2. **Unsure about path?** → Use `memoir_remember` (auto-classification)
   - Complex or ambiguous content that needs intelligent categorization"""

    def _get_default_namespace(self) -> str:
        """
        Get the resolved namespace for this user.

        Returns the identity-resolved namespace (e.g., "kevin") if available,
        otherwise falls back to channel:user_id format.
        """
        if self.resolved_namespace:
            return self.resolved_namespace
        return f"{self.channel}:{self.user_id}"

    def start_session(self, session_id: Optional[str] = None) -> Session:
        """Start a new conversation session."""
        self.session = self.session_manager.create_session(
            user_id=self.user_id,
            channel=self.channel,
            agent_id="real-llm",
            session_id=session_id,
        )

        # Resolve namespace once at session start using fast CLI lookup
        if self.hooks:
            # Access the underlying HookSystem (unwrap if instrumented)
            hook_system = self.hooks
            if hasattr(self.hooks, "_hooks"):
                hook_system = self.hooks._hooks

            # Resolve identity: channel:user_id -> namespace
            resolved = hook_system._get_identity_for_channel(self.channel, self.user_id)
            if resolved:
                self.resolved_namespace = resolved
                logger.info(
                    f"Resolved namespace: {self.channel}:{self.user_id} -> {resolved}"
                )
            else:
                self.resolved_namespace = f"{self.channel}:{self.user_id}"
                logger.info(
                    f"No identity mapping, using fallback: {self.resolved_namespace}"
                )

            # Fire bootstrap hook (for memory context injection)
            result = self.hooks.on_agent_bootstrap(self.session.session_key)
            if result.context_injection:
                self.session.metadata["memory_context"] = result.context_injection
        else:
            self.resolved_namespace = f"{self.channel}:{self.user_id}"

        # Log to TUI
        if self.tui:
            self.tui.log_event(
                MemoryEvent(
                    timestamp=time.time(),
                    source=EventSource.SYSTEM,
                    operation="session-start",
                    details=f"User {self.user_id} -> {self.resolved_namespace}",
                )
            )

        return self.session

    def end_session(self) -> None:
        """End the current session."""
        if self.session and self.hooks:
            self.hooks.flush_buffer(self.session.session_key)

        if self.tui:
            self.tui.log_event(
                MemoryEvent(
                    timestamp=time.time(),
                    source=EventSource.SYSTEM,
                    operation="session-end",
                    details=f"User {self.user_id} session ended",
                )
            )

        if self.session:
            self.session_manager.end_session(self.session.session_key)
            self.session = None

    def _get_tool_definitions(self) -> list[dict]:
        """Get tool definitions for LLM."""
        return TOOL_DEFINITIONS

    def _build_messages(self, extra_context: Optional[str] = None) -> list[dict]:
        """Build message list for LLM."""
        # Substitute channel, namespace, and taxonomy in system prompt
        user_ns = self._get_default_namespace()
        taxonomy_section = (
            self._taxonomy_section or self._get_fallback_taxonomy_section()
        )

        system_prompt = (
            self.SYSTEM_PROMPT_TEMPLATE.replace("{channel}", self.channel)
            .replace("{user_namespace}", user_ns)
            .replace("{taxonomy_section}", taxonomy_section)
        )
        messages = [{"role": "system", "content": system_prompt}]

        # Add memory context from bootstrap hook
        if self.session and "memory_context" in self.session.metadata:
            messages.append(
                {
                    "role": "system",
                    "content": f"[Previous Memories]\n{self.session.metadata['memory_context']}",
                }
            )

        # Add extra context (e.g., from keyword recall)
        if extra_context:
            messages.append(
                {
                    "role": "system",
                    "content": f"[Relevant Memories]\n{extra_context}",
                }
            )

        # Add conversation history
        if self.session:
            for msg in self.session.messages:
                messages.append({"role": msg.role, "content": msg.content})

        return messages

    def _execute_tool(self, tool_call: ToolCall) -> tuple[dict, str]:
        """Execute a memoir tool call.

        Returns:
            Tuple of (result_dict, cli_command_string)
        """
        name = tool_call.name
        args = tool_call.arguments

        # Get the default namespace (identity-based if available)
        default_ns = self._get_default_namespace()

        if name == "memoir_remember":
            result = self.cli.remember(
                content=args.get("content", ""),
                namespace=args.get("namespace", default_ns),
            )
            return (
                {
                    "success": result.success,
                    "key": result.data.get("key") if result.data else None,
                    "message": (
                        f"Stored memory at {result.data.get('key')}"
                        if result.success
                        else result.error
                    ),
                },
                result.command,
            )

        elif name == "memoir_recall":
            result = self.cli.recall(
                query=args.get("query", ""),
                namespace=args.get("namespace", default_ns),
                limit=args.get("limit", 5),
            )
            memories = []
            if result.success and result.data:
                for mem in result.data.get("memories", []):
                    memories.append(
                        {
                            "path": mem.get("path", mem.get("key", "")),
                            "content": mem.get("content", ""),
                        }
                    )
            return (
                {
                    "success": result.success,
                    "memories": memories,
                    "count": len(memories),
                },
                result.command,
            )

        elif name == "memoir_forget":
            result = self.cli.forget(
                key=args.get("path", ""),
                namespace=args.get("namespace", default_ns),
            )
            return (
                {
                    "success": result.success,
                    "message": (
                        f"Deleted {args.get('path')}"
                        if result.success
                        else result.error
                    ),
                },
                result.command,
            )

        elif name == "memoir_set":
            result = self.cli.set(
                key=args.get("key", ""),
                content=args.get("content", ""),
                namespace=args.get("namespace", default_ns),
            )
            return (
                {
                    "success": result.success,
                    "key": result.data.get("key") if result.data else args.get("key"),
                    "message": (
                        f"Stored at {args.get('key')}"
                        if result.success
                        else result.error
                    ),
                },
                result.command,
            )

        elif name == "memoir_get":
            result = self.cli.get(
                key=args.get("key", ""),
                namespace=args.get("namespace", default_ns),
            )
            content = None
            if result.success and result.data:
                content = result.data.get("content")
            return (
                {
                    "success": result.success,
                    "key": args.get("key"),
                    "content": content,
                    "found": content is not None,
                },
                result.command,
            )

        elif name == "memoir_help":
            result = self.cli.help(command=args.get("command"))
            return (
                {
                    "success": result.success,
                    "help_text": result.stdout,
                },
                result.command,
            )

        else:
            return ({"success": False, "error": f"Unknown tool: {name}"}, "")

    async def chat(self, user_message: str) -> AgentResponse:
        """
        Send a message and get a response.

        The LLM may decide to call memoir tools based on the message.
        """
        start_time = time.time()

        # Ensure session exists
        if not self.session:
            self.start_session()

        # Fire message:received hook (may trigger keyword recall)
        extra_context = None
        if self.hooks:
            result = self.hooks.on_message_received(
                message=user_message,
                session_key=self.session.session_key,
            )
            if result.context_injection:
                extra_context = result.context_injection

        # Add user message to session
        self.session.add_user_message(user_message)

        # Log to TUI
        if self.tui:
            self.tui.log_conversation(
                role="user",
                content=user_message,
                user_id=self.user_id,
                session_id=self.session.session_id,
                channel=self.session.channel,
            )

        # Build messages and call LLM
        messages = self._build_messages(extra_context)
        tools = self._get_tool_definitions()

        # LLM call loop - continue until no more tool calls (max 5 iterations)
        response = await self.llm.ainvoke_with_tools(messages, tools)

        all_tool_calls = []
        all_tool_results = []
        thinking = response.content  # Initial response/thinking
        max_iterations = 5
        iteration = 0

        while response.tool_calls and iteration < max_iterations:
            iteration += 1
            round_tool_calls = []
            round_tool_results = []

            for tc_data in response.tool_calls:
                # Parse arguments
                try:
                    args = json.loads(tc_data["arguments"])
                except json.JSONDecodeError:
                    args = {}

                tool_call = ToolCall(
                    id=tc_data["id"],
                    name=tc_data["name"],
                    arguments=args,
                    raw_arguments=tc_data["arguments"],
                )
                round_tool_calls.append(tool_call)
                all_tool_calls.append(tool_call)

                # Execute tool (returns tuple of result dict and command)
                tool_start = time.time()
                result, command = self._execute_tool(tool_call)
                tool_duration_ms = (time.time() - tool_start) * 1000
                round_tool_results.append(result)
                all_tool_results.append(result)

                # Log to TUI with the actual memoir command
                if self.tui:
                    self.tui.log_llm_operation(
                        operation=tool_call.name.replace("memoir_", ""),
                        details=command,
                        tool_name=tool_call.name,
                        namespace=args.get("namespace", self._get_default_namespace()),
                        success=result.get("success", False),
                        duration_ms=tool_duration_ms,
                    )

            # Build follow-up messages with tool results
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": tc.raw_arguments,
                            },
                        }
                        for tc in round_tool_calls
                    ],
                }
            )

            for tc, result in zip(round_tool_calls, round_tool_results):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    }
                )

            # Next LLM call - may return more tool calls or final response
            # Note: Must pass tools again because Anthropic requires tools param
            # when message history contains tool calls
            response = await self.llm.ainvoke_with_tools(messages, tools)

        final_content = response.content
        tool_calls = all_tool_calls
        tool_results = all_tool_results

        # Add assistant message to session
        self.session.add_assistant_message(final_content)

        # Log to TUI
        if self.tui:
            self.tui.log_conversation(
                role="assistant",
                content=final_content,
                user_id=self.user_id,
                session_id=self.session.session_id,
                channel=self.session.channel,
            )

        # Fire message:sent hook
        if self.hooks:
            self.hooks.on_message_sent(
                user_message=user_message,
                assistant_message=final_content,
                session_key=self.session.session_key,
            )

        return AgentResponse(
            content=final_content,
            tool_calls=tool_calls,
            tool_results=tool_results,
            thinking=thinking,
            duration_ms=(time.time() - start_time) * 1000,
        )

    def chat_sync(self, user_message: str) -> AgentResponse:
        """Synchronous wrapper for chat()."""
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.chat(user_message))
        finally:
            loop.close()

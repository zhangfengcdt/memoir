"""
Real LLM Agent - Agent that uses actual LLM for tool calling decisions.

This agent:
1. Sends messages to a real LLM (e.g., claude-haiku-4-5)
2. LLM sees memoir tool definitions
3. LLM decides when to call memoir tools
4. Tool calls execute real memoir CLI commands
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


class RealLLMAgent:
    """
    Agent that uses real LLM for intelligent tool calling.

    Example:
        agent = RealLLMAgent(
            store_path="/path/to/store",
            model="claude-haiku-4-5",
            user_id="alice",
            tui=tui,  # Optional TUI for visualization
        )

        response = await agent.chat("Remember that I prefer dark mode")
        # LLM decides to call memoir_remember tool
        # Tool executes real memoir CLI command
        # LLM provides final response
    """

    SYSTEM_PROMPT = """You are a helpful AI assistant with persistent memory via the Memoir system.

## Tools:
- memoir_help: Get CLI help (call with no args for general help, or specify command name)
- memoir_remember: Store memories (with namespace: 'agent' or 'user_id:{user_id}')
- memoir_recall: Search memories (with namespace: 'agent' or 'user_id:{user_id}')
- memoir_checkout: Switch branches for context isolation
- memoir_forget: Delete a memory

## Namespaces:
- **user_id:{user_id}**: User preferences, facts, projects (default)
- **agent**: Your own learnings, skills, techniques, insights

## Rules:

**Discovering commands:**
- Use memoir_help() to see all available commands
- Use memoir_help(command="remember") to see detailed help for a command

**Storing memories:**
- User preferences/facts → namespace="user_id:{user_id}" (or omit for default)
- Your learnings/skills → namespace="agent"
- Example: "I learned to use rg for fast search" → namespace="agent"
- Example: "User prefers dark mode" → namespace="user_id:{user_id}"

**Recalling memories:**
- When asked about user → search user namespace
- When asked about your skills → search agent namespace
- When asked "what do you remember" → search both namespaces

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

    def start_session(self, session_id: Optional[str] = None) -> Session:
        """Start a new conversation session."""
        self.session = self.session_manager.create_session(
            user_id=self.user_id,
            channel=self.channel,
            agent_id="real-llm",
            session_id=session_id,
        )

        # Fire bootstrap hook
        if self.hooks:
            result = self.hooks.on_agent_bootstrap(self.session.session_key)
            if result.context_injection:
                self.session.metadata["memory_context"] = result.context_injection

        # Log to TUI
        if self.tui:
            self.tui.log_event(
                MemoryEvent(
                    timestamp=time.time(),
                    source=EventSource.SYSTEM,
                    operation="session-start",
                    details=f"User {self.user_id} started session",
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
        # Substitute user_id in system prompt
        system_prompt = self.SYSTEM_PROMPT.replace("{user_id}", self.user_id)
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

        if name == "memoir_remember":
            result = self.cli.remember(
                content=args.get("content", ""),
                namespace=args.get("namespace", f"user_id:{self.user_id}"),
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
                namespace=args.get("namespace", f"user_id:{self.user_id}"),
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
                namespace=args.get("namespace", f"user_id:{self.user_id}"),
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

        elif name == "memoir_checkout":
            result = self.cli.checkout(
                branch_name=args.get("branch", ""),
                create_if_missing=args.get("create_if_missing", True),
            )
            return (
                {
                    "success": result.success,
                    "message": (
                        f"Switched to branch {args.get('branch')}"
                        if result.success
                        else result.error
                    ),
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

        # First LLM call - may return tool calls
        response = await self.llm.ainvoke_with_tools(messages, tools)

        tool_calls = []
        tool_results = []
        thinking = response.content  # Initial response/thinking

        # Process tool calls if any
        if response.tool_calls:
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
                tool_calls.append(tool_call)

                # Execute tool (returns tuple of result dict and command)
                tool_start = time.time()
                result, command = self._execute_tool(tool_call)
                tool_duration_ms = (time.time() - tool_start) * 1000
                tool_results.append(result)

                # Log to TUI with the actual memoir command
                if self.tui:
                    self.tui.log_llm_operation(
                        operation=tool_call.name.replace("memoir_", ""),
                        details=command,
                        tool_name=tool_call.name,
                        namespace=args.get("namespace", f"user_id:{self.user_id}"),
                        success=result.get("success", False),
                        duration_ms=tool_duration_ms,
                    )

            # Build follow-up messages with tool results
            messages.append(
                {
                    "role": "assistant",
                    "content": thinking or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": tc.raw_arguments,
                            },
                        }
                        for tc in tool_calls
                    ],
                }
            )

            for tc, result in zip(tool_calls, tool_results):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result),
                    }
                )

            # Second LLM call - get final response
            # Note: Must pass tools again because Anthropic requires tools param
            # when message history contains tool calls
            final_response = await self.llm.ainvoke_with_tools(messages, tools)
            final_content = final_response.content
        else:
            final_content = response.content

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

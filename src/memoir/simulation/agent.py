"""
Agent Simulation - Simulate LLM-powered agent with memoir integration.

This module provides an agent that:
1. Uses LLM for conversation
2. Has memoir skill injected into system prompt
3. Can execute memoir tool calls
4. Integrates with hooks for automatic memory operations
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from memoir.simulation.cli_executor import CLIExecutor
from memoir.simulation.hooks import HookSystem
from memoir.simulation.session import Session, SessionManager
from memoir.simulation.skill import SkillInjector

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Configuration for agent simulation."""

    # Agent identity
    agent_id: str = "main"
    name: str = "Memoir Agent"

    # LLM configuration
    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000

    # Memoir configuration
    store_path: Optional[str] = None
    enable_hooks: bool = True
    enable_tools: bool = True

    # System prompt customization
    base_system_prompt: str = """You are a helpful AI assistant with access to
persistent memory through the Memoir system. You can remember important
information across conversations and recall it when needed.

Be concise and helpful. When you learn something important about the user
or discover a useful technique, consider storing it in memory for future use.
"""

    # Tool execution
    tool_executor: Optional[Callable] = None


@dataclass
class ToolCall:
    """A tool call from the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class AgentResponse:
    """Response from the agent."""

    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    hook_results: list[dict] = field(default_factory=list)
    memory_context: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0


class Agent:
    """
    Simulated agent with memoir integration.

    This agent:
    1. Manages its own session
    2. Has memoir skill in system prompt
    3. Executes memoir tool calls
    4. Fires hooks at appropriate times

    Example:
        agent = Agent(
            config=AgentConfig(
                store_path="/path/to/store",
                model="gpt-4o-mini",
            ),
            user_id="user123",
        )

        # Start a conversation
        response = await agent.chat("Hello! I prefer dark mode.")
        print(response.content)

        # Agent can store memories via tools
        response = await agent.chat("Remember that I'm working on Project X")
        print(response.tool_results)
    """

    def __init__(
        self,
        config: AgentConfig,
        user_id: str = "default",
        session_manager: Optional[SessionManager] = None,
    ):
        """
        Initialize agent.

        Args:
            config: Agent configuration
            user_id: User ID for this agent instance
            session_manager: Optional shared session manager
        """
        self.config = config
        self.user_id = user_id

        # Session management
        self.session_manager = session_manager or SessionManager()
        self.session: Optional[Session] = None

        # Memoir components
        self.skill_injector = SkillInjector(
            user_id=user_id,
            store_path=config.store_path,
        )

        self.hooks: Optional[HookSystem] = None
        if config.enable_hooks and config.store_path:
            self.hooks = HookSystem(
                store_path=config.store_path,
                user_id=user_id,
            )

        self.cli: Optional[CLIExecutor] = None
        if config.store_path:
            self.cli = CLIExecutor(config.store_path)

        # LLM client (lazy loaded)
        self._llm = None

    @property
    def llm(self):
        """Lazy-load LLM client."""
        if self._llm is None:
            from memoir.llm import get_llm

            self._llm = get_llm(
                model=self.config.model,
                temperature=self.config.temperature,
            )
        return self._llm

    def start_session(self, session_id: Optional[str] = None) -> Session:
        """
        Start a new conversation session.

        Fires the agent:bootstrap hook to inject memories.

        Args:
            session_id: Optional session ID

        Returns:
            New session
        """
        self.session = self.session_manager.create_session(
            user_id=self.user_id,
            agent_id=self.config.agent_id,
            session_id=session_id,
        )

        # Fire bootstrap hook
        if self.hooks:
            result = self.hooks.on_agent_bootstrap(self.session.session_key)
            if result.context_injection:
                self.session.metadata["memory_context"] = result.context_injection

        return self.session

    def get_system_prompt(self) -> str:
        """
        Build the full system prompt.

        Includes:
        - Base system prompt
        - Memoir skill instructions
        - Injected memory context (from bootstrap hook)

        Returns:
            Complete system prompt
        """
        parts = [self.config.base_system_prompt]

        # Add memoir skill
        if self.config.enable_tools:
            parts.append(self.skill_injector.get_system_prompt_injection())

        # Add memory context from bootstrap
        if self.session and "memory_context" in self.session.metadata:
            parts.append(self.session.metadata["memory_context"])

        return "\n\n".join(parts)

    async def chat(self, user_message: str) -> AgentResponse:
        """
        Send a message and get a response.

        This method:
        1. Fires message:received hook (may recall memories)
        2. Sends to LLM with tools
        3. Executes any tool calls
        4. Fires message:sent hook (buffers for storage)

        Args:
            user_message: User's message

        Returns:
            AgentResponse with content, tool results, etc.
        """
        start_time = time.time()

        # Ensure session exists
        if not self.session:
            self.start_session()

        hook_results = []
        memory_context = None

        # Fire message:received hook (keyword recall)
        if self.hooks:
            result = self.hooks.on_message_received(
                message=user_message,
                session_key=self.session.session_key,
            )
            if result.context_injection:
                memory_context = result.context_injection
            hook_results.append(result.__dict__)

        # Add user message to session
        self.session.add_user_message(user_message)

        # Build messages for LLM
        messages = self._build_messages(memory_context)

        # Get tools if enabled
        tools = None
        if self.config.enable_tools:
            tools = self.skill_injector.get_tool_definitions()

        # Call LLM
        response_content, tool_calls = await self._call_llm(messages, tools)

        # Execute tool calls
        tool_results = []
        if tool_calls:
            for tc in tool_calls:
                result = self._execute_tool_call(tc)
                tool_results.append(result)

            # If there were tool calls, get follow-up response
            if tool_results:
                # Add assistant message with tool calls and results
                messages.append(
                    {
                        "role": "assistant",
                        "content": response_content or "",
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.name,
                                    "arguments": json.dumps(tc.arguments),
                                },
                            }
                            for tc in tool_calls
                        ],
                    }
                )

                # Add tool results
                for tc, result in zip(tool_calls, tool_results):
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": json.dumps(result),
                        }
                    )

                # Get follow-up response
                response_content, _ = await self._call_llm(messages, tools=None)

        # Add assistant message to session
        self.session.add_assistant_message(response_content)

        # Fire message:sent hook (buffer for storage)
        if self.hooks:
            result = self.hooks.on_message_sent(
                user_message=user_message,
                assistant_message=response_content,
                session_key=self.session.session_key,
            )
            hook_results.append(result.__dict__)

        return AgentResponse(
            content=response_content,
            tool_calls=tool_calls,
            tool_results=tool_results,
            hook_results=hook_results,
            memory_context=memory_context,
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

    def end_session(self) -> None:
        """
        End the current session.

        Fires hooks to flush any buffered data.
        """
        if self.session and self.hooks:
            self.hooks.flush_buffer(self.session.session_key)

        if self.session:
            self.session_manager.end_session(self.session.session_key)
            self.session = None

    # ==========================================================================
    # Private Methods
    # ==========================================================================

    def _build_messages(self, extra_context: Optional[str] = None) -> list[dict]:
        """Build message list for LLM."""
        messages = [{"role": "system", "content": self.get_system_prompt()}]

        # Add extra context if provided (from recall hook)
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
                messages.append(
                    {
                        "role": msg.role,
                        "content": msg.content,
                    }
                )

        return messages

    async def _call_llm(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> tuple[str, list[ToolCall]]:
        """
        Call the LLM.

        Args:
            messages: Message history
            tools: Tool definitions

        Returns:
            Tuple of (response content, tool calls)
        """
        try:
            # Use LangChain-style invocation
            from langchain_core.messages import (
                AIMessage,
                HumanMessage,
                SystemMessage,
                ToolMessage,
            )

            # Convert to LangChain messages
            lc_messages = []
            for msg in messages:
                role = msg["role"]
                content = msg.get("content", "")

                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    if "tool_calls" in msg:
                        lc_messages.append(
                            AIMessage(
                                content=content,
                                tool_calls=[
                                    {
                                        "id": tc["id"],
                                        "name": tc["function"]["name"],
                                        "args": json.loads(tc["function"]["arguments"]),
                                    }
                                    for tc in msg["tool_calls"]
                                ],
                            )
                        )
                    else:
                        lc_messages.append(AIMessage(content=content))
                elif role == "tool":
                    lc_messages.append(
                        ToolMessage(
                            content=content,
                            tool_call_id=msg["tool_call_id"],
                        )
                    )

            # Bind tools if provided
            llm = self.llm
            if tools:
                llm = llm.bind_tools(tools)

            # Invoke
            response = await llm.ainvoke(lc_messages)

            # Extract content and tool calls
            content = (
                response.content if hasattr(response, "content") else str(response)
            )

            tool_calls = []
            if hasattr(response, "tool_calls") and response.tool_calls:
                for tc in response.tool_calls:
                    tool_calls.append(
                        ToolCall(
                            id=tc.get("id", f"call_{len(tool_calls)}"),
                            name=tc["name"],
                            arguments=tc.get("args", {}),
                        )
                    )

            return content, tool_calls

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return f"I apologize, but I encountered an error: {e}", []

    def _execute_tool_call(self, tool_call: ToolCall) -> dict:
        """Execute a memoir tool call."""
        if self.config.tool_executor:
            return self.config.tool_executor(tool_call.name, tool_call.arguments)

        return self.skill_injector.execute_tool_call(
            tool_call.name,
            tool_call.arguments,
        )


class MockAgent(Agent):
    """
    Mock agent for testing without LLM.

    Useful for testing hook behavior and tool execution
    without making actual LLM calls.
    """

    def __init__(
        self,
        config: AgentConfig,
        user_id: str = "default",
        responses: Optional[list[str]] = None,
        **kwargs,
    ):
        """
        Initialize mock agent.

        Args:
            config: Agent configuration
            user_id: User ID
            responses: List of canned responses to cycle through
            **kwargs: Additional args for Agent
        """
        super().__init__(config, user_id, **kwargs)
        self.responses = responses or [
            "I understand. Let me help you with that.",
            "That's interesting! I'll remember that.",
            "Sure, I can do that for you.",
        ]
        self._response_index = 0

    async def _call_llm(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> tuple[str, list[ToolCall]]:
        """Return canned response instead of calling LLM."""
        response = self.responses[self._response_index % len(self.responses)]
        self._response_index += 1
        return response, []

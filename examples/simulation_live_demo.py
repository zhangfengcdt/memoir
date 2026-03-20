#!/usr/bin/env python3
"""
Live Simulation Demo - Real-time visualization of memoir agent operations.

This demo shows:
- Hook-triggered operations (yellow [HOOK] labels)
- LLM-triggered operations (cyan [LLM] labels)
- Real-time memory tree updates from the REAL store
- Multi-user conversations

Usage:
    # Run with mock agent (no LLM required)
    python examples/simulation_live_demo.py --mock

    # Run with real LLM (requires ANTHROPIC_API_KEY)
    python examples/simulation_live_demo.py --model claude-haiku-4-5

    # Run for specific duration
    python examples/simulation_live_demo.py --duration 30
"""

import argparse
import asyncio
import sys
import tempfile
import threading
import time
from pathlib import Path

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from memoir.simulation.cli_executor import CLIExecutor
from memoir.simulation.live_tui import (
    EventSource,
    LiveSimulationTUI,
    MemoryEvent,
)
from memoir.simulation.session import SessionManager


class LiveSimulationDemo:
    """Demo that runs agents with live TUI visualization."""

    def __init__(
        self,
        store_path: str,
        model: str = "claude-haiku-4-5",
        use_mock: bool = False,
    ):
        self.store_path = store_path
        self.model = model
        self.use_mock = use_mock

        # Initialize memoir store
        cli = CLIExecutor(store_path)
        result = cli.new(store_path)
        if not result.success:
            print(f"Warning: Store creation: {result.error}")

        # Create TUI
        self.tui = LiveSimulationTUI(store_path)

        # Session manager for all users
        self.session_manager = SessionManager()

    def create_mock_agent(self, user_id: str):
        """Create a mock agent for testing without LLM."""
        from memoir.simulation.agent import AgentConfig
        from memoir.simulation.hooks import HookSystem
        from memoir.simulation.live_tui import (
            InstrumentedHookSystem,
            InstrumentedSkillInjector,
        )
        from memoir.simulation.skill import SkillInjector

        # Create base components
        base_hooks = HookSystem(
            store_path=self.store_path,
            user_id=user_id,
            batch_size=3,
        )
        base_skill = SkillInjector(
            user_id=user_id,
            store_path=self.store_path,
        )

        # Wrap with instrumentation
        instrumented_hooks = InstrumentedHookSystem(base_hooks, self.tui)
        instrumented_skill = InstrumentedSkillInjector(base_skill, self.tui)

        config = AgentConfig(
            store_path=self.store_path,
            enable_hooks=True,
            enable_tools=True,
        )

        return MockAgentWithInstrumentation(
            config=config,
            user_id=user_id,
            session_manager=self.session_manager,
            tui=self.tui,
            hooks=instrumented_hooks,
            skill_injector=instrumented_skill,
        )

    def create_real_agent(self, user_id: str):
        """Create a real LLM agent."""
        from memoir.simulation.real_llm_agent import RealLLMAgent

        return RealLLMAgent(
            store_path=self.store_path,
            model=self.model,
            user_id=user_id,
            session_manager=self.session_manager,
            tui=self.tui,
            enable_hooks=True,  # Enable hooks for bootstrap/recall
        )

    async def run_user_scenario(
        self,
        user_id: str,
        messages: list[str],
        delay: float = 3.0,
    ):
        """Run a scenario for a single user."""
        # Create appropriate agent
        if self.use_mock:
            agent = self.create_mock_agent(user_id)
        else:
            agent = self.create_real_agent(user_id)

        # Start session
        self.tui.log_event(
            MemoryEvent(
                timestamp=time.time(),
                source=EventSource.SYSTEM,
                operation="session-start",
                details=f"User {user_id} starting session",
            )
        )

        session = agent.start_session()

        for message in messages:
            await asyncio.sleep(delay)

            # Log user message (for mock agent - real agent logs internally)
            if self.use_mock:
                self.tui.log_conversation(
                    role="user",
                    content=message,
                    user_id=user_id,
                    session_id=session.session_id,
                )

            try:
                # Get response
                response = await agent.chat(message)

                # Log assistant response (for mock agent)
                if self.use_mock:
                    self.tui.log_conversation(
                        role="assistant",
                        content=response.content,
                        user_id=user_id,
                        session_id=session.session_id,
                    )

                # Log tool calls info
                if response.tool_calls:
                    for tc in response.tool_calls:
                        self.tui.log_event(
                            MemoryEvent(
                                timestamp=time.time(),
                                source=EventSource.LLM,
                                operation="tool-result",
                                details=f"{tc.name}: {str(tc.arguments)[:40]}...",
                            )
                        )

            except Exception as e:
                self.tui.log_event(
                    MemoryEvent(
                        timestamp=time.time(),
                        source=EventSource.SYSTEM,
                        operation="error",
                        details=str(e)[:50],
                        success=False,
                    )
                )

            await asyncio.sleep(delay / 2)

        # End session
        agent.end_session()

        self.tui.log_event(
            MemoryEvent(
                timestamp=time.time(),
                source=EventSource.SYSTEM,
                operation="session-end",
                details=f"User {user_id} session ended",
            )
        )

    async def run_demo_scenarios(self):
        """Run user scenario with 30 turns covering various memory types."""
        # Extended conversation with user preferences and agent learnings
        messages = [
            # User preferences
            "Hi! Please remember that I prefer dark mode.",
            "Also remember that I use vim keybindings.",
            "I like to use Python for most of my projects.",
            "My timezone is Pacific Time (PST).",
            "I prefer concise responses over verbose ones.",
            # Project context
            "I'm working on an API refactoring project, store that.",
            "The project uses FastAPI and PostgreSQL.",
            "We're migrating from REST to GraphQL.",
            # Agent learnings - teach the agent some skills
            "By the way, you should remember that 'rg' is faster than 'grep' for searching code. Store this as your own learning.",
            "Another tip for you: use 'jq' for parsing JSON in the terminal. Remember this as an agent skill.",
            "You learned that FastAPI's dependency injection is great for testing. Store in agent namespace.",
            # Recall user info
            "What do you remember about my preferences?",
            # More user info
            "I usually work from 9am to 6pm.",
            "My favorite programming language is Rust, but I use Python more often.",
            "I don't like excessive comments in code.",
            # More agent learnings
            "Remember as your skill: pytest fixtures are better than setUp/tearDown.",
            "Store as agent learning: always use type hints in Python for better IDE support.",
            "Your learning: pre-commit hooks save time on code review.",
            # Recall agent skills
            "What skills have you learned?",
            # More user context
            "I'm also learning Go for systems programming.",
            "My git workflow uses feature branches and squash merges.",
            "I prefer tabs over spaces, but follow project conventions.",
            # Technical preferences
            "I use Docker for all my development environments.",
            "Kubernetes is my preferred orchestration platform.",
            "I value test coverage above 80%.",
            # More agent learnings
            "Agent tip: use 'make' for project automation, store this.",
            "Your learning: black + isort + ruff is a great Python linting combo.",
            # Final recalls
            "What do you know about my development setup?",
            "What are all your agent learnings?",
            "Summarize everything you remember about me.",
        ]

        await self.run_user_scenario("alice", messages, delay=4.0)

    def run(self, duration: float = 60.0):
        """Run the live demo."""
        # Start TUI in separate thread - run indefinitely until stopped
        tui_thread = threading.Thread(
            target=lambda: self.tui.run(duration=0),  # 0 = run forever
            daemon=True,
        )
        tui_thread.start()

        # Give TUI time to start
        time.sleep(1)

        # Run scenarios
        try:
            asyncio.run(self.run_demo_scenarios())
        except Exception as e:
            print(f"Error in scenarios: {e}")

        # Log completion message
        self.tui.log_event(
            MemoryEvent(
                timestamp=time.time(),
                source=EventSource.SYSTEM,
                operation="demo-complete",
                details="Simulation finished. Press Ctrl+C to exit.",
            )
        )

        # Wait for Ctrl+C
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.tui.stop()


class MockAgentWithInstrumentation:
    """Mock agent with TUI instrumentation."""

    def __init__(
        self,
        config,
        user_id: str,
        session_manager,
        tui,
        hooks,
        skill_injector,
    ):
        self.config = config
        self.user_id = user_id
        self.session_manager = session_manager
        self.tui = tui
        self.hooks = hooks
        self.skill_injector = skill_injector
        self.session = None

        self.responses = [
            "I'll remember that for you!",
            "Got it! I've stored that in my memory.",
            "Based on my memories, here's what I know about you...",
            "I've noted your preference.",
        ]
        self._response_index = 0

    def start_session(self, session_id=None):
        """Start session with bootstrap hook."""
        self.session = self.session_manager.create_session(
            user_id=self.user_id,
            agent_id="mock",
            session_id=session_id,
        )

        if self.hooks:
            self.hooks.on_agent_bootstrap(self.session.session_key)

        return self.session

    async def chat(self, user_message: str):
        """Chat with mock responses but real tool execution."""
        from memoir.simulation.agent import AgentResponse, ToolCall

        if not self.session:
            self.start_session()

        # Fire message:received hook
        if self.hooks:
            self.hooks.on_message_received(
                message=user_message,
                session_key=self.session.session_key,
            )

        self.session.add_user_message(user_message)

        # Simulate tool calls based on keywords
        tool_calls = []
        tool_results = []

        lower_msg = user_message.lower()

        if any(kw in lower_msg for kw in ["remember", "store", "please remember"]):
            # Extract what to remember
            content = user_message
            if "remember that" in lower_msg:
                content = user_message.split("remember that", 1)[-1].strip()
            elif "please remember" in lower_msg:
                content = user_message.split("please remember", 1)[-1].strip()

            tc = ToolCall(
                id=f"call_{time.time()}",
                name="memoir_remember",
                arguments={"content": content, "namespace": f"user:{self.user_id}"},
            )
            tool_calls.append(tc)
            result = self.skill_injector.execute_tool_call(tc.name, tc.arguments)
            tool_results.append(result)

        elif any(kw in lower_msg for kw in ["recall", "remember about", "what do you know"]):
            tc = ToolCall(
                id=f"call_{time.time()}",
                name="memoir_recall",
                arguments={"query": "user preferences", "namespace": f"user:{self.user_id}"},
            )
            tool_calls.append(tc)
            result = self.skill_injector.execute_tool_call(tc.name, tc.arguments)
            tool_results.append(result)

        # Get response
        response_content = self.responses[self._response_index % len(self.responses)]
        self._response_index += 1

        self.session.add_assistant_message(response_content)

        # Fire message:sent hook
        if self.hooks:
            self.hooks.on_message_sent(
                user_message=user_message,
                assistant_message=response_content,
                session_key=self.session.session_key,
            )

        return AgentResponse(
            content=response_content,
            tool_calls=tool_calls,
            tool_results=tool_results,
        )

    def end_session(self):
        """End session with flush hook."""
        if self.session and self.hooks:
            self.hooks.flush_buffer(self.session.session_key)

        if self.session:
            self.session_manager.end_session(self.session.session_key)
            self.session = None


def main():
    parser = argparse.ArgumentParser(
        description="Live Simulation Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with mock agent (no API key needed)
    python examples/simulation_live_demo.py --mock

    # Run with Claude Haiku (requires ANTHROPIC_API_KEY)
    python examples/simulation_live_demo.py --model claude-haiku-4-5

    # Set API key and run
    export ANTHROPIC_API_KEY=your-key-here
    python examples/simulation_live_demo.py
        """,
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=60.0,
        help="Duration in seconds (default: 60)",
    )
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5",
        help="LLM model to use (default: claude-haiku-4-5)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use mock agent instead of real LLM",
    )
    parser.add_argument(
        "--store",
        help="Path to memoir store (default: temp directory)",
    )

    args = parser.parse_args()

    # Use temp directory if no store specified
    if args.store:
        store_path = args.store
    else:
        tmpdir = tempfile.mkdtemp(prefix="memoir-live-demo-")
        store_path = f"{tmpdir}/store"
        print(f"Using temporary store: {store_path}")

    # Check for API key if using real LLM
    if not args.mock:
        import os

        if not os.getenv("ANTHROPIC_API_KEY"):
            print("\n" + "=" * 60)
            print("ERROR: ANTHROPIC_API_KEY not set")
            print("=" * 60)
            print("\nTo use real LLM, set your API key:")
            print("  export ANTHROPIC_API_KEY=your-key-here")
            print("\nOr run with --mock for testing without an API key:")
            print("  python examples/simulation_live_demo.py --mock")
            print()
            sys.exit(1)

    print("\n" + "=" * 60)
    print("Memoir Live Simulation Demo")
    print("=" * 60)
    print(f"\nMode: {'MOCK' if args.mock else 'REAL LLM'}")
    if not args.mock:
        print(f"Model: {args.model}")
    print(f"Store: {store_path}")
    print("\nLegend:")
    print("  [HOOK] = Automatically triggered by hooks (yellow)")
    print("  [LLM]  = Agent tool call (cyan)")
    print("  [SYS]  = System event (magenta)")
    print("\nPress Ctrl+C to exit\n")

    time.sleep(2)

    demo = LiveSimulationDemo(
        store_path=store_path,
        model=args.model,
        use_mock=args.mock,
    )

    try:
        demo.run(duration=args.duration)
    except KeyboardInterrupt:
        print("\nDemo stopped.")


if __name__ == "__main__":
    main()

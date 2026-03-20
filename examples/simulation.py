#!/usr/bin/env python3
"""
Live Simulation Demo - Real-time visualization of memoir agent operations.

This demo shows:
- Hook-triggered operations (yellow [HOOK] labels)
- LLM-triggered operations (cyan [LLM] labels)
- Real-time memory tree updates from the REAL store
- Multi-user conversations with identity-based namespaces

Usage:
    # Run with Claude Haiku (requires ANTHROPIC_API_KEY)
    python examples/simulation.py --model claude-haiku-4-5
"""

import argparse
import asyncio
import json
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
    ):
        self.store_path = store_path
        self.model = model

        # Initialize memoir store
        cli = CLIExecutor(store_path)
        result = cli.new(store_path)
        if not result.success:
            print(f"Warning: Store creation: {result.error}")

        # Seed demo identity configs into store
        # (Hooks and agents read these dynamically from the store)
        self._seed_demo_identities(cli)

        # Create TUI
        self.tui = LiveSimulationTUI(store_path)

        # Session manager for all users
        self.session_manager = SessionManager()

    def _seed_demo_identities(self, cli: CLIExecutor):
        """Seed demo identity configurations into the store.

        Stores all identity mappings in a single JSON config.
        Hooks inject this into LLM prompt, and LLM figures out the correct namespace.

        Tests both mapping formats:
        - channel only: "discord" matches any user
        - channel:user_id: "web:51321" matches specific user
        """
        identities = {
            # Specific user mapping (channel:user_id)
            "kevin": {"channels": ["web:51321"]},
            "slackBot": {"channels": ["slack:U04ABCD1234"]},
            "TeleBot": {"channels": ["telegram:12345678"]},
            # Channel-only mapping (any user on discord)
            "feng": {"channels": ["discord"]},
        }

        cli.set(
            key="config.identities",
            content=json.dumps(identities),
            namespace="agent",
        )

    def create_agent(self, user_id: str, channel: str = "web"):
        """Create an LLM agent for the given user and channel."""
        from memoir.simulation.llm_agent import LLMAgent

        return LLMAgent(
            store_path=self.store_path,
            model=self.model,
            user_id=user_id,
            channel=channel,
            session_manager=self.session_manager,
            tui=self.tui,
            enable_hooks=True,
        )

    async def run_user_scenario(
        self,
        user_id: str,
        messages: list[str],
        channel: str = "web",
        delay: float = 3.0,
    ):
        """Run a scenario for a single user on a specific channel."""
        agent = self.create_agent(user_id, channel)

        # Start session
        self.tui.log_event(
            MemoryEvent(
                timestamp=time.time(),
                source=EventSource.SYSTEM,
                operation="session-start",
                details=f"{channel}:{user_id} starting session",
            )
        )

        session = agent.start_session()

        for message in messages:
            await asyncio.sleep(delay)

            try:
                response = await agent.chat(message)

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
                details=f"{channel}:{user_id} session ended",
            )
        )

    async def run_demo_scenarios(self):
        """Run 4 concurrent user sessions across different channels.

        Demonstrates OpenClaw's channel/session/user model:
        - Different users on different channels chat simultaneously
        - Each channel has its own user ID format (platform-specific)
        - Without manual linking, each is a separate user with separate memory
        - Session display shows channel:user_id:session format
        """
        # Web channel - developer preferences
        web_messages = [
            "Hi! Please remember that I prefer dark mode.",
            "Also remember that I use vim keybindings.",
            "I like to use Python for most of my projects.",
            "My timezone is Pacific Time (PST).",
            "Remember as your skill: 'rg' is faster than 'grep'.",
            "What do you know about my preferences?",
        ]

        # Slack channel - work context
        slack_messages = [
            "Hey, I'm working on an API refactoring project.",
            "The project uses FastAPI and PostgreSQL.",
            "We're migrating from REST to GraphQL.",
            "Store as your learning: FastAPI dependency injection is great.",
            "I prefer TypeScript for frontend work.",
            "What do you remember about my project?",
        ]

        # Discord channel - gaming/casual
        discord_messages = [
            "I'm learning Go for systems programming.",
            "My favorite language is Rust, but I use Python more.",
            "Remember: I stream on weekends.",
            "Your learning: pytest fixtures beat setUp/tearDown.",
            "I use Arch Linux btw.",
            "What preferences do you remember?",
        ]

        # Telegram channel - mobile quick notes
        telegram_messages = [
            "Quick note: I use Docker for all dev environments.",
            "Remember: I value test coverage above 80%.",
            "Store: I prefer tabs over spaces.",
            "Your learning: black + isort + ruff is great for Python.",
            "My work hours are 9am-6pm.",
            "What skills have you learned?",
        ]

        # Run all 4 channel sessions concurrently
        # Each channel has its own user ID format (like real platforms)
        await asyncio.gather(
            self.run_user_scenario("51321", web_messages, channel="web", delay=4.0),
            self.run_user_scenario("U04ABCD1234", slack_messages, channel="slack", delay=4.5),
            self.run_user_scenario("987654321012", discord_messages, channel="discord", delay=5.0),
            self.run_user_scenario("12345678", telegram_messages, channel="telegram", delay=5.5),
        )

    def run(self):
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


def main():
    parser = argparse.ArgumentParser(
        description="Live Simulation Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run with Claude Haiku (requires ANTHROPIC_API_KEY)
    python examples/simulation.py --model claude-haiku-4-5

    # Set API key and run
    export ANTHROPIC_API_KEY=your-key-here
    python examples/simulation.py
        """,
    )
    parser.add_argument(
        "--model",
        default="claude-haiku-4-5",
        help="LLM model to use (default: claude-haiku-4-5)",
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

    # Check for API key
    import os

    if not os.getenv("ANTHROPIC_API_KEY"):
        print("\n" + "=" * 60)
        print("ERROR: ANTHROPIC_API_KEY not set")
        print("=" * 60)
        print("\nSet your API key:")
        print("  export ANTHROPIC_API_KEY=your-key-here")
        print()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Memoir Live Simulation Demo")
    print("=" * 60)
    print(f"\nModel: {args.model}")
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
    )

    try:
        demo.run()
    except KeyboardInterrupt:
        print("\nDemo stopped.")


if __name__ == "__main__":
    main()

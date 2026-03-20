#!/usr/bin/env python3
"""
Live Simulation Demo - Real-time visualization of memoir agent operations.

This demo shows:
- Hook-triggered operations (yellow [HOOK] labels)
- LLM-triggered operations (cyan [LLM] labels)
- Real-time memory tree updates from the REAL store
- Multi-user conversations with identity-based namespaces
- Interactive slash commands (/memoir_*, /summarize, /incognito, etc.)

Usage:
    # Run automated demo (requires ANTHROPIC_API_KEY)
    python examples/simulation.py --model claude-haiku-4-5

    # Run interactive mode with LLM chat (requires ANTHROPIC_API_KEY)
    python examples/simulation.py --interactive --model claude-haiku-4-5

    # Run interactive with slash commands only (no API key needed)
    python examples/simulation.py --interactive --no-chat
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
from memoir.simulation.live_tui import EventSource, LiveSimulationTUI, MemoryEvent
from memoir.simulation.session import SessionManager
from memoir.simulation.skill import SkillInjector, get_slash_commands


class LiveSimulationDemo:
    """Demo that runs agents with live TUI visualization."""

    def __init__(
        self,
        store_path: str,
        model: str = "claude-haiku-4-5",
        interactive: bool = False,
    ):
        self.store_path = store_path
        self.model = model
        self.interactive = interactive

        # Initialize memoir store
        cli = CLIExecutor(store_path)
        result = cli.new(store_path)
        if not result.success:
            print(f"Warning: Store creation: {result.error}")

        # Seed demo identity configs into store
        # (Hooks and agents read these dynamically from the store)
        self._seed_demo_identities(cli)

        # Create TUI (interactive mode for single conversation view)
        self.tui = LiveSimulationTUI(store_path, interactive=interactive)

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

    def run_interactive(self, enable_chat: bool = True):
        """Run in interactive mode - accept slash commands and chat with LLM.

        Uses a scrolling console approach (not full-screen) so input is visible.
        Reuses TUI render methods for memory store and stats panels.

        Args:
            enable_chat: If True, non-slash text is sent to LLM for chat.
                        If False, only slash commands are accepted.
        """
        import sys

        from rich.console import Console, Group
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        console = Console()

        # User identity for namespace (channel:user_id pattern)
        user_id = "interactive"
        channel = "repl"
        user_namespace = f"{channel}:{user_id}"

        skill = SkillInjector(user_id=user_id, store_path=self.store_path)

        # Conversation history for display (role, content, is_slash)
        conversation: list[tuple[str, str, bool]] = []

        # Create LLM agent for chat (if enabled)
        agent = None
        if enable_chat:
            agent = self.create_agent(user_id=user_id, channel=channel)
            agent.start_session()

        def render_conversation():
            """Render the conversation panel."""
            if not conversation:
                return Panel(
                    Text("Start chatting! Type a message or /command", style="dim"),
                    title="[bold green]Conversation[/bold green]",
                    border_style="green",
                    height=15,
                )

            content = []
            # Show last 12 messages
            for role, msg, is_slash in conversation[-12:]:
                if role == "user":
                    if is_slash:
                        content.append(Text(f"> {msg}", style="yellow"))
                    else:
                        content.append(Text(f"> {msg}", style="green"))
                elif role == "slash_result":
                    content.append(Text(f"  {msg}", style="dim yellow"))
                else:
                    # Truncate long AI responses for display
                    display_msg = msg[:200] + "..." if len(msg) > 200 else msg
                    content.append(Text(f"  {display_msg}", style="cyan"))

            return Panel(
                Group(*content),
                title="[bold green]Conversation[/bold green]",
                border_style="green",
                height=15,
            )

        def refresh_display():
            """Refresh the display with all panels - reuses TUI render methods."""
            # Clear screen and move cursor to top
            print("\033[2J\033[H", end="")
            sys.stdout.flush()

            # Process any queued events (so stats update)
            self.tui._process_events()

            # Header
            console.print(Panel(
                f"[bold cyan]Memoir Interactive[/bold cyan] │ Store: {Path(self.store_path).name} │ Namespace: {user_namespace}",
                style="bold",
            ))

            # Use Table for side-by-side layout (doesn't fill screen like Layout)
            main_table = Table.grid(padding=0, expand=True)
            main_table.add_column(ratio=3)
            main_table.add_column(ratio=2)

            # Right column: memories on top, stats below
            right_content = Group(
                self.tui._render_memories(),
                self.tui._render_stats(),
            )

            main_table.add_row(
                render_conversation(),
                right_content,
            )

            console.print(main_table)

            # Input hint and bordered input area right below panels
            mode_hint = "Chat or /command" if enable_chat else "/command only"
            console.print(f"[dim]({mode_hint} │ /help │ /quit)[/dim]")
            console.rule(style="dim")  # Top line of input box

        # Initial display
        refresh_display()

        # Interactive loop
        try:
            while True:
                try:
                    # Show prompt and get input
                    sys.stdout.write("> ")
                    sys.stdout.flush()
                    cmd = input().strip()
                    console.rule(style="dim")  # Bottom line of input box
                    if not cmd:
                        refresh_display()
                        continue

                    # Handle special commands
                    if cmd in ("/quit", "/exit", "/q"):
                        break
                    elif cmd == "/help":
                        console.print()
                        console.print("[bold]Commands:[/bold]")
                        console.print("  [cyan]/remember <text>[/cyan]  - Store a memory")
                        console.print("  [cyan]/recall <query>[/cyan]   - Search memories")
                        console.print("  [cyan]/summarize[/cyan]        - Summarize memories")
                        console.print("  [cyan]/incognito[/cyan]        - Start incognito mode")
                        console.print("  [cyan]/off-record[/cyan]       - Start off-record mode")
                        console.print("  [cyan]/on-record[/cyan]        - Return to normal")
                        console.print("  [cyan]/commits[/cyan]          - Show history")
                        console.print("  [cyan]/quit[/cyan]             - Exit")
                        if enable_chat:
                            console.print()
                            console.print("[dim]Or just type a message to chat with the AI[/dim]")
                        console.print()
                        console.print("[dim]Press Enter to continue...[/dim]", end="")
                        input()
                        refresh_display()
                        continue
                    elif cmd == "/commands":
                        cmds = get_slash_commands()
                        console.print(f"[dim]Available: /{', /'.join(cmds)}[/dim]")
                        console.print("[dim]Press Enter to continue...[/dim]", end="")
                        input()
                        refresh_display()
                        continue
                    elif cmd == "/clear":
                        conversation.clear()
                        refresh_display()
                        continue

                    # Handle memoir slash commands
                    if cmd.startswith("/"):
                        # Add slash command to conversation
                        conversation.append(("user", cmd, True))

                        # Log to TUI for stats tracking
                        self.tui.log_event(MemoryEvent(
                            timestamp=time.time(),
                            source=EventSource.USER,
                            operation="slash-cmd",
                            details=cmd,
                        ))

                        # Normalize: /summarize -> /memoir_summarize
                        if not cmd.startswith("/memoir_"):
                            slash_cmd = "/memoir_" + cmd[1:]
                        else:
                            slash_cmd = cmd

                        result = skill.execute_slash_command(slash_cmd, default_namespace=user_namespace)

                        # Add result to conversation
                        if result["success"]:
                            result_text = f"✓ {result.get('command', 'Done')}"
                            if result.get("data"):
                                data = result["data"]
                                if isinstance(data, dict):
                                    if "memories" in data:
                                        count = len(data["memories"])
                                        result_text = f"✓ Found {count} memories"
                                    elif "key" in data:
                                        result_text = f"✓ Stored at: {data['key']}"
                        else:
                            result_text = f"✗ {result.get('error', 'Failed')}"

                        conversation.append(("slash_result", result_text, True))
                        refresh_display()

                    elif enable_chat and agent:
                        # Add user message to conversation
                        conversation.append(("user", cmd, False))
                        refresh_display()

                        # Show thinking indicator
                        console.print("[dim]Thinking...[/dim]")

                        # Send to LLM (stats tracked by agent via TUI)
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            try:
                                response = loop.run_until_complete(agent.chat(cmd))
                                # Add AI response to conversation
                                conversation.append(("assistant", response.content, False))

                                # Show tool calls if any
                                if response.tool_calls:
                                    tool_info = ", ".join([tc.name for tc in response.tool_calls])
                                    conversation.append(("slash_result", f"→ Tools: {tool_info}", False))
                            finally:
                                loop.close()
                        except Exception as e:
                            conversation.append(("assistant", f"Error: {str(e)[:50]}", False))

                        refresh_display()
                    else:
                        console.print("[yellow]Chat disabled. Use /commands for available slash commands.[/yellow]")
                        console.print("[dim]Press Enter to continue...[/dim]", end="")
                        input()
                        refresh_display()

                except EOFError:
                    break

        except KeyboardInterrupt:
            pass
        finally:
            if agent:
                agent.end_session()
            console.print()
            console.print("[dim]Session ended.[/dim]")



def main():
    parser = argparse.ArgumentParser(
        description="Live Simulation Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Run automated demo with Claude Haiku (requires ANTHROPIC_API_KEY)
    python examples/simulation.py --model claude-haiku-4-5

    # Run interactive mode with LLM chat (requires ANTHROPIC_API_KEY)
    python examples/simulation.py --interactive --model claude-haiku-4-5

    # Interactive with a different model
    python examples/simulation.py -i --model claude-sonnet-4-20250514

    # Interactive with slash commands only (no API key needed)
    python examples/simulation.py --interactive --no-chat

    # Interactive with existing store
    python examples/simulation.py -i --model claude-haiku-4-5 --store /path/to/store

Interactive Mode:
    - Type a message to chat with the LLM (LLM may call memoir tools)
    - Type /command for direct slash commands (bypass LLM)

Slash Commands:
    /remember <content>           Store a memory
    /recall <query>               Search memories
    /summarize --namespace <ns>   Summarize memories
    /incognito                    Start incognito mode
    /off-record                   Start off-record mode
    /on-record                    Return to normal mode
    /commits --limit 10           Show commit history
    /help                         Show help
    /quit                         Exit
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
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Run in interactive mode (chat + slash commands)",
    )
    parser.add_argument(
        "--no-chat",
        action="store_true",
        help="Disable LLM chat in interactive mode (slash commands only, no API key needed)",
    )

    args = parser.parse_args()

    # Use temp directory if no store specified
    if args.store:
        store_path = args.store
    else:
        tmpdir = tempfile.mkdtemp(prefix="memoir-live-demo-")
        store_path = f"{tmpdir}/store"
        print(f"Using temporary store: {store_path}")

    # Check for API key (not needed only for interactive --no-chat mode)
    import os

    needs_api_key = not (args.interactive and args.no_chat)
    if needs_api_key and not os.getenv("ANTHROPIC_API_KEY"):
        print("\n" + "=" * 60)
        print("ERROR: ANTHROPIC_API_KEY not set")
        print("=" * 60)
        print("\nSet your API key:")
        print("  export ANTHROPIC_API_KEY=your-key-here")
        if not args.interactive:
            print("\nOr run in interactive mode with slash commands only:")
            print("  python examples/simulation.py --interactive --no-chat")
        else:
            print("\nOr disable LLM chat (slash commands only):")
            print("  python examples/simulation.py --interactive --no-chat")
        print()
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Memoir Live Simulation Demo")
    print("=" * 60)
    if args.interactive:
        chat_mode = "DISABLED" if args.no_chat else "ENABLED"
        print(f"\nMode: INTERACTIVE (chat: {chat_mode})")
    else:
        print("\nMode: AUTOMATED")
    print(f"Model: {args.model}")
    print(f"Store: {store_path}")
    print("\nLegend:")
    print("  [HOOK] = Automatically triggered by hooks (yellow)")
    print("  [LLM]  = Agent tool call (cyan)")
    print("  [USER] = User input/slash command (green)")
    print("  [SYS]  = System event (magenta)")
    if args.interactive:
        if args.no_chat:
            print("\nSlash commands only. Type /help for commands, /quit to exit")
        else:
            print("\nType message to chat, /command for direct execution, /quit to exit")
    print("\nPress Ctrl+C to exit\n")

    time.sleep(1)

    demo = LiveSimulationDemo(
        store_path=store_path,
        model=args.model,
        interactive=args.interactive,
    )

    try:
        if args.interactive:
            demo.run_interactive(enable_chat=not args.no_chat)
        else:
            demo.run()
    except KeyboardInterrupt:
        print("\nDemo stopped.")


if __name__ == "__main__":
    main()

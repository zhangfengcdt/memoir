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

        # Initialize memoir store with builtin taxonomy
        cli = CLIExecutor(store_path)
        result = cli.new(store_path, taxonomy_builtin=True)
        if not result.success:
            print(f"Warning: Store creation: {result.error}")

        # Seed demo identity configs into store
        # (Hooks and agents read these dynamically from the store)
        self._seed_demo_identities(cli)

        # Seed agent's own knowledge (tools, skills, learned patterns)
        self._seed_agent_knowledge(cli)

        # Create TUI (interactive mode for single conversation view)
        self.tui = LiveSimulationTUI(store_path, interactive=interactive)

        # Session manager for all users
        self.session_manager = SessionManager()

    def _seed_demo_identities(self, cli: CLIExecutor):
        """Seed demo identity configurations into the store.

        Stores identity mappings as direct key-value pairs for fast lookup.
        Format: agent:config.identity.{channel}:{user_id} -> namespace

        This allows O(1) lookup without LLM:
            memoir get config.identity.web:51321 --namespace agent
            -> alex

        Supports both formats:
        - Specific: config.identity.web:51321 -> alex
        - Channel-wide: config.identity.discord -> sarah (any user on discord)
        """
        # Identity mappings: {channel}:{user_id} or {channel} -> namespace
        identity_mappings = {
            # Specific user mappings (channel:user_id)
            "web:51321": "alex",
            "slack:U04ABCD1234": "slackbot",
            "telegram:12345678": "assistant",
            # Channel-wide mapping (any user on this channel)
            "discord": "sarah",
        }

        for channel_key, namespace in identity_mappings.items():
            cli.set(
                key=f"config.identity.{channel_key}",
                content=namespace,
                namespace="agent",
            )

    def _seed_agent_knowledge(self, cli: CLIExecutor):
        """Seed agent's own knowledge - tools, skills, and learned patterns.

        This represents what the agent has learned about:
        - Tools it can use effectively
        - Patterns it has discovered
        - Skills it has developed
        """
        agent_knowledge = {
            # Tool integrations
            "tools.calendar": "Google Calendar API - check availability, create events, send invites.",
            "tools.email": "Gmail API - draft and send emails, format executive summaries.",
            "tools.slack": "Slack API - post to channels, DM users, aggregate updates.",
            "tools.search": "Perplexity API - web research, market analysis, competitor tracking.",
            "tools.docs": "Google Docs API - create documents, share with team, export PDFs.",
            # Skills and learned capabilities
            "skills.board_prep": "Board meeting prep: financial summary, metrics dashboard, risk register. Start 5 days before.",
            "skills.daily_standup": "Aggregate Slack channels by 9am. Include: blockers, wins, priorities.",
            "skills.investor_updates": "Monthly format: ARR, runway, key hires, product milestones. Under 500 words.",
            "skills.morning_brief": "Morning brief: calendar, overnight Slack, urgent emails, top 3 priorities.",
            "skills.meeting_prep": "Pull attendee context, gather docs, prepare talking points.",
            "skills.weekly_report": "Friday EOD: team updates, sprint velocity, customer feedback, week-ahead.",
        }

        for key, content in agent_knowledge.items():
            cli.set(
                key=key,
                content=content,
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
        # Web channel - alex (Owner/CEO)
        # Includes questions that require recalling agent tools/skills
        web_messages = [
            "Remember that my top priority this quarter is the Series B fundraise.",
            "I prefer morning meetings before 10am Pacific.",
            "What calendar tools do you have?",  # Requires agent recall: tools.calendar
            "Always brief me on key metrics before board meetings.",
            "What skills do you have for board meeting prep?",  # Requires agent recall: skills.board_prep
            "My communication style is direct - keep updates concise.",
        ]

        # Slack channel - slackbot (Daily report aggregator)
        slack_messages = [
            "Daily report: Engineering completed 12 PRs, 3 critical bugs fixed.",
            "Sales update: Q1 pipeline at $2.4M, 15% above target.",
            "What skills do you have for daily standups?",  # Requires agent recall: skills.daily_standup
            "Customer success: NPS score improved to 72, up from 68 last month.",
            "HR update: 3 new hires starting Monday in engineering.",
            "What do you know about formatting investor updates?",  # Requires agent recall: skills.investor_updates
        ]

        # Discord channel - sarah (Developer)
        discord_messages = [
            "I prefer using Rust for performance-critical services.",
            "Remember: I use neovim with LSP for all my coding.",
            "What search tools do you have?",  # Requires agent recall: tools.search
            "My dev environment runs on NixOS for reproducibility.",
            "I always write integration tests before unit tests.",
            "What skills do you have for morning briefs?",  # Requires agent recall: skills.morning_brief
        ]

        # Telegram channel - assistant (Executive assistant to alex)
        telegram_messages = [
            "Alex's board meeting is next Tuesday at 2pm.",
            "What meeting prep skills do you have?",  # Requires agent recall: skills.meeting_prep
            "Remember to prep the Q1 financial summary for Alex by Friday.",
            "Alex prefers his coffee meetings at Blue Bottle on Market St.",
            "What email tools do you have?",  # Requires agent recall: tools.email
            "Block Alex's calendar for focused work every Thursday morning.",
        ]

        # Run all 4 channel sessions concurrently
        # Each channel has its own user ID format (like real platforms)
        # Delays increased to avoid API rate limits
        await asyncio.gather(
            self.run_user_scenario("51321", web_messages, channel="web", delay=8.0),
            self.run_user_scenario("U04ABCD1234", slack_messages, channel="slack", delay=9.0),
            self.run_user_scenario("987654321012", discord_messages, channel="discord", delay=10.0),
            self.run_user_scenario("12345678", telegram_messages, channel="telegram", delay=11.0),
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

    def run_interactive(
        self,
        enable_chat: bool = True,
        user_id: str = "51321",
        channel: str = "web",
    ):
        """Run in interactive mode - accept slash commands and chat with LLM.

        Uses a scrolling console approach (not full-screen) so input is visible.
        Reuses TUI render methods for memory store and stats panels.

        Args:
            enable_chat: If True, non-slash text is sent to LLM for chat.
                        If False, only slash commands are accepted.
            user_id: User ID for identity resolution (default: 51321 -> alex)
            channel: Channel for identity resolution (default: web)
        """
        import sys
        import warnings

        from rich.align import Align
        from rich.console import Console, Group
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        # Suppress asyncio warnings about pending tasks (from litellm logging)
        warnings.filterwarnings("ignore", message=".*was destroyed but it is pending.*")
        warnings.filterwarnings("ignore", message=".*coroutine.*was never awaited.*")
        warnings.filterwarnings("ignore", category=RuntimeWarning)

        # Suppress asyncio task destruction messages (printed directly to stderr)
        import logging
        logging.getLogger("asyncio").setLevel(logging.CRITICAL)

        console = Console()

        # Create a single event loop for the session
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # User identity for namespace (channel:user_id pattern)
        fallback_namespace = f"{channel}:{user_id}"

        # CLI executor for identity lookup
        cli = CLIExecutor(self.store_path)
        skill = SkillInjector(user_id=user_id, store_path=self.store_path)

        # Conversation history for display (role, content, is_slash)
        conversation: list[tuple[str, str, bool]] = []

        # Resolve identity using CLI get (fast, no LLM needed)
        session_namespace = fallback_namespace
        console.print("[dim]Resolving identity...[/dim]")

        def get_content(result) -> str | None:
            """Safely extract content from CLI result."""
            if result.success and result.data and isinstance(result.data, dict):
                content = result.data.get("content")
                if content and isinstance(content, str):
                    return content.strip()
            return None

        # Try specific mapping first: config.identity.{channel}:{user_id}
        result = cli.get(key=f"config.identity.{channel}:{user_id}", namespace="agent")
        content = get_content(result)
        if content:
            session_namespace = content
            self.tui.log_event(MemoryEvent(
                timestamp=time.time(),
                source=EventSource.SYSTEM,
                operation="resolve-ns",
                details=f"Found: config.identity.{channel}:{user_id} -> {session_namespace}",
            ))
        else:
            # Try channel-wide mapping: config.identity.{channel}
            result = cli.get(key=f"config.identity.{channel}", namespace="agent")
            content = get_content(result)
            if content:
                session_namespace = content
                self.tui.log_event(MemoryEvent(
                    timestamp=time.time(),
                    source=EventSource.SYSTEM,
                    operation="resolve-ns",
                    details=f"Found: config.identity.{channel} -> {session_namespace}",
                ))
            else:
                self.tui.log_event(MemoryEvent(
                    timestamp=time.time(),
                    source=EventSource.SYSTEM,
                    operation="resolve-ns",
                    details=f"No mapping found, using fallback: {fallback_namespace}",
                ))

        if session_namespace != fallback_namespace:
            console.print(f"[green]Identity resolved: {session_namespace}[/green]")
        else:
            console.print(f"[yellow]Using fallback namespace: {fallback_namespace}[/yellow]")

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
                    height=35,
                )

            content = []
            # Show last 15 messages (each may be ~2 lines)
            for role, msg, is_slash in conversation[-15:]:
                if role == "user":
                    if is_slash:
                        content.append(Text(f"> {msg}", style="yellow"))
                    else:
                        content.append(Text(f"> {msg}", style="green"))
                elif role == "slash_result":
                    content.append(Text(f"  {msg}", style="dim yellow"))
                else:
                    # Truncate long AI responses to ~3 lines to ensure scrolling works
                    display_msg = msg[:300] + "..." if len(msg) > 300 else msg
                    content.append(Text(f"  {display_msg}", style="cyan"))

            return Panel(
                Align(Group(*content), vertical="bottom"),
                title="[bold green]Conversation[/bold green]",
                border_style="green",
                height=35,
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
                f"[bold cyan]Memoir Interactive[/bold cyan] │ Store: {Path(self.store_path).name} │ Namespace: {session_namespace}",
                style="bold",
            ))

            # Use Table for side-by-side layout (doesn't fill screen like Layout)
            main_table = Table.grid(padding=0, expand=True)
            main_table.add_column(ratio=3)  # Left column
            main_table.add_column(ratio=2)  # Right column

            # Left column: event log on top, conversation below
            left_content = Group(
                self.tui._render_events(),
                render_conversation(),
            )

            # Right column: memories on top, stats below
            right_content = Group(
                self.tui._render_memories(),
                self.tui._render_stats(),
            )

            main_table.add_row(
                left_content,
                right_content,
            )

            console.print(main_table)

            # Input hint and bordered input area right below panels
            mode_hint = "Chat or /command" if enable_chat else "/command only"
            pending_hint = f" │ [yellow]{pending_count} pending[/yellow]" if pending_count > 0 else ""
            console.print(f"[dim]({mode_hint} │ /help │ /clear │ /quit{pending_hint})[/dim]")
            console.rule(style="dim")  # Top line of input box
            # Print placeholder for input line and bottom line, then move cursor up
            print("> ")  # Input line placeholder
            console.rule(style="dim")  # Bottom line of input box
            # Move cursor up 2 lines to the input line, after "> "
            sys.stdout.write("\033[2A\033[3C")
            sys.stdout.flush()

        # Background task queue for truly async execution
        import queue

        result_queue: queue.Queue = queue.Queue()
        pending_count = 0  # Track number of pending tasks

        def run_slash_in_background(slash_cmd: str, namespace: str):
            """Run slash command in background thread."""
            nonlocal pending_count

            def worker():
                nonlocal pending_count
                try:
                    # Use synchronous version for thread safety
                    result = skill.execute_slash_command(slash_cmd, default_namespace=namespace)
                    result_queue.put(("slash", "success", result))
                except Exception as e:
                    result_queue.put(("slash", "error", str(e)))
                finally:
                    pending_count -= 1

            pending_count += 1
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()

        def run_chat_in_background(message: str):
            """Run LLM chat in background thread with its own event loop."""
            nonlocal pending_count

            def worker():
                nonlocal pending_count
                try:
                    # Create a new event loop for this thread
                    chat_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(chat_loop)
                    try:
                        result = chat_loop.run_until_complete(agent.chat(message))
                        result_queue.put(("chat", "success", result))
                    finally:
                        chat_loop.close()
                except Exception as e:
                    result_queue.put(("chat", "error", str(e)))
                finally:
                    pending_count -= 1

            pending_count += 1
            thread = threading.Thread(target=worker, daemon=True)
            thread.start()

        def replace_last_placeholder(role_match: str, placeholder: str, new_content: str):
            """Replace the last placeholder message with actual content."""
            for i in range(len(conversation) - 1, -1, -1):
                role, content, is_slash = conversation[i]
                if role == role_match and content == placeholder:
                    conversation[i] = (role, new_content, is_slash)
                    return True
            return False

        def process_results():
            """Process any completed background tasks. Returns True if any processed."""
            processed = False
            while not result_queue.empty():
                try:
                    task_type, status, result = result_queue.get_nowait()
                    processed = True

                    if task_type == "slash":
                        # Slash command result - replace placeholder
                        if status == "success" and result.get("success"):
                            result_text = f"✓ {result.get('command', 'Done')}"
                            if result.get("data"):
                                data = result["data"]
                                if isinstance(data, dict):
                                    if "memories" in data:
                                        result_text = f"✓ Found {len(data['memories'])} memories"
                                    elif "key" in data:
                                        result_text = f"✓ Stored at: {data['key']}"
                        else:
                            error = result.get("error", "Failed") if status == "success" else result
                            result_text = f"✗ {error}"
                        replace_last_placeholder("slash_result", "[executing...]", result_text)

                    elif task_type == "chat":
                        # LLM chat result - replace placeholder
                        if status == "success":
                            replace_last_placeholder("assistant", "[thinking...]", result.content)
                            if result.tool_calls:
                                tool_info = ", ".join([tc.name for tc in result.tool_calls])
                                conversation.append(("slash_result", f"→ Tools: {tool_info}", False))
                        else:
                            replace_last_placeholder("assistant", "[thinking...]", f"Error: {str(result)[:50]}")

                except queue.Empty:
                    break
            return processed

        # Input queue for non-blocking input
        input_queue: queue.Queue = queue.Queue()
        stop_event = threading.Event()

        def input_thread_fn():
            """Read input in a separate thread."""
            while not stop_event.is_set():
                try:
                    line = input()
                    input_queue.put(line)
                except EOFError:
                    input_queue.put(None)  # Signal EOF
                    break
                except Exception:
                    break

        input_thread = threading.Thread(target=input_thread_fn, daemon=True)
        input_thread.start()

        # Initial display
        refresh_display()

        # Interactive loop with polling
        try:
            while True:
                try:
                    # Check for completed background tasks
                    if process_results():
                        refresh_display()

                    # Check for user input (non-blocking)
                    try:
                        cmd = input_queue.get(timeout=0.1)  # Poll every 100ms
                        if cmd is None:  # EOF
                            break
                        cmd = cmd.strip()
                        if not cmd:
                            refresh_display()
                            continue
                    except queue.Empty:
                        # No input yet, continue polling
                        continue

                    # Handle special commands
                    if cmd in ("/quit", "/exit", "/q"):
                        break
                    elif cmd == "/help":
                        # Show help below the input area
                        refresh_display()
                        console.print()
                        console.print("[bold]Commands:[/bold]")
                        console.print("  [cyan]/remember <text>[/cyan]  - Store a memory")
                        console.print("  [cyan]/recall <query>[/cyan]   - Search memories")
                        console.print("  [cyan]/summarize[/cyan]        - Summarize memories")
                        console.print("  [cyan]/incognito[/cyan]        - Start incognito mode")
                        console.print("  [cyan]/off-record[/cyan]       - Start off-record mode")
                        console.print("  [cyan]/on-record[/cyan]        - Return to normal")
                        console.print("  [cyan]/commits[/cyan]          - Show history")
                        console.print("  [cyan]/clear[/cyan]            - Clear conversation (test memory without short-term context)")
                        console.print("  [cyan]/quit[/cyan]             - Exit")
                        if enable_chat:
                            console.print()
                            console.print("[dim]Or just type a message to chat with the AI[/dim]")
                        continue
                    elif cmd == "/commands":
                        cmds = get_slash_commands()
                        refresh_display()
                        console.print()
                        console.print(f"[dim]Available: /{', /'.join(cmds)}[/dim]")
                        continue
                    elif cmd == "/clear":
                        conversation.clear()
                        # Also clear LLM session messages (keeps system prompt)
                        if agent and agent.session:
                            agent.session.messages.clear()
                            self.tui.log_event(MemoryEvent(
                                timestamp=time.time(),
                                source=EventSource.USER,
                                operation="clear",
                                details="Cleared conversation context (memory persists)",
                            ))
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

                        # Log full command with namespace
                        self.tui.log_event(MemoryEvent(
                            timestamp=time.time(),
                            source=EventSource.USER,
                            operation="exec-slash",
                            details=f"{slash_cmd} --namespace {session_namespace}",
                        ))

                        # Execute in background (non-blocking)
                        run_slash_in_background(slash_cmd, session_namespace)
                        conversation.append(("slash_result", "[executing...]", True))
                        refresh_display()

                    elif enable_chat and agent:
                        # Add user message to conversation
                        conversation.append(("user", cmd, False))

                        # Execute chat in background (non-blocking)
                        run_chat_in_background(cmd)
                        conversation.append(("assistant", "[thinking...]", False))
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
            # Stop input thread
            stop_event.set()

            if agent:
                agent.end_session()

            # Suppress stderr during cleanup to hide asyncio task warnings
            import io
            old_stderr = sys.stderr
            sys.stderr = io.StringIO()

            try:
                # Clean up the event loop
                try:
                    # Cancel any pending tasks
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    # Allow cancelled tasks to complete
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
                finally:
                    loop.close()
            finally:
                # Restore stderr
                sys.stderr = old_stderr

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
    parser.add_argument(
        "--user-id",
        default="51321",
        help="User ID for interactive mode (default: 51321, maps to alex)",
    )
    parser.add_argument(
        "--channel",
        default="web",
        help="Channel for interactive mode (default: web)",
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
        print(f"Identity: {args.channel}:{args.user_id}")
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
            demo.run_interactive(
                enable_chat=not args.no_chat,
                user_id=args.user_id,
                channel=args.channel,
            )
        else:
            demo.run()
    except KeyboardInterrupt:
        print("\nDemo stopped.")


if __name__ == "__main__":
    main()

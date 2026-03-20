"""
Live Simulation TUI - Real-time visualization of memoir agent simulations.

Shows:
- Memory operations in real-time (from REAL memoir store)
- Clear distinction between HOOK-triggered and LLM-triggered calls
- Session conversations
- Memory store state

Uses Rich for terminal rendering with live updates.
"""

import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

try:
    from rich.align import Align
    from rich.console import Console, Group
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.tree import Tree

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class EventSource(Enum):
    """Source of a memoir operation."""

    HOOK = "hook"  # Triggered by hook system
    LLM = "llm"  # Triggered by LLM tool call
    USER = "user"  # Direct user action
    SYSTEM = "system"  # System event


@dataclass
class MemoryEvent:
    """A memory operation event."""

    timestamp: float
    source: EventSource
    operation: str  # remember, recall, forget, checkout, etc.
    details: str
    namespace: str = "default"
    success: bool = True
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def time_str(self) -> str:
        return datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S")

    @property
    def source_color(self) -> str:
        colors = {
            EventSource.HOOK: "yellow",
            EventSource.LLM: "cyan",
            EventSource.USER: "green",
            EventSource.SYSTEM: "magenta",
        }
        return colors.get(self.source, "white")

    @property
    def source_label(self) -> str:
        labels = {
            EventSource.HOOK: "[HOOK]",
            EventSource.LLM: "[LLM]",
            EventSource.USER: "[USER]",
            EventSource.SYSTEM: "[SYS]",
        }
        return labels.get(self.source, "[???]")


@dataclass
class ConversationMessage:
    """A message in the conversation."""

    timestamp: float
    role: str  # user or assistant
    content: str
    user_id: str
    session_id: str
    channel: str = "web"  # telegram, whatsapp, discord, slack, web


class LiveSimulationTUI:
    """
    Real-time TUI for memoir agent simulations.

    Displays:
    - Event log with hook vs LLM distinction
    - Memory tree visualization
    - Active conversations
    - Statistics

    Example:
        tui = LiveSimulationTUI(store_path="/path/to/store")

        # Log events from hooks or LLM
        tui.log_event(MemoryEvent(
            source=EventSource.HOOK,
            operation="remember",
            details="User prefers dark mode",
        ))

        # Start live display
        tui.run()
    """

    def __init__(
        self,
        store_path: str,
        refresh_rate: float = 4.0,  # Updates per second
    ):
        if not RICH_AVAILABLE:
            raise ImportError(
                "Rich is required for TUI. Install with: pip install rich"
            )

        self.store_path = store_path
        self.refresh_rate = refresh_rate
        self.console = Console()

        # Event tracking
        self.events: list[MemoryEvent] = []
        self.max_events = 50

        # Conversation tracking
        self.conversations: dict[str, list[ConversationMessage]] = {}

        # Memory tracking
        self.memories: dict[str, dict[str, Any]] = {}  # namespace -> {path: content}

        # Statistics
        self.stats = {
            "hook_calls": 0,
            "llm_calls": 0,
            "total_memories": 0,
            "sessions": set(),
            # Breakdown by operation type
            "hook_ops": {},  # e.g., {"recall": 3, "remember": 1}
            "llm_ops": {},  # e.g., {"remember": 2, "recall": 1}
        }

        # Thread-safe event queue
        self._event_queue: queue.Queue = queue.Queue()
        self._running = False
        self._lock = threading.Lock()

        # Store reader for real-time memory display
        self._last_store_read = 0
        self._store_read_interval = 1.0  # Read store every 1 second
        self._real_memories: dict[str, dict[str, Any]] = {}

    def log_event(self, event: MemoryEvent) -> None:
        """
        Log a memory operation event.

        Thread-safe - can be called from any thread.
        """
        self._event_queue.put(event)

    def log_hook_operation(
        self,
        operation: str,
        details: str,
        hook_name: str = "",
        namespace: str = "default",
        success: bool = True,
        duration_ms: float = 0.0,
    ) -> None:
        """Log an operation triggered by a hook."""
        self.log_event(
            MemoryEvent(
                timestamp=time.time(),
                source=EventSource.HOOK,
                operation=operation,
                details=details,
                namespace=namespace,
                success=success,
                duration_ms=duration_ms,
                metadata={"hook_name": hook_name},
            )
        )

    def log_llm_operation(
        self,
        operation: str,
        details: str,
        tool_name: str = "",
        namespace: str = "default",
        success: bool = True,
        duration_ms: float = 0.0,
    ) -> None:
        """Log an operation triggered by LLM tool call."""
        self.log_event(
            MemoryEvent(
                timestamp=time.time(),
                source=EventSource.LLM,
                operation=operation,
                details=details,
                namespace=namespace,
                success=success,
                duration_ms=duration_ms,
                metadata={"tool_name": tool_name},
            )
        )

    def log_conversation(
        self,
        role: str,
        content: str,
        user_id: str,
        session_id: str,
        channel: str = "web",
    ) -> None:
        """Log a conversation message."""
        # Skip empty messages
        if not content or not content.strip():
            return

        # Key format: channel:session:user (OpenClaw style)
        key = f"{channel}:{session_id}:{user_id}"
        with self._lock:
            if key not in self.conversations:
                self.conversations[key] = []
            self.conversations[key].append(
                ConversationMessage(
                    timestamp=time.time(),
                    role=role,
                    content=content,
                    user_id=user_id,
                    session_id=session_id,
                    channel=channel,
                )
            )
            # Keep last 20 messages per conversation
            self.conversations[key] = self.conversations[key][-20:]
            self.stats["sessions"].add(key)

    def update_memory(
        self,
        namespace: str,
        path: str,
        content: Any,
        deleted: bool = False,
    ) -> None:
        """Update the memory tree visualization."""
        with self._lock:
            if namespace not in self.memories:
                self.memories[namespace] = {}

            if deleted:
                self.memories[namespace].pop(path, None)
            else:
                self.memories[namespace][path] = content
                self.stats["total_memories"] = sum(
                    len(ns) for ns in self.memories.values()
                )

    def _process_events(self) -> None:
        """Process queued events."""
        while not self._event_queue.empty():
            try:
                event = self._event_queue.get_nowait()
                with self._lock:
                    self.events.append(event)
                    self.events = self.events[-self.max_events :]

                    # Update stats
                    if event.source == EventSource.HOOK:
                        self.stats["hook_calls"] += 1
                        op = event.operation
                        self.stats["hook_ops"][op] = (
                            self.stats["hook_ops"].get(op, 0) + 1
                        )
                    elif event.source == EventSource.LLM:
                        self.stats["llm_calls"] += 1
                        op = event.operation
                        self.stats["llm_ops"][op] = self.stats["llm_ops"].get(op, 0) + 1
            except queue.Empty:
                break

    def _make_layout(self) -> Layout:
        """Create the main layout."""
        layout = Layout()

        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=3),
        )

        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="right", ratio=1),
        )

        layout["left"].split_column(
            Layout(name="events", ratio=1),
            Layout(name="conversations", ratio=2),
        )

        # Split conversations into 4 sub-windows (2x2 grid)
        layout["conversations"].split_column(
            Layout(name="conv_top", ratio=1),
            Layout(name="conv_bottom", ratio=1),
        )
        layout["conv_top"].split_row(
            Layout(name="conv_web", ratio=1),
            Layout(name="conv_slack", ratio=1),
        )
        layout["conv_bottom"].split_row(
            Layout(name="conv_discord", ratio=1),
            Layout(name="conv_telegram", ratio=1),
        )

        layout["right"].split_column(
            Layout(name="memories", ratio=2),
            Layout(name="stats", ratio=1),
        )

        return layout

    def _render_header(self) -> Panel:
        """Render header panel."""
        title = Text()
        title.append("Memoir ", style="bold cyan")
        title.append("Agent Simulation ", style="white")
        title.append("Live View", style="bold green")
        title.append(f"  |  Store: {Path(self.store_path).name}", style="dim")

        return Panel(title, style="bold", height=3)

    def _render_events(self) -> Panel:
        """Render event log panel (starts from bottom, rolls up)."""
        max_visible = 12
        table = Table(
            show_header=True,
            header_style="bold",
            expand=True,
            box=None,
        )
        table.add_column("Time", style="dim", width=8)
        table.add_column("Source", width=8)
        table.add_column("Op", no_wrap=True)
        table.add_column("Details", ratio=1)
        table.add_column("ms", width=6, justify="right")

        with self._lock:
            recent_events = self.events[-max_visible:]

            for event in recent_events:
                source_text = Text(event.source_label, style=event.source_color)
                status = "" if event.success else " [red]FAIL[/red]"
                ms_str = f"{event.duration_ms:.0f}" if event.duration_ms > 0 else "-"

                details = (
                    event.details[:200] + "..."
                    if len(event.details) > 200
                    else event.details
                )

                table.add_row(
                    event.time_str,
                    source_text,
                    event.operation + status,
                    details,
                    ms_str,
                )

        return Panel(
            Align(table, vertical="bottom"),
            title="[bold]Event Log[/bold] [dim](HOOK=auto, LLM=agent)[/dim]",
            border_style="blue",
        )

    def _render_channel_conversation(self, target_channel: str) -> Panel:
        """Render conversation panel for a specific channel."""
        content = []
        title = f"[bold]{target_channel.upper()}[/bold]"
        border_colors = {
            "web": "green",
            "slack": "magenta",
            "discord": "blue",
            "telegram": "cyan",
        }
        border_style = border_colors.get(target_channel, "white")

        with self._lock:
            # Find conversation for this channel
            for key in self.conversations:
                parts = key.split(":")
                if len(parts) >= 3:
                    channel, _session_id, user_id = parts[0], parts[1], parts[2]
                else:
                    continue

                if channel != target_channel:
                    continue

                messages = self.conversations[key]
                title = f"[bold]{channel}:{user_id}[/bold]"

                # Filter out empty messages and get last 5 (to fit smaller panel)
                non_empty = [m for m in messages if m.content and m.content.strip()]
                recent_messages = non_empty[-5:]
                num_messages = len(recent_messages)

                for idx, msg in enumerate(recent_messages):
                    role_style = "green" if msg.role == "user" else "cyan"
                    # Short prefix for compact display
                    role_prefix = f"{user_id}:" if msg.role == "user" else "Agent:"
                    # Truncate for smaller panels
                    text = (
                        msg.content[:80] + "..."
                        if len(msg.content) > 80
                        else msg.content
                    )

                    # Highlight the last (newest) message
                    is_last = idx == num_messages - 1
                    if is_last:
                        content.append(
                            Text(
                                f"▶ {role_prefix} {text}", style=f"{role_style} reverse"
                            )
                        )
                    else:
                        content.append(
                            Text(f"  {role_prefix} {text}", style=role_style)
                        )
                break  # Only show first matching conversation per channel

        if not content:
            content = [Text("Waiting...", style="dim")]

        return Panel(
            Align(Group(*content), vertical="bottom"),
            title=title,
            border_style=border_style,
        )

    def _read_real_store(self) -> dict[str, dict[str, Any]]:
        """Read memories from the real memoir store."""
        now = time.time()
        if now - self._last_store_read < self._store_read_interval:
            return self._real_memories

        self._last_store_read = now
        memories: dict[str, dict[str, Any]] = {}

        try:
            # Read directly from ProllyTreeStore to get all namespaces
            from memoir.store.prolly_adapter import ProllyTreeStore

            if not Path(self.store_path).exists():
                return self._real_memories

            store = ProllyTreeStore(
                path=self.store_path,
                enable_versioning=True,
                auto_commit=False,
                cache_size=10000,
            )

            # Get all keys using list_keys
            if hasattr(store.tree, "list_keys"):
                keys = store.tree.list_keys()
                for key in keys:
                    try:
                        full_key = (
                            key.decode("utf-8") if isinstance(key, bytes) else str(key)
                        )

                        # Skip taxonomy and system keys
                        if full_key.startswith("taxonomy:"):
                            continue

                        # Parse namespace and path from key
                        # Format: channel:userid:semantic.path or agent:semantic.path
                        parts = full_key.split(":")
                        if len(parts) < 2:
                            continue

                        # Handle various namespace formats:
                        # - channel:userid:path (web, slack, discord, telegram)
                        # - person:path (feng, kevin - identity-based)
                        # - agent:path, system:path
                        if (
                            parts[0] in ("web", "slack", "discord", "telegram")
                            and len(parts) >= 3
                        ):
                            namespace = f"{parts[0]}:{parts[1]}"
                            path = parts[2]  # Just the semantic path
                        elif parts[0] in ("agent", "system"):
                            namespace = parts[0]
                            path = parts[1] if len(parts) > 1 else ""
                        elif len(parts) >= 2:
                            # Person-based namespace (feng, kevin, etc.)
                            namespace = parts[0]
                            path = parts[1]
                        else:
                            # Skip other formats
                            continue

                        if not path:
                            continue

                        # Get memory content
                        key_bytes = (
                            key if isinstance(key, bytes) else full_key.encode("utf-8")
                        )
                        value_bytes = store.tree.get(key_bytes)
                        if value_bytes:
                            value_data = store._decode_value(value_bytes)
                            content = ""
                            if isinstance(value_data, dict):
                                # Extract just the content field
                                raw_content = value_data.get("content", "")
                                if isinstance(raw_content, str):
                                    content = raw_content
                                else:
                                    content = str(raw_content)
                            else:
                                content = str(value_data)

                            # Clean up content - remove any metadata artifacts
                            content = content.strip()
                            if not content:
                                continue

                            if namespace not in memories:
                                memories[namespace] = {}
                            memories[namespace][path] = content

                    except Exception:
                        continue

            self._real_memories = memories
            self.stats["total_memories"] = sum(len(ns) for ns in memories.values())

        except Exception:
            # Fall back to tracked memories if store read fails
            pass

        return self._real_memories

    def _render_memories(self) -> Panel:
        """Render memory tree panel from REAL store."""
        tree = Tree("[bold]Memories (Real Store)[/bold]")

        # Read from real store
        real_memories = self._read_real_store()

        if real_memories:
            # Sort namespaces for stable display
            for namespace in sorted(real_memories.keys()):
                paths = real_memories[namespace]
                ns_tree = tree.add(f"[yellow]{namespace}[/yellow]")
                # Sort paths for stable display
                for path in sorted(paths.keys()):
                    content = paths[path]
                    content_str = str(content)[:60]
                    if len(str(content)) > 60:
                        content_str += "..."
                    ns_tree.add(f"[cyan]{path}[/cyan]: {content_str}")
        else:
            # Fall back to instrumented memories
            with self._lock:
                for namespace, paths in self.memories.items():
                    ns_tree = tree.add(f"[yellow]{namespace}[/yellow]")
                    for path, content in list(paths.items())[-10:]:
                        content_str = str(content)[:60]
                        ns_tree.add(f"[cyan]{path}[/cyan]: {content_str}")

        if not real_memories and not self.memories:
            tree.add("[dim]No memories stored yet[/dim]")

        return Panel(tree, title="[bold]Memory Store[/bold]", border_style="magenta")

    def _render_stats(self) -> Panel:
        """Render statistics panel."""
        content = []

        with self._lock:
            # Hook calls breakdown
            hook_total = self.stats["hook_calls"]
            hook_ops = self.stats["hook_ops"]
            if hook_ops:
                ops_str = ", ".join(f"{k}: {v}" for k, v in sorted(hook_ops.items()))
                content.append(Text(f"Hook Calls: {hook_total}", style="yellow bold"))
                content.append(Text(f"  {ops_str}", style="yellow"))
            else:
                content.append(Text(f"Hook Calls: {hook_total}", style="yellow bold"))

            # LLM calls breakdown
            llm_total = self.stats["llm_calls"]
            llm_ops = self.stats["llm_ops"]
            if llm_ops:
                ops_str = ", ".join(f"{k}: {v}" for k, v in sorted(llm_ops.items()))
                content.append(Text(f"LLM Calls: {llm_total}", style="cyan bold"))
                content.append(Text(f"  {ops_str}", style="cyan"))
            else:
                content.append(Text(f"LLM Calls: {llm_total}", style="cyan bold"))

            content.append(Text(f"Memories: {self.stats['total_memories']}"))
            content.append(Text(f"Sessions: {len(self.stats['sessions'])}"))

        return Panel(
            Group(*content), title="[bold]Statistics[/bold]", border_style="yellow"
        )

    def _render_footer(self) -> Panel:
        """Render footer panel."""
        legend = Text()
        legend.append("[HOOK]", style="yellow")
        legend.append(" = Auto-triggered by hooks  ", style="dim")
        legend.append("[LLM]", style="cyan")
        legend.append(" = Agent tool call  ", style="dim")
        legend.append("[USER]", style="green")
        legend.append(" = Direct user action", style="dim")

        return Panel(legend, style="dim", height=3)

    def _generate_display(self) -> Layout:
        """Generate the complete display."""
        self._process_events()

        layout = self._make_layout()
        layout["header"].update(self._render_header())
        layout["events"].update(self._render_events())
        # Render 4 channel conversation panels
        layout["conv_web"].update(self._render_channel_conversation("web"))
        layout["conv_slack"].update(self._render_channel_conversation("slack"))
        layout["conv_discord"].update(self._render_channel_conversation("discord"))
        layout["conv_telegram"].update(self._render_channel_conversation("telegram"))
        layout["memories"].update(self._render_memories())
        layout["stats"].update(self._render_stats())
        layout["footer"].update(self._render_footer())

        return layout

    def run(self, duration: Optional[float] = None) -> None:
        """
        Run the live TUI.

        Args:
            duration: Optional duration in seconds (None = run until stopped)
        """
        self._running = True
        start_time = time.time()

        with Live(
            self._generate_display(),
            console=self.console,
            refresh_per_second=self.refresh_rate,
            screen=True,
        ) as live:
            try:
                while self._running:
                    live.update(self._generate_display())
                    time.sleep(1 / self.refresh_rate)

                    if duration and (time.time() - start_time) > duration:
                        break
            except KeyboardInterrupt:
                pass

        self._running = False

    def stop(self) -> None:
        """Stop the live display."""
        self._running = False


class InstrumentedHookSystem:
    """
    Wrapper around HookSystem that logs events to TUI.

    Intercepts all hook operations and logs them with proper source tagging.
    """

    def __init__(self, hook_system, tui: LiveSimulationTUI):
        self._hooks = hook_system
        self._tui = tui

    def on_agent_bootstrap(self, session_key: str):
        self._tui.log_event(
            MemoryEvent(
                timestamp=time.time(),
                source=EventSource.HOOK,
                operation="bootstrap",
                details=f"Session: {session_key}",
                metadata={"hook_name": "memoir-recall"},
            )
        )

        result = self._hooks.on_agent_bootstrap(session_key)

        for cli_result in result.cli_results:
            if cli_result.data:
                self._tui.log_hook_operation(
                    operation="recall",
                    details=cli_result.command,
                    hook_name="memoir-recall",
                    duration_ms=cli_result.duration_ms,
                    success=cli_result.success,
                )

        return result

    def on_message_received(self, message: str, session_key: str):
        result = self._hooks.on_message_received(message, session_key)

        if result.data.get("triggered"):
            self._tui.log_hook_operation(
                operation="recall",
                details=f"Keyword trigger: {result.data.get('query', '')}",
                hook_name="keyword-recall",
                duration_ms=result.duration_ms,
            )

        return result

    def on_message_sent(
        self,
        user_message: str,
        assistant_message: str,
        session_key: str,
    ):
        result = self._hooks.on_message_sent(
            user_message, assistant_message, session_key
        )

        if result.data.get("buffered"):
            self._tui.log_hook_operation(
                operation="buffer",
                details=f"Turn buffered ({result.data.get('buffer_size')}/{self._hooks.batch_size})",
                hook_name="memoir-store",
                duration_ms=result.duration_ms,
            )

        if result.data.get("flushed"):
            self._tui.log_hook_operation(
                operation="batch-store",
                details=f"Flushed {result.data.get('turns_processed')} turns",
                hook_name="memoir-store",
                duration_ms=result.duration_ms,
            )

        return result

    def flush_buffer(self, session_key: str):
        result = self._hooks.flush_buffer(session_key)

        if result.data.get("flushed"):
            self._tui.log_hook_operation(
                operation="batch-store",
                details=f"Flushed {result.data.get('turns_processed')} turns",
                hook_name="flush-batch",
                duration_ms=result.duration_ms,
            )

        return result


class InstrumentedSkillInjector:
    """
    Wrapper around SkillInjector that logs tool calls to TUI.

    Intercepts all tool executions and logs them with LLM source tagging.
    """

    def __init__(self, skill_injector, tui: LiveSimulationTUI):
        self._skill = skill_injector
        self._tui = tui

    def get_skill_markdown(self):
        return self._skill.get_skill_markdown()

    def get_system_prompt_injection(self):
        return self._skill.get_system_prompt_injection()

    def get_tool_definitions(self):
        return self._skill.get_tool_definitions()

    def execute_tool_call(self, tool_name: str, arguments: dict) -> dict:
        start = time.time()
        result = self._skill.execute_tool_call(tool_name, arguments)
        duration_ms = (time.time() - start) * 1000

        # Map tool names to operations
        op_map = {
            "memoir_remember": "remember",
            "memoir_recall": "recall",
            "memoir_forget": "forget",
            "memoir_checkout": "checkout",
        }
        operation = op_map.get(tool_name, tool_name)

        # Use the actual memoir command from the result
        details = result.get("command", "")

        self._tui.log_llm_operation(
            operation=operation,
            details=details,
            tool_name=tool_name,
            namespace=arguments.get("namespace", "default"),
            success=result.get("success", False),
            duration_ms=duration_ms,
        )

        # Update memory visualization
        if result.get("success") and result.get("data"):
            data = result["data"]
            if operation == "remember" and "key" in data:
                self._tui.update_memory(
                    namespace=arguments.get("namespace", "default"),
                    path=data["key"],
                    content=arguments.get("content", ""),
                )

        return result

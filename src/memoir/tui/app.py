"""
Memoir TUI - Terminal User Interface.

A simple CLI-style interface for memoir, styled similar to Claude Code.
Uses a scrolling prompt, not a full-screen TUI.
"""

from __future__ import annotations

import asyncio
import contextlib
import readline  # noqa: F401 - enables input history
from pathlib import Path

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text

    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None


# Command aliases (matching web UI)
ALIASES = {
    "/con": "/connect",
    "/conn": "/connect",
    "/rem": "/remember",
    "/del": "/forget",
    "/br": "/branch",
    "/co": "/checkout",
    "/log": "/commits",
    "/h": "/help",
    "/?": "/help",
}


class MemoirCLI:
    """Memoir CLI - scrolling terminal interface."""

    def __init__(self, store_path: str | None = None):
        self.store_path = store_path
        self._memory_service = None
        self._branch_service = None
        self._store_service = None
        self.console = Console() if RICH_AVAILABLE else None
        self.running = True

    def print(self, text: str = "", style: str | None = None, end: str = "\n"):
        """Print text, with optional Rich styling."""
        if self.console and RICH_AVAILABLE:
            self.console.print(text, style=style, end=end)
        else:
            print(text, end=end)

    def print_error(self, text: str):
        """Print error message."""
        self.print(f"✗ {text}", style="red")

    def print_success(self, text: str):
        """Print success message."""
        self.print(f"✓ {text}", style="green")

    def print_dim(self, text: str):
        """Print dimmed text."""
        self.print(text, style="dim")

    def _get_prompt(self) -> str:
        """Get the prompt string."""
        if self.store_path:
            branch = self._get_current_branch()
            return f"\033[36m{Path(self.store_path).name}\033[0m \033[33m({branch})\033[0m > "
        return "> "

    def _get_current_branch(self) -> str:
        """Get current branch name."""
        try:
            service = self._get_branch_service()
            info = service.list_branches()
            return info.current or "main"
        except Exception:
            return "main"

    def _show_welcome(self):
        """Show welcome message."""
        if self.console and RICH_AVAILABLE:
            self.console.print()
            self.console.print(
                Panel(
                    Text("Memoir CLI\nGit for AI Memory", justify="center"),
                    border_style="blue",
                    padding=(0, 2),
                )
            )
            self.console.print()
        else:
            print("\n=== Memoir CLI ===")
            print("Git for AI Memory\n")

        self.print_dim("Type /help for commands, Ctrl+C to quit")
        if self.store_path:
            self.print_success(f"Connected to {self.store_path}")
        self.print()

    def run(self):
        """Run the CLI loop."""
        self._show_welcome()

        while self.running:
            try:
                command = input(self._get_prompt()).strip()
                if command:
                    asyncio.run(self._execute_command(command))
            except KeyboardInterrupt:
                self.print("\nBye!")
                break
            except EOFError:
                self.print("\nBye!")
                break

    async def _execute_command(self, command: str) -> None:
        """Execute a command."""
        # Handle aliases
        for alias, full_cmd in ALIASES.items():
            if command.startswith(alias + " ") or command == alias:
                command = command.replace(alias, full_cmd, 1)
                break

        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        try:
            if cmd in ("/help", "help"):
                self._show_help()
            elif cmd == "/connect":
                await self._cmd_connect(args)
            elif cmd == "/new":
                await self._cmd_new(args)
            elif cmd == "/status":
                await self._cmd_status()
            elif cmd == "/remember":
                await self._cmd_remember(args)
            elif cmd == "/recall":
                await self._cmd_recall(args)
            elif cmd == "/forget":
                await self._cmd_forget(args)
            elif cmd == "/branch":
                await self._cmd_branch(args)
            elif cmd == "/checkout":
                await self._cmd_checkout(args)
            elif cmd == "/commits":
                await self._cmd_commits(args)
            elif cmd == "/quit" or cmd == "/exit":
                self.running = False
                self.print("Bye!")
            else:
                self.print_error(f"Unknown command: {cmd}")
                self.print_dim("Type /help for available commands")
        except Exception as e:
            self.print_error(str(e))

    def _show_help(self) -> None:
        """Show help message."""
        self.print()
        self.print("Commands:", style="bold")
        self.print("  /connect <path>  Connect to a memory store")
        self.print("  /new <path>      Create a new memory store")
        self.print("  /status          Show store status")
        self.print("  /remember <text> Store a memory")
        self.print("  /recall <query>  Search memories")
        self.print("  /forget <key>    Delete a memory")
        self.print("  /branch [name]   List or create branches")
        self.print("  /checkout <ref>  Switch branch/commit")
        self.print("  /commits         Show commit history")
        self.print("  /quit            Exit")
        self.print()
        self.print_dim("Aliases: /con, /rem, /del, /br, /co, /log, /h")
        self.print()

    async def _cmd_connect(self, path_str: str) -> None:
        """Connect to a memory store."""
        if not path_str:
            self.print_error("Usage: /connect <path>")
            return

        path = Path(path_str).expanduser().resolve()

        if not path.exists():
            self.print_error(f"Path does not exist: {path}")
            return

        if not (path / ".git").exists():
            self.print_error(f"Not a valid memoir store: {path}")
            return

        self.store_path = str(path)
        self._memory_service = None
        self._branch_service = None
        self._store_service = None

        self.print_success(f"Connected to {path}")

    async def _cmd_new(self, path_str: str) -> None:
        """Create a new memory store."""
        if not path_str:
            self.print_error("Usage: /new <path>")
            return

        path = Path(path_str).expanduser().resolve()

        if path.exists():
            self.print_error(f"Path already exists: {path}")
            return

        try:
            from memoir.services.store_service import StoreService

            service = StoreService(str(path))
            result = service.create_store()

            if result:
                self.store_path = str(path)
                self._memory_service = None
                self._branch_service = None
                self._store_service = None
                self.print_success(f"Created new store at {path}")
            else:
                self.print_error("Failed to create store")
        except Exception as e:
            self.print_error(str(e))

    async def _cmd_status(self) -> None:
        """Show store status."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        service = self._get_store_service()
        info = service.get_status()

        self.print()
        self.print("Store Status", style="bold")
        self.print(f"  Path: {info.path}")
        self.print(f"  Branch: {info.branch or 'N/A'}")
        self.print(f"  Commits: {info.commit_count or 0}")
        self.print(f"  Memories: {info.memory_count or 0}")
        if info.namespaces:
            self.print(f"  Namespaces: {', '.join(info.namespaces)}")
        self.print()

    async def _cmd_remember(self, content: str) -> None:
        """Store a memory."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        if not content:
            self.print_error("Usage: /remember <content>")
            return

        self.print_dim("Classifying and storing...")

        service = self._get_memory_service()
        result = await service.remember(content, "default")

        if result.success:
            self.print_success(f"Stored at: {result.key}")
            if result.confidence:
                self.print(f"  Confidence: {result.confidence:.2f}")
            if result.commit_hash:
                self.print(f"  Commit: {result.commit_hash[:8]}")
        else:
            self.print_error(f"Failed: {result.error}")

    async def _cmd_recall(self, query: str) -> None:
        """Search memories."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        if not query:
            self.print_error("Usage: /recall <query>")
            return

        service = self._get_memory_service()
        result = await service.recall(query, limit=10)

        if not result.memories:
            self.print("No memories found", style="yellow")
            return

        self.print()
        self.print(f"Found {len(result.memories)} memories:", style="bold")
        for i, mem in enumerate(result.memories, 1):
            path = mem.get("path", mem.get("key", "unknown"))
            content = mem.get("content", mem.get("value", ""))
            score = mem.get("score", mem.get("relevance", 0))

            if len(str(content)) > 60:
                content = str(content)[:60] + "..."

            self.print(f"  [{i}] {path}", style="green")
            self.print(f"      {content} ({score:.2f})")

        self.print_dim(f"\nSearch took {result.timing_ms:.1f}ms")
        self.print()

    async def _cmd_forget(self, key: str) -> None:
        """Delete a memory."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        if not key:
            self.print_error("Usage: /forget <key>")
            return

        service = self._get_memory_service()
        result = await service.forget(key, "default")

        if result.success:
            self.print_success(f"Deleted: {result.key}")
        else:
            self.print_error(f"Failed: {result.error}")

    async def _cmd_branch(self, args: str) -> None:
        """List or create branches."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        service = self._get_branch_service()

        if args:
            # Create new branch
            result = service.create_branch(args)
            if result.success:
                self.print_success(f"Created branch: {args}")
            else:
                self.print_error(f"Failed: {result.error}")
        else:
            # List branches
            info = service.list_branches()
            self.print()
            self.print("Branches:", style="bold")
            for branch in info.branches:
                if branch == info.current:
                    self.print(f"  * {branch}", style="green")
                else:
                    self.print(f"    {branch}")
            self.print()

    async def _cmd_checkout(self, target: str) -> None:
        """Switch branch or commit."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        if not target:
            self.print_error("Usage: /checkout <branch|commit>")
            return

        service = self._get_branch_service()
        result = service.checkout(target)

        if result.success:
            self.print_success(f"Switched to: {result.branch or result.commit}")
        else:
            self.print_error(f"Failed: {result.error}")

    async def _cmd_commits(self, args: str) -> None:
        """Show commit history."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        limit = 10
        if args:
            with contextlib.suppress(ValueError):
                limit = int(args)

        service = self._get_branch_service()
        commits = service.get_commits("HEAD", limit=limit)

        if not commits:
            self.print("No commits found", style="yellow")
            return

        self.print()
        self.print("Commit History:", style="bold")
        for commit in commits:
            self.print(f"  {commit.short_hash}", style="yellow", end="")
            self.print(f" {commit.message}")
        self.print()

    def _get_memory_service(self):
        """Lazy load memory service."""
        if self._memory_service is None:
            from memoir.services.memory_service import MemoryService

            self._memory_service = MemoryService(self.store_path)
        return self._memory_service

    def _get_branch_service(self):
        """Lazy load branch service."""
        if self._branch_service is None:
            from memoir.services.branch_service import BranchService

            self._branch_service = BranchService(self.store_path)
        return self._branch_service

    def _get_store_service(self):
        """Lazy load store service."""
        if self._store_service is None:
            from memoir.services.store_service import StoreService

            self._store_service = StoreService(self.store_path)
        return self._store_service


# Keep old names for compatibility
MemoirTUI = MemoirCLI


def run_tui(store_path: str | None = None) -> None:
    """
    Run the memoir CLI.

    Args:
        store_path: Optional path to memory store
    """
    if not RICH_AVAILABLE:
        print("Warning: Rich not installed. Install with: pip install rich")
        print("Continuing with basic output...\n")

    app = MemoirCLI(store_path=store_path)
    app.run()

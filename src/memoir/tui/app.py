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
    "/tt": "/time-travel",
    "/tl": "/timeline",
    "/loc": "/location",
    "/d": "/diff",
    "/sum": "/summarize",
    "/search": "/recall",
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
            elif cmd == "/merge":
                await self._cmd_merge(args)
            elif cmd == "/proof":
                await self._cmd_proof(args)
            elif cmd == "/verify":
                await self._cmd_verify(args)
            elif cmd == "/blame":
                await self._cmd_blame(args)
            elif cmd == "/time-travel":
                await self._cmd_time_travel(args)
            elif cmd == "/diff":
                await self._cmd_diff(args)
            elif cmd == "/summarize":
                await self._cmd_summarize(args)
            elif cmd == "/timeline":
                await self._cmd_timeline(args)
            elif cmd == "/location":
                await self._cmd_location(args)
            # Placeholder commands
            elif cmd == "/import":
                self._placeholder_command(
                    "import", "Import conversations from JSON or TXT files"
                )
            elif cmd == "/eval":
                self._placeholder_command(
                    "eval", "Evaluate recall hit rate and answer quality"
                )
            elif cmd == "/organize":
                self._placeholder_command(
                    "organize", "Reorganize and optimize memory taxonomy"
                )
            elif cmd == "/inspect":
                self._placeholder_command(
                    "inspect", "Deep dive into a specific memory path"
                )
            elif cmd == "/benchmark":
                self._placeholder_command("benchmark", "Run performance benchmarks")
            elif cmd == "/export":
                self._placeholder_command("export", "Export memories to JSON/CSV")
            elif cmd == "/compare-stores":
                self._placeholder_command("compare-stores", "Compare two memory stores")
            elif cmd == "/replay":
                self._placeholder_command(
                    "replay", "Replay agent interactions with memory"
                )
            elif cmd == "/template":
                self._placeholder_command("template", "Generate prompt templates")
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
        self.print("Memory Commands:", style="bold")
        self.print("  /connect <path>    Connect to a memory store")
        self.print("  /new <path>        Create a new memory store")
        self.print("  /status            Show store status")
        self.print("  /remember <text>   Store a memory")
        self.print("  /recall <query>    Search memories")
        self.print("  /forget <key>      Delete a memory")
        self.print()
        self.print("Branch Commands:", style="bold")
        self.print("  /branch [name]     List or create branches")
        self.print("  /checkout <ref>    Switch branch/commit")
        self.print("  /merge <branch>    Merge branch into current")
        self.print("  /commits [n]       Show commit history")
        self.print("  /time-travel <ref> Travel to commit and create branch")
        self.print("  /diff [c1] [c2]    Compare commits")
        self.print()
        self.print("Crypto Commands:", style="bold")
        self.print("  /proof <path>      Generate cryptographic proof")
        self.print("  /verify <proof>    Verify a proof")
        self.print("  /blame <key>       Show blame history for key")
        self.print()
        self.print("Analysis Commands:", style="bold")
        self.print("  /summarize [type]  Summarize memories (all/taxonomy/timeline)")
        self.print("  /timeline [event]  Show or add timeline events")
        self.print("  /location [event]  Show or add location events")
        self.print()
        self.print("Other:", style="bold")
        self.print("  /help              Show this help")
        self.print("  /quit              Exit")
        self.print()
        self.print_dim(
            "Aliases: /con, /rem, /del, /br, /co, /log, /tt, /tl, /loc, /d, /sum"
        )
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

    async def _cmd_merge(self, source: str) -> None:
        """Merge a branch into current."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        if not source:
            self.print_error("Usage: /merge <source-branch>")
            return

        service = self._get_branch_service()
        result = service.merge(source)

        if result.success:
            self.print_success(f"Merged {source} into current branch")
        else:
            self.print_error(f"Failed: {result.error}")
            if result.conflicts:
                self.print("Conflicts:", style="yellow")
                for conflict in result.conflicts:
                    self.print(f"  {conflict}")

    async def _cmd_proof(self, path: str) -> None:
        """Generate cryptographic proof."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        if not path:
            self.print_error("Usage: /proof <memory-path>")
            return

        try:
            service = self._get_crypto_service()
            result = service.generate_proof(path)

            if result.success:
                self.print_success(f"Proof generated for: {path}")
                self.print(f"  Proof: {result.proof_b64[:50]}...")
                self.print(f"  Key: {result.key}")
                self.print(f"  Namespace: {result.namespace}")
            else:
                self.print_error(f"Failed: {result.error}")
        except Exception as e:
            self.print_error(str(e))

    async def _cmd_verify(self, args: str) -> None:
        """Verify a cryptographic proof."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        if not args:
            self.print_error("Usage: /verify <proof> <key> [namespace]")
            return

        parts = args.split()
        if len(parts) < 2:
            self.print_error("Usage: /verify <proof> <key> [namespace]")
            return

        proof = parts[0]
        key = parts[1]
        namespace = parts[2] if len(parts) > 2 else "default"

        try:
            service = self._get_crypto_service()
            result = service.verify_proof(proof, key, namespace)

            if result.valid:
                self.print_success("Proof is VALID")
                self.print(f"  Key: {key}")
                self.print(f"  Namespace: {namespace}")
            else:
                self.print_error("Proof is INVALID")
                if result.reason:
                    self.print(f"  Reason: {result.reason}")
        except Exception as e:
            self.print_error(str(e))

    async def _cmd_blame(self, key: str) -> None:
        """Show blame history for a key."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        if not key:
            self.print_error("Usage: /blame <key>")
            return

        try:
            service = self._get_crypto_service()
            blame_info = service.get_blame(key)

            if not blame_info:
                self.print("No history found for key", style="yellow")
                return

            self.print()
            self.print(f"Blame for: {key}", style="bold")
            for entry in blame_info:
                self.print(
                    f"  {entry.get('commit', 'N/A')[:8]}", style="yellow", end=""
                )
                self.print(f" {entry.get('author', 'Unknown')}", end="")
                self.print(f" - {entry.get('message', 'No message')}")
            self.print()
        except Exception as e:
            self.print_error(str(e))

    async def _cmd_time_travel(self, target: str) -> None:
        """Time travel to a commit and create a branch."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        if not target:
            self.print_error("Usage: /time-travel <commit-hash>")
            return

        try:
            service = self._get_branch_service()
            # Create a branch at the target commit
            branch_name = f"time-travel-{target[:8]}"
            result = service.checkout(target, create=True)

            if result.success:
                self.print_success(f"Time traveled to {target[:8]}")
                self.print(f"  Created branch: {branch_name}")
            else:
                self.print_error(f"Failed: {result.error}")
        except Exception as e:
            self.print_error(str(e))

    async def _cmd_diff(self, args: str) -> None:
        """Show diff between commits."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        try:
            service = self._get_branch_service()
            parts = args.split() if args else []

            if len(parts) == 0:
                # Diff current vs last commit
                diff = service.get_diff("HEAD~1", "HEAD")
            elif len(parts) == 1:
                # Diff specified commit vs HEAD
                diff = service.get_diff(parts[0], "HEAD")
            else:
                # Diff between two commits
                diff = service.get_diff(parts[0], parts[1])

            if not diff:
                self.print("No differences found", style="yellow")
                return

            self.print()
            self.print("Diff:", style="bold")
            for line in diff.split("\n")[:50]:  # Limit output
                if line.startswith("+"):
                    self.print(f"  {line}", style="green")
                elif line.startswith("-"):
                    self.print(f"  {line}", style="red")
                else:
                    self.print(f"  {line}")
            self.print()
        except Exception as e:
            self.print_error(str(e))

    async def _cmd_summarize(self, args: str) -> None:
        """Summarize memories."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        summary_type = args.lower() if args else "all"

        try:
            service = self._get_store_service()
            data = service.read_store()

            self.print()
            self.print(f"Memory Summary ({summary_type}):", style="bold")

            namespaces = data.get("namespaces", {})
            total_memories = sum(len(keys) for keys in namespaces.values())

            self.print(f"  Total namespaces: {len(namespaces)}")
            self.print(f"  Total memories: {total_memories}")

            if summary_type in ("all", "taxonomy"):
                self.print()
                self.print("  By namespace:", style="bold")
                for ns, keys in namespaces.items():
                    self.print(f"    {ns}: {len(keys)} memories")

            self.print()
        except Exception as e:
            self.print_error(str(e))

    async def _cmd_timeline(self, args: str) -> None:
        """Show or add timeline events."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        try:
            service = self._get_store_service()
            data = service.read_store()

            if args:
                # Add timeline event
                self.print_dim("Adding timeline event...")
                # Parse: YYYY-MM-DD description
                parts = args.split(maxsplit=1)
                if len(parts) < 2:
                    self.print_error("Usage: /timeline YYYY-MM-DD <description>")
                    return
                date, description = parts
                memory_service = self._get_memory_service()
                result = await memory_service.remember(
                    f"Timeline event on {date}: {description}", "timeline"
                )
                if result.success:
                    self.print_success(f"Added timeline event: {date}")
                else:
                    self.print_error(f"Failed: {result.error}")
            else:
                # Show timeline
                timeline = data.get("namespaces", {}).get("timeline", [])
                if not timeline:
                    self.print("No timeline events found", style="yellow")
                    return

                self.print()
                self.print("Timeline:", style="bold")
                for event in timeline[:20]:
                    self.print(f"  {event}")
                self.print()
        except Exception as e:
            self.print_error(str(e))

    async def _cmd_location(self, args: str) -> None:
        """Show or add location events."""
        if not self.store_path:
            self.print_error("No store connected")
            return

        try:
            service = self._get_store_service()
            data = service.read_store()

            if args:
                # Add location event
                self.print_dim("Adding location event...")
                memory_service = self._get_memory_service()
                result = await memory_service.remember(f"Location: {args}", "location")
                if result.success:
                    self.print_success(f"Added location: {args}")
                else:
                    self.print_error(f"Failed: {result.error}")
            else:
                # Show locations
                locations = data.get("namespaces", {}).get("location", [])
                if not locations:
                    self.print("No location events found", style="yellow")
                    return

                self.print()
                self.print("Locations:", style="bold")
                for loc in locations[:20]:
                    self.print(f"  {loc}")
                self.print()
        except Exception as e:
            self.print_error(str(e))

    def _placeholder_command(self, name: str, description: str) -> None:
        """Show placeholder message for unimplemented commands."""
        self.print(f"/{name} - {description}", style="yellow")
        self.print_dim("Coming soon...")

    def _get_crypto_service(self):
        """Lazy load crypto service."""
        if not hasattr(self, "_crypto_service") or self._crypto_service is None:
            from memoir.services.crypto_service import CryptoService

            self._crypto_service = CryptoService(self.store_path)
        return self._crypto_service

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

"""
Memoir CLI - Main entry point.

This is the Click-based command-line interface for memoir.
Optimized for both human use and shell-based AI agents.
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click

# Exit codes for agent error handling
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_NOT_FOUND = 2
EXIT_NO_STORE = 3
EXIT_CLASSIFICATION_FAILED = 4
EXIT_GIT_FAILED = 5


def get_config_dir() -> Path:
    """Get the memoir configuration directory."""
    config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(config_home) / "memoir"


def load_default_store() -> Optional[str]:
    """Load the default store path from config."""
    config_file = get_config_dir() / "config.json"
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
                return config.get("default_store")
        except Exception:
            pass
    return None


def save_default_store(path: str) -> None:
    """Save the default store path to config."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    config_file = config_dir / "config.json"

    config = {}
    if config_file.exists():
        try:
            with open(config_file) as f:
                config = json.load(f)
        except Exception:
            pass

    config["default_store"] = path
    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)


class MemoirContext:
    """Context object passed to all commands."""

    def __init__(self):
        self.store_path: Optional[str] = None
        self.json_output: bool = False
        self.quiet: bool = False
        self.verbose: bool = False

    def output(self, data: dict) -> None:
        """Output data as JSON or human-readable format."""
        if self.json_output:
            click.echo(json.dumps(data, indent=2, default=str))
        else:
            # Human-readable output handled by commands
            pass

    def success(self, message: str, data: Optional[dict] = None) -> None:
        """Output a success message."""
        if self.json_output:
            output = {"success": True, "message": message}
            if data:
                output.update(data)
            click.echo(json.dumps(output, indent=2, default=str))
        elif not self.quiet:
            click.echo(click.style("✓ ", fg="green") + message)

    def error(self, message: str, code: int = EXIT_ERROR) -> None:
        """Output an error message and exit."""
        if self.json_output:
            click.echo(json.dumps({"success": False, "error": message, "code": code}))
        else:
            click.echo(click.style("✗ ", fg="red") + message, err=True)
        sys.exit(code)

    def info(self, message: str) -> None:
        """Output an info message."""
        if not self.json_output and not self.quiet:
            click.echo(click.style("→ ", fg="blue") + message)

    def warn(self, message: str) -> None:
        """Output a warning message."""
        if not self.json_output and not self.quiet:
            click.echo(click.style("⚠ ", fg="yellow") + message, err=True)


pass_context = click.make_pass_decorator(MemoirContext, ensure=True)


@click.group()
@click.option(
    "-s",
    "--store",
    envvar="MEMOIR_STORE",
    help="Memory store path (or set MEMOIR_STORE env var)",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    envvar="MEMOIR_JSON",
    help="Output as JSON (for agents/scripting)",
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    envvar="MEMOIR_QUIET",
    help="Suppress non-essential output",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Enable verbose output",
)
@click.version_option(package_name="memoir")
@pass_context
def cli(
    ctx: MemoirContext,
    store: Optional[str],
    json_output: bool,
    quiet: bool,
    verbose: bool,
):
    """Memoir - Git for AI Memory.

    Manage AI memories with semantic organization and version control.

    \b
    Examples:
      memoir new /tmp/memories          # Create new store
      memoir connect /tmp/memories      # Set default store
      memoir remember "User likes tea"  # Store a memory
      memoir recall "preferences"       # Search memories

    \b
    Environment Variables:
      MEMOIR_STORE  Default store path
      MEMOIR_JSON   Always output JSON (set to 1)
      MEMOIR_QUIET  Suppress output (set to 1)
    """
    ctx.store_path = store or load_default_store()
    ctx.json_output = json_output
    ctx.quiet = quiet
    ctx.verbose = verbose


# Import and register command groups
from memoir.cli.commands import branch, crypto, memory, store  # noqa: E402

# Store commands
cli.add_command(store.new)
cli.add_command(store.connect)
cli.add_command(store.status)
cli.add_command(store.refresh)

# Memory commands
cli.add_command(memory.remember)
cli.add_command(memory.recall)
cli.add_command(memory.forget)

# Branch commands
cli.add_command(branch.branch)
cli.add_command(branch.checkout)
cli.add_command(branch.merge)
cli.add_command(branch.commits)

# Crypto commands
cli.add_command(crypto.proof)
cli.add_command(crypto.verify)
cli.add_command(crypto.blame)


# Utility commands
@cli.command()
@pass_context
def warmup(ctx: MemoirContext):
    """Pre-load models for faster subsequent calls.

    Use this in agent startup scripts to reduce latency
    on the first remember/recall call.
    """
    if not ctx.store_path:
        ctx.error(
            "No store configured. Use 'memoir connect <path>' first.", EXIT_NO_STORE
        )

    from memoir.services.memory_service import MemoryService

    service = MemoryService(ctx.store_path)
    warmup_time = service.warmup()

    ctx.success(f"Models loaded in {warmup_time:.2f}s", {"warmup_time": warmup_time})


@cli.command()
@pass_context
def code(ctx: MemoirContext):
    """Show Python integration code example."""
    code_example = """
# Memoir Python SDK Usage

from memoir.sdk import MemoryClient

async with MemoryClient("/path/to/store") as memory:
    # Store a memory
    result = await memory.remember("User prefers dark mode")
    print(f"Stored at: {result.key}")

    # Search memories
    memories = await memory.recall("user preferences")
    for m in memories:
        print(f"  {m.path}: {m.content}")

    # Delete a memory
    await memory.forget("old.path")

    # Branch operations
    await memory.branch.create("experiment")
    await memory.branch.checkout("experiment")
"""
    if ctx.json_output:
        click.echo(json.dumps({"code": code_example.strip()}))
    else:
        click.echo(code_example)


@cli.command()
@click.option("-p", "--port", default=8080, help="Port number")
@click.option("--no-browser", is_flag=True, help="Don't open browser")
@pass_context
def ui(ctx: MemoirContext, port: int, no_browser: bool):
    """Launch web UI."""
    import webbrowser

    if not no_browser:
        webbrowser.open(f"http://localhost:{port}")

    ctx.info(f"Starting web UI on port {port}...")

    from memoir.ui.server import run_server

    run_server(port=port)


@cli.command()
@click.option("-c", "--connect", "store_path", help="Store to connect")
@pass_context
def tui(ctx: MemoirContext, store_path: Optional[str]):
    """Launch interactive TUI."""
    path = store_path or ctx.store_path

    try:
        from memoir.tui.app import MemoirTUI

        app = MemoirTUI(store_path=path)
        app.run()
    except ImportError:
        ctx.error(
            "TUI not available. Install with: pip install memoir[tui]",
            EXIT_ERROR,
        )


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()

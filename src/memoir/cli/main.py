"""
Memoir CLI - Main entry point.

This is the Click-based command-line interface for memoir.
Optimized for both human use and shell-based AI agents.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import click

# Exit codes for agent error handling
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_NOT_FOUND = 2
EXIT_NO_STORE = 3
EXIT_CLASSIFICATION_FAILED = 4
EXIT_GIT_FAILED = 5

# Commands that are ready for agent use
AGENT_READY_COMMANDS = {
    "connect",
    "remember",
    "recall",
    "forget",
    "set",
    "get",
    "summarize",
    "incognito",
    "off-record",
    "on-record",
}


class AgentFilteredGroup(click.Group):
    """Custom Group that can filter commands for agent-only help."""

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter):
        """Override to filter commands when --agent-only is in argv."""
        # Check sys.argv directly since --help is eager and processes before callbacks
        agent_only = "--agent-only" in sys.argv

        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None:
                continue
            if agent_only and subcommand not in AGENT_READY_COMMANDS:
                continue
            help_text = cmd.get_short_help_str(limit=formatter.width)
            commands.append((subcommand, help_text))

        if commands:
            with formatter.section("Commands"):
                formatter.write_dl(commands)


def get_command_schema(cmd: click.Command, name: str) -> dict[str, Any]:
    """Extract schema from a Click command for machine-readable output."""
    schema: dict[str, Any] = {
        "name": name,
        "description": cmd.help.split("\n")[0] if cmd.help else None,
    }

    # Extract full help if available (for detailed docs)
    if cmd.help:
        # Parse INPUT/OUTPUT sections if present
        help_text = cmd.help
        if "INPUT:" in help_text:
            input_start = help_text.find("INPUT:")
            input_end = help_text.find("OUTPUT:", input_start)
            if input_end == -1:
                input_end = help_text.find("\n\n", input_start)
            if input_end == -1:
                input_end = len(help_text)
            schema["input"] = help_text[input_start + 6 : input_end].strip()

        if "OUTPUT:" in help_text:
            output_start = help_text.find("OUTPUT:")
            output_end = help_text.find("\n\n", output_start)
            if output_end == -1:
                output_end = len(help_text)
            schema["output"] = help_text[output_start + 7 : output_end].strip()

    # Extract arguments
    arguments = []
    for param in cmd.params:
        if isinstance(param, click.Argument):
            arguments.append(
                {
                    "name": param.name,
                    "required": param.required,
                    "type": (
                        param.type.name if hasattr(param.type, "name") else "string"
                    ),
                }
            )
    if arguments:
        schema["arguments"] = arguments

    # Extract options
    options = []
    for param in cmd.params:
        if isinstance(param, click.Option):
            opt: dict[str, Any] = {
                "name": param.name,
                "flags": list(param.opts),
                "required": param.required,
                "is_flag": param.is_flag,
            }
            if param.help:
                opt["description"] = param.help
            # Only include default if it's a simple JSON-serializable type
            if (
                param.default is not None
                and not param.is_flag
                and isinstance(param.default, (str, int, float, bool, list, dict))
            ):
                opt["default"] = param.default
            if param.envvar:
                opt["env_var"] = param.envvar
            options.append(opt)
    if options:
        schema["options"] = options

    return schema


def get_cli_schema(group: click.Group) -> dict[str, Any]:
    """Extract full CLI schema for machine-readable output."""
    schema: dict[str, Any] = {
        "name": "memoir",
        "description": "Git for AI Memory - versioned, semantic memory system for AI agents",
        "version": None,
        "exit_codes": {
            "0": "success",
            "1": "error",
            "2": "not_found",
            "3": "no_store",
            "4": "classification_failed",
            "5": "git_failed",
        },
        "env_vars": {
            "MEMOIR_STORE": "Default store path",
            "MEMOIR_JSON": "Always output JSON (set to 1)",
            "MEMOIR_QUIET": "Suppress non-essential output (set to 1)",
        },
        "global_options": [],
        "commands": {},
    }

    # Try to get version
    try:
        from importlib.metadata import version

        schema["version"] = version("memoir")
    except Exception:
        pass

    # Extract global options
    for param in group.params:
        if isinstance(param, click.Option):
            opt: dict[str, Any] = {
                "name": param.name,
                "flags": list(param.opts),
                "is_flag": param.is_flag,
            }
            if param.help:
                opt["description"] = param.help
            if param.envvar:
                opt["env_var"] = param.envvar
            schema["global_options"].append(opt)

    # Extract commands by group
    command_groups = {
        "store": ["new", "connect", "status", "refresh"],
        "memory": ["remember", "recall", "forget", "set", "get"],
        "branch": ["branch", "checkout", "merge", "time-travel", "diff"],
        "crypto": ["proof", "verify", "blame"],
        "analysis": ["summarize"],
        "taxonomy": ["taxonomy"],
        "utility": ["ui", "tui"],
    }

    for group_name, cmd_names in command_groups.items():
        schema["commands"][group_name] = []
        for cmd_name in cmd_names:
            if cmd_name in group.commands:
                cmd = group.commands[cmd_name]
                schema["commands"][group_name].append(get_command_schema(cmd, cmd_name))

    return schema


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


def print_machine_readable(ctx: click.Context, _param: click.Parameter, value: bool):
    """Callback to print machine-readable CLI schema and exit."""
    if not value or ctx.resilient_parsing:
        return
    # Import here to avoid circular import - cli is defined below
    schema = get_cli_schema(ctx.command)  # type: ignore
    click.echo(json.dumps(schema, indent=2))
    ctx.exit()


@click.group(cls=AgentFilteredGroup)
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
@click.option(
    "--machine-readable",
    "--json-schema",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=print_machine_readable,
    help="Output CLI schema as JSON (for agents to parse commands)",
)
@click.option(
    "--agent-only",
    is_flag=True,
    expose_value=False,
    help="Show only agent-ready commands in help output",
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

    A versioned, semantic memory system for AI agents. Memories are stored
    with automatic classification into hierarchical paths (e.g., user.preferences.theme)
    and full Git-like version control (branches, commits, time-travel).

    \b
    QUICK START FOR AGENTS:
      1. memoir new /path/to/store      # Create store (once)
      2. memoir connect /path/to/store  # Set as default
      3. memoir remember "content"      # Store memories
      4. memoir recall "query"          # Search memories

    \b
    COMMAND GROUPS:
      Store:    new, connect, status, refresh
      Memory:   remember, recall, forget
      Branch:   branch, checkout, merge, time-travel, diff
      Crypto:   proof, verify, blame
      Analysis: summarize

    \b
    AGENT TIPS:
      - Use --json flag for machine-readable output
      - Set MEMOIR_STORE env var to avoid -s flag on every command
      - Use 'checkout --create-if-missing' for auto-creating context branches
      - Exit codes: 0=success, 1=error, 2=not found, 3=no store, 5=git error

    \b
    ENVIRONMENT VARIABLES:
      MEMOIR_STORE  Default store path (recommended for agents)
      MEMOIR_JSON   Always output JSON (set to 1)
      MEMOIR_QUIET  Suppress non-essential output (set to 1)
    """
    ctx.store_path = store or load_default_store()
    ctx.json_output = json_output
    ctx.quiet = quiet
    ctx.verbose = verbose


# Import and register command groups
from memoir.cli.commands import (  # noqa: E402
    analysis,
    branch,
    crypto,
    memory,
    store,
    taxonomy,
)

# Store commands
cli.add_command(store.new)
cli.add_command(store.connect)
cli.add_command(store.status)
cli.add_command(store.refresh)

# Taxonomy commands
cli.add_command(taxonomy.taxonomy)

# Memory commands
cli.add_command(memory.remember)
cli.add_command(memory.recall)
cli.add_command(memory.forget)
cli.add_command(memory.set_memory)
cli.add_command(memory.get_memory)

# Branch commands
cli.add_command(branch.branch)
cli.add_command(branch.checkout)
cli.add_command(branch.merge)
cli.add_command(branch.time_travel)
cli.add_command(branch.diff)

# Crypto commands
cli.add_command(crypto.proof)
cli.add_command(crypto.verify)
cli.add_command(crypto.blame)

# Analysis commands
cli.add_command(analysis.summarize)


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


# Session mode commands (placeholders for agent integration)
@cli.command()
@pass_context
def incognito(ctx: MemoirContext):
    """Start incognito mode - AI cannot see past or save anything new.

    In this mode, every conversation is like a "first date" - no memory
    context is loaded and no new memories are stored.

    Use 'on-record' to exit incognito mode.
    """
    ctx.warn("Incognito mode not yet implemented")
    ctx.info("In incognito mode: AI cannot see your past and cannot save anything new")


@cli.command("off-record")
@pass_context
def off_record(ctx: MemoirContext):
    """Start off-record mode - AI can see past but won't save anything new.

    In this mode, memory context is loaded normally but new memories
    are held in a buffer without being persisted.

    Use 'on-record' to exit and choose to save or discard buffered memories.
    """
    ctx.warn("Off-record mode not yet implemented")
    ctx.info("In off-record mode: AI can see your past, but won't save anything new")


@cli.command("on-record")
@pass_context
def on_record(ctx: MemoirContext):
    """Exit incognito or off-record mode and return to normal.

    When exiting off-record mode, you'll be prompted to save or discard
    any memories that were buffered during the session.
    """
    ctx.warn("On-record mode not yet implemented")
    ctx.info("Returning to normal mode: AI can see and save memories")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()

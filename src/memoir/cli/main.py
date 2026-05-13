# SPDX-License-Identifier: Apache-2.0
"""
Memoir CLI - Main entry point.

This is the Click-based command-line interface for memoir.
Optimized for both human use and shell-based AI agents.
"""

import json
import os
import sys
from typing import Any

import click

from memoir import __version__

# Exit codes for agent error handling
EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_NOT_FOUND = 2
EXIT_NO_STORE = 3
EXIT_CLASSIFICATION_FAILED = 4
EXIT_GIT_FAILED = 5


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

        schema["version"] = version("memoir-ai")
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
        "store": ["new", "status", "refresh"],
        "memory": ["remember", "recall", "forget"],
        "branch": [
            "branch",
            "checkout",
            "merge",
            "sync-branch",
            "time-travel",
            "diff",
        ],
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


# Store-path resolution is intentionally three-tier and fully explicit:
#   1. -s / --store flag         (per-invocation, wins everything)
#   2. MEMOIR_STORE env var       (per-shell, picked up by Click envvar=)
#   3. current working directory  (per-cwd; lets you `cd <store> && memoir …`)
# There is no global default written to ~/.config/memoir/config.json — that
# was deliberately removed: a long-lived hidden default from a forgotten
# `memoir connect` from an earlier session caused stale-state surprises and
# wrong-store recalls in cross-project work. If you want a personal default,
# set MEMOIR_STORE in your shell rc.


class MemoirContext:
    """Context object passed to all commands."""

    def __init__(self):
        self.store_path: str | None = None
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

    def success(self, message: str, data: dict | None = None) -> None:
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
@click.option(
    "--machine-readable",
    "--json-schema",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=print_machine_readable,
    help="Output CLI schema as JSON (for agents to parse commands)",
)
@click.version_option(__version__)
@pass_context
def cli(
    ctx: MemoirContext,
    store: str | None,
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
      1. memoir new /path/to/store           # Create store (once)
      2. export MEMOIR_STORE=/path/to/store  # Or use -s on each command
      3. memoir remember "content"           # Store memories
      4. memoir recall "query"               # Search memories

    \b
    COMMAND GROUPS:
      Store:    new, status, refresh
      Memory:   remember, recall, get, forget
      Branch:   branch, checkout, merge, sync-branch, time-travel, diff
      Crypto:   proof, verify, blame
      Analysis: summarize
      Utility:  ui, tui

    \b
    STORE RESOLUTION (no hidden global default):
      1. -s / --store flag
      2. MEMOIR_STORE env var
      3. current working directory (cd into a memoir store and just run)

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
    # Resolution: -s flag (or MEMOIR_STORE via Click envvar=) → cwd → command-time error.
    # Click already folds MEMOIR_STORE into `store` via envvar="MEMOIR_STORE", so by the
    # time we're here `store` is None only when neither was set.
    ctx.store_path = store or os.getcwd()
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
    tui,
    ui,
)

# Store commands
cli.add_command(store.new)
cli.add_command(store.status)
cli.add_command(store.refresh)

# Taxonomy commands
cli.add_command(taxonomy.taxonomy)

# Memory commands
cli.add_command(memory.remember)
cli.add_command(memory.recall)
cli.add_command(memory.get_memory)
cli.add_command(memory.forget)

# Branch commands
cli.add_command(branch.branch)
cli.add_command(branch.checkout)
cli.add_command(branch.merge)
cli.add_command(branch.sync_branch)
cli.add_command(branch.time_travel)
cli.add_command(branch.diff)

# Crypto commands
cli.add_command(crypto.proof)
cli.add_command(crypto.verify)
cli.add_command(crypto.blame)

# Analysis commands
cli.add_command(analysis.summarize)

# Utility commands
cli.add_command(ui.ui)
cli.add_command(tui.tui)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()

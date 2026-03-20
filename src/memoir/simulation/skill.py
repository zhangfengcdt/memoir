"""
Skill Injector - Inject memoir skill instructions into agent system prompts.

This module provides the SKILL.md content that teaches the agent
how to use memoir commands, following the OpenClaw skill pattern.

Supports two modes of execution:
1. LLM Tool Calls - LLM decides when to call memoir tools
2. Slash Commands - User directly invokes commands via /memoir_*
"""

import contextlib
from dataclasses import dataclass, field
from enum import Flag, auto
from typing import Any, Callable, Optional


class CommandVisibility(Flag):
    """Controls where a command is visible/available."""

    NONE = 0
    LLM_TOOL = auto()  # Available as LLM function tool
    SLASH_CMD = auto()  # Available as /slash_command for users
    BOTH = LLM_TOOL | SLASH_CMD  # Available in both contexts


@dataclass
class CommandDefinition:
    """Definition of a memoir command."""

    name: str  # e.g., "remember", "incognito"
    description: str
    visibility: CommandVisibility = CommandVisibility.BOTH
    parameters: dict = field(default_factory=dict)
    cli_command: str = ""  # CLI command template, e.g., "memoir remember {content}"
    handler: Optional[Callable] = None  # Custom handler if not CLI-based


@dataclass
class SkillMetadata:
    """Skill metadata for OpenClaw compatibility."""

    name: str = "memoir"
    description: str = (
        "Git-like versioned memory - store, recall, and branch persistent memories"
    )
    requires_bins: list[str] = None

    def __post_init__(self):
        if self.requires_bins is None:
            self.requires_bins = ["memoir"]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "openclaw": {
                "requires": {"bins": self.requires_bins},
                "install": [
                    {
                        "kind": "pip",
                        "package": "memoir",
                        "bins": ["memoir"],
                        "label": "Install via pip",
                    }
                ],
            },
        }


SKILL_MARKDOWN = """
# Memoir - Versioned Agent Memory

Memoir provides persistent, versioned memory across sessions with namespace isolation.

## Namespaces

| Namespace | Use For |
|-----------|---------|
| `system` | Shared environment, tools, policies |
| `agent` | Your learnings, skills, lessons |
| `{channel}:{user_id}` | User preferences, projects |

## Commands

### Store a memory

When you learn something important:

```bash
# About yourself (skills, lessons)
memoir remember "Learned to use rg instead of grep for speed" --namespace agent --json

# About the user (preferences, context)
memoir remember "User prefers functional programming style" --namespace {channel}:{user_id} --json

# About the system
memoir remember "MCP server github available on port 3000" --namespace system --json
```

### Recall memories

When you need context:

```bash
# Semantic search (expensive - use sparingly)
memoir recall "debugging techniques" --namespace agent --limit 5 --json

# Direct path lookup (cheap - prefer this)
memoir recall preferences.theme --namespace {channel}:{user_id} --limit 1 --json
```

### Direct path access (fast, no LLM)

When you know the exact path, use set/get to bypass LLM classification:

```bash
# Store at exact path (no classification)
memoir set "config.identity.feng" "channels: discord, slack" --namespace agent --json

# Get by exact path (O(log n) lookup)
memoir get "config.identity.feng" --namespace agent --json
```

**When to use set/get vs remember/recall:**
- Use `set`/`get` when you know the exact path (config, identity, known preferences)
- Use `remember`/`recall` when content needs classification or semantic search

### View history

```bash
memoir commits --limit 10 --json
```

## Decision Guide

Before storing, ask: **Who benefits from this memory?**

| What to Store | Namespace | Example |
|--------------|-----------|---------|
| Skill you learned | `agent` | "Use console.trace() for call stacks" |
| User preference | `{channel}:{user_id}` | "Prefers dark mode" |
| System info | `system` | "Redis available on localhost:6379" |

## Best Practices

1. **Prefer path lookup over recall** - Direct path queries are free, semantic search costs tokens
2. **Store atomically** - One fact per remember call
3. **Use namespaces for isolation** - Different users/contexts get different namespaces
4. **Let hooks handle routine storage** - Focus on explicit important learnings
5. **Use --json flag** - Always include for machine-readable output
"""


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "memoir_remember",
            "description": "Store a memory. Use namespace 'agent' for your own learnings/skills, or '{channel}:{user_id}' for user preferences/facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The content to remember. Should be a clear, atomic fact or piece of information.",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace: 'agent' for your learnings, '{channel}:{user_id}' for user info. Default is user namespace.",
                    },
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memoir_recall",
            "description": "Search stored memories. Use namespace 'agent' for your learnings, or '{channel}:{user_id}' for user info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language search query.",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace to search: 'agent' or '{channel}:{user_id}'. Default is user namespace.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return.",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memoir_forget",
            "description": "Delete a memory by its path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The memory path to delete.",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace containing the memory.",
                        "default": "agent",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memoir_set",
            "description": "Store content at an exact path WITHOUT LLM classification. Use when you know the exact semantic path (e.g., 'config.identity.feng', 'preferences.theme'). Faster and cheaper than memoir_remember.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The exact semantic path to store at (e.g., 'config.identity.feng', 'preferences.theme').",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to store.",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace: 'agent' for your data, or person name for user data.",
                        "default": "agent",
                    },
                },
                "required": ["key", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memoir_get",
            "description": "Get content by exact path WITHOUT LLM search. O(log n) lookup - very fast and no LLM calls. Use when you know the exact path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "The exact semantic path to retrieve (e.g., 'config.identity.feng', 'preferences.theme').",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace to look in.",
                        "default": "agent",
                    },
                },
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "memoir_help",
            "description": "Get help for memoir CLI commands. Call with no arguments for general help, or specify a command name for detailed help.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Command name to get help for (e.g., 'remember', 'recall', 'branch'). Leave empty for general help.",
                    },
                },
                "required": [],
            },
        },
    },
]


# Command Registry - defines all available commands and their visibility
# Commands with LLM_TOOL visibility are exposed as function tools to the LLM
# Commands with SLASH_CMD visibility can be invoked by users via /memoir_*
COMMAND_REGISTRY: dict[str, CommandDefinition] = {
    # Core memory commands - available to both LLM and users
    "remember": CommandDefinition(
        name="remember",
        description="Store a memory with intelligent classification",
        visibility=CommandVisibility.BOTH,
        cli_command="memoir remember {content} --namespace {namespace} --json",
    ),
    "recall": CommandDefinition(
        name="recall",
        description="Search memories using semantic query",
        visibility=CommandVisibility.BOTH,
        cli_command="memoir recall {query} --namespace {namespace} --limit {limit} --json",
    ),
    "forget": CommandDefinition(
        name="forget",
        description="Delete a memory by its path",
        visibility=CommandVisibility.BOTH,
        cli_command="memoir forget {path} --namespace {namespace} --json",
    ),
    "set": CommandDefinition(
        name="set",
        description="Store content at exact path (no LLM classification)",
        visibility=CommandVisibility.BOTH,
        cli_command="memoir set {key} {content} --namespace {namespace} --json",
    ),
    "get": CommandDefinition(
        name="get",
        description="Get content by exact path (fast lookup)",
        visibility=CommandVisibility.BOTH,
        cli_command="memoir get {key} --namespace {namespace} --json",
    ),
    "help": CommandDefinition(
        name="help",
        description="Get help for memoir commands",
        visibility=CommandVisibility.BOTH,
        cli_command="memoir {command} --help",
    ),
    # Session mode commands - SLASH_CMD only (user controls, not LLM)
    "incognito": CommandDefinition(
        name="incognito",
        description="Start incognito mode - AI cannot see past or save anything new",
        visibility=CommandVisibility.SLASH_CMD,
        cli_command="memoir incognito --json",
    ),
    "off-record": CommandDefinition(
        name="off-record",
        description="Start off-record mode - AI can see past but won't save new",
        visibility=CommandVisibility.SLASH_CMD,
        cli_command="memoir off-record --json",
    ),
    "on-record": CommandDefinition(
        name="on-record",
        description="Exit incognito/off-record mode, return to normal",
        visibility=CommandVisibility.SLASH_CMD,
        cli_command="memoir on-record --json",
    ),
    # Analysis commands - SLASH_CMD only for now
    "summarize": CommandDefinition(
        name="summarize",
        description="Summarize memories in the store",
        visibility=CommandVisibility.SLASH_CMD,
        cli_command="memoir summarize --namespace {namespace} --json",
    ),
    "commits": CommandDefinition(
        name="commits",
        description="Show commit history",
        visibility=CommandVisibility.SLASH_CMD,
        cli_command="memoir commits --limit {limit} --json",
    ),
}


def get_llm_visible_commands() -> list[str]:
    """Get list of command names visible to LLM as tools."""
    return [
        name
        for name, cmd in COMMAND_REGISTRY.items()
        if CommandVisibility.LLM_TOOL in cmd.visibility
    ]


def get_slash_commands() -> list[str]:
    """Get list of command names available as slash commands."""
    return [
        name
        for name, cmd in COMMAND_REGISTRY.items()
        if CommandVisibility.SLASH_CMD in cmd.visibility
    ]


class SkillInjector:
    """
    Inject memoir skill instructions into agent system prompts.

    This class provides the skill documentation and tool definitions
    that teach an agent how to use memoir commands.

    Supports two execution modes:
    1. LLM Tool Calls - get_tool_definitions() returns tools for LLM
    2. Slash Commands - execute_slash_command() for user /memoir_* commands

    Example:
        injector = SkillInjector(user_id="user123")

        # Get skill instructions for system prompt
        system_prompt = injector.get_system_prompt_injection()

        # Get tool definitions for LLM
        tools = injector.get_tool_definitions()

        # Handle tool calls from LLM
        result = injector.execute_tool_call(
            "memoir_remember",
            {"content": "User prefers dark mode"}
        )
    """

    def __init__(
        self,
        user_id: str = "default",
        store_path: Optional[str] = None,
    ):
        """
        Initialize skill injector.

        Args:
            user_id: User ID for namespace substitution
            store_path: Path to memoir store (for tool execution)
        """
        self.user_id = user_id
        self.store_path = store_path
        self.metadata = SkillMetadata()
        self._executor = None

    @property
    def executor(self):
        """Lazy-load CLI executor."""
        if self._executor is None and self.store_path:
            from memoir.simulation.cli_executor import CLIExecutor

            self._executor = CLIExecutor(self.store_path)
        return self._executor

    def get_skill_markdown(self) -> str:
        """
        Get the skill markdown with user ID substituted.

        Returns:
            Skill documentation with {user_id} replaced
        """
        return SKILL_MARKDOWN.replace("{user_id}", self.user_id)

    def get_system_prompt_injection(self) -> str:
        """
        Get the complete system prompt injection.

        This includes:
        - Skill description header
        - Full skill documentation
        - Usage guidelines

        Returns:
            Text to inject into agent's system prompt
        """
        skill = self.get_skill_markdown()

        return f"""
## Available Skill: Memoir (Versioned Memory)

You have access to the memoir memory system for persistent, versioned memory
across sessions. Use memoir to store important information and recall it later.

{skill}

### Important Notes

- All memoir commands output JSON when you include --json flag
- Memories are automatically classified into semantic paths
- Use namespaces to organize: agent (your learnings), {{channel}}:{self.user_id} (user prefs), system (shared)
- Branches provide isolation for projects and experiments
"""

    def get_tool_definitions(self) -> list[dict]:
        """
        Get tool definitions for LLM function calling.

        Returns:
            List of tool definitions in OpenAI format
        """
        # Substitute user_id in tool definitions
        tools = []
        for tool in TOOL_DEFINITIONS:
            tool_copy = tool.copy()
            func = tool_copy.get("function", {})

            # Update namespace defaults with user_id
            if "parameters" in func:
                params = func["parameters"].get("properties", {})
                if "namespace" in params:
                    ns = params["namespace"]
                    if "default" in ns and "{id}" in ns.get("description", ""):
                        ns["description"] = ns["description"].replace(
                            "{id}", self.user_id
                        )

            tools.append(tool_copy)

        return tools

    def execute_tool_call(
        self,
        tool_name: str,
        arguments: dict,
    ) -> dict:
        """
        Execute a memoir tool call.

        Args:
            tool_name: Tool name (e.g., "memoir_remember")
            arguments: Tool arguments

        Returns:
            Tool execution result as dict (includes 'command' field with CLI command)
        """
        if not self.executor:
            return {
                "success": False,
                "error": "No store path configured",
                "command": "",
            }

        # Map tool calls to executor methods
        if tool_name == "memoir_remember":
            result = self.executor.remember(
                content=arguments["content"],
                namespace=arguments.get("namespace", "agent"),
            )
        elif tool_name == "memoir_recall":
            result = self.executor.recall(
                query=arguments["query"],
                namespace=arguments.get("namespace", "agent"),
                limit=arguments.get("limit", 5),
            )
        elif tool_name == "memoir_forget":
            result = self.executor.forget(
                key=arguments["path"],
                namespace=arguments.get("namespace", "agent"),
            )
        elif tool_name == "memoir_set":
            result = self.executor.set(
                key=arguments["key"],
                content=arguments["content"],
                namespace=arguments.get("namespace", "agent"),
            )
        elif tool_name == "memoir_get":
            result = self.executor.get(
                key=arguments["key"],
                namespace=arguments.get("namespace", "agent"),
            )
        elif tool_name == "memoir_help":
            result = self.executor.help(
                command=arguments.get("command"),
            )
        else:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "command": "",
            }

        # Convert CLIResult to dict (include command for logging)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "command": result.command,
        }

    def get_slash_commands(self) -> list[dict[str, str]]:
        """
        Get list of available slash commands.

        Returns:
            List of dicts with 'name' and 'description' for each command
        """
        return [
            {"name": f"/memoir_{name}", "description": cmd.description}
            for name, cmd in COMMAND_REGISTRY.items()
            if CommandVisibility.SLASH_CMD in cmd.visibility
        ]

    def parse_slash_command(
        self, command_str: str
    ) -> tuple[Optional[str], dict[str, Any]]:
        """
        Parse a slash command string into command name and arguments.

        Args:
            command_str: Command string like "/memoir_remember hello world --namespace agent"

        Returns:
            Tuple of (command_name, arguments_dict) or (None, {}) if invalid
        """
        if not command_str.startswith("/memoir_"):
            return None, {}

        # Remove /memoir_ prefix
        rest = command_str[8:].strip()
        if not rest:
            return None, {}

        # Split into parts
        parts = rest.split()
        cmd_name = parts[0]

        # Check if command exists and is slash-enabled
        if cmd_name not in COMMAND_REGISTRY:
            return None, {}

        cmd_def = COMMAND_REGISTRY[cmd_name]
        if CommandVisibility.SLASH_CMD not in cmd_def.visibility:
            return None, {}

        # Parse arguments (simple key=value or positional)
        args: dict[str, Any] = {}
        positional = []
        i = 1
        while i < len(parts):
            part = parts[i]
            if part.startswith("--"):
                # Named argument
                key = part[2:]
                if i + 1 < len(parts) and not parts[i + 1].startswith("--"):
                    args[key] = parts[i + 1]
                    i += 2
                else:
                    args[key] = True
                    i += 1
            else:
                positional.append(part)
                i += 1

        # Map positional arguments based on command
        if cmd_name == "remember" and positional:
            args["content"] = " ".join(positional)
        elif cmd_name == "recall" and positional:
            args["query"] = " ".join(positional)
        elif cmd_name == "forget" and positional:
            args["path"] = positional[0]
        elif cmd_name == "set" and len(positional) >= 2:
            args["key"] = positional[0]
            args["content"] = " ".join(positional[1:])
        elif cmd_name == "get" and positional:
            args["key"] = positional[0]
        elif cmd_name == "summarize" and positional:
            args["namespace"] = positional[0]
        elif cmd_name == "commits" and positional:
            with contextlib.suppress(ValueError):
                args["limit"] = int(positional[0])

        return cmd_name, args

    def execute_slash_command(
        self,
        command_str: str,
        default_namespace: str = "agent",
    ) -> dict[str, Any]:
        """
        Execute a slash command from user input.

        Args:
            command_str: Full command string like "/memoir_remember user prefers dark mode"
            default_namespace: Default namespace if not specified

        Returns:
            Execution result dict with success, data, error, command fields
        """
        cmd_name, args = self.parse_slash_command(command_str)

        if cmd_name is None:
            return {
                "success": False,
                "error": f"Invalid slash command: {command_str}",
                "command": "",
                "data": None,
            }

        # Set default namespace if not provided
        if "namespace" not in args:
            args["namespace"] = default_namespace

        # Set default limit for recall/commits
        if cmd_name == "recall" and "limit" not in args:
            args["limit"] = 5
        if cmd_name == "commits" and "limit" not in args:
            args["limit"] = 10

        # Execute via CLI executor
        if not self.executor:
            return {
                "success": False,
                "error": "No store path configured",
                "command": "",
                "data": None,
            }

        # Map to executor methods
        try:
            if cmd_name == "remember":
                result = self.executor.remember(
                    content=args.get("content", ""),
                    namespace=args.get("namespace", default_namespace),
                )
            elif cmd_name == "recall":
                result = self.executor.recall(
                    query=args.get("query", ""),
                    namespace=args.get("namespace", default_namespace),
                    limit=args.get("limit", 5),
                )
            elif cmd_name == "forget":
                result = self.executor.forget(
                    key=args.get("path", ""),
                    namespace=args.get("namespace", default_namespace),
                )
            elif cmd_name == "set":
                result = self.executor.set(
                    key=args.get("key", ""),
                    content=args.get("content", ""),
                    namespace=args.get("namespace", default_namespace),
                )
            elif cmd_name == "get":
                result = self.executor.get(
                    key=args.get("key", ""),
                    namespace=args.get("namespace", default_namespace),
                )
            elif cmd_name == "summarize":
                result = self.executor.summarize(
                    namespace=args.get("namespace", default_namespace),
                )
            elif cmd_name == "commits":
                result = self.executor.commits(
                    limit=args.get("limit", 10),
                )
            elif cmd_name in ("incognito", "off-record", "on-record"):
                # Mode commands - execute directly via CLI
                result = self.executor.run_command(cmd_name)
            else:
                return {
                    "success": False,
                    "error": f"Unknown command: {cmd_name}",
                    "command": "",
                    "data": None,
                }

            return {
                "success": result.success,
                "data": result.data,
                "error": result.error,
                "command": result.command,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "command": "",
                "data": None,
            }

    def is_slash_command(self, text: str) -> bool:
        """Check if text is a memoir slash command."""
        return text.strip().startswith("/memoir_")

    async def execute_slash_command_async(
        self,
        command_str: str,
        default_namespace: str = "agent",
    ) -> dict[str, Any]:
        """
        Execute a slash command asynchronously.

        Runs the synchronous execute_slash_command in a thread pool
        to avoid blocking the event loop.

        Args:
            command_str: Full command string like "/memoir_remember user prefers dark mode"
            default_namespace: Default namespace if not specified

        Returns:
            Execution result dict with success, data, error, command fields
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,  # Use default thread pool
            lambda: self.execute_slash_command(command_str, default_namespace),
        )


def create_skill_file(output_path: str, user_id: str = "default") -> str:
    """
    Create a SKILL.md file for OpenClaw.

    Args:
        output_path: Path to write the skill file
        user_id: User ID for namespace substitution

    Returns:
        Path to created file
    """
    injector = SkillInjector(user_id=user_id)

    content = f"""---
name: memoir
description: {injector.metadata.description}
metadata: {{"openclaw":{{"requires":{{"bins":["memoir"]}},"install":[{{"kind":"pip","package":"memoir","bins":["memoir"],"label":"Install via pip"}}]}}}}
---

{injector.get_skill_markdown()}
"""

    with open(output_path, "w") as f:
        f.write(content)

    return output_path

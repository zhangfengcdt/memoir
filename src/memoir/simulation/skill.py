"""
Skill Injector - Inject memoir skill instructions into agent system prompts.

This module provides the SKILL.md content that teaches the agent
how to use memoir commands, following the OpenClaw skill pattern.
"""

from dataclasses import dataclass
from typing import Optional


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


class SkillInjector:
    """
    Inject memoir skill instructions into agent system prompts.

    This class provides the skill documentation and tool definitions
    that teach an agent how to use memoir commands.

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

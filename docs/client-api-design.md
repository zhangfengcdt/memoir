# Memoir Unified Client API Design

## Overview

The Memoir Client API provides a unified Python interface for interacting with memory stores across different backends (local, remote, cloud, MCP). The design prioritizes simplicity with a single natural language interface.

## Design Principles

1. **Ultra-Simple**: Single `execute()` method for all operations
2. **Natural Language**: Describe what you want instead of learning API methods
3. **Self-Discoverable**: `ability()` method reveals capabilities for LLM tools
4. **Backend Agnostic**: Same interface for local, remote, cloud, and MCP
5. **Connection String Based**: URI-style configuration
6. **Safe Experimentation**: Version control enables reversible operations and error recovery

## Why Natural Language Works: The Version Control Foundation

The key insight enabling Memoir's natural language interface is **version control as a safety mechanism**. Unlike traditional databases where mistakes can be catastrophic, Memoir's Git-like versioning provides:

**Safety Through Reversibility:**
- Every operation creates a new commit with cryptographic integrity
- Mistakes can be instantly reverted: `"Go back to before I messed up"`
- Branches allow safe experimentation: `"Create a test branch for this risky operation"`
- Time travel enables recovery: `"Show me the state from yesterday"`

**Confidence for AI Tools:**
Just as AI coding assistants work confidently with Git repositories (knowing code changes are reversible), AI tools can safely experiment with memory operations knowing that:
- Bad commands won't corrupt the memory store permanently
- Previous states are always recoverable
- Experimental branches can be safely deleted
- Operations are auditable through the commit history

**This is Revolutionary:**
Traditional memory systems require precise API calls because errors are permanent. Memoir enables imprecise natural language because **every state is preserved and recoverable**. This is the same principle that makes Git essential for AI-powered development tools.

```python
# AI tools can experiment safely
await client.execute("Create a branch called experiment")
await client.execute("Try organizing my memories by importance") 
# If it doesn't work well:
await client.execute("Switch back to main branch")
await client.execute("Delete the experiment branch")
# Zero risk, full reversibility
```

## Core Client Interface

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class MemoirClient(ABC):
    """Unified client interface for all Memoir backends."""
    
    # --- Connection Management ---
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the memory store."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the memory store."""
        pass
    
    # --- Self-Discovery ---
    @abstractmethod
    async def ability(self) -> str:
        """
        Return natural language description of client capabilities.
        
        This helps LLM tools understand what operations are supported
        and can be used as prompt context to generate better execute() calls.
        
        Returns:
            Natural language description of supported operations
        """
        pass
    
    # --- Primary Interface ---
    @abstractmethod
    async def execute(self, command: str) -> Dict[str, Any]:
        """
        Execute commands against the memory store using natural language or structured commands.
        
        Args:
            command: Natural language instruction OR structured command (starting with /)
            
        Returns:
            Dictionary containing:
            - action: The interpreted action
            - result: The action result  
            - explanation: Human-readable explanation
            
        Natural Language Examples:
            "Remember that Alice prefers morning meetings"
            "What do I know about Alice?"
            "Create a branch for testing" 
            "Go back to yesterday"
            "Summarize everything"
            "Export as JSON"
            
        Structured Command Examples:
            "/remember Alice prefers Python programming"
            "/search Alice"
            "/branch create testing"
            "/timeline go 2024-01-01"  
            "/summarize timeline"
            "/export json"
        """
        pass
    
    # --- Sync Wrappers ---
    def ability_sync(self) -> str:
        """Synchronous wrapper for ability()."""
        import asyncio
        return asyncio.run(self.ability())
    
    def execute_sync(self, command: str) -> Dict[str, Any]:
        """Synchronous wrapper for execute()."""
        import asyncio
        return asyncio.run(self.execute(command))
```

## Connection String Format

### Supported Schemes
- `local:///absolute/path` - Local filesystem
- `local:./relative/path` - Local filesystem relative
- `http://host:port/path` - HTTP server
- `https://host:port/path` - HTTPS server  
- `cloud://org/store` - Memoir Cloud
- `cloud://store` - Memoir Cloud (default org)
- `mcp://service` - MCP service

### Connection Factory

```python
from memoir.client import connect

def connect(connection_string: str, **kwargs) -> MemoirClient:
    """
    Create client from connection string.
    
    Examples:
        connect("local:///tmp/memories")
        connect("cloud://my-org/production")
        connect("https://api.memoir.ai/store", api_key="...")
    """
```

## Hybrid Command System

The `execute()` method supports both natural language and structured commands for maximum flexibility:

### Natural Language Commands (Flexible)
Use conversational language when you want flexibility and don't need precision:

**Memory Operations:**
- `"Remember that Alice prefers Python"`  
- `"What do I know about Alice?"`
- `"Forget about old meeting preferences"`
- `"Update Bob's role to Senior Engineer"`

**Version Control:**
- `"Create a branch called experiment"`
- `"Switch to main branch"`
- `"Go back to yesterday"`
- `"Show me recent changes"`

**Analysis:**
- `"Summarize everything I know"`
- `"What patterns do you see?"`  
- `"Export my memories as JSON"`
- `"Show usage statistics"`

### Structured Commands (Precise)
Use `/command` syntax when you need precision and consistency (same as UI/CLI):

**Memory Operations:**
- `/remember [key] [value]` - Store memory with specific key
- `/search [query]` - Search memories  
- `/get [path]` - Get specific memory path
- `/delete [path]` - Remove specific memory
- `/update [path] [value]` - Update existing memory

**Version Control:**
- `/branch create [name]` - Create new branch
- `/branch switch [name]` - Switch to branch
- `/branch list` - List all branches
- `/commit [message]` - Create commit with message
- `/timeline go [date/commit]` - Time travel to specific point
- `/timeline recent [period]` - Show recent timeline

**Analysis & Export:**
- `/summarize [scope]` - Summarize specific scope (all, timeline, taxonomy, places)
- `/export [format]` - Export in specific format (json, csv, yaml)
- `/stats` - Show detailed statistics
- `/proof [path]` - Generate cryptographic proof

**System Operations:**
- `/connect [connection_string]` - Connect to different store
- `/refresh` - Refresh current view
- `/verify [proof]` - Verify cryptographic proof

### When to Use Each Approach

**Use Natural Language When:**
- ✅ Rapid prototyping and experimentation
- ✅ Interactive exploration and discovery
- ✅ Complex queries that need interpretation
- ✅ Human-readable logging and documentation
- ✅ AI tools generating exploratory commands

**Use Structured Commands When:**
- ✅ Automation and scripting
- ✅ Precise operations with specific parameters
- ✅ Performance-critical operations
- ✅ Integration with UI/CLI workflows
- ✅ Deterministic behavior required

**Example Scenarios:**

```python
# Interactive exploration - Natural Language
await client.execute("What are the main themes in my memories?")
await client.execute("Show me patterns from last month")

# Automation script - Structured Commands  
await client.execute("/branch create backup")
await client.execute("/export json /tmp/backup.json")
await client.execute("/commit 'Daily backup'")

# Mixed approach - Best of both worlds
await client.execute("/timeline go yesterday")  # Precise time travel
await client.execute("What changed since then?")  # Natural exploration
```

**Consistency Across Interfaces:**
All structured commands work identically in:
- **Client API**: `await client.execute("/branch list")`
- **CLI Tool**: `memoir /branch list`  
- **Web UI**: Type `/branch list` in command interface

## Usage Examples

### Basic Usage

```python
from memoir.client import connect

# Connect to any backend
client = connect("local:///my/memories")
await client.connect()

# Discover capabilities
capabilities = await client.ability()
print(capabilities)
# Output: "I can store and retrieve memories, create branches, search content, 
#          export data, travel through time, summarize information, and more..."

# Natural language operations
await client.execute("Remember that Alice prefers Python")
await client.execute("What do I know about Alice?")
await client.execute("Create a branch called testing")

# Structured command operations (more precise)
await client.execute("/remember Bob role Senior Engineer")
await client.execute("/search Bob")
await client.execute("/branch switch testing")
await client.execute("/export json")

# Mix both approaches as needed
await client.execute("Show me recent changes")  # Natural
await client.execute("/timeline recent 7days")   # Structured

await client.disconnect()
```

### CLI Tool

```python
import click
from memoir.client import connect

@click.command()
@click.option('--store', default='local:~/.memoir/default')
@click.argument('command', nargs=-1)
async def memoir(store, command):
    """Execute memoir operations in natural language."""
    instruction = ' '.join(command)
    
    async with connect(store) as client:
        response = await client.execute(instruction)
        click.echo(response['explanation'])

# Usage - Natural Language:
# memoir remember that Alice likes Python
# memoir what do I know about Alice?
# memoir create a branch for testing

# Usage - Structured Commands:
# memoir /remember alice.skills python
# memoir /search alice
# memoir /branch create testing
```

### Agent Integration

```python
from memoir.client import connect

class MemoryAgent:
    def __init__(self, store_url: str):
        self.memory = connect(store_url)
    
    async def process_message(self, message: str):
        # Store interaction
        await self.memory.execute(f"Remember user said: {message}")
        
        # Get relevant context
        context = await self.memory.execute(f"What's relevant to: {message}")
        
        # Generate response with context
        response = self.generate_response(message, context)
        
        # Store response
        await self.memory.execute(f"Remember I replied: {response}")
        
        return response
```

### LLM Tool Self-Discovery

LLM tools can discover capabilities dynamically and use them to generate better prompts:

```python
# AI tools can self-discover capabilities
from memoir.client import connect

class SmartAgent:
    def __init__(self, store_url: str):
        self.memory = connect(store_url)
        self.capabilities = None
    
    async def initialize(self):
        await self.memory.connect()
        # Get capabilities for prompt engineering
        self.capabilities = await self.memory.ability()
        # Now the agent knows exactly what it can do with memory
        
    async def process_with_context(self, user_request: str):
        # Use capabilities in system prompt
        system_prompt = f"""
        You are an AI agent with access to a memory system.
        
        Available memory capabilities:
        {self.capabilities}
        
        Use natural language commands to interact with memory.
        Examples: "Remember X", "What do I know about Y?", "Create branch Z"
        """
        
        # Generate memory operations based on discovered capabilities
        memory_commands = self.generate_memory_commands(user_request)
        
        # Execute the commands
        for command in memory_commands:
            await self.memory.execute(command)
```

## Advanced Example: Version Control in Action

This example demonstrates how natural language commands leverage Memoir's Git-like version control:

```python
# User wants to test something without affecting their main memory
await client.execute("help me to test the memory in a test environment")
# Behind the scenes:
# 1. Creates a new branch: /branch create test-environment-[timestamp]
# 2. Switches to that branch: /branch switch test-environment-[timestamp]
# 3. Records the commit hash before branching for later recovery

# User adds test data
await client.execute("My friend told me AI will replace programmers")
# Behind the scenes:
# 1. Classifies content: profile.social.conversations.friend
# 2. Stores in test branch: /remember profile.social.conversations.friend.[id] "AI will replace..."
# 3. Creates commit: "Added conversation memory"

# User modifies existing memories (assuming current year is 2025)
await client.execute("I want to forget what I have been doing when I visited Japan last year")
# Behind the scenes:
# 1. Determines "last year" = 2024 (current year - 1)
# 2. Searches for Japan-related memories from 2024: /search "Japan 2024"
# 3. Identifies matching memory paths (e.g., Tokyo Tech Conference)
# 4. Deletes those memories: /delete profile.travel.japan.2024.*
# 5. Creates commit: "Removed Japan 2024 memories"

# User queries to verify deletion worked
await client.execute("Please recall what did I do in Japan in 2024")
# Behind the scenes:
# 1. Searches for Japan 2024 memories: /search "Japan 2024"
# 2. No results found in test branch (successfully deleted)
# Response: "No memories found about Japan in 2024"

# User wants to discard all test changes
await client.execute("OK, now I am done, I want to go back to the time before I say 'help me to test the memory ...'")
# Behind the scenes:
# 1. Identifies the commit hash from before the test branch was created
# 2. Switches back to main branch: /branch switch main
# 3. Optionally deletes test branch: /branch delete test-environment-[timestamp]
# 4. Resets to the saved commit: /timeline go [saved-commit-hash]
# All test operations are completely reversed!

# User verifies original state is restored
await client.execute("Now, please recall what did I do in Japan in 2024")
# Behind the scenes:
# 1. Searches in main branch: /search "Japan 2024"
# 2. Returns original results (2024 memories that were "deleted" only in test branch)
# Response: "You attended Tokyo Tech Conference in March 2024, visited Mount Fuji..."
# The deletion only happened in the test branch - main branch still has everything!
```

### What Makes This Possible

**Version Control Magic:**
- Every operation creates an immutable commit
- Branches provide isolated environments
- Time travel allows instant recovery
- No operation is truly destructive

**Natural Language Understanding:**
- "help me to test" → Create safe testing branch
- "I want to forget" → Delete operations
- "go back to the time before" → Time travel to specific commit
- "now I am done" → Cleanup and restore

**Safety Guarantees:**
- Test operations never affect main branch
- All changes are reversible
- Complete audit trail maintained
- Cryptographic integrity preserved

This example shows why **version control is the foundation** that enables confident natural language interaction - users can experiment freely knowing they can always recover.

## LLM Ecosystem Integration

### AI Development Tools

The natural language interface creates unprecedented opportunities for AI-powered development tools:

**Claude Code, Cursor, GitHub Copilot Integration:**
```python
# AI coding assistants can directly use Memoir
client = connect("cloud://team/ai-development")

# Store patterns they discover
await client.execute("Remember that React hooks pattern fixes the useEffect infinite loop")

# Query solutions they've seen before  
await client.execute("What solutions work for Python import errors?")

# Share knowledge across development sessions
await client.execute("What debugging approaches worked for this team last month?")
```

**Key Benefits for AI Tools:**
- **Zero Integration Friction**: No API learning curve for LLM tools
- **Self-Discovery**: `ability()` method reveals capabilities for dynamic prompt generation
- **Institutional Memory**: Build knowledge bases across projects
- **Pattern Recognition**: Store and retrieve successful debugging patterns
- **Team Learning**: Share solutions across human and AI developers
- **Context Persistence**: Maintain debugging context across sessions

**Ecosystem Advantages:**
1. **Universal Interface**: Any LLM can integrate without custom API learning
2. **Self-Documenting**: Natural language makes integration obvious
3. **Git-Like Safety**: Version control enables confident experimentation (just like AI coding tools with Git)
4. **Collaborative Intelligence**: Human and AI debugging knowledge combined
5. **Continuous Learning**: Each debugging session improves the knowledge base
6. **Cross-Tool Compatibility**: Same memory accessible by different AI tools

### Revolutionary Impact on AI Development Ecosystem

The natural language interface creates a **game-changing paradigm** where Memoir becomes immediately accessible to any LLM-based tool without requiring custom SDK development, API documentation learning, or integration complexity.

**Transformative Use Cases:**

**AI Coding Assistants Integration:**
- **Claude Code**: Store/retrieve debugging patterns naturally
- **GitHub Copilot**: Query solutions from team knowledge base
- **Cursor**: Maintain context across development sessions  
- **v0.dev**: Remember successful UI patterns and components

**Agent Development & Debugging:**
```python
# Any AI tool can easily debug agents
await client.execute("Remember this agent failed because of rate limiting on OpenAI API")
await client.execute("What rate limiting solutions have worked before?")
await client.execute("Store the backoff strategy that fixed the timeout issue")
```

**Institutional Knowledge Building:**
- **Team Learning**: AI-discovered solutions shared across teams
- **Pattern Recognition**: AI tools identify and store successful patterns
- **Continuous Improvement**: Each debugging session improves knowledge base
- **Cross-Project Learning**: Insights from one project help others

**Collaborative Intelligence:**
- **Human + AI**: Both contribute to same knowledge base  
- **Tool Interoperability**: Claude Code discoveries help GitHub Copilot users
- **Session Continuity**: Start debugging in one tool, continue in another

**Ecosystem Network Effects:**
1. **Zero Barrier Integration**: LLM tools integrate in minutes, not weeks
2. **Self-Improving System**: More usage = better suggestions
3. **Universal Compatibility**: Same interface for any AI development tool
4. **Compound Intelligence**: Combined knowledge exceeds individual capabilities

**Strategic Advantage:** Creates a flywheel effect where more AI tools integrate → more knowledge accumulated → better assistance → more adoption → ecosystem growth.

**Result**: Memoir becomes the **central nervous system** for AI-powered development, enabling unprecedented collaboration between human developers, AI coding assistants, and debugging tools.

## Error Handling

```python
from memoir.client.exceptions import (
    MemoirConnectionError,
    MemoirAuthenticationError, 
    MemoirTimeoutError
)

try:
    client = connect("cloud://my-org/store")
    await client.connect()
    result = await client.execute("Remember something important")
except MemoirConnectionError as e:
    print(f"Connection failed: {e}")
except MemoirAuthenticationError as e:
    print(f"Authentication failed: {e}")
```

## Environment Configuration

```python
# Environment variables
MEMOIR_STORE = "cloud://my-org/production"
MEMOIR_CLOUD_API_KEY = "mk_live_..."
MEMOIR_LOCAL_PATH = "~/.memoir/default"

# Usage
import os
client = connect(os.getenv("MEMOIR_STORE", "local:~/.memoir/default"))
```

## Benefits

### vs Traditional APIs

| Aspect | Traditional API | Memoir Client |
|--------|----------------|---------------|
| **Methods** | 15+ specific methods | 5 total methods |
| **Learning** | Memorize method names | Describe in English |
| **Documentation** | Method references | Natural examples |
| **Flexibility** | Fixed signatures | Natural variations |
| **Future-proof** | New features = new methods | Automatic via NL |

### Key Advantages

✅ **Minimal**: 5 methods vs 15+ traditional APIs  
✅ **Natural**: English commands vs method memorization  
✅ **Self-Discoverable**: LLM tools can learn capabilities dynamically  
✅ **Universal**: Same interface across all backends  
✅ **Future-proof**: New features work automatically  
✅ **Simple**: Just describe what you want to do  

## Summary

The Memoir Client API revolutionizes memory store interaction by replacing complex method-based APIs with simple natural language commands. Instead of learning 15+ specific methods, developers just describe what they want to accomplish.

**Core Philosophy**: Intent-based computing where you describe the goal, not the implementation.

**Result**: Memory operations become as intuitive as having a conversation while maintaining enterprise-grade power and flexibility.
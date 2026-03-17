# Memoir TUI Specification

A terminal user interface for memoir with the same functionality as the web UI, designed with Claude Code / OpenClaw styling conventions.

## Goals

1. **Feature parity** with web UI (all slash commands)
2. **Maximum code reuse** from existing Python handlers
3. **Claude Code / OpenClaw style** - minimal, elegant terminal experience
4. **Fast and responsive** - direct Python calls, no HTTP overhead

---

## Architecture Overview

### Current UI Architecture (Web)

```
┌─────────────────────────────────────────────────────────────────┐
│                         Web Browser                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  ui.html + static/js/*.js                                   ││
│  │  - Command parsing (handleCommand)                          ││
│  │  - UI rendering (D3.js tree, modals)                        ││
│  │  - HTTP API calls                                           ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │ HTTP
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       server.py (HTTP)                           │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  handlers/                                                   ││
│  │  ├── store_handler.py    (store ops)                        ││
│  │  ├── memory_handler.py   (remember/forget/recall)           ││
│  │  ├── branch_handler.py   (git ops)                          ││
│  │  ├── crypto_handler.py   (proof/verify/blame)               ││
│  │  └── utils.py            (data extraction)                  ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Core memoir library                           │
│  ProllyTreeStore, IntelligentClassifier, SearchEngine, etc.     │
└─────────────────────────────────────────────────────────────────┘
```

### Proposed TUI Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Terminal                                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  tui/app.py (Textual App)                                   ││
│  │  - Terminal UI rendering                                    ││
│  │  - Command input handling                                   ││
│  │  - Rich text output                                         ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │ Direct Python calls
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    services/ (NEW - Shared Layer)                │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  services/                                                   ││
│  │  ├── store_service.py    (store operations)                 ││
│  │  ├── memory_service.py   (remember/forget/recall)           ││
│  │  ├── branch_service.py   (git operations)                   ││
│  │  ├── crypto_service.py   (proof/verify/blame)               ││
│  │  └── command_processor.py (command parsing & dispatch)      ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌──────────────────────────┐    ┌──────────────────────────┐
│  ui/handlers/ (HTTP)      │    │  tui/app.py (Terminal)   │
│  Thin HTTP adapter layer  │    │  Direct service calls    │
└──────────────────────────┘    └──────────────────────────┘
```

**Key Insight**: Extract business logic from `handlers/*.py` into `services/*.py`, then both HTTP handlers and TUI can use the same services.

---

## Directory Structure

```
src/memoir/
├── services/                      # NEW: Shared business logic layer
│   ├── __init__.py
│   ├── store_service.py           # Store operations
│   ├── memory_service.py          # Memory operations
│   ├── branch_service.py          # Git/branch operations
│   ├── crypto_service.py          # Cryptographic operations
│   └── command_processor.py       # Command parsing & dispatch
│
├── tui/                           # NEW: Terminal UI
│   ├── __init__.py
│   ├── app.py                     # Main Textual application
│   ├── screens/
│   │   ├── __init__.py
│   │   ├── main_screen.py         # Primary interface
│   │   ├── help_screen.py         # Help overlay
│   │   └── branch_screen.py       # Branch management modal
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── command_input.py       # Command line input
│   │   ├── output_panel.py        # Output display
│   │   ├── tree_view.py           # Memory tree visualization
│   │   ├── status_bar.py          # Connection/branch status
│   │   └── timeline_view.py       # Timeline visualization
│   ├── styles/
│   │   └── memoir.tcss            # Textual CSS styling
│   └── themes/
│       ├── claude.py              # Claude Code theme
│       └── default.py             # Default theme
│
├── ui/                            # EXISTING: Web UI (refactored)
│   ├── handlers/
│   │   ├── api_handler.py         # Thin HTTP adapter
│   │   ├── store_handler.py       # Delegates to store_service
│   │   ├── memory_handler.py      # Delegates to memory_service
│   │   ├── branch_handler.py      # Delegates to branch_service
│   │   └── crypto_handler.py      # Delegates to crypto_service
│   └── ...
```

---

## TUI Design (Claude Code Style)

### Main Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ memoir ─ /tmp/my-memory-store                          main ● 3 commits    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ╭─ Memory Tree ─────────────────────────────────────────────────────────╮  │
│  │ ▼ profile                                                             │  │
│  │   ▼ personal                                                          │  │
│  │     ├── name: "John Doe"                                              │  │
│  │     └── preferences: {...}                                            │  │
│  │   ▶ professional                                                      │  │
│  │ ▼ context                                                             │  │
│  │   └── current: {...}                                                  │  │
│  │ ▶ timeline                                                            │  │
│  ╰───────────────────────────────────────────────────────────────────────╯  │
│                                                                             │
│  ╭─ Output ──────────────────────────────────────────────────────────────╮  │
│  │ ✓ Connected to /tmp/my-memory-store                                   │  │
│  │ ✓ Loaded 42 memories across 8 namespaces                              │  │
│  │                                                                       │  │
│  │ > /remember I love hiking in the mountains on weekends                │  │
│  │                                                                       │  │
│  │ ✓ Classified: profile.personal.interests.outdoor                     │  │
│  │   Confidence: 0.92                                                    │  │
│  │   Commit: abc1234                                                     │  │
│  │   Timing: 1.2s (classify: 0.8s, store: 0.3s, commit: 0.1s)            │  │
│  ╰───────────────────────────────────────────────────────────────────────╯  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ > /remember _                                                     [↑↓] [?] │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Color Scheme (Claude Code Inspired)

```python
# memoir/tui/themes/claude.py
CLAUDE_THEME = {
    "background": "#1a1a2e",          # Deep dark blue
    "foreground": "#e0e0e0",          # Soft white
    "accent": "#ff6b35",              # Orange accent (memoir brand)
    "success": "#4ade80",             # Green
    "error": "#ef4444",               # Red
    "warning": "#fbbf24",             # Yellow
    "info": "#60a5fa",                # Blue
    "muted": "#6b7280",               # Gray
    "border": "#374151",              # Dark gray
    "highlight": "#2d2d44",           # Slightly lighter background
    "command": "#a78bfa",             # Purple for commands
    "path": "#34d399",                # Teal for memory paths
}
```

### Key UI Elements

1. **Header Bar**: Store path, current branch, commit count
2. **Memory Tree Panel**: Collapsible tree view of memories
3. **Output Panel**: Command results, logs, notifications
4. **Command Input**: Slash command entry with history
5. **Status Bar**: Quick actions, keyboard shortcuts

---

## Commands (Same as Web UI)

### Connection & Store Management
| Command | Aliases | Description |
|---------|---------|-------------|
| `/connect <path>` | `/con`, `/conn` | Connect to memory store |
| `/new <path>` | `/create` | Create new memory store |
| `/demo` | - | Load demo data |
| `/refresh` | `/ref` | Refresh current connection |

### Memory Operations
| Command | Aliases | Description |
|---------|---------|-------------|
| `/remember <content>` | `/rem` | Classify and store content |
| `/forget <key>` | `/del` | Delete a memory |
| `/recall <query>` | `/search` | Search memories |

### Git & Version Control
| Command | Aliases | Description |
|---------|---------|-------------|
| `/branch [list\|create\|delete] [args]` | `/br` | Branch operations |
| `/checkout <target>` | `/co` | Switch branch/commit |
| `/merge <source>` | - | Merge branches |
| `/commits` | `/log` | Show commit history |
| `/branches` | - | List all branches |

### Cryptographic Operations
| Command | Aliases | Description |
|---------|---------|-------------|
| `/proof <path>` | - | Generate SHA-256 proof |
| `/verify [proof]` | - | Verify proof integrity |
| `/blame <key>` | - | Show blame history |

### Time & Timeline
| Command | Aliases | Description |
|---------|---------|-------------|
| `/time-travel <target>` | `/tt` | Travel to commit/date |
| `/timeline [event]` | `/tl` | Show/add timeline events |
| `/location [place]` | `/loc` | Show/add location events |

### UI & Navigation
| Command | Aliases | Description |
|---------|---------|-------------|
| `/help` | `/h`, `?` | Show help |
| `/clear` | `/cls`, `Ctrl+L` | Clear output |
| `/quit` | `/exit`, `q` | Exit TUI |
| `/code` | - | Show Python integration code |
| `/diff [c1] [c2]` | `/d` | Compare commits |
| `/summarize [type]` | - | Generate summary |

---

## Services Layer (Code Reuse)

### Example: memory_service.py

```python
"""
Memory service - shared business logic for memory operations.
Used by both HTTP handlers and TUI.
"""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from memoir.classifier.intelligent import IntelligentClassifier
from memoir.store.prolly_adapter import ProllyTreeStore


@dataclass
class RememberResult:
    """Result of a remember operation."""
    success: bool
    key: str
    keys: list[str]  # All paths for multi-label
    confidence: float
    reasoning: str
    commit_hash: Optional[str]
    timings: dict[str, float]
    timeline_events: Optional[list] = None
    location_events: Optional[list] = None
    error: Optional[str] = None


@dataclass
class RecallResult:
    """Result of a recall/search operation."""
    success: bool
    memories: list[dict]
    query: str
    timing_ms: float
    error: Optional[str] = None


class MemoryService:
    """Service for memory operations."""

    def __init__(self, store_path: str):
        self.store_path = store_path
        self._store: Optional[ProllyTreeStore] = None
        self._classifier: Optional[IntelligentClassifier] = None

    async def remember(
        self,
        content: str,
        namespace: str = "default"
    ) -> RememberResult:
        """Classify and store content in memory."""
        timings = {}
        start = time.time()

        try:
            # Step 1: Initialize store
            t1 = time.time()
            store = self._get_store()
            timings["store_init"] = time.time() - t1

            # Step 2: Classify content
            t2 = time.time()
            classifier = self._get_classifier()
            result = await classifier.classify_input(content)
            timings["classification"] = time.time() - t2

            # Step 3: Store memory
            t3 = time.time()
            # ... storage logic ...
            timings["storage"] = time.time() - t3

            timings["total"] = time.time() - start

            return RememberResult(
                success=True,
                key=result.path,
                keys=result.paths or [result.path],
                confidence=result.confidence,
                reasoning=f"Classified as {result.path}",
                commit_hash="abc123",  # actual commit
                timings=timings,
                timeline_events=result.timeline_events,
                location_events=result.location_events,
            )

        except Exception as e:
            return RememberResult(
                success=False,
                key="",
                keys=[],
                confidence=0.0,
                reasoning="",
                commit_hash=None,
                timings=timings,
                error=str(e),
            )

    async def recall(self, query: str) -> RecallResult:
        """Search memories."""
        start = time.time()
        # ... search logic ...
        return RecallResult(
            success=True,
            memories=[],
            query=query,
            timing_ms=(time.time() - start) * 1000,
        )

    async def forget(self, key: str, namespace: str = "default") -> bool:
        """Delete a memory."""
        # ... delete logic ...
        return True

    def _get_store(self) -> ProllyTreeStore:
        if self._store is None:
            self._store = ProllyTreeStore(
                path=self.store_path,
                enable_versioning=True,
                auto_commit=True,
            )
        return self._store

    def _get_classifier(self) -> IntelligentClassifier:
        if self._classifier is None:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
            self._classifier = IntelligentClassifier(llm=llm)
        return self._classifier
```

### Command Processor

```python
"""
Command processor - parses and dispatches commands.
Shared between Web UI and TUI.
"""

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class CommandResult:
    """Result of command execution."""
    success: bool
    output: str
    data: Optional[Any] = None
    error: Optional[str] = None


class CommandProcessor:
    """Parses and executes slash commands."""

    # Command aliases
    ALIASES = {
        "/con": "/connect",
        "/conn": "/connect",
        "/rem": "/remember",
        "/del": "/forget",
        "/create": "/new",
        "/ref": "/refresh",
        "/h": "/help",
        "/cls": "/clear",
        "/br": "/branch",
        "/co": "/checkout",
        "/log": "/commits",
        "/tt": "/time-travel",
        "/tl": "/timeline",
        "/loc": "/location",
        "/d": "/diff",
    }

    def __init__(self, services: "ServiceContainer"):
        self.services = services
        self._handlers: dict[str, Callable] = {}
        self._register_handlers()

    def _register_handlers(self):
        """Register command handlers."""
        self._handlers = {
            "/connect": self._handle_connect,
            "/new": self._handle_new,
            "/remember": self._handle_remember,
            "/forget": self._handle_forget,
            "/recall": self._handle_recall,
            "/refresh": self._handle_refresh,
            "/branch": self._handle_branch,
            "/checkout": self._handle_checkout,
            "/merge": self._handle_merge,
            "/commits": self._handle_commits,
            "/branches": self._handle_branches,
            "/proof": self._handle_proof,
            "/verify": self._handle_verify,
            "/blame": self._handle_blame,
            "/time-travel": self._handle_time_travel,
            "/timeline": self._handle_timeline,
            "/location": self._handle_location,
            "/diff": self._handle_diff,
            "/summarize": self._handle_summarize,
            "/help": self._handle_help,
            "/clear": self._handle_clear,
            "/demo": self._handle_demo,
            "/code": self._handle_code,
        }

    def parse(self, input_text: str) -> tuple[str, list[str]]:
        """Parse command and arguments."""
        parts = input_text.strip().split(maxsplit=1)
        if not parts:
            return "", []

        cmd = parts[0].lower()
        cmd = self.ALIASES.get(cmd, cmd)

        args = parts[1].split() if len(parts) > 1 else []
        return cmd, args

    async def execute(self, input_text: str) -> CommandResult:
        """Execute a command."""
        cmd, args = self.parse(input_text)

        if not cmd.startswith("/"):
            # Natural language query - treat as recall
            return await self._handle_recall(input_text)

        handler = self._handlers.get(cmd)
        if not handler:
            return CommandResult(
                success=False,
                output=f"Unknown command: {cmd}",
                error=f"Use /help to see available commands",
            )

        return await handler(args)

    async def _handle_remember(self, args: list[str]) -> CommandResult:
        content = " ".join(args)
        if not content:
            return CommandResult(False, "Usage: /remember <content>")

        result = await self.services.memory.remember(content)
        if result.success:
            output = f"✓ Classified: {result.key}\n"
            output += f"  Confidence: {result.confidence:.2f}\n"
            output += f"  Commit: {result.commit_hash}"
            return CommandResult(True, output, data=result)
        return CommandResult(False, result.error or "Failed")

    # ... other handlers ...
```

---

## Textual App Implementation

### Main Application

```python
"""
Memoir TUI - Terminal User Interface
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Header, Footer

from memoir.tui.screens.main_screen import MainScreen
from memoir.tui.screens.help_screen import HelpScreen


class MemoirTUI(App):
    """Memoir Terminal User Interface."""

    TITLE = "memoir"
    SUB_TITLE = "Git for AI Memory"
    CSS_PATH = "styles/memoir.tcss"

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("?", "help", "Help"),
        Binding("ctrl+l", "clear", "Clear"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, store_path: str = None):
        super().__init__()
        self.store_path = store_path

    def compose(self) -> ComposeResult:
        yield Header()
        yield MainScreen(store_path=self.store_path)
        yield Footer()

    def action_help(self):
        self.push_screen(HelpScreen())

    def action_clear(self):
        self.query_one(MainScreen).clear_output()


def main():
    """Entry point for TUI."""
    import argparse

    parser = argparse.ArgumentParser(description="Memoir TUI")
    parser.add_argument("--connect", "-c", help="Store path to connect to")
    args = parser.parse_args()

    app = MemoirTUI(store_path=args.connect)
    app.run()


if __name__ == "__main__":
    main()
```

### Textual CSS Styling

```css
/* memoir/tui/styles/memoir.tcss */

/* Claude Code inspired dark theme */
Screen {
    background: #1a1a2e;
}

Header {
    background: #16213e;
    color: #e0e0e0;
}

Footer {
    background: #16213e;
}

/* Memory tree panel */
#tree-panel {
    border: round #374151;
    background: #1a1a2e;
    padding: 1;
    height: 40%;
}

#tree-panel .tree--label {
    color: #34d399;  /* Teal for paths */
}

#tree-panel .tree--cursor {
    background: #2d2d44;
}

/* Output panel */
#output-panel {
    border: round #374151;
    background: #1a1a2e;
    padding: 1;
    height: 1fr;
}

.output--success {
    color: #4ade80;
}

.output--error {
    color: #ef4444;
}

.output--info {
    color: #60a5fa;
}

.output--command {
    color: #a78bfa;
}

.output--path {
    color: #34d399;
}

/* Command input */
#command-input {
    dock: bottom;
    height: 3;
    border: round #374151;
    background: #16213e;
}

#command-input Input {
    background: transparent;
    border: none;
}

#command-input .input--cursor {
    color: #ff6b35;  /* Orange accent */
}

/* Status bar */
#status-bar {
    dock: top;
    height: 1;
    background: #16213e;
    padding: 0 1;
}

.status--connected {
    color: #4ade80;
}

.status--disconnected {
    color: #6b7280;
}

.status--branch {
    color: #a78bfa;
}

/* Notifications */
.notification {
    layer: notification;
    width: 50;
    height: auto;
    padding: 1 2;
    border: round $accent;
}

.notification--success {
    border: round #4ade80;
}

.notification--error {
    border: round #ef4444;
}
```

---

## Implementation Phases

### Phase 1: Services Layer Extraction (Foundation)
1. Create `services/` directory
2. Extract `MemoryService` from `memory_handler.py`
3. Extract `BranchService` from `branch_handler.py`
4. Extract `CryptoService` from `crypto_handler.py`
5. Extract `StoreService` from `store_handler.py`
6. Create `CommandProcessor` for command parsing
7. Update HTTP handlers to use services (thin adapters)
8. Add unit tests for services

### Phase 2: Basic TUI
1. Set up Textual app structure
2. Implement command input widget
3. Implement output panel
4. Implement status bar
5. Wire up core commands: `/connect`, `/remember`, `/forget`, `/recall`
6. Add command history (up/down arrows)

### Phase 3: Tree Visualization
1. Implement tree view widget for memories
2. Add collapsible/expandable nodes
3. Add selection and navigation
4. Show memory details on selection

### Phase 4: Git Operations
1. Implement `/branch`, `/checkout`, `/merge`
2. Implement `/commits` with scrollable list
3. Implement `/time-travel`
4. Show branch/commit in status bar

### Phase 5: Advanced Features
1. Implement `/proof`, `/verify`, `/blame`
2. Implement `/timeline`, `/location`
3. Implement `/diff` with side-by-side view
4. Implement `/summarize`

### Phase 6: Polish
1. Help screen with command reference
2. Keyboard shortcuts
3. Themes (Claude, default)
4. Error handling and edge cases
5. Performance optimization

---

## Dependencies

```toml
# pyproject.toml additions
[project.optional-dependencies]
tui = [
    "textual>=3.0.0",
    "rich>=13.0.0",
]

[project.scripts]
memoir-tui = "memoir.tui.app:main"
```

---

## Usage Examples

```bash
# Start TUI
memoir-tui

# Start TUI and connect to store
memoir-tui --connect /tmp/my-memory-store

# Or use Python module
python -m memoir.tui

# Using make
make tui                    # Start TUI
make tui-dev               # Start with dev mode (auto-reload)
```

---

## Comparison: Web UI vs TUI

| Feature | Web UI | TUI |
|---------|--------|-----|
| Memory Tree | D3.js interactive | Textual TreeView |
| Command Input | HTML input | Input widget |
| Output | DOM manipulation | Rich text panel |
| Notifications | Toast system | Textual notifications |
| Timeline | Visual timeline | Text-based list |
| Diff View | HTML side-by-side | Terminal diff |
| Proof Generation | Modal popup | Inline output |
| Branch Switching | Dropdown | Command or modal |
| Code Sharing | HTTP API | Services layer |

---

## Future Enhancements

1. **Split pane layout** - Tree on left, output on right
2. **Multiple tabs** - Multiple store connections
3. **Watch mode** - Auto-refresh on changes
4. **Export/import** - Save/load sessions
5. **Plugin system** - Custom commands
6. **Remote stores** - Connect via SSH

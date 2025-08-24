# Memoir UI Visualization

Interactive visualization tool for exploring Memoir memory stores with Git-like versioning.

## Quick Start

1. **Initialize sample data:**
   ```bash
   python src/memoir/ui/initialize_sample_store.py
   ```
   This creates a sample memory store at `/tmp/memoir_ui_store` with branches and commits.

2. **Start the UI server:**
   ```bash
   python src/memoir/ui/serve_ui.py
   ```
   Opens on http://localhost:8080

3. **Connect to a memory store:**
   In the UI search box, type:
   ```
   /connect /tmp/memoir_ui_store
   ```
   Then press Enter.

## Available Commands

### Working Commands
- `/connect <path>` - Connect to a memory store at the specified path
- `/refresh` - Refresh the current connection  
- `/demo` - Show original demo data visualization
- `/repo` - Show repository information and Git details
- `/code` - Show Python LangGraph integration code example with syntax highlighting
- `/help` - Show all available commands

### Planned Commands (Coming Soon)
- `/share <path>` - Share memory or branch with others
- `/summarize [path]` - Generate summary of memories at path
- `/remember <content>` - Add memory with smart classification
- `/forget <pattern>` - Remove memories matching pattern
- `/time-travel <commit>` - View memories at specific commit
- `/blame <path>` - Show history of memory changes
- `/timeline [filter]` - Show chronological memory timeline
- `/location <place>` - Filter memories by location context
- `/what-if <scenario>` - Simulate hypothetical memory scenarios
- `/never-mind` - Undo last operation or clear current context
- `/merge <branch>` - Merge memory branch into current branch
- `/what-happened [timeframe]` - Show recent memory changes and activity
- `/organize [pattern]` - Auto-organize and restructure memories
- `/sign-in [provider]` - Sign in to sync memories across devices
- `/sign-out` - Sign out and clear session data
- `/upgrade` - Upgrade to premium features
- `/portal [destination]` - Open web portal or external integrations
- `/test [suite]` - Run memory system tests and diagnostics
- `/prompt <template>` - Create and manage AI prompt templates
- `/encrypt [method]` - Encrypt memory data with security options

## Features

- **Git-like visualization**: See branches, commits, and memory structure
- **Real-time connection**: Connect to any local memory store
- **Interactive exploration**: Click on nodes to explore memory contents
- **Search functionality**: Search through memory paths
- **Branch switching**: View different branches and their commits
- **Syntax highlighting**: Python code snippets displayed with full syntax highlighting
- **Code integration examples**: Use `/code` command to see LangGraph integration examples with proper highlighting

## Files

- `visualization.html` - Main UI interface with D3.js visualization and syntax highlighting
- `initialize_sample_store.py` - Creates sample data with branches
- `memory_store_reader.py` - Reads memory store data as JSON
- `serve_ui.py` - HTTP server for the UI

## Custom Memory Store

To create your own memory store with custom data:

```bash
python src/memoir/ui/initialize_sample_store.py --store-path /path/to/your/store
```

Then connect to it in the UI:
```
/connect /path/to/your/store
```

## Requirements

- Python 3.8+
- Memoir package installed
- Modern web browser (Chrome, Firefox, Safari, Edge)

## Technical Details

### Syntax Highlighting
The UI uses [highlight.js](https://highlightjs.org/) for syntax highlighting of Python code:
- GitHub Dark theme for consistency with the UI design
- Custom color scheme optimized for dark backgrounds
- Supports Python-specific syntax elements (decorators, async/await, type hints)

### Libraries Used
- **D3.js v7**: Force-directed graph visualization
- **Highlight.js v11.9**: Syntax highlighting for code snippets
- **Inter & JetBrains Mono**: Typography for UI and code display

## Notes

- The UI currently shows demo data for the tree visualization
- Full memory tree rendering from real data will be implemented in the next iteration
- Clicking on commits and branches updates the UI but uses mock data for now

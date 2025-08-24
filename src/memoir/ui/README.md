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

- `/connect <path>` - Connect to a memory store at the specified path
- `/refresh` - Refresh the current connection
- `/help` - Show available commands

## Features

- **Git-like visualization**: See branches, commits, and memory structure
- **Real-time connection**: Connect to any local memory store
- **Interactive exploration**: Click on nodes to explore memory contents
- **Search functionality**: Search through memory paths
- **Branch switching**: View different branches and their commits

## Files

- `visualization_mockup.html` - Main UI interface
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

## Notes

- The UI currently shows demo data for the tree visualization
- Full memory tree rendering from real data will be implemented in the next iteration
- Clicking on commits and branches updates the UI but uses mock data for now

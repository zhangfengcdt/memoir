# Memoir UI - Memory Visualization Interface

A modern web interface for visualizing Memoir's Git-like memory history and hierarchical structure.

## 🎯 Features

- **Git-like History Timeline**: Browse commits with clickable timeline navigation
- **Interactive Memory Tree**: Explore hierarchical taxonomy structure with memory counts
- **Force-Directed Graph View**: Alternative visualization of memory relationships  
- **Real-time Search**: Filter memory paths and content
- **Memory Details Panel**: Inspect individual memories with confidence scores
- **Branch Support**: Switch between different memory branches
- **Interactive Input**: Add memories and query existing ones
- **Zoom & Pan**: Full zoom and pan controls for graph exploration
- **Dark Modern UI**: Clean, responsive interface optimized for memory exploration

## 🚀 Quick Start

### Simple Runner (Recommended)

```bash
# From the ui directory
cd src/memoir/ui

# Install dependencies
pip install fastapi uvicorn

# Run the visualization service with sample data
python run_visualization.py
```

Then open http://127.0.0.1:8000 in your browser.

### Manual Setup

```bash
# Install dependencies  
pip install fastapi uvicorn

# Set the data path (optional)
export MEMOIR_STORE_PATH="/tmp/memoir_visualization_data"

# Start the service from the ui directory
cd src/memoir/ui
uvicorn visualization_service:app --host 127.0.0.1 --port 8000 --reload
```

## 🏗️ Architecture

### Frontend (`visualization_mockup.html`)
- **Timeline Panel**: Git commit history with branch selector
- **Tree View**: Hierarchical memory taxonomy with click interactions
- **Graph View**: D3.js force-directed graph of memory relationships
- **Details Panel**: Expandable memory details with metadata
- **Search & Filtering**: Real-time path and content filtering
- **Input Bar**: Interactive input for queries and adding memories

### Backend (`visualization_service.py`)
- **FastAPI Service**: RESTful API for memory data access
- **Git Integration**: Direct git command execution for commit history
- **Memory Manager**: Integration with Memoir's ProllyTree storage
- **Real-time Updates**: Live memory structure updates

### Runner (`run_visualization.py`)
- **Sample Data**: Creates demonstration memory dataset
- **Path Configuration**: Sets up proper import paths
- **Service Launch**: Starts uvicorn server with configuration

## 📡 API Endpoints

- `GET /` - Serve visualization frontend
- `GET /api/branches` - List available memory branches
- `GET /api/commits?branch=main&limit=50` - Get commit history
- `GET /api/structure?commit_id=abc123` - Get memory taxonomy structure
- `GET /api/memories/{path}` - Get detailed memory info for path
- `GET /api/search?query=python` - Search memories (planned)
- `GET /health` - Service health check
- `GET /static/{filename}` - Serve static assets (logo, etc.)

## 🎨 Interactive Features

### Memory Input Bar
- **Smart Detection**: Automatically detects queries vs statements
- **Dual Actions**: Search icon for queries, plus icon for adding memories
- **Suggestions**: Shows example queries and actions
- **Visual Feedback**: Button highlights and success notifications

### Graph Navigation
- **Zoom Controls**: Zoom in, zoom out, and reset view buttons
- **Pan Support**: Click and drag to pan around the graph
- **Watermark**: "MEMOIR" branding with monospace font
- **Node Interactions**: Click nodes to highlight connections

## 🔧 File Structure

```
src/memoir/ui/
├── __init__.py                  # Package initialization
├── README.md                    # This documentation
├── visualization_mockup.html    # Main frontend interface
├── visualization_service.py     # FastAPI backend service
├── run_visualization.py        # Runner script with sample data
└── static/                     # Static assets
    └── memoir.png              # Logo file
```

## 🛠️ Development Notes

- **Data Storage**: Uses `/tmp/memoir_visualization_data` to avoid cluttering project
- **Import Paths**: Configured to work from the ui subdirectory
- **Static Files**: Served via FastAPI StaticFiles mount
- **Logo Setup**: Place memoir.png in static/ directory for branding

## 📱 Mobile Support

The interface is responsive and includes:
- Adjusted input bar sizing for mobile
- Touch-friendly zoom and pan controls
- Responsive layout for smaller screens
- Optimized font sizes and spacing

## 🐛 Troubleshooting

**Service won't start**
- Check that FastAPI and uvicorn are installed: `pip install fastapi uvicorn`
- Verify you're running from the ui directory
- Check for port conflicts (default: 8000)

**Empty visualization**
- Run from ui directory: `python run_visualization.py` 
- Verify the Memoir packages are installed and importable
- Check the service logs for initialization errors

**Logo not showing**
- Ensure memoir.png exists in the static/ directory
- Check browser console for 404 errors on static files
- Verify static files are being served at `/static/`
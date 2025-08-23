"""
Memory Visualization Service

A FastAPI service for visualizing Memoir's Git-like memory history and structure.
Provides REST endpoints for the memory visualization frontend.
"""

import asyncio
import logging
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from memoir.core.memory import ProllyTreeMemoryStoreManager
from memoir.store.prolly_adapter import ProllyTreeStore


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Data Models
class CommitInfo(BaseModel):
    """Represents a commit in the memory history."""
    id: str
    message: str
    timestamp: float
    author: str
    branch: str
    parent_commits: List[str] = []


class MemoryNode(BaseModel):
    """Represents a node in the memory taxonomy tree."""
    path: str
    name: str
    memory_count: int
    children: List["MemoryNode"] = []
    memories: List[Dict[str, Any]] = []
    last_updated: float


class MemoryDetails(BaseModel):
    """Detailed memory information for a specific path."""
    path: str
    memories: List[Dict[str, Any]]
    total_count: int
    confidence_avg: float
    first_timestamp: float
    last_timestamp: float


class BranchInfo(BaseModel):
    """Information about a memory branch."""
    name: str
    head_commit: str
    commit_count: int
    last_updated: float


# FastAPI App
app = FastAPI(
    title="Memoir Memory Visualizer",
    description="Visualize Git-like memory history and structure",
    version="1.0.0",
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Global memory manager instance
memory_manager: Optional[ProllyTreeMemoryStoreManager] = None


class VisualizationService:
    """Service class for memory visualization operations."""
    
    def __init__(self, memory_store_path: str):
        """Initialize the visualization service."""
        self.store_path = Path(memory_store_path)
        self.memory_manager = None
        self._initialize_memory_manager()
    
    def _initialize_memory_manager(self):
        """Initialize the memory manager with a ProllyTree store."""
        try:
            # Create store with versioning enabled
            prolly_store = ProllyTreeStore(
                path=str(self.store_path),
                enable_versioning=True,
                auto_commit=False,  # Manual commit control for visualization
                cache_size=10000
            )
            
            # Initialize memory manager
            self.memory_manager = ProllyTreeMemoryStoreManager(
                prolly_store=prolly_store,
                enable_versioning=True,
                auto_commit=False
            )
            
            logger.info(f"Memory manager initialized at {self.store_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize memory manager: {e}")
            raise
    
    async def get_commit_history(self, branch: str = "main", limit: int = 50) -> List[CommitInfo]:
        """Get commit history for a branch."""
        try:
            # Get git log using subprocess since ProllyTree uses git internally
            git_dir = self.store_path / ".git"
            if not git_dir.exists():
                return []
            
            cmd = [
                "git", "log", 
                f"--max-count={limit}",
                "--pretty=format:%H|%s|%at|%an",
                branch
            ]
            
            result = subprocess.run(
                cmd,
                cwd=self.store_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            commits = []
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                    
                parts = line.split('|', 3)
                if len(parts) >= 4:
                    commit_id, message, timestamp, author = parts
                    commits.append(CommitInfo(
                        id=commit_id[:8],  # Short hash
                        message=message,
                        timestamp=float(timestamp),
                        author=author,
                        branch=branch
                    ))
            
            return commits
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Git command failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting commit history: {e}")
            return []
    
    async def get_branches(self) -> List[BranchInfo]:
        """Get list of available branches."""
        try:
            git_dir = self.store_path / ".git"
            if not git_dir.exists():
                return [BranchInfo(name="main", head_commit="", commit_count=0, last_updated=time.time())]
            
            cmd = ["git", "branch", "-v"]
            result = subprocess.run(
                cmd,
                cwd=self.store_path,
                capture_output=True,
                text=True,
                check=True
            )
            
            branches = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    # Parse branch info (format: "* branch_name commit_hash commit_message")
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        is_current = parts[0] == '*'
                        branch_name = parts[1] if is_current else parts[0]
                        head_commit = parts[2] if is_current else parts[1]
                        
                        branches.append(BranchInfo(
                            name=branch_name,
                            head_commit=head_commit[:8],
                            commit_count=1,  # Would need additional git command for accurate count
                            last_updated=time.time()
                        ))
            
            return branches
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Git branch command failed: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting branches: {e}")
            return []
    
    async def get_memory_structure(self, commit_id: Optional[str] = None) -> MemoryNode:
        """Get the memory taxonomy structure at a specific commit."""
        try:
            # For now, get current structure
            # TODO: Implement historical structure retrieval when ProllyTree supports it
            
            if not self.memory_manager:
                raise ValueError("Memory manager not initialized")
            
            # Get all memory paths from the store
            all_memories = {}
            
            # Iterate through namespaces and keys
            async for namespace_bytes, key_bytes, value_bytes in self.memory_manager.prolly_store.tree.iter():
                try:
                    namespace_str = namespace_bytes.decode('utf-8')
                    key_str = key_bytes.decode('utf-8')
                    
                    # Parse semantic path
                    if ':' in key_str:
                        path = key_str
                    else:
                        path = f"{namespace_str}:{key_str}" if namespace_str else key_str
                    
                    if path not in all_memories:
                        all_memories[path] = []
                    
                    # Decode memory content
                    import json
                    try:
                        memory_data = json.loads(value_bytes.decode('utf-8'))
                        all_memories[path].append(memory_data)
                    except json.JSONDecodeError:
                        # Handle non-JSON data
                        all_memories[path].append({
                            'content': value_bytes.decode('utf-8', errors='ignore'),
                            'timestamp': time.time()
                        })
                        
                except UnicodeDecodeError:
                    # Skip binary or corrupted data
                    continue
            
            # Build tree structure
            root = MemoryNode(
                path="root",
                name="root",
                memory_count=0,
                children=[]
            )
            
            # Group memories by taxonomy path
            path_groups = {}
            for path, memories in all_memories.items():
                # Extract semantic path parts
                if ':' in path:
                    semantic_path = path.split(':', 1)[1] if ':' in path else path
                else:
                    semantic_path = path
                
                # Group by path prefix
                if '.' in semantic_path:
                    path_parts = semantic_path.split('.')
                    for i in range(len(path_parts)):
                        partial_path = '.'.join(path_parts[:i+1])
                        if partial_path not in path_groups:
                            path_groups[partial_path] = []
                        if i == len(path_parts) - 1:  # Leaf node
                            path_groups[partial_path].extend(memories)
                else:
                    if semantic_path not in path_groups:
                        path_groups[semantic_path] = []
                    path_groups[semantic_path].extend(memories)
            
            # Build hierarchical structure
            def build_tree_recursive(base_path: str, parent: MemoryNode):
                for path, memories in path_groups.items():
                    if path.startswith(base_path) and path != base_path:
                        # Check if this is a direct child
                        relative_path = path[len(base_path):].lstrip('.')
                        if '.' not in relative_path:
                            node = MemoryNode(
                                path=path,
                                name=relative_path,
                                memory_count=len(memories),
                                memories=[
                                    {
                                        'content': m.get('content', str(m)),
                                        'timestamp': m.get('timestamp', time.time()),
                                        'confidence': m.get('confidence', 1.0)
                                    }
                                    for m in memories[:10]  # Limit for performance
                                ],
                                last_updated=max(
                                    [m.get('timestamp', time.time()) for m in memories],
                                    default=time.time()
                                )
                            )
                            parent.children.append(node)
                            build_tree_recursive(path + '.', node)
            
            # Start with main taxonomy roots
            main_roots = ['profile', 'context', 'preferences', 'system']
            for root_name in main_roots:
                if any(path.startswith(root_name) for path in path_groups.keys()):
                    root_node = MemoryNode(
                        path=root_name,
                        name=root_name,
                        memory_count=sum(
                            len(memories) for path, memories in path_groups.items() 
                            if path.startswith(root_name)
                        )
                    )
                    root.children.append(root_node)
                    build_tree_recursive(root_name + '.', root_node)
            
            return root
            
        except Exception as e:
            logger.error(f"Error getting memory structure: {e}")
            # Return empty structure on error
            return MemoryNode(path="root", name="root", memory_count=0)
    
    async def get_memory_details(self, path: str, commit_id: Optional[str] = None) -> MemoryDetails:
        """Get detailed memory information for a specific path."""
        try:
            if not self.memory_manager:
                raise ValueError("Memory manager not initialized")
            
            # Search for memories at this path
            memories = []
            total_confidence = 0.0
            timestamps = []
            
            # Get memories from the prolly store
            # This is a simplified implementation - in reality you'd search by semantic path
            async for namespace_bytes, key_bytes, value_bytes in self.memory_manager.prolly_store.tree.iter():
                try:
                    key_str = key_bytes.decode('utf-8')
                    
                    if path in key_str or key_str.endswith(path):
                        import json
                        try:
                            memory_data = json.loads(value_bytes.decode('utf-8'))
                        except json.JSONDecodeError:
                            memory_data = {
                                'content': value_bytes.decode('utf-8', errors='ignore'),
                                'timestamp': time.time(),
                                'confidence': 1.0
                            }
                        
                        memories.append(memory_data)
                        total_confidence += memory_data.get('confidence', 1.0)
                        timestamps.append(memory_data.get('timestamp', time.time()))
                        
                except UnicodeDecodeError:
                    continue
            
            return MemoryDetails(
                path=path,
                memories=memories,
                total_count=len(memories),
                confidence_avg=total_confidence / max(len(memories), 1),
                first_timestamp=min(timestamps) if timestamps else time.time(),
                last_timestamp=max(timestamps) if timestamps else time.time()
            )
            
        except Exception as e:
            logger.error(f"Error getting memory details for {path}: {e}")
            return MemoryDetails(
                path=path,
                memories=[],
                total_count=0,
                confidence_avg=0.0,
                first_timestamp=time.time(),
                last_timestamp=time.time()
            )


# Initialize service
service: Optional[VisualizationService] = None


@app.on_event("startup")
async def startup_event():
    """Initialize the visualization service on startup."""
    global service
    
    # Get store path from environment or use default
    store_path = os.getenv("MEMOIR_STORE_PATH", "/tmp/memoir_visualization_data")
    
    try:
        service = VisualizationService(store_path)
        logger.info("Visualization service started successfully")
    except Exception as e:
        logger.error(f"Failed to start visualization service: {e}")
        raise


# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the visualization frontend."""
    try:
        # Get path relative to this file's directory
        html_path = Path(__file__).parent / "visualization_mockup.html"
        with open(html_path, "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Visualization frontend not found</h1>", status_code=404)


@app.get("/api/branches", response_model=List[BranchInfo])
async def get_branches():
    """Get list of available memory branches."""
    if not service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    return await service.get_branches()


@app.get("/api/commits", response_model=List[CommitInfo])
async def get_commits(
    branch: str = Query(default="main", description="Branch name"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of commits to return")
):
    """Get commit history for a branch."""
    if not service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    return await service.get_commit_history(branch=branch, limit=limit)


@app.get("/api/structure", response_model=MemoryNode)
async def get_memory_structure(
    commit_id: Optional[str] = Query(default=None, description="Commit ID to view (default: HEAD)")
):
    """Get memory taxonomy structure at a specific commit."""
    if not service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    return await service.get_memory_structure(commit_id=commit_id)


@app.get("/api/memories/{path:path}", response_model=MemoryDetails)
async def get_memory_details(
    path: str,
    commit_id: Optional[str] = Query(default=None, description="Commit ID to view (default: HEAD)")
):
    """Get detailed memory information for a specific taxonomy path."""
    if not service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    return await service.get_memory_details(path=path, commit_id=commit_id)


@app.get("/api/search")
async def search_memories(
    query: str = Query(description="Search query"),
    commit_id: Optional[str] = Query(default=None, description="Commit ID to search in")
):
    """Search memories by content or path."""
    if not service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    
    # TODO: Implement search functionality
    return {"message": "Search not yet implemented", "query": query}


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "memoir-visualization",
        "timestamp": time.time(),
        "initialized": service is not None
    }


if __name__ == "__main__":
    import uvicorn
    
    # Run the server
    uvicorn.run(
        "visualization_service:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        log_level="info"
    )
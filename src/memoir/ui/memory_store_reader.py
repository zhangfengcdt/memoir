#!/usr/bin/env python3
"""
Memory store reader for UI - provides JSON data from the memory store.
This script can be called from the UI to fetch memory store data.
"""

import argparse
import json
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from memoir.store.prolly_adapter import ProllyTreeStore


def read_store_data(store_path: str):
    """Read memory store data and return as JSON."""
    
    if not Path(store_path).exists():
        return json.dumps({"error": f"Store path does not exist: {store_path}"})
    
    try:
        # Initialize store
        store = ProllyTreeStore(
            path=store_path,
            enable_versioning=True,
            auto_commit=False,
            cache_size=10000,
        )
        
        # Get branches
        branches = store.tree.list_branches()
        current_branch = store.tree.current_branch()
        
        # Get commits for current branch
        commits = []
        try:
            # Try to get commit history (this might need git commands)
            import subprocess
            result = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                cwd=store_path,
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split(' ', 1)
                        commits.append({
                            "hash": parts[0],
                            "message": parts[1] if len(parts) > 1 else ""
                        })
        except Exception:
            pass
        
        # Get memory entries
        memories = []
        try:
            keys = store.tree.list_keys()
            for key in keys:
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                value = store.tree.get(key if isinstance(key, bytes) else key.encode("utf-8"))
                
                if value:
                    # Parse the stored value
                    try:
                        value_str = value.decode("utf-8") if isinstance(value, bytes) else value
                        value_data = json.loads(value_str) if isinstance(value_str, str) else value_str
                        
                        # Extract namespace and path from key
                        key_parts = key_str.split(":")
                        namespace = key_parts[0] if key_parts else "default"
                        path = ":".join(key_parts[1:]) if len(key_parts) > 1 else key_str
                        
                        memories.append({
                            "key": key_str,
                            "namespace": namespace,
                            "path": path,
                            "value": value_data
                        })
                    except Exception as e:
                        memories.append({
                            "key": key_str,
                            "error": str(e)
                        })
        except Exception as e:
            # In case list_keys doesn't work
            pass
        
        # Build tree structure from paths
        tree = {}
        for memory in memories:
            if "path" in memory:
                parts = memory["path"].split(".")
                current = tree
                for part in parts:
                    if part not in current:
                        current[part] = {}
                    current = current[part]
        
        result = {
            "store_path": store_path,
            "branches": branches,
            "current_branch": current_branch,
            "commits": commits,
            "memories": memories,
            "tree": tree,
            "total_memories": len(memories)
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        return json.dumps({"error": str(e)})


def main():
    parser = argparse.ArgumentParser(description="Read memory store data")
    parser.add_argument("store_path", help="Path to the memory store")
    parser.add_argument("--output", help="Output file (default: stdout)")
    
    args = parser.parse_args()
    
    result = read_store_data(args.store_path)
    
    if args.output:
        with open(args.output, "w") as f:
            f.write(result)
    else:
        print(result)


if __name__ == "__main__":
    main()
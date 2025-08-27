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
        # Initialize store with versioning disabled to prevent new commits
        # We only need to read data, not create new commits
        store = ProllyTreeStore(
            path=store_path,
            enable_versioning=True,
            auto_commit=False,
            cache_size=10000,
        )

        # Get branches and current branch using git directly
        # since we disabled versioning to prevent commits
        branches = []
        current_branch = "main"
        try:
            import subprocess

            # Get branches
            result = subprocess.run(
                ["git", "branch", "--list"],
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                branches = [
                    line.strip().lstrip("* ")
                    for line in result.stdout.strip().split("\n")
                    if line.strip()
                ]
                # Get current branch
                result = subprocess.run(
                    ["git", "branch", "--show-current"],
                    cwd=store_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0 and result.stdout.strip():
                    current_branch = result.stdout.strip()
        except Exception as e:
            print(f"Error reading git branches: {e}")
            branches = ["main"]

        # Get commits for current branch
        commits = []
        try:
            # Try to get commit history, filtering out generic messages
            import subprocess

            result = subprocess.run(
                [
                    "git",
                    "log",
                    "--oneline",
                    "--all",
                ],  # Get ALL commits from all branches
                cwd=store_path,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        parts = line.split(" ", 1)
                        hash_val = parts[0]
                        message = parts[1] if len(parts) > 1 else ""

                        # Keep ALL commits - no filtering or deduplication
                        commits.append({"hash": hash_val, "message": message})
        except Exception:
            pass

        # Get memory entries using list_keys approach as suggested
        memories = []
        tree_paths = {}

        try:
            # Try to get all keys using list_keys if available
            all_keys = []
            if hasattr(store.tree, "list_keys"):
                print("Using list_keys to get all keys...")
                try:
                    keys = store.tree.list_keys()
                    all_keys = [key.decode("utf-8") for key in keys]
                    print(f"Found {len(all_keys)} total keys in store")
                except Exception as e:
                    print(f"Error with list_keys: {e}")

            # If no list_keys, fall back to search
            if not all_keys:
                print("Falling back to BaseStore.search...")
                # Search both primary namespaces: alice_chen and memory:general
                items = []
                for namespace in [("alice_chen",), ("memory", "general")]:
                    try:
                        ns_items = list(store.search(namespace))
                        items.extend(ns_items)
                        print(f"Found {len(ns_items)} items in namespace {namespace}")
                    except Exception as e:
                        print(f"Error searching namespace {namespace}: {e}")
                
                print(f"Found {len(items)} total items using BaseStore.search()")

                # Also try with empty search to get all items
                if not items:
                    print("Trying search with no filter...")
                    items = list(store.search(namespace, limit=100))
                    print(f"Found {len(items)} items with no filter")

                # Try different possible namespaces since list_namespaces doesn't exist
                if not items:
                    print("Trying different namespaces...")
                    possible_namespaces = [
                        ("alice_chen",),
                        ("memory", "general"),  # Add memory:general namespace for timeline/location data
                        ("default",),
                        ("",),
                        (),
                    ]
                    for ns in possible_namespaces:
                        try:
                            ns_items = list(store.search(ns, limit=100))
                            print(f"Namespace {ns}: {len(ns_items)} items")
                            if ns_items:
                                items.extend(ns_items)
                                break  # Found items, stop searching
                        except Exception as e:
                            print(f"Error searching namespace {ns}: {e}")

                for item in items:
                    try:
                        # Extract path and value from the store item
                        # ProllyTreeStore.search() returns tuples: (namespace, key, value)
                        if isinstance(item, tuple) and len(item) == 3:
                            item_namespace, semantic_path, value_data = item
                        else:
                            # Fallback to object attributes if not tuple format
                            semantic_path = item.key
                            value_data = item.value

                        # Convert namespace tuple back to string format for display
                        if isinstance(item_namespace, tuple):
                            namespace_str = ":".join(item_namespace)
                        else:
                            namespace_str = str(item_namespace)

                        memory_entry = {
                            "key": f"{namespace_str}:{semantic_path}",
                            "namespace": namespace_str,
                            "path": semantic_path,
                            "value": value_data,
                            "content": (
                                value_data.get("content")
                                if isinstance(value_data, dict)
                                else str(value_data)
                            ),
                        }
                        memories.append(memory_entry)

                        # Build tree structure from semantic paths
                        if semantic_path and "." in semantic_path:
                            parts = semantic_path.split(".")
                            for i in range(len(parts)):
                                path_prefix = ".".join(parts[: i + 1])
                                tree_paths[path_prefix] = (
                                    tree_paths.get(path_prefix, 0) + 1
                                )
                        elif semantic_path:
                            tree_paths[semantic_path] = (
                                tree_paths.get(semantic_path, 0) + 1
                            )

                        print(f"  Found memory: {semantic_path}")

                    except Exception as e:
                        print(f"Error processing item: {e}")
                        continue
            else:
                # Process keys directly using list_keys approach
                print("Processing keys from list_keys...")
                for full_key in all_keys:
                    try:
                        # Parse the key to extract namespace and semantic path
                        # Format: namespace:key (e.g., "alice_chen:memory.1724123456")
                        # Or: namespace:subnspace:key (e.g., "memory:general:timeline.20241127")
                        if ":" in full_key:
                            parts = full_key.split(":")
                            if len(parts) >= 3 and parts[0] == "memory" and parts[1] == "general":
                                # Handle memory:general:path format
                                namespace_part = "memory:general"
                                semantic_path = ":".join(parts[2:])
                            elif len(parts) == 2:
                                # Handle alice_chen:path format
                                namespace_part, semantic_path = parts
                            else:
                                namespace_part = ":".join(parts[:-1])
                                semantic_path = parts[-1]
                        else:
                            namespace_part = ""
                            semantic_path = full_key

                        # Include alice_chen and memory:general namespaces for UI
                        if namespace_part not in ["alice_chen", "memory:general"]:
                            continue

                        # Get the value for this key
                        key_bytes = full_key.encode("utf-8")
                        value_bytes = store.tree.get(key_bytes)
                        if not value_bytes:
                            continue

                        # Decode the value
                        value_data = store._decode_value(value_bytes)

                        memory_entry = {
                            "key": full_key,
                            "namespace": namespace_part,
                            "path": semantic_path,
                            "value": value_data,
                            "content": (
                                value_data.get("content")
                                if isinstance(value_data, dict)
                                else str(value_data)
                            ),
                        }
                        memories.append(memory_entry)

                        # Build tree structure from semantic paths
                        if semantic_path and "." in semantic_path:
                            parts = semantic_path.split(".")
                            for i in range(len(parts)):
                                path_prefix = ".".join(parts[: i + 1])
                                tree_paths[path_prefix] = (
                                    tree_paths.get(path_prefix, 0) + 1
                                )
                        elif semantic_path:
                            tree_paths[semantic_path] = (
                                tree_paths.get(semantic_path, 0) + 1
                            )

                        print(f"  Found memory: {semantic_path}")

                    except Exception as e:
                        print(f"Error processing key {full_key}: {e}")
                        continue

        except Exception as e:
            print(f"Error reading from store: {e}")
            pass

        # Don't use sample data for real stores - return empty if no memories found
        # This prevents fake data from appearing in new/empty stores
        if not memories:
            print("No memories found in store - returning empty result")

        result = {
            "store_path": store_path,
            "branches": branches,
            "current_branch": current_branch,
            "commits": commits,
            "memories": memories,
            "tree": tree_paths,  # Use the path counts we built above
            "total_memories": len(memories),
        }

        return json.dumps(result, indent=2)

    except Exception as e:
        return json.dumps({"error": str(e)})


def get_blame_info(store_path: str, memory_key: str, namespace: str = "alice_chen"):
    """Get git blame-like information for a specific memory key."""

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

        # Create the full key
        full_key = f"{namespace}:{memory_key}"

        # Get current value to verify key exists
        key_bytes = full_key.encode("utf-8")
        current_value = None
        try:
            value_bytes = store.tree.get(key_bytes)
            if value_bytes:
                current_value = store._decode_value(value_bytes)
        except Exception as e:
            print(f"Error getting current value: {e}")

        # Use git to get the blame information for this key
        blame_info = []
        try:
            import subprocess

            # Search git history for commits that mention this key
            # Use git log to find all commits that changed files containing this key pattern
            result = subprocess.run(
                [
                    "git",
                    "log",
                    "--oneline",
                    "--all",
                    "--grep",
                    memory_key,
                    "--grep",
                    full_key,
                ],
                cwd=store_path,
                capture_output=True,
                text=True,
            )

            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    if line.strip():
                        parts = line.split(" ", 1)
                        commit_hash = parts[0]

                        # Get commit details
                        detail_result = subprocess.run(
                            [
                                "git",
                                "show",
                                "--format=%H|%an|%ae|%ad|%s",
                                "--date=iso",
                                "--name-only",
                                commit_hash,
                            ],
                            cwd=store_path,
                            capture_output=True,
                            text=True,
                        )

                        if detail_result.returncode == 0:
                            lines = detail_result.stdout.strip().split("\n")
                            if lines:
                                commit_details = lines[0].split("|")
                                if len(commit_details) >= 5:
                                    blame_entry = {
                                        "commit_hash": commit_details[0][
                                            :8
                                        ],  # Short hash
                                        "full_hash": commit_details[0],
                                        "author": commit_details[1],
                                        "email": commit_details[2],
                                        "date": commit_details[3],
                                        "message": commit_details[4],
                                        "files": lines[1:] if len(lines) > 1 else [],
                                    }
                                    blame_info.append(blame_entry)

            # If no specific commits found, get general git history
            if not blame_info:
                result = subprocess.run(
                    [
                        "git",
                        "log",
                        "--oneline",
                        "-10",  # Last 10 commits
                        "--format=%H|%an|%ae|%ad|%s",
                        "--date=iso",
                    ],
                    cwd=store_path,
                    capture_output=True,
                    text=True,
                )

                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        if line.strip():
                            commit_details = line.split("|")
                            if len(commit_details) >= 5:
                                blame_entry = {
                                    "commit_hash": commit_details[0][:8],
                                    "full_hash": commit_details[0],
                                    "author": commit_details[1],
                                    "email": commit_details[2],
                                    "date": commit_details[3],
                                    "message": commit_details[4],
                                    "files": [],
                                    "note": "General repository history (key-specific history not found)",
                                }
                                blame_info.append(blame_entry)

        except Exception as e:
            print(f"Error getting git blame info: {e}")
            blame_info.append(
                {
                    "error": f"Could not retrieve git history: {e!s}",
                    "commit_hash": "unknown",
                    "author": "unknown",
                    "date": "unknown",
                    "message": "Error retrieving history",
                }
            )

        # Get the current status of the key
        key_status = "exists" if current_value else "not_found"

        # If key doesn't exist, return clear error message
        if key_status == "not_found":
            return json.dumps(
                {
                    "key": memory_key,
                    "full_key": full_key,
                    "namespace": namespace,
                    "status": key_status,
                    "error": f"Key '{memory_key}' does not exist in namespace '{namespace}'",
                    "message": f"The memory key '{memory_key}' was not found in the store. Please check the key name and try again.",
                    "store_path": store_path,
                },
                indent=2,
            )

        result = {
            "key": memory_key,
            "full_key": full_key,
            "namespace": namespace,
            "status": key_status,
            "current_value": current_value,
            "blame_info": blame_info,
            "total_commits": len(blame_info),
            "store_path": store_path,
        }

        return json.dumps(result, indent=2, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)})


def main():
    parser = argparse.ArgumentParser(description="Read memory store data")
    parser.add_argument("store_path", help="Path to the memory store")
    parser.add_argument("--output", help="Output file (default: stdout)")
    parser.add_argument("--blame", help="Get blame info for specific key")
    parser.add_argument(
        "--namespace", default="alice_chen", help="Namespace for blame lookup"
    )

    args = parser.parse_args()

    if args.blame:
        result = get_blame_info(args.store_path, args.blame, args.namespace)
    else:
        result = read_store_data(args.store_path)

    if args.output:
        with open(args.output, "w") as f:
            f.write(result)
    else:
        print(result)


if __name__ == "__main__":
    main()

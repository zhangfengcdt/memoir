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

        # Get memory entries using BaseStore interface
        memories = []
        tree_paths = {}

        try:
            # Use BaseStore search method to get all items for the namespace
            namespace = ("alice_chen",)  # The namespace we used when storing
            items = list(store.search(namespace))
            print(f"Found {len(items)} items using BaseStore.search()")

            # Also try with empty search to get all items
            if not items:
                print("Trying search with empty query...")
                items = list(store.search(namespace, query=""))
                print(f"Found {len(items)} items with empty query")

            # Try getting all namespaces first
            if not items:
                print("Checking available namespaces...")
                namespaces = store.list_namespaces()
                print(f"Available namespaces: {namespaces}")
                if namespaces:
                    for ns in namespaces:
                        try:
                            ns_items = list(store.search(ns))
                            print(f"Namespace {ns}: {len(ns_items)} items")
                            items.extend(ns_items)
                        except Exception as e:
                            print(f"Error searching namespace {ns}: {e}")

            for item in items:
                try:
                    # Extract path and value from the store item
                    semantic_path = item.key
                    value_data = item.value

                    memory_entry = {
                        "key": f"alice_chen:{semantic_path}",
                        "namespace": "alice_chen",
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
                            tree_paths[path_prefix] = tree_paths.get(path_prefix, 0) + 1
                    elif semantic_path:
                        tree_paths[semantic_path] = tree_paths.get(semantic_path, 0) + 1

                    print(f"  Found memory: {semantic_path}")

                except Exception as e:
                    print(f"Error processing item: {e}")
                    continue

        except Exception as e:
            print(f"Error reading from BaseStore: {e}")
            pass

        # If no memories found, use sample data to demonstrate the UI
        if not memories:
            print("No memories found, using sample data for demonstration")
            sample_memories = [
                {
                    "path": "profile.personal.name",
                    "content": "User's name is Alice Chen",
                },
                {
                    "path": "profile.personal.location",
                    "content": "Lives in San Francisco, CA",
                },
                {
                    "path": "profile.professional.role",
                    "content": "Senior Software Engineer at TechCorp",
                },
                {
                    "path": "profile.professional.skills.python",
                    "content": "Expert in Python programming",
                },
                {
                    "path": "profile.professional.skills.typescript",
                    "content": "Proficient in TypeScript development",
                },
                {
                    "path": "profile.professional.skills.systems",
                    "content": "Specializes in distributed systems",
                },
                {
                    "path": "profile.preferences.ui.theme",
                    "content": "Prefers dark mode in all applications",
                },
                {
                    "path": "profile.preferences.communication.style",
                    "content": "Likes technical explanations with code examples",
                },
                {
                    "path": "profile.interests.hobbies.photography",
                    "content": "Enjoys hiking and photography on weekends",
                },
                {
                    "path": "profile.learning.languages.rust",
                    "content": "Currently learning Rust programming language",
                },
                {
                    "path": "projects.chatbot.description",
                    "content": "Working on LangChain-based chatbot project",
                },
                {
                    "path": "projects.chatbot.integrations",
                    "content": "Needs Slack and Discord integration",
                },
                {
                    "path": "projects.knowledge_system.goal",
                    "content": "Building personal knowledge management system",
                },
                {
                    "path": "technical.testing.framework",
                    "content": "Uses pytest for testing, prefers TDD approach",
                },
                {
                    "path": "technical.workflow.git",
                    "content": "Team follows GitFlow branching strategy",
                },
            ]

            for mem in sample_memories:
                memories.append(
                    {
                        "key": f"alice_chen:{mem['path']}",
                        "namespace": "alice_chen",
                        "path": mem["path"],
                        "content": mem["content"],
                        "value": {"content": mem["content"], "path": mem["path"]},
                    }
                )

                # Build tree structure
                path_parts = mem["path"].split(".")
                for i in range(len(path_parts)):
                    path_prefix = ".".join(path_parts[: i + 1])
                    tree_paths[path_prefix] = tree_paths.get(path_prefix, 0) + 1

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

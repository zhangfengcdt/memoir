#!/usr/bin/env python3
"""
Populate memory store with sample data that can be easily read by the UI.
"""

import json
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from memoir.store.prolly_adapter import ProllyTreeStore


def populate_store(store_path):
    """Populate store with sample hierarchical memory data."""
    
    # Initialize store
    store = ProllyTreeStore(
        path=store_path,
        enable_versioning=True,
        auto_commit=True,
    )
    
    # Sample memory data with semantic paths
    sample_memories = [
        # Profile data
        {
            "key": "alice_chen:profile.personal.name",
            "content": "User's name is Alice Chen",
            "path": "profile.personal.name"
        },
        {
            "key": "alice_chen:profile.personal.location", 
            "content": "Lives in San Francisco, CA",
            "path": "profile.personal.location"
        },
        {
            "key": "alice_chen:profile.professional.role",
            "content": "Senior Software Engineer at TechCorp",
            "path": "profile.professional.role"
        },
        {
            "key": "alice_chen:profile.professional.skills.python",
            "content": "Expert in Python programming",
            "path": "profile.professional.skills.python"
        },
        {
            "key": "alice_chen:profile.professional.skills.typescript",
            "content": "Proficient in TypeScript development",
            "path": "profile.professional.skills.typescript"
        },
        {
            "key": "alice_chen:profile.professional.skills.systems",
            "content": "Specializes in distributed systems",
            "path": "profile.professional.skills.systems"
        },
        {
            "key": "alice_chen:profile.preferences.ui.theme",
            "content": "Prefers dark mode in all applications",
            "path": "profile.preferences.ui.theme"
        },
        {
            "key": "alice_chen:profile.preferences.communication.style",
            "content": "Likes technical explanations with code examples",
            "path": "profile.preferences.communication.style"
        },
        {
            "key": "alice_chen:profile.interests.hobbies.photography",
            "content": "Enjoys hiking and photography on weekends",
            "path": "profile.interests.hobbies.photography"
        },
        {
            "key": "alice_chen:profile.learning.languages.rust",
            "content": "Currently learning Rust programming language",
            "path": "profile.learning.languages.rust"
        },
        # Project data
        {
            "key": "alice_chen:projects.chatbot.description",
            "content": "Working on LangChain-based chatbot project",
            "path": "projects.chatbot.description"
        },
        {
            "key": "alice_chen:projects.chatbot.integrations",
            "content": "Needs Slack and Discord integration",
            "path": "projects.chatbot.integrations"
        },
        {
            "key": "alice_chen:projects.knowledge_system.goal",
            "content": "Building personal knowledge management system",
            "path": "projects.knowledge_system.goal"
        },
        # Technical preferences
        {
            "key": "alice_chen:technical.testing.framework",
            "content": "Uses pytest for testing, prefers TDD approach",
            "path": "technical.testing.framework"
        },
        {
            "key": "alice_chen:technical.workflow.git",
            "content": "Team follows GitFlow branching strategy",
            "path": "technical.workflow.git"
        }
    ]
    
    print(f"Populating store at {store_path} with {len(sample_memories)} memories...")
    
    # Store each memory using the BaseStore interface
    for memory in sample_memories:
        namespace = ("alice_chen",)  # Tuple format for namespace
        key = memory["path"]  # Use the semantic path as key
        data = {
            "content": memory["content"],
            "path": memory["path"],
            "metadata": {
                "type": "sample",
                "timestamp": "2024-08-24T15:00:00Z"
            }
        }
        
        try:
            # Use the BaseStore put method
            store.put(namespace, key, data)
            print(f"  Stored: {memory['path']}")
        except Exception as e:
            print(f"  Error storing {key}: {e}")
    
    print(f"✅ Successfully populated store with {len(sample_memories)} memories")
    print(f"📁 Store location: {store_path}")
    
    # Verify storage
    keys = list(store.tree.list_keys())
    print(f"🔍 Verification: {len(keys)} keys found in store")
    
    return len(keys)


if __name__ == "__main__":
    store_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/memoir_ui_store"
    populate_store(store_path)
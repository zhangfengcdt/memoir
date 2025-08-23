#!/usr/bin/env python3
"""
Simple runner script for the Memoir Memory Visualization Service.

This script sets up and runs the visualization service with sample data.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the memoir package to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    import uvicorn
    from fastapi import FastAPI
except ImportError:
    print("Error: FastAPI and uvicorn are required. Install with:")
    print("pip install fastapi uvicorn")
    sys.exit(1)


def setup_sample_data():
    """Set up sample memory data for demonstration."""
    print("Setting up sample memory data...")
    
    try:
        from memoir.core.memory import ProllyTreeMemoryStoreManager
        from memoir.store.prolly_adapter import ProllyTreeStore
        from memoir.classifier.semantic import SemanticClassifier
        from memoir.taxonomy.semantic import SemanticTaxonomy
        
        # Create store directory in /tmp/ to avoid cluttering project
        store_path = Path("/tmp/memoir_visualization_data")
        store_path.mkdir(exist_ok=True)
        
        # Initialize components
        taxonomy = SemanticTaxonomy()
        classifier = SemanticClassifier(taxonomy=taxonomy)
        
        prolly_store = ProllyTreeStore(
            path=str(store_path),
            enable_versioning=True,
            auto_commit=True
        )
        
        memory_manager = ProllyTreeMemoryStoreManager(
            prolly_store=prolly_store,
            classifier=classifier,
            enable_versioning=True,
            auto_commit=True
        )
        
        # Add sample memories
        sample_memories = [
            ("My name is John Doe, I prefer to be called Johnny", "profile.personal.identity.name"),
            ("I'm 28 years old, born March 15, 1995", "profile.personal.identity.age"),
            ("I use he/him pronouns", "profile.personal.identity.gender"),
            ("I live in San Francisco, California", "profile.personal.location.current"),
            ("I'm originally from New York", "profile.personal.location.hometown"),
            ("I work as a Software Engineer", "profile.professional.occupation"),
            ("I'm skilled in Python, JavaScript, and React", "profile.professional.skills.programming"),
            ("I have 5 years of experience in web development", "profile.professional.experience"),
            ("I prefer dark mode interfaces", "profile.preferences.interface.theme"),
            ("I like minimal email notifications", "profile.preferences.notifications.email"),
        ]
        
        print(f"Adding {len(sample_memories)} sample memories...")
        
        # Add memories with different commits
        for i, (content, suggested_path) in enumerate(sample_memories):
            # Store the memory
            asyncio.run(memory_manager.store_memory(content))
            
            # Commit every few memories to create history
            if i % 3 == 2:
                commit_msg = f"Added memories batch {i//3 + 1}"
                prolly_store.commit(commit_msg)
                print(f"Committed: {commit_msg}")
        
        # Final commit
        prolly_store.commit("Initial memory setup complete")
        
        print("✅ Sample data setup complete!")
        print(f"📁 Data stored in: {store_path.absolute()}")
        
        return True
        
    except ImportError as e:
        print(f"Warning: Could not set up sample data due to missing imports: {e}")
        print("The visualization service will still run, but with empty data.")
        return False
    except Exception as e:
        print(f"Warning: Error setting up sample data: {e}")
        return False


def main():
    """Main entry point."""
    print("🧠 Memoir Memory Visualization Service")
    print("=" * 40)
    
    # Create static directory if it doesn't exist
    static_dir = Path("./static")
    static_dir.mkdir(exist_ok=True)
    
    # Set up sample data if memoir packages are available
    setup_sample_data()
    
    # Set environment variable for the service
    os.environ["MEMOIR_STORE_PATH"] = "/tmp/memoir_visualization_data"
    
    print("\n🚀 Starting visualization service...")
    print("📊 Open http://127.0.0.1:8000 to view the memory visualization")
    print("🔧 API documentation available at http://127.0.0.1:8000/docs")
    print("\nPress Ctrl+C to stop the server")
    print("-" * 40)
    
    # Start the server
    try:
        uvicorn.run(
            "visualization_service:app",
            host="127.0.0.1",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n👋 Server stopped")
    except Exception as e:
        print(f"❌ Error running server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
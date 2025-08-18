#!/usr/bin/env python3
"""
Split console app for Intelligent Taxonomy Classification system with real LLM.
Features three panels: conversations (top-left), memory decisions (bottom-left), and current memories (right).
"""

import asyncio
import contextlib
import os
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich.tree import Tree

from langmem_prollytree.core.prolly_adapter import ProllyTreeStore
from langmem_prollytree.taxonomy.intelligent_classifier import IntelligentClassifier
from langmem_prollytree.taxonomy.semantic_classifier import SemanticClassifier
from langmem_prollytree.taxonomy.taxonomy_presets import TaxonomyVersion


class TaxonomyApp:
    """Split console app for intelligent taxonomy classification."""

    def __init__(self):
        self.console = Console()
        self.layout = Layout()
        self.conversations = []
        self.memory_decisions = []
        self.current_memories = []
        self.intelligent_classifier = None
        self.running = False
        self.current_processing = None  # Track what input is being processed
        self.demo_waiting_for_input = False  # Track if waiting for demo continuation
        self.cursor_visible = True  # Track cursor blink state
        self.cursor_toggle_time = time.time()  # Track last cursor toggle
        self.cursor_blink_interval = 0.5  # Cursor blink interval in seconds

        # Setup layout
        self.setup_layout()

    def setup_layout(self):
        """Setup the three-panel layout."""
        # Create main layout - make memory structure much wider
        self.layout.split_row(
            Layout(name="left", ratio=2), Layout(name="right", ratio=3)
        )

        # Split left side into top and bottom
        self.layout["left"].split_column(
            Layout(name="conversations", ratio=1), Layout(name="decisions", ratio=1)
        )

        # Set initial content
        self.layout["conversations"].update(
            Panel(
                "🗣️  Conversations\n\nWaiting for input...",
                title="Conversations",
                border_style="blue",
            )
        )

        self.layout["decisions"].update(
            Panel(
                "🧠 Memory Decisions\n\nNo decisions yet...",
                title="Memory Processing",
                border_style="green",
            )
        )

        self.layout["right"].update(
            Panel(
                "📚 Current Memories\n\nNo memories stored...",
                title="Memory Structure",
                border_style="purple",
            )
        )

    def get_llm(self):
        """Get OpenAI LLM instance - requires API key and langchain-openai."""
        # Check for API key
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        # Try to import and create OpenAI LLM
        try:
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0,
                api_key=api_key,
                max_tokens=500,
            )
        except ImportError:
            raise ImportError(
                "langchain-openai package is required. Install with: pip install langchain-openai"
            )

    async def setup_classifier(self):
        """Setup the intelligent classifier with memory store."""
        # Get LLM
        llm = self.get_llm()

        # Setup memory store
        data_dir = Path("/tmp/intelligent_taxonomy_app")
        data_dir.mkdir(parents=True, exist_ok=True)

        # Create a simple classifier for the store
        classifier = SemanticClassifier(llm=None)

        store = ProllyTreeStore(
            path=str(data_dir),
            classifier=classifier,
            enable_versioning=False,
        )

        # Create intelligent classifier
        self.intelligent_classifier = IntelligentClassifier(
            llm=llm,
            memory_store=store,
            taxonomy_version=TaxonomyVersion.GENERAL,
            confidence_thresholds={
                "high": 0.8,  # Slightly lower to see more high confidence classifications
                "medium": 0.5,  # More reasonable medium threshold
                "low": 0.0,
            },
            min_items_for_expansion=1,  # Lower threshold for easier expansion triggering
        )

    def update_cursor_state(self):
        """Update cursor blinking state."""
        current_time = time.time()
        if current_time - self.cursor_toggle_time >= self.cursor_blink_interval:
            self.cursor_visible = not self.cursor_visible
            self.cursor_toggle_time = current_time

    def get_cursor_text(self):
        """Get cursor character based on visibility state."""
        return "█" if self.cursor_visible else " "

    def update_conversations_panel(self):
        """Update the conversations panel."""
        # Update cursor state for blinking animation
        self.update_cursor_state()

        if not self.conversations:
            cursor = self.get_cursor_text()
            content = f"🗣️  Conversations\n\nWaiting for input...{cursor}"
        else:
            # Calculate conversations to show based on actual panel space
            console_height = self.console.size.height
            # Each conversation takes about 3-4 lines (title + content + timestamp + spacing)
            # Conversations panel gets half the left side (which is 2/5 of total width)
            available_lines = max(
                8, console_height // 3
            )  # Reserve space but use more than 1/6
            # Account for panel borders and headers (about 3 lines)
            content_lines = available_lines - 3
            # Each conversation needs about 3 lines
            max_conversations = max(2, content_lines // 3)

            lines = [f"🗣️  Conversations ({len(self.conversations)} total)"]

            # Always show the most recent conversations
            start_idx = max(0, len(self.conversations) - max_conversations)
            recent_conversations = self.conversations[start_idx:]

            # Add scroll indicator if there are more conversations
            if start_idx > 0:
                lines.append(
                    f"📜 (last {len(recent_conversations)} of {len(self.conversations)} shown)"
                )

            lines.append("")  # Empty line after header

            for i, conv in enumerate(recent_conversations):
                speaker = conv.get("speaker", "User")
                conv_content = conv.get("content", "")
                timestamp = conv.get("timestamp", "")

                conv_number = start_idx + i + 1
                lines.append(f"[{conv_number}] {speaker}:")

                # Show full content without truncation, but wrap it nicely
                # Split long messages into multiple lines for better readability
                if len(conv_content) > 60:
                    # Break long content into chunks
                    words = conv_content.split()
                    current_line = "  💬 "
                    for word in words:
                        if (
                            len(current_line + word) > 55
                        ):  # Leave room for panel borders
                            lines.append(current_line)
                            current_line = "      " + word  # Continuation indent
                        else:
                            if current_line == "  💬 ":
                                current_line += word
                            else:
                                current_line += " " + word
                    if current_line.strip():
                        lines.append(current_line)
                else:
                    lines.append(f"  💬 {conv_content}")

                if timestamp:
                    lines.append(f"    ⏰ {timestamp}")
                lines.append("")  # Empty line for spacing

            # Add cursor at the end if waiting for input
            if not self.current_processing and not self.demo_waiting_for_input:
                cursor = self.get_cursor_text()
                lines.append(f"💬 Ready for input...{cursor}")

            content = "\n".join(lines)

        # Create a text object for better rendering
        text_obj = Text(content)
        self.layout["conversations"].update(
            Panel(text_obj, title="Conversations", border_style="blue")
        )

    def update_decisions_panel(self):
        """Update the memory decisions panel."""
        if not self.memory_decisions and not self.current_processing:
            content = "🧠 Memory Decisions\n\nNo decisions yet..."
        else:
            lines = ["🧠 Memory Decisions\n"]

            if self.memory_decisions:
                # Calculate how many decisions to show based on available height
                console_height = self.console.size.height
                # Memory processing panel gets half the left side height
                available_lines = max(8, console_height // 3)
                # Each decision takes about 8-10 lines, show as many as fit
                max_decisions = max(1, (available_lines - 5) // 8)

                # Show recent decisions up to the limit
                recent_decisions = self.memory_decisions[-max_decisions:]

                lines.append(
                    f"📚 Total Memories: {self.memory_decisions[-1].get('memory_count', 0)}"
                )
                lines.append("")

                for i, decision in enumerate(recent_decisions):
                    decision_num = (
                        len(self.memory_decisions) - len(recent_decisions) + i + 1
                    )
                    classification = decision.get("classification", {})
                    storage = decision.get("storage", {})

                    lines.append(f"[{decision_num}] Classification Results:")

                    # Memory worthiness
                    memory_worthy = (
                        "✅ Memory-worthy"
                        if classification.get("is_memory", False)
                        else "❌ Not memory-worthy"
                    )
                    lines.append(f"   {memory_worthy}")

                    # Path and confidence
                    if classification.get("path"):
                        lines.append(f"   📍 Path: {classification.get('path')}")
                        lines.append(
                            f"   📊 Confidence: {classification.get('confidence', 0.0):.2f}"
                        )

                    # Actions
                    action = classification.get("suggested_action", "UNKNOWN")
                    storage_action = storage.get("action", "unknown")
                    lines.append(f"   🎯 Classification: {action}")
                    lines.append(f"   💾 Storage: {storage_action}")

                    # Reasoning if available
                    if classification.get("reasoning"):
                        reasoning = classification.get("reasoning", "")[:100]
                        lines.append(f"   💭 Reasoning: {reasoning}...")

                    lines.append("")  # Space between decisions

            # Show what's currently being processed at the end
            if self.current_processing:
                lines.append("⚡ Currently Processing:")
                lines.append(
                    f'   💬 "{self.current_processing[:40]}{"..." if len(self.current_processing) > 40 else ""}"'
                )
                lines.append("   🤖 REAL LLM CALL: Processing with GPT-4o-mini...")

            content = "\n".join(lines)

        # Create text object for decisions panel
        text_obj = Text(content)
        self.layout["decisions"].update(
            Panel(text_obj, title="Memory Processing", border_style="green")
        )

    def update_memories_panel(self):
        """Update the current memories panel."""
        if not self.intelligent_classifier:
            content = "📚 Current Memories\n\nClassifier not ready..."
        else:
            # Get all stored memories to show full tree structure
            stored_memories = self.intelligent_classifier.get_stored_memories(limit=100)

            if not stored_memories:
                content = "📚 Current Memories\n\nNo memories stored..."
            else:
                # Create tree structure
                tree = Tree("📚 Memory Structure")

                # Group by taxonomy hierarchy for better tree display
                hierarchy = {}
                for memory in stored_memories:
                    path = memory["path"]
                    parts = path.split(".")

                    # Create nested structure
                    current = hierarchy
                    for i, part in enumerate(parts):
                        if part not in current:
                            current[part] = {"memories": [], "children": {}}
                        if i == len(parts) - 1:
                            # This is a leaf node, add the memory
                            current[part]["memories"].append(memory)
                        current = current[part]["children"]

                # Build hierarchical tree structure
                def build_tree_node(
                    node_dict, parent_node, max_depth=3, current_depth=0
                ):
                    """Recursively build tree nodes showing full hierarchy."""
                    for key, value in sorted(node_dict.items()):
                        memories = value["memories"]
                        children = value["children"]

                        # Count total memories in this subtree
                        def count_memories(node):
                            count = len(node["memories"])
                            for child in node["children"].values():
                                count += count_memories(child)
                            return count

                        total_count = count_memories(value)

                        if memories or children:
                            # Create node with memory count
                            if current_depth == 0:
                                node_title = f"📁 {key.title()} ({total_count})"
                            else:
                                node_title = f"📂 {key.replace('_', ' ').title()} ({total_count})"

                            branch_node = parent_node.add(node_title)

                            # Add memories at this level
                            for memory in memories:
                                if isinstance(memory["content"], dict):
                                    content_text = memory["content"].get(
                                        "content", str(memory["content"])
                                    )
                                else:
                                    content_text = str(memory["content"])

                                preview = (
                                    content_text[:50] + "..."
                                    if len(content_text) > 50
                                    else content_text
                                )
                                branch_node.add(f"📄 {memory['path']}: {preview}")

                            # Recursively add children if not too deep
                            if current_depth < max_depth and children:
                                build_tree_node(
                                    children, branch_node, max_depth, current_depth + 1
                                )

                # Build the tree using full height
                console_height = self.console.size.height
                # Use almost full height for memory structure
                max_tree_depth = 4 if console_height > 30 else 3

                build_tree_node(hierarchy, tree, max_tree_depth)

                # Convert tree to string representation
                content = f"📚 Current Memories ({len(stored_memories)} total)\n\n"
                content += self._tree_to_string(tree)

        # Create text object for memory structure panel
        text_obj = Text(content)
        self.layout["right"].update(
            Panel(text_obj, title="Memory Structure", border_style="purple")
        )

    def _tree_to_string(self, tree, indent=0):
        """Convert tree to string representation."""
        lines = []
        if hasattr(tree, "children"):
            for node in tree.children:
                lines.append("  " * indent + str(node.label))
                if hasattr(node, "children") and node.children:
                    lines.extend(self._tree_to_string(node, indent + 1).split("\n"))
        return "\n".join(lines)

    def update_display(self):
        """Update all panels."""
        self.update_conversations_panel()
        self.update_decisions_panel()
        self.update_memories_panel()

    async def process_conversation(
        self, content: str, speaker: str = "User", metadata: Optional[dict] = None
    ):
        """Process a conversation input through the taxonomy system."""
        if not self.intelligent_classifier:
            return

        # Add to conversations immediately for better UX
        conversation = {
            "speaker": speaker,
            "content": content,
            "timestamp": time.strftime("%H:%M:%S"),
        }
        self.conversations.append(conversation)

        # Update display to show the new conversation right away
        self.update_display()

        # Set current processing indicator
        self.current_processing = content
        self.update_display()  # Show processing status

        # Get current memory count
        current_memories = self.intelligent_classifier.get_stored_memories(limit=100)
        memory_count = len(current_memories)

        # Process with classifier
        metadata = metadata or {"source": "interactive_app"}
        result = await self.intelligent_classifier.process_memory_with_storage(
            content, metadata
        )

        # Create decision record
        decision = {
            "memory_count": memory_count,
            "classification": {
                "is_memory": result.classification.is_memory,
                "path": result.classification.path,
                "confidence": result.classification.confidence,
                "suggested_action": (
                    result.classification.suggested_action.value
                    if hasattr(result.classification.suggested_action, "value")
                    else str(result.classification.suggested_action)
                ),
                "reasoning": result.classification.reasoning,
            },
            "storage": {
                "action": (
                    result.memory_action.value
                    if hasattr(result.memory_action, "value")
                    else str(result.memory_action)
                ),
                "reasoning": result.storage_reasoning,
                "path": result.memory_path,
            },
        }
        self.memory_decisions.append(decision)

        # Clear current processing indicator and update display
        self.current_processing = None
        self.update_display()

        return result

    def show_demo_completion(self):
        """Show demo completion message in the decisions panel."""
        lines = [
            "🎉 Demo Completed Successfully!",
            "",
            "✅ All 7 scenarios processed",
            "✅ Classification actions demonstrated:",
            "   • SKIP (greetings)",
            "   • CLASSIFY (clear classifications)",
            "   • EXPAND (new categories needed)",
            "   • USE_PARENT (generic categories)",
            "",
            "✅ Memory actions demonstrated:",
            "   • STORE (new memories)",
            "   • REPLACE (updated info)",
            "   • APPEND (additional info)",
            "   • MERGE (combined content)",
            "",
            "🔄 You can now:",
            "   • Type messages to classify interactively",
            "   • Type 'demo' to run demo again",
            "   • Type 'quit' to exit",
            "   • Press any key to continue...",
        ]

        content = "\n".join(lines)
        text_obj = Text(content)
        self.layout["decisions"].update(
            Panel(text_obj, title="🎉 Demo Complete", border_style="bright_green")
        )

    async def run_demo_scenarios(self):
        """Run a series of demo scenarios."""
        demo_scenarios = [
            {
                "content": "Hello, how are you today?",
                "speaker": "User",
                "description": "Simple greeting",
            },
            {
                "content": "I live in San Francisco and work as a software engineer",
                "speaker": "User",
                "description": "Personal info",
            },
            {
                "content": "My favorite programming language is Python for data science",
                "speaker": "User",
                "description": "Preferences",
            },
            {
                "content": "I'm developing quantum entanglement protocols for distributed systems",
                "speaker": "User",
                "description": "Highly specific technical content",
            },
            {
                "content": "I do some stuff with computers sometimes",
                "speaker": "User",
                "description": "Vague technical activity",
            },
            {
                "content": "I moved to New York City and now work as a senior architect",
                "speaker": "User",
                "description": "Updated location/job",
            },
            {
                "content": "I also like JavaScript and Rust for systems programming",
                "speaker": "User",
                "description": "Additional preferences",
            },
        ]

        for i, scenario in enumerate(demo_scenarios):
            await self.process_conversation(
                scenario["content"],
                scenario["speaker"],
                {"demo_step": i + 1, "description": scenario["description"]},
            )
            await asyncio.sleep(2)  # Pause between scenarios to see updates

        # Demo completed - show completion message
        self.show_demo_completion()

    def get_user_input(self, prompt_text: str = "💬 Enter your message") -> str:
        """Get user input using Rich prompt outside of Live display."""
        try:
            return Prompt.ask(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            return "quit"

    def wait_for_continue_input(self):
        """Wait for user to press any key to continue after demo completion."""
        # Update the decisions panel to show waiting message
        lines = [
            "🎉 Demo Completed Successfully!",
            "",
            "✅ All 7 scenarios processed",
            "✅ Classification actions demonstrated:",
            "   • SKIP (greetings)",
            "   • CLASSIFY (clear classifications)",
            "   • EXPAND (new categories needed)",
            "   • USE_PARENT (generic categories)",
            "",
            "✅ Memory actions demonstrated:",
            "   • STORE (new memories)",
            "   • REPLACE (updated info)",
            "   • APPEND (additional info)",
            "   • MERGE (combined content)",
            "",
            "🔄 After continuing, you can:",
            "   • Type messages to classify interactively",
            "   • Type 'demo' to run demo again",
            "   • Type 'quit' to exit",
        ]

        content = "\n".join(lines)
        text_obj = Text(content)
        self.layout["decisions"].update(
            Panel(text_obj, title="🎉 Demo Complete", border_style="bright_yellow")
        )

        # Store the current state for resuming
        self.demo_waiting_for_input = True

    async def continuous_refresh_task(self):
        """Background task to continuously refresh display for cursor blinking."""
        while self.running:
            self.update_display()
            await asyncio.sleep(0.1)  # Refresh every 100ms for smooth animation

    async def interactive_mode(self, live_display):
        """Run interactive mode where user can input conversations."""
        # Start background refresh task for cursor animation
        refresh_task = asyncio.create_task(self.continuous_refresh_task())

        try:
            # Start with demo automatically to show functionality
            await asyncio.sleep(1)
            await self.run_demo_scenarios()

            # Wait for user input after demo completion
            self.wait_for_continue_input()

            # Exit live display to get input cleanly
            live_display.stop()

            # Clear demo completion state immediately
            if self.demo_waiting_for_input:
                self.demo_waiting_for_input = False
                self.update_decisions_panel()  # Clear demo completion message

            # Restart live display
            live_display.start()

            # Interactive loop
            while self.running:
                try:
                    # Exit live display for clean input
                    live_display.stop()

                    # Get user input with Rich prompt (no extra blank lines)
                    user_input = self.get_user_input(
                        "💬 Enter your message (or 'demo'/'quit')"
                    )

                    # Restart live display
                    live_display.start()

                    if user_input.lower() == "quit":
                        break
                    elif user_input.lower() == "demo":
                        await self.run_demo_scenarios()
                        self.wait_for_continue_input()

                        # Handle demo completion
                        self.demo_waiting_for_input = False
                        self.update_decisions_panel()
                    elif user_input:
                        try:
                            # Process the conversation while live display is running
                            await self.process_conversation(user_input)

                            # Brief pause to see the updates
                            await asyncio.sleep(1)
                        except Exception as e:
                            # Stop live display to show error
                            live_display.stop()
                            self.console.print(
                                f"❌ Error processing input: {e}", style="red"
                            )
                            input("\nPress Enter to continue...")
                            live_display.start()

                except (KeyboardInterrupt, EOFError):
                    break

        finally:
            # Cancel the refresh task
            refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await refresh_task

        self.running = False

    async def run(self):
        """Run the taxonomy app with live display."""
        try:
            # Setup classifier
            await self.setup_classifier()

            # Show startup message
            self.console.print(
                "\n🧠 Intelligent Taxonomy Classification App", style="bold blue"
            )
            self.console.print("=" * 60)
            self.console.print("✅ LLM classifier ready", style="green")
            self.console.print("✅ Memory store initialized", style="green")
            self.console.print("✅ Live display active", style="green")
            self.console.print("\n🎯 Starting demo automatically...", style="yellow")
            self.console.print(
                "💡 After demo: type messages to classify, 'demo' to repeat, or 'quit' to exit",
                style="cyan",
            )

            # Create and start live display
            live_display = Live(
                self.layout, console=self.console, refresh_per_second=10
            )
            live_display.start()

            self.running = True
            # Initial display update
            self.update_display()

            try:
                # Start interactive mode with live display control
                await self.interactive_mode(live_display)
            finally:
                live_display.stop()
                # Clear screen and show goodbye message
                self.console.clear()
                self.console.print(
                    "👋 Thank you for using Intelligent Taxonomy Classification!",
                    style="bold blue",
                )
                self.console.print(
                    "🧠 Your memory classifications have been saved.", style="green"
                )

        except Exception as e:
            self.console.print(f"❌ Error: {e}", style="red")
            sys.exit(1)


def main():
    """Main entry point."""
    app = TaxonomyApp()
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

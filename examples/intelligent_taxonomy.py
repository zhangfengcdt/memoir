#!/usr/bin/env python3
"""
Split console app for Intelligent Taxonomy Classification system with real LLM.
Features three panels: conversations (top-left), memory decisions (bottom-left), and current memories (right).

Usage:
    # Run with demo scenarios (default settings)
    python examples/intelligent_taxonomy.py

    # Run with conversation JSON file (specific session)
    python examples/intelligent_taxonomy.py --json-file /path/to/conversation.json --person Caroline --session 1

    # Run with all sessions randomly mixed
    python examples/intelligent_taxonomy.py --json-file /path/to/conversation.json --person Caroline

    # Control memory aggressiveness (conservative - only high-confidence memories)
    python examples/intelligent_taxonomy.py --high-threshold 0.9 --medium-threshold 0.7 --low-threshold 0.5

    # Aggressive mode (stores almost everything)
    python examples/intelligent_taxonomy.py --high-threshold 0.6 --medium-threshold 0.3 --low-threshold 0.0
"""

import argparse
import asyncio
import json
import os
import signal
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

    def __init__(
        self,
        json_file: Optional[str] = None,
        person_name: Optional[str] = None,
        session_num: Optional[int] = None,
        confidence_thresholds: Optional[dict[str, float]] = None,
        min_items_for_expansion: Optional[int] = None,
    ):
        self.console = Console()
        self.layout = Layout()
        self.conversations = []
        self.memory_decisions = []
        self.current_memories = []
        self.intelligent_classifier = None
        self.running = False
        self.current_processing = None  # Track what input is being processed
        self.demo_waiting_for_input = False  # Track if waiting for demo continuation
        self.last_update_hash = (
            None  # Track content changes to avoid unnecessary updates
        )
        self.live_display = None  # Store live display reference for manual refresh
        self.interrupt_requested = (
            False  # Track if user wants to enter interactive mode
        )

        # Store JSON conversation data if provided
        self.json_file = json_file
        self.person_name = person_name
        self.session_num = session_num
        self.conversation_data = None

        # Store classifier configuration
        self.confidence_thresholds = confidence_thresholds or {
            "high": 0.8,
            "medium": 0.5,
            "low": 0.0,
        }
        self.min_items_for_expansion = min_items_for_expansion or 1

        # Load conversation data if provided
        if json_file:
            self.load_conversation_data()

        # Setup layout
        self.setup_layout()

    def load_conversation_data(self):
        """Load conversation data from JSON file."""
        try:
            with open(self.json_file) as f:
                content = f.read()
                # Handle potential extra data at the end of JSON
                # Find the first complete JSON object
                brace_count = 0
                end_pos = 0
                for i, char in enumerate(content):
                    if char == "{":
                        brace_count += 1
                    elif char == "}":
                        brace_count -= 1
                        if brace_count == 0:
                            end_pos = i + 1
                            break

                # Parse just the first JSON object
                data = json.loads(content[:end_pos])

            # Extract conversation data
            if "conversation" in data:
                conv = data["conversation"]

                # Find all available sessions
                available_sessions = []
                for key in conv:
                    if key.startswith("session_") and not key.endswith("_date_time"):
                        session_num = key.replace("session_", "")
                        if session_num.isdigit():
                            available_sessions.append(int(session_num))

                available_sessions.sort()

                if self.session_num is None:
                    # No session specified - use all sessions randomly
                    import random

                    all_sessions_data = []

                    for session_id in available_sessions:
                        session_data = conv.get(f"session_{session_id}", [])
                        if session_data:  # Only include sessions with actual data
                            all_sessions_data.extend(session_data)

                    # Shuffle all exchanges randomly
                    random.shuffle(all_sessions_data)

                    self.conversation_data = {
                        "speaker_a": conv.get("speaker_a", "Unknown"),
                        "speaker_b": conv.get("speaker_b", "Unknown"),
                        "session": all_sessions_data,
                        "date_time": "Mixed sessions (randomized)",
                        "sessions_used": available_sessions,
                    }

                    self.console.print(
                        f"⏺ Loaded conversation from {self.json_file}", style="white"
                    )
                    self.console.print(
                        f"   ⏺ Random mode: {self.conversation_data['speaker_a']} and {self.conversation_data['speaker_b']}",
                        style="white",
                    )
                    self.console.print(
                        f"   ⏺ Using sessions: {available_sessions} (randomized)",
                        style="white",
                    )
                    self.console.print(
                        f"   ⏺ Total exchanges: {len(self.conversation_data['session'])}",
                        style="white",
                    )

                else:
                    # Specific session requested
                    self.conversation_data = {
                        "speaker_a": conv.get("speaker_a", "Unknown"),
                        "speaker_b": conv.get("speaker_b", "Unknown"),
                        "session": conv.get(f"session_{self.session_num}", []),
                        "date_time": conv.get(
                            f"session_{self.session_num}_date_time", "Unknown time"
                        ),
                    }

                    self.console.print(
                        f"⏺ Loaded conversation from {self.json_file}", style="white"
                    )
                    self.console.print(
                        f"   ⏺ Session {self.session_num}: {self.conversation_data['speaker_a']} and {self.conversation_data['speaker_b']}",
                        style="white",
                    )
                    self.console.print(
                        f"   ⏺ Date/Time: {self.conversation_data['date_time']}",
                        style="white",
                    )
                    self.console.print(
                        f"   ⏺ Total exchanges: {len(self.conversation_data['session'])}",
                        style="white",
                    )
                    self.console.print(
                        f"   info: Available sessions: {available_sessions}",
                        style="white",
                    )
            else:
                self.console.print(
                    f"⏺ No conversation data found in {self.json_file}", style="white"
                )
        except Exception as e:
            self.console.print(f"⏺ Error loading JSON file: {e}", style="white")
            sys.exit(1)

    def setup_layout(self):
        """Setup the four-panel layout with parameter display at top."""
        # Create main layout with parameter display at top
        self.layout.split_column(
            Layout(
                name="params", size=5
            ),  # Small top panel for parameters (3 lines + borders)
            Layout(name="main", ratio=1),  # Main content area
        )

        # Split main area into left and right
        self.layout["main"].split_row(
            Layout(name="left", ratio=2), Layout(name="right", ratio=3)
        )

        # Split left side into conversations and decisions - give more space to conversations
        self.layout["left"].split_column(
            Layout(name="conversations", ratio=3), Layout(name="decisions", ratio=2)
        )

        # Set initial content
        self.update_params_panel()  # Initialize params panel

        self.layout["conversations"].update(
            Panel(
                "⏺ Conversations\n\nWaiting for input...",
                title="Conversations",
                border_style="white",
            )
        )

        self.layout["decisions"].update(
            Panel(
                "⏺ Memory Decisions\n\nNo decisions yet...",
                title="Memory Processing",
                border_style="white",
            )
        )

        self.layout["right"].update(
            Panel(
                "⏺ Current Memories\n\nNo memories stored...",
                title="Memory Structure",
                border_style="white",
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

        # Create intelligent classifier with configurable parameters
        self.intelligent_classifier = IntelligentClassifier(
            llm=llm,
            memory_store=store,
            taxonomy_version=TaxonomyVersion.GENERAL,
            confidence_thresholds=self.confidence_thresholds,
            min_items_for_expansion=self.min_items_for_expansion,
        )

        # Show the current configuration
        self.console.print(
            f"   ⏺ Confidence thresholds: high={self.confidence_thresholds['high']}, medium={self.confidence_thresholds['medium']}, low={self.confidence_thresholds['low']}",
            style="white",
        )
        self.console.print(
            f"   ⏺ Min items for expansion: {self.min_items_for_expansion}",
            style="white",
        )

    def get_cursor_text(self):
        """Get static cursor character."""
        return "█"  # Static cursor, no blinking

    def update_params_panel(self):
        """Update the parameters display panel."""
        # Build compact parameter display
        lines = []

        # Show key configuration parameters in a compact format
        config_items = []

        # File/session info
        if self.json_file:
            filename = self.json_file.split("/")[
                -1
            ]  # Just show filename, not full path
            config_items.append(f"⏺ File: {filename}")
        if self.person_name:
            config_items.append(f"⏺ Person: {self.person_name}")
        if self.session_num is None:
            config_items.append("⏺ Sessions: Random")
        else:
            config_items.append(f"⏺ Session: {self.session_num}")

        # Confidence thresholds in compact format
        thresholds = f"⏺ Thresholds: H:{self.confidence_thresholds['high']}/M:{self.confidence_thresholds['medium']}/L:{self.confidence_thresholds['low']}"
        config_items.append(thresholds)

        # Expansion setting
        if self.min_items_for_expansion != 1:
            config_items.append(f"⏺ Min-expand: {self.min_items_for_expansion}")

        # Split into two lines if we have many items
        if len(config_items) <= 3:
            lines.append("  ".join(config_items))
        else:
            # Split into two lines
            mid = len(config_items) // 2
            lines.append("  ".join(config_items[:mid]))
            lines.append("  ".join(config_items[mid:]))

        # Add aggressiveness indicator
        if self.confidence_thresholds["low"] >= 0.5:
            mode = "⏺ Conservative (selective)"
        elif (
            self.confidence_thresholds["low"] == 0.0
            and self.confidence_thresholds["high"] >= 0.8
        ):
            mode = "⏺ Balanced (default)"
        else:
            mode = "⏺ Aggressive (stores more)"

        lines.append(f"Memory Mode: {mode}")

        content = "\n".join(lines)
        text_obj = Text(content)
        self.layout["params"].update(
            Panel(text_obj, title="Configuration", border_style="white")
        )

    def update_conversations_panel(self):
        """Update the conversations panel."""

        if not self.conversations:
            cursor = self.get_cursor_text()
            content = f"⏺ Conversations\n\nWaiting for input...{cursor}"
        else:
            # Calculate conversations to show based on actual panel space
            console_height = self.console.size.height
            console_width = self.console.size.width

            # Conversations panel gets half the left side height, and left side is 2/5 of total width
            # So conversations gets roughly 1/4 of total screen height
            available_lines = max(
                12,
                (console_height - 5)
                // 2,  # Subtract 5 for params panel, divide by 2 for half of remaining
            )
            # Account for panel borders and headers (about 4 lines)
            content_lines = available_lines - 4
            # Be more conservative with conversation count to avoid cutting off
            max_conversations = max(
                1, content_lines // 4
            )  # 4 lines per conversation to be safe

            lines = [f"⏺ Conversations ({len(self.conversations)} total)"]

            # Always show the most recent conversations
            start_idx = max(0, len(self.conversations) - max_conversations)
            recent_conversations = self.conversations[start_idx:]

            # Add scroll indicator if there are more conversations
            if start_idx > 0:
                lines.append(
                    f"⏺ (last {len(recent_conversations)} of {len(self.conversations)} shown)"
                )

            lines.append("")  # Empty line after header

            for i, conv in enumerate(recent_conversations):
                speaker = conv.get("speaker", "User")
                conv_content = conv.get("content", "")
                timestamp = conv.get("timestamp", "")

                conv_number = start_idx + i + 1
                if timestamp:
                    lines.append(f"[{conv_number}] [{timestamp}] {speaker}:")
                else:
                    lines.append(f"[{conv_number}] {speaker}:")

                # Improve text wrapping to use available width better
                # Left panel gets 2/5 of total width, so calculate usable width
                left_panel_width = max(50, (console_width * 2) // 5)
                # Account for panel borders, icons, and indentation
                usable_width = left_panel_width - 10

                # Smart text wrapping
                if len(conv_content) > usable_width:
                    # Break long content into chunks
                    words = conv_content.split()
                    current_line = "  ⏺ "

                    for word in words:
                        # Check if adding this word would exceed the width
                        if len(current_line + " " + word) > usable_width:
                            lines.append(current_line)
                            current_line = "      " + word  # Continuation indent
                        else:
                            if current_line == "  ⏺ ":
                                current_line += word
                            else:
                                current_line += " " + word

                    # Add the final line if it has content
                    if current_line.strip() and current_line != "      ":
                        lines.append(current_line)
                else:
                    lines.append(f"  ⏺ {conv_content}")

                lines.append("")  # Empty line for spacing

            # Add cursor at the end if waiting for input
            if not self.current_processing and not self.demo_waiting_for_input:
                cursor = self.get_cursor_text()
                lines.append(f"⏺ Ready for input...{cursor}")

            content = "\n".join(lines)

        # Create a text object for better rendering
        text_obj = Text(content)
        self.layout["conversations"].update(
            Panel(text_obj, title="Conversations", border_style="white")
        )

    def update_decisions_panel(self):
        """Update the memory decisions panel."""
        if not self.memory_decisions and not self.current_processing:
            content = "⏺ Memory Decisions\n\nNo decisions yet..."
        else:
            lines = ["⏺ Memory Decisions\n"]

            if self.memory_decisions:
                # Calculate how many decisions to show based on available height
                console_height = self.console.size.height
                # Memory processing panel gets 2/5 of left side height (ratio 2 out of 5)
                # And left side gets half of main area (after params panel)
                available_lines = max(8, ((console_height - 5) * 2) // 5)
                # Each decision takes about 8-10 lines, show as many as fit
                max_decisions = max(
                    1, (available_lines - 5) // 9
                )  # Be more conservative

                # Show recent decisions up to the limit
                recent_decisions = self.memory_decisions[-max_decisions:]

                lines.append(
                    f"⏺ Total Memories: {self.memory_decisions[-1].get('memory_count', 0)}"
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
                        "⏺ Memory-worthy"
                        if classification.get("is_memory", False)
                        else "⏺ Not memory-worthy"
                    )
                    lines.append(f"   {memory_worthy}")

                    # Path and confidence
                    if classification.get("path"):
                        lines.append(f"   ⏺ Path: {classification.get('path')}")
                        lines.append(
                            f"   ⏺ Confidence: {classification.get('confidence', 0.0):.2f}"
                        )

                    # Actions
                    action = classification.get("suggested_action", "UNKNOWN")
                    storage_action = storage.get("action", "unknown")
                    lines.append(f"   ⏺ Classification: {action}")
                    lines.append(f"   ⏺ Storage: {storage_action}")

                    # Reasoning if available
                    if classification.get("reasoning"):
                        reasoning = classification.get("reasoning", "")[:100]
                        lines.append(f"   ⏺ Reasoning: {reasoning}...")

                    lines.append("")  # Space between decisions

            # Show what's currently being processed at the end
            if self.current_processing:
                lines.append("⏺ Currently Processing:")
                lines.append(
                    f'   ⏺ "{self.current_processing[:40]}{"..." if len(self.current_processing) > 40 else ""}"'
                )
                lines.append("   ⏺ REAL LLM CALL: Processing with GPT-4o-mini...")

            content = "\n".join(lines)

        # Create text object for decisions panel
        text_obj = Text(content)
        self.layout["decisions"].update(
            Panel(text_obj, title="Memory Processing", border_style="white")
        )

    def update_memories_panel(self):
        """Update the current memories panel."""
        if not self.intelligent_classifier:
            content = "⏺ Current Memories\n\nClassifier not ready..."
        else:
            # Get all stored memories to show full tree structure
            stored_memories = self.intelligent_classifier.get_stored_memories(limit=100)

            if not stored_memories:
                content = "⏺ Current Memories\n\nNo memories stored..."
            else:
                # Create tree structure
                tree = Tree("⏺ Memory Structure")

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
                                node_title = f"⏺ {key.title()} ({total_count})"
                            else:
                                node_title = (
                                    f"⏺ {key.replace('_', ' ').title()} ({total_count})"
                                )

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
                                branch_node.add(f"⏺ {memory['path']}: {preview}")

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
                content = f"⏺ Current Memories ({len(stored_memories)} total)\n\n"
                content += self._tree_to_string(tree)

        # Create text object for memory structure panel
        text_obj = Text(content)
        self.layout["right"].update(
            Panel(text_obj, title="Memory Structure", border_style="white")
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

    def update_display(self, force_update=False, panels_to_update=None):
        """Update panels selectively to avoid color flashing."""
        # Generate hashes for each panel separately
        state_data = {
            "params": {
                "thresholds": self.confidence_thresholds,
                "json_file": self.json_file,
                "person_name": self.person_name,
                "session_num": self.session_num,
            },
            "conversations": {
                "count": len(self.conversations),
                "current_processing": self.current_processing,
                "demo_waiting": self.demo_waiting_for_input,
            },
            "decisions": {
                "count": len(self.memory_decisions),
                "current_processing": self.current_processing,
                "demo_waiting": self.demo_waiting_for_input,
            },
            "memories": {
                "count": (
                    len(self.current_memories)
                    if hasattr(self, "current_memories")
                    else 0
                ),
            },
        }

        import hashlib

        # Initialize panel hashes if not exists
        if not hasattr(self, "panel_hashes"):
            self.panel_hashes = {}

        # Check which panels need updating
        panels_needing_update = set()

        for panel_name, panel_data in state_data.items():
            current_hash = hashlib.md5(str(panel_data).encode()).hexdigest()

            if force_update or current_hash != self.panel_hashes.get(panel_name):
                panels_needing_update.add(panel_name)
                self.panel_hashes[panel_name] = current_hash

        # If specific panels requested, only update those
        if panels_to_update:
            panels_needing_update = panels_needing_update.intersection(
                set(panels_to_update)
            )

        # Update only the panels that need it
        updated_any = False
        if "params" in panels_needing_update:
            self.update_params_panel()
            updated_any = True
        if "conversations" in panels_needing_update:
            self.update_conversations_panel()
            updated_any = True
        if "decisions" in panels_needing_update:
            self.update_decisions_panel()
            updated_any = True
        if "memories" in panels_needing_update:
            self.update_memories_panel()
            updated_any = True

        # Manually refresh display only if we updated something
        if updated_any and hasattr(self, "live_display") and self.live_display:
            self.live_display.refresh()

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
        self.update_display(force_update=True)

        # Set current processing indicator
        self.current_processing = content
        self.update_display(force_update=True)  # Show processing status

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
        self.update_display(force_update=True)

        return result

    def show_demo_completion(self):
        """Show demo completion message in the decisions panel."""
        lines = [
            "⏺ Demo Completed Successfully!",
            "",
            "⏺ All 7 scenarios processed",
            "⏺ Classification actions demonstrated:",
            "   • SKIP (greetings)",
            "   • CLASSIFY (clear classifications)",
            "   • EXPAND (new categories needed)",
            "   • USE_PARENT (generic categories)",
            "",
            "⏺ Memory actions demonstrated:",
            "   • STORE (new memories)",
            "   • REPLACE (updated info)",
            "   • APPEND (additional info)",
            "   • MERGE (combined content)",
            "",
            "⏺ You can now:",
            "   • Type messages to classify interactively",
            "   • Type 'demo' to run demo again",
            "   • Type 'quit' to exit",
            "   • Press any key to continue...",
        ]

        content = "\n".join(lines)
        text_obj = Text(content)
        self.layout["decisions"].update(
            Panel(text_obj, title="⏺ Demo Complete", border_style="white")
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
            # Check if user wants to interrupt
            if self.interrupt_requested:
                self.console.print(
                    "\n⏺ Switching to interactive mode...", style="white"
                )
                self.interrupt_requested = False
                return  # Exit demo early

            await self.process_conversation(
                scenario["content"],
                scenario["speaker"],
                {"demo_step": i + 1, "description": scenario["description"]},
            )
            await asyncio.sleep(2)  # Pause between scenarios to see updates

        # Demo completed - show completion message
        self.show_demo_completion()

    def get_user_input(self, prompt_text: str = "⏺ Enter your message") -> str:
        """Get user input using Rich prompt outside of Live display."""
        try:
            return Prompt.ask(prompt_text).strip()
        except (EOFError, KeyboardInterrupt):
            return "quit"

    def wait_for_continue_input(self):
        """Wait for user to press any key to continue after demo completion."""
        # Update the decisions panel to show waiting message
        lines = [
            "⏺ Demo Completed Successfully!",
            "",
            "⏺ All 7 scenarios processed",
            "⏺ Classification actions demonstrated:",
            "   • SKIP (greetings)",
            "   • CLASSIFY (clear classifications)",
            "   • EXPAND (new categories needed)",
            "   • USE_PARENT (generic categories)",
            "",
            "⏺ Memory actions demonstrated:",
            "   • STORE (new memories)",
            "   • REPLACE (updated info)",
            "   • APPEND (additional info)",
            "   • MERGE (combined content)",
            "",
            "⏺ After continuing, you can:",
            "   • Type messages to classify interactively",
            "   • Type 'demo' to run demo again",
            "   • Type 'quit' to exit",
        ]

        content = "\n".join(lines)
        text_obj = Text(content)
        self.layout["decisions"].update(
            Panel(text_obj, title="⏺ Demo Complete", border_style="white")
        )

        # Store the current state for resuming
        self.demo_waiting_for_input = True

    async def process_conversation_from_json(self):
        """Process conversation data from JSON file."""
        if not self.conversation_data:
            return

        self.console.print(
            f"\n⏺ Processing conversation for {self.person_name}...", style="white"
        )

        # Filter conversations for the specified person
        person_messages = []
        for exchange in self.conversation_data["session"]:
            if exchange.get("speaker") == self.person_name:
                # Extract the person's message and any context
                message = exchange.get("text", "")

                # Add image context if present
                if "img_url" in exchange:
                    caption = exchange.get("blip_caption", "")
                    if caption:
                        message += f" [Context: Shared image of {caption}]"

                person_messages.append(
                    {"dia_id": exchange.get("dia_id", ""), "text": message}
                )

        # Process each message as a potential memory
        for msg in person_messages:
            # Check if user wants to interrupt
            if self.interrupt_requested:
                self.console.print(
                    "\n⏺ Switching to interactive mode...", style="white"
                )
                self.interrupt_requested = False
                return  # Exit JSON processing early

            self.console.print(f"\n⏺ Processing: {msg['text'][:100]}...", style="white")
            await self.process_conversation(msg["text"])
            await asyncio.sleep(0.5)  # Brief pause between messages

        self.console.print(
            f"\n⏺ Processed {len(person_messages)} messages from {self.person_name}",
            style="white",
        )

    async def interactive_mode(self, live_display):
        """Run interactive mode where user can input conversations."""
        try:
            # If JSON data is loaded, process it first
            if self.conversation_data:
                await asyncio.sleep(1)
                await self.process_conversation_from_json()

                # Only wait if not interrupted
                if not self.interrupt_requested:
                    self.wait_for_continue_input()
            else:
                # Start with demo automatically to show functionality
                await asyncio.sleep(1)
                await self.run_demo_scenarios()

                # Only wait if not interrupted
                if not self.interrupt_requested:
                    self.wait_for_continue_input()

            # Clear interrupt flag if it was set
            if self.interrupt_requested:
                self.interrupt_requested = False

            # Exit live display to get input cleanly
            live_display.stop()

            # Clear demo completion state immediately
            if self.demo_waiting_for_input:
                self.demo_waiting_for_input = False
                self.update_display(force_update=True)  # Clear demo completion message

            # Restart live display
            live_display.start()

            # Interactive loop
            while self.running:
                try:
                    # Exit live display for clean input
                    live_display.stop()

                    # Get user input with Rich prompt (no extra blank lines)
                    user_input = self.get_user_input(
                        "⏺ Enter your message (or 'demo'/'quit')"
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
                        self.update_display(force_update=True)
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
                                f"⏺ Error processing input: {e}", style="white"
                            )
                            input("\nPress Enter to continue...")
                            live_display.start()

                except (KeyboardInterrupt, EOFError):
                    break

        finally:
            # Ensure cursor is visible when exiting
            self.console.show_cursor(True)

        self.running = False

    def cleanup_terminal(self):
        """Clean up terminal state - used by signal handlers."""
        try:
            if hasattr(self, "live_display") and self.live_display:
                self.live_display.stop()
            if hasattr(self, "console"):
                self.console.show_cursor(True)
            # Stop keyboard monitoring thread if it exists
            if hasattr(self, "keyboard_thread_stop"):
                self.keyboard_thread_stop = True
        except Exception:
            pass

    async def run(self):
        """Run the taxonomy app with live display."""

        # Setup signal handlers for proper terminal cleanup
        def handle_suspend(signum, frame):  # noqa: ARG001
            """Handle Ctrl+Z (SIGTSTP) to properly suspend."""
            self.cleanup_terminal()
            # Re-raise the signal to actually suspend
            signal.signal(signal.SIGTSTP, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGTSTP)
            # When resumed, restore our handler and restart display
            signal.signal(signal.SIGTSTP, handle_suspend)
            if hasattr(self, "live_display") and self.live_display:
                self.live_display.start()

        def handle_interrupt(signum, frame):  # noqa: ARG001
            r"""Handle Ctrl+\ (SIGQUIT) to enter interactive mode."""
            self.interrupt_requested = True
            self.console.print(
                "\n⏺ Interactive mode requested (Ctrl+\\)...", style="white"
            )

        # Install signal handlers (Unix/Linux/Mac only)
        if hasattr(signal, "SIGTSTP"):
            signal.signal(signal.SIGTSTP, handle_suspend)
        if hasattr(signal, "SIGQUIT"):
            signal.signal(signal.SIGQUIT, handle_interrupt)

        try:
            # Setup classifier
            await self.setup_classifier()

            # Show startup message
            self.console.print(
                "\n⏺ Intelligent Taxonomy Classification App", style="white"
            )
            self.console.print("=" * 60)
            self.console.print("⏺ LLM classifier ready", style="white")
            self.console.print("⏺ Memory store initialized", style="white")
            self.console.print("⏺ Live display active", style="white")
            self.console.print("\n⏺ Starting demo automatically...", style="white")
            self.console.print(
                "⏺ Press Ctrl+\\ anytime to skip to interactive mode",
                style="white",
            )
            self.console.print(
                "⏺ After demo: type messages to classify, 'demo' to repeat, or 'quit' to exit",
                style="white",
            )

            # Create and start live display with minimal refresh rate to prevent color flashing
            self.live_display = Live(
                self.layout,
                console=self.console,
                refresh_per_second=1,  # Very low refresh rate
                auto_refresh=False,  # Disable automatic refresh - we control it manually
            )
            self.live_display.start()

            self.running = True
            # Initial display update
            self.update_display(force_update=True)

            try:
                # Start interactive mode with live display control
                await self.interactive_mode(self.live_display)
            finally:
                self.live_display.stop()
                # Ensure cursor is visible
                self.console.show_cursor(True)
                # Clear screen and show goodbye message
                self.console.clear()
                self.console.print(
                    "⏺ Thank you for using Intelligent Taxonomy Classification!",
                    style="white",
                )
                self.console.print(
                    "⏺ Your memory classifications have been saved.", style="white"
                )

        except Exception as e:
            # Ensure cursor is visible even on error
            self.console.show_cursor(True)
            self.console.print(f"⏺ Error: {e}", style="white")
            sys.exit(1)


def main():
    """Main entry point."""
    # Store original terminal settings for restoration
    import termios

    try:
        original_terminal_settings = termios.tcgetattr(sys.stdin)
    except Exception:
        original_terminal_settings = None

    def restore_terminal():
        """Restore terminal to original state."""
        try:
            # Show cursor
            print("\033[?25h", end="", flush=True)
            # Restore terminal settings if we have them
            if original_terminal_settings:
                termios.tcsetattr(
                    sys.stdin, termios.TCSANOW, original_terminal_settings
                )
        except Exception:
            pass

    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description="Intelligent Taxonomy Demo with conversation processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with all sessions randomly mixed:
  python examples/intelligent_taxonomy.py --json-file conversation.json --person Caroline

  # Run with specific session:
  python examples/intelligent_taxonomy.py --json-file conversation.json --person Caroline --session 1

  # Conservative memory settings (only high-confidence memories):
  python examples/intelligent_taxonomy.py --high-threshold 0.9 --medium-threshold 0.7 --low-threshold 0.5

  # Aggressive memory settings (stores almost everything):
  python examples/intelligent_taxonomy.py --high-threshold 0.6 --medium-threshold 0.3 --low-threshold 0.0
        """,
    )

    # Conversation processing arguments
    parser.add_argument("--json-file", type=str, help="Path to conversation JSON file")
    parser.add_argument(
        "--person",
        type=str,
        help="Name of person to create memories for (e.g., Caroline or Melanie)",
    )
    parser.add_argument(
        "--session",
        type=int,
        default=None,
        help="Session number to process (default: None = all sessions randomly)",
    )

    # Memory aggressiveness control arguments
    parser.add_argument(
        "--high-threshold",
        type=float,
        default=0.8,
        help="High confidence threshold (0.0-1.0, default: 0.8). Higher = more selective",
    )
    parser.add_argument(
        "--medium-threshold",
        type=float,
        default=0.5,
        help="Medium confidence threshold (0.0-1.0, default: 0.5). Higher = more selective",
    )
    parser.add_argument(
        "--low-threshold",
        type=float,
        default=0.0,
        help="Low confidence threshold (0.0-1.0, default: 0.0). Higher = more selective",
    )
    parser.add_argument(
        "--min-expansion",
        type=int,
        default=1,
        help="Minimum items before taxonomy expansion (default: 1). Higher = less expansion",
    )

    args = parser.parse_args()

    # Validate arguments
    if args.json_file and not args.person:
        print("⏺ Error: --person is required when using --json-file")
        sys.exit(1)

    # Validate threshold ordering
    if not (args.low_threshold <= args.medium_threshold <= args.high_threshold):
        print("⏺ Error: Thresholds must be ordered: low <= medium <= high")
        sys.exit(1)

    # Build confidence thresholds from arguments
    confidence_thresholds = {
        "high": args.high_threshold,
        "medium": args.medium_threshold,
        "low": args.low_threshold,
    }

    # Create app with arguments
    app = TaxonomyApp(
        json_file=args.json_file,
        person_name=args.person,
        session_num=args.session,
        confidence_thresholds=confidence_thresholds,
        min_items_for_expansion=args.min_expansion,
    )

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        restore_terminal()
        print("\n\n⏺ Goodbye!")
    except Exception as e:
        restore_terminal()
        print(f"\n⏺ Error: {e}")
        sys.exit(1)
    finally:
        restore_terminal()


if __name__ == "__main__":
    main()

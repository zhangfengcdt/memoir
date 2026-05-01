# SPDX-License-Identifier: Apache-2.0
"""
Utility handler for common helper functions and data processing utilities.
"""

import json

from .api_handler import BaseAPIHandler


class UtilityHandler(BaseAPIHandler):
    """Handler for utility functions and common data processing operations."""

    def extract_memory_content(self, data):
        """Extract meaningful content from memory data structure."""
        if isinstance(data, str):
            return data

        if isinstance(data, dict):
            # Try different extraction strategies
            if (
                "memories" in data
                and isinstance(data["memories"], list)
                and len(data["memories"]) > 0
            ):
                memory_item = data["memories"][0]
                if "content" in memory_item:
                    content_obj = memory_item["content"]
                    if isinstance(content_obj, dict):
                        # Look for actual content
                        for key in [
                            "content",
                            "raw_text",
                            "original_content",
                            "description",
                        ]:
                            if content_obj.get(key):
                                return str(content_obj[key])
                        # Look in structured_data
                        if "structured_data" in content_obj:
                            structured = content_obj["structured_data"]
                            if isinstance(structured, dict):
                                for key in [
                                    "original_content",
                                    "content",
                                    "description",
                                ]:
                                    if structured.get(key):
                                        return str(structured[key])
                    elif isinstance(content_obj, str):
                        return content_obj

            # Direct field access
            for field in ["content", "raw_text", "description", "summary"]:
                if data.get(field):
                    return str(data[field])

        return str(data) if data else ""

    def extract_diff_content(self, value_data):
        """Extract human-readable content from diff value data."""
        if not value_data:
            return "No content"

        try:
            # Try to decode if it's bytes
            if isinstance(value_data, bytes):
                decoded_data = value_data.decode("utf-8")
            else:
                decoded_data = str(value_data)

            # Try to parse as JSON to get structured data
            try:
                data = json.loads(decoded_data)
                # Use existing content extraction method
                return self.extract_memory_content(data)
            except (json.JSONDecodeError, TypeError):
                # If not JSON, return as-is (truncated for display)
                content = decoded_data.strip()
                if len(content) > 200:
                    return content[:200] + "..."
                return content

        except Exception as e:
            print(f"Error extracting diff content: {e}")
            return f"Error reading content: {e}"

    def extract_timeline_content(self, data, date_str):
        """Extract timeline content from various data structure formats."""
        if not data:
            return ""

        # Try different extraction strategies
        content = ""

        if isinstance(data, dict):
            # NEW Strategy: Handle the memory store format with "memories" array
            if (
                "memories" in data
                and isinstance(data["memories"], list)
                and len(data["memories"]) > 0
            ):
                # Get the first (and usually only) memory from the array
                memory_item = data["memories"][0]

                if "content" in memory_item and isinstance(
                    memory_item["content"], dict
                ):
                    content_obj = memory_item["content"]

                    # Priority 1: raw_text (this contains the actual description)
                    content = content_obj.get("raw_text", "")
                    if content and content.strip():
                        return content.strip()

                    # Priority 2: structured_data -> original_content
                    if "structured_data" in content_obj:
                        structured = content_obj["structured_data"]
                        if isinstance(structured, dict):
                            content = structured.get("original_content", "")
                            if content and content.strip():
                                return content.strip()

                            content = structured.get("timeline_content", "")
                            if content and content.strip():
                                return content.strip()

            # OLD Strategy 1: Check if it's the old format with nested content
            if "content" in data and isinstance(data["content"], dict):
                timeline_data_obj = data["content"]

                # Priority 1: original_content from structured_data
                if "structured_data" in timeline_data_obj:
                    structured = timeline_data_obj["structured_data"]
                    if isinstance(structured, dict):
                        content = structured.get("original_content", "")
                        if content:
                            return content

                        content = structured.get("timeline_content", "")
                        if content:
                            return content

                # Priority 2: raw_text
                content = timeline_data_obj.get("raw_text", "")
                if content:
                    return content

            # Strategy 3: Direct fields
            for field in [
                "raw_text",
                "timeline_content",
                "original_content",
                "summary",
                "description",
            ]:
                if data.get(field):
                    content = str(data[field])
                    return content

        elif isinstance(data, str):
            return data

        # Last resort: convert to string and hope for the best
        content = str(data) if data else ""
        return content

    def extract_location_content(self, data, location_key):
        """Extract location content from various data structure formats."""
        if not data:
            return ""

        # Try different extraction strategies
        content = ""

        if isinstance(data, dict):
            # NEW Strategy: Handle the memory store format with "memories" array
            if (
                "memories" in data
                and isinstance(data["memories"], list)
                and len(data["memories"]) > 0
            ):
                # Get the first (and usually only) memory from the array
                memory_item = data["memories"][0]

                if "content" in memory_item and isinstance(
                    memory_item["content"], dict
                ):
                    content_obj = memory_item["content"]

                    # Priority 1: raw_text (this contains the actual description)
                    content = content_obj.get("raw_text", "")
                    if content and content.strip():
                        return content.strip()

                    # Priority 2: structured_data -> location_content
                    if "structured_data" in content_obj:
                        structured = content_obj["structured_data"]
                        if isinstance(structured, dict):
                            content = structured.get("location_content", "")
                            if content and content.strip():
                                return content.strip()

            # Strategy 3: Direct fields
            for field in [
                "raw_text",
                "location_content",
                "summary",
                "description",
            ]:
                if data.get(field):
                    content = str(data[field])
                    return content

        elif isinstance(data, str):
            return data

        # Last resort: convert to string and hope for the best
        content = str(data) if data else ""
        return content

    def format_key_as_path(self, key):
        """Format a ProllyTree key as a semantic path."""
        # Remove namespace prefix and convert to dot notation
        if ":" in key:
            parts = key.split(":")
            # Skip namespace parts and join the rest with dots
            if len(parts) > 1:
                return ".".join(parts[1:])
        return key

    def parse_prollytree_value(self, value):
        """Parse a value from ProllyTree store."""
        try:
            # If it's bytes, decode it
            if isinstance(value, bytes):
                value = value.decode("utf-8")

            # Try to parse as JSON
            if isinstance(value, str):
                try:
                    data = json.loads(value)
                    return self.parse_memory_content(json.dumps(data))
                except json.JSONDecodeError:
                    return str(value)[:200]

            # If it's already a dict or other type
            if isinstance(value, dict):
                if "content" in value:
                    return str(value["content"])
                elif "memories" in value and isinstance(value["memories"], list):
                    # Aggregated memory
                    memories = value["memories"][:3]
                    content_parts = []
                    for memory in memories:
                        if isinstance(memory, dict) and "content" in memory:
                            content_parts.append(str(memory["content"])[:100])
                    return " | ".join(content_parts) if content_parts else str(value)

            return str(value)[:200] if value else ""

        except Exception:
            return str(value)[:200] if value else ""

    def parse_memory_content(self, raw_content):
        """Parse memory content from JSON file."""
        try:
            data = json.loads(raw_content)

            # Extract meaningful content from the memory data
            if isinstance(data, dict):
                if "content" in data:
                    return str(data["content"])
                elif "memories" in data and isinstance(data["memories"], list):
                    # Aggregated memory - show first few entries
                    memories = data["memories"][:3]  # Show first 3
                    content_parts = []
                    for memory in memories:
                        if isinstance(memory, dict) and "content" in memory:
                            content_parts.append(str(memory["content"])[:100])
                    return " | ".join(content_parts) if content_parts else str(data)
                else:
                    return str(data)
            else:
                return str(data)

        except Exception:
            # If not valid JSON or other error, return raw content truncated
            return str(raw_content)[:200] if raw_content else ""

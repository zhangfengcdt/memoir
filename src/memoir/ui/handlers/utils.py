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
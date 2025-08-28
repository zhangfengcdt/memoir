"""
Profile Memento for User Profile Generation and Management.

Handles profile serialization, summary generation, and profile updates.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ProfileMemento:
    """Manages user profile data and generates profile summaries."""

    def __init__(self, memory_store):
        """Initialize profile memento with memory store."""
        self.memory_store = memory_store

    async def apply_profile_updates(
        self,
        profile_updates: list[dict[str, str]],
        metadata: Optional[dict] = None,
        namespace: str = "default",
    ) -> None:
        """
        Apply profile updates to the memory store.

        Args:
            profile_updates: List of profile updates with path and value
            metadata: Optional metadata to include with updates
            namespace: Namespace to store the profile updates in (default: "default")
        """
        if not profile_updates:
            return

        for update in profile_updates:
            path = update.get("path", "")
            value = update.get("value", "")

            if not path or not value:
                logger.warning(f"Invalid profile update: {update}")
                continue

            # Check if this is a profile path
            if not path.startswith("profile."):
                logger.warning(f"Non-profile path in profile update: {path}")
                continue

            # Store the profile update as a memory with special handling
            memory_data = {
                "raw_text": value,
                "summary": f"Profile update: {path.split('.')[-1]} = {value}",
                "structured_data": {
                    "profile_field": path,
                    "profile_value": value,
                    "update_type": "profile_update",
                },
                "memory_type": "profile_update",
            }

            # Store directly using the async method (consistent with timeline manager)
            await self.memory_store.store_memory_async(namespace, memory_data, path)
            logger.info(f"Applied profile update: {path} = {value}")

    async def get_profile_summary(self, llm=None, namespace: str = "default") -> str:
        """
        Generate a comprehensive profile summary from stored profile data.

        Args:
            llm: Optional LLM for generating narrative summary
            namespace: Namespace to search for profile data (default: "default")

        Returns:
            Profile summary string
        """
        try:
            # Search for all profile memories using the correct method signature
            # Use provided namespace string as expected by asearch method
            profile_memories = await self.memory_store.asearch(namespace, "profile.")

            # Debug: log what we found
            logger.debug(f"Found {len(profile_memories)} profile memories")

            # Limit results manually if needed
            if len(profile_memories) > 1000:
                profile_memories = profile_memories[:1000]

            if not profile_memories:
                return "No profile information available."

            # Organize profile data by category
            profile_data = self._organize_profile_data(profile_memories)

            # Generate summary
            if llm:
                return await self._generate_llm_summary(profile_data, llm)
            else:
                return self._generate_structured_summary(profile_data)

        except Exception as e:
            import traceback

            logger.error(f"Failed to generate profile summary: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return f"Error generating profile summary: {e}"

    def _organize_profile_data(
        self, profile_memories: list[tuple[str, Any]]
    ) -> dict[str, dict[str, str]]:
        """Organize profile memories into a structured hierarchy."""
        organized = {}

        for semantic_key, data in profile_memories:
            try:
                # Ensure semantic_key is a string
                if not isinstance(semantic_key, str):
                    logger.warning(
                        f"Non-string semantic key: {type(semantic_key)}: {semantic_key}"
                    )
                    semantic_key = str(semantic_key)

                # Handle the data format - it could be a MemoryItem dict or other format
                if isinstance(data, dict):
                    # Check if this is a MemoryItem structure with content field
                    if "content" in data and isinstance(data["content"], dict):
                        # This is a MemoryItem with content - extract the actual memory data
                        memory_data = data["content"]
                        structured_data = memory_data.get("structured_data", {})
                    else:
                        # This is the memory data directly
                        memory_data = data
                        structured_data = data.get("structured_data", {})
                else:
                    # If it's not a dict, try to extract meaningful data
                    logger.warning(
                        f"Unexpected data format for {semantic_key}: {type(data)}"
                    )
                    continue

                # Get the profile path and value
                profile_field = structured_data.get("profile_field")
                profile_value = structured_data.get("profile_value")
                update_type = structured_data.get("update_type")

                # Only process memories that are actual profile updates
                if update_type != "profile_update":
                    logger.debug(f"Skipping non-profile-update memory: {semantic_key}")
                    continue

                if not profile_field or not profile_value:
                    logger.warning(
                        f"Profile update memory missing field or value: {semantic_key}"
                    )
                    continue

                # Ensure profile_field is a string
                if not isinstance(profile_field, str):
                    logger.warning(
                        f"Non-string profile_field: {type(profile_field)}: {profile_field}"
                    )
                    profile_field = (
                        str(profile_field)
                        if profile_field is not None
                        else semantic_key
                    )

                if profile_field and profile_value:
                    # Convert profile_value to string if it's not already
                    if isinstance(profile_value, dict):
                        # If it's a dict, convert to JSON string
                        import json

                        profile_value_str = json.dumps(profile_value)
                    elif isinstance(profile_value, (list, tuple)):
                        # If it's a list/tuple, join as string
                        profile_value_str = ", ".join(str(x) for x in profile_value)
                    else:
                        profile_value_str = str(profile_value)

                    # Build nested dictionary structure
                    parts = profile_field.split(".")
                    current = organized

                    # Navigate to the correct nested position
                    for part in parts[:-1]:  # All except the last part
                        # Ensure part is a string
                        part = str(part) if part is not None else "unknown"
                        if part not in current:
                            current[part] = {}
                        current = current[part]

                    # Set the final value as string
                    final_key = str(parts[-1]) if parts[-1] is not None else "unknown"
                    current[final_key] = profile_value_str

            except Exception as e:
                logger.warning(f"Failed to process profile memory {semantic_key}: {e}")
                continue

        return organized

    def _generate_structured_summary(self, profile_data: dict[str, Any]) -> str:
        """Generate a structured text summary of profile data."""
        if not profile_data:
            return "No profile information available."

        summary_parts = ["=== USER PROFILE SUMMARY ===\n"]

        # Process each main category
        category_order = [
            ("personal", "Personal Information"),
            ("professional", "Professional Profile"),
            ("health", "Health & Wellness"),
            ("finance", "Financial Profile"),
            ("living", "Living Situation"),
            ("relationships", "Relationships & Social"),
            ("goals", "Goals & Aspirations"),
        ]

        for key, title in category_order:
            if key in profile_data:
                summary_parts.append(f"\n{title}:")
                summary_parts.append(
                    self._format_category_data(profile_data[key], indent=1)
                )

        # Add any other categories not in the standard order
        processed_keys = {key for key, _ in category_order}
        for key, data in profile_data.items():
            if key not in processed_keys:
                title = key.replace("_", " ").title()
                summary_parts.append(f"\n{title}:")
                summary_parts.append(self._format_category_data(data, indent=1))

        return "\n".join(summary_parts)

    def _format_category_data(self, data: dict[str, Any], indent: int = 0) -> str:
        """Format category data with proper indentation."""
        if not data:
            return "  " * indent + "No information available"

        lines = []
        prefix = "  " * indent

        for key, value in data.items():
            if isinstance(value, dict):
                # Nested category
                category_title = key.replace("_", " ").title()
                lines.append(f"{prefix}{category_title}:")
                lines.append(self._format_category_data(value, indent + 1))
            else:
                # Leaf value
                field_name = key.replace("_", " ").title()
                lines.append(f"{prefix}- {field_name}: {value}")

        return "\n".join(lines)

    async def _generate_llm_summary(self, profile_data: dict[str, Any], llm) -> str:
        """Generate a narrative summary using LLM."""
        try:
            # Convert profile data to a readable format for LLM
            structured_summary = self._generate_structured_summary(profile_data)

            prompt = f"""Generate a comprehensive, narrative profile summary based on the following structured profile data. Create a natural, flowing description that captures the key aspects of this person's life, background, and characteristics.

Profile Data:
{structured_summary}

Instructions:
- Write in third person
- Create a cohesive narrative that flows naturally
- Focus on the most important and defining characteristics
- Group related information together logically
- Keep it comprehensive but concise (2-3 paragraphs)
- Avoid simply listing facts - weave them into a story

Generate a professional profile summary:"""

            response = await llm.ainvoke(prompt)

            if hasattr(response, "content"):
                narrative_summary = response.content
            else:
                narrative_summary = str(response)

            # Combine structured and narrative summaries
            return f"=== USER PROFILE SUMMARY ===\n\n{narrative_summary}\n\n--- Detailed Profile Data ---\n{structured_summary}"

        except Exception as e:
            logger.error(f"Failed to generate LLM summary: {e}")
            # Fallback to structured summary
            return self._generate_structured_summary(profile_data)

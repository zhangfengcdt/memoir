"""
Location Memento for Spatial Memory Management and Geographic Event Storage.

Handles location-based event storage, geographic organization, and location summaries.
Events are stored under location.{location_name} keys with automatic merging of same-location events.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class LocationMemento:
    """Manages user location data and generates geographic event summaries."""

    def __init__(self, memory_store):
        """Initialize location memento with memory store."""
        self.memory_store = memory_store

    async def apply_location_events(
        self,
        location_events: list[dict[str, str]],
        metadata: dict | None = None,
        namespace: str = "default",
    ) -> None:
        """
        Apply location events to the memory store.

        For same-location events, retrieves existing content and merges with new event.

        Args:
            location_events: List of location events with location and description
            metadata: Optional metadata to include with events
            namespace: Namespace to store location events in (default: "default")
        """
        logger.debug(
            f"LocationManager.apply_location_events called with {len(location_events) if location_events else 0} events"
        )
        if not location_events:
            logger.debug("No location events provided to apply_location_events")
            return

        for event in location_events:
            location_name = event.get("location", "")
            description = event.get("description", "")

            if not location_name or not description:
                logger.warning(f"Invalid location event: {event}")
                continue

            # Normalize location name for consistent storage
            normalized_location = self._normalize_location_name(location_name)

            if not normalized_location:
                logger.debug(f"Invalid location name: {location_name}")
                continue

            # Create the location path
            location_path = f"location.{normalized_location}"

            try:
                await self._store_or_merge_location_event(
                    location_path, description, metadata, namespace
                )
                logger.debug(f"Applied location event: {location_path} - {description}")
            except Exception as e:
                logger.error(f"Failed to apply location event {location_path}: {e}")

    def _normalize_location_name(self, location_name: str) -> str:
        """
        Normalize location name for consistent storage.

        Args:
            location_name: Raw location name from LLM

        Returns:
            Normalized location name suitable for path storage
        """
        if not location_name or not isinstance(location_name, str):
            return ""

        # Clean and normalize the location name
        # Remove extra whitespace and convert to lowercase
        normalized = location_name.strip().lower()

        # Replace spaces and special characters with underscores
        normalized = re.sub(
            r"[^\w\s-]", "", normalized
        )  # Remove special chars except spaces and hyphens
        normalized = re.sub(
            r"[\s-]+", "_", normalized
        )  # Replace spaces/hyphens with underscores
        normalized = re.sub(r"_+", "_", normalized)  # Collapse multiple underscores
        normalized = normalized.strip("_")  # Remove leading/trailing underscores

        # Handle common location patterns and abbreviations
        location_mappings = {
            "new_york_city": "new_york_city",
            "nyc": "new_york_city",
            "ny": "new_york",
            "california": "california",
            "ca": "california",
            "san_francisco": "san_francisco",
            "sf": "san_francisco",
            "los_angeles": "los_angeles",
            "la": "los_angeles",
            "united_states": "united_states",
            "usa": "united_states",
            "us": "united_states",
        }

        # Apply mappings if available
        if normalized in location_mappings:
            normalized = location_mappings[normalized]

        # Ensure minimum length and validity
        if len(normalized) < 2:
            return ""

        return normalized

    async def _store_or_merge_location_event(
        self,
        location_path: str,
        description: str,
        metadata: dict | None = None,
        namespace: str = "default",
    ) -> None:
        """
        Store location event or merge with existing location events.

        Args:
            location_path: Storage path for the location (e.g., "location.san_francisco")
            description: Event description
            metadata: Optional metadata
            namespace: Namespace to store location data in (default: "default")
        """
        # namespace parameter is passed to function

        # Check if location already has events
        existing_items = await self.memory_store.asearch(namespace, location_path)

        if existing_items:
            # Merge with existing location events
            _, existing_data = existing_items[0]

            if isinstance(existing_data, str):
                existing_content = existing_data
            elif isinstance(existing_data, dict):
                existing_content = existing_data.get("raw_text", "")
            else:
                existing_content = str(existing_data)

            # Merge descriptions, avoiding duplicates
            merged_content = self._merge_location_descriptions(
                existing_content, description
            )

            content = {
                "raw_text": merged_content,
                "summary": f"Location events at {location_path.split('.')[1].replace('_', ' ').title()}",
                "structured_data": {
                    "location_name": location_path.split(".")[1]
                    .replace("_", " ")
                    .title(),
                    "location_content": merged_content,
                    "update_type": "location_event",
                },
                "memory_type": "location_event",
            }
        else:
            # Create new location event
            content = {
                "raw_text": description,
                "summary": f"Location event at {location_path.split('.')[1].replace('_', ' ').title()}",
                "structured_data": {
                    "location_name": location_path.split(".")[1]
                    .replace("_", " ")
                    .title(),
                    "location_content": description,
                    "update_type": "location_event",
                },
                "memory_type": "location_event",
            }

        # Include metadata if provided
        if metadata:
            content["metadata"] = metadata

        # Store the location event
        logger.debug(
            f"About to call store_memory_async with namespace='{namespace}', path='{location_path}'"
        )
        logger.debug(f"Content to store: {content}")

        result = await self.memory_store.store_memory_async(
            namespace, content, location_path
        )
        logger.debug(f"store_memory_async returned: {result}")

        # Debug: immediately test if we can find what we just stored
        try:
            test_search = await self.memory_store.asearch(namespace, location_path)
            logger.debug(
                f"Immediate search for '{location_path}' found {len(test_search)} items"
            )
            if test_search:
                logger.debug(f"Found item: {test_search[0]}")

            # Also try searching with prefix
            prefix_search = await self.memory_store.asearch(namespace, "location.")
            logger.debug(
                f"Prefix search for 'location.' found {len(prefix_search)} items"
            )

        except Exception as e:
            logger.debug(f"Immediate search test failed: {e}")

    def _merge_location_descriptions(self, existing: str, new: str) -> str:
        """
        Merge location event descriptions, avoiding duplicates.

        Args:
            existing: Existing location event descriptions
            new: New location event description

        Returns:
            Merged location descriptions
        """
        if not existing:
            return new

        if not new:
            return existing

        # Split by common delimiters
        existing_events = [
            event.strip() for event in existing.split("|") if event.strip()
        ]

        # Check if new event is already present (fuzzy matching)
        new_lower = new.lower()
        for existing_event in existing_events:
            if existing_event.lower() == new_lower:
                return existing  # Duplicate, return existing

        # Add new event
        existing_events.append(new.strip())
        return " | ".join(existing_events)

    async def get_location_summary(
        self, llm: Any | None = None, namespace: str = "default"
    ) -> str:
        """
        Generate a summary of all location events.

        Args:
            llm: Optional LLM for generating narrative summaries
            namespace: Namespace to search for location data (default: "default")

        Returns:
            String summary of location events
        """
        try:
            # namespace parameter is passed to function

            # Search for all location events
            logger.debug(
                f"Searching for location events with query: namespace='{namespace}', prefix='location.'"
            )
            all_items = await self.memory_store.asearch(namespace, "location.")
            logger.debug(f"Search returned {len(all_items)} items")

            # Debug: log what we found
            if all_items:
                logger.info(f"Found {len(all_items)} items with location. prefix")
                for item in all_items[:3]:  # Log first few items
                    logger.info(f"Location item: {item}")
            else:
                logger.debug("No items found with location. prefix")

                # Debug: search for ANY items with location data
                logger.debug("Searching for ANY items with location data...")
                all_items_debug = await self.memory_store.asearch(namespace, "")
                location_items_debug = []
                for path, data in all_items_debug:
                    if isinstance(data, dict) and (
                        data.get("memory_type") == "location_event"
                        or "location_name" in data.get("structured_data", {})
                    ):
                        location_items_debug.append((path, data))
                        logger.debug(f"Found location data under path: {path}")

                if location_items_debug:
                    logger.debug(
                        f"Found {len(location_items_debug)} location events but not under location.* paths!"
                    )
                    return self._generate_structured_location_summary(
                        location_items_debug
                    )
                else:
                    logger.debug("No location events found anywhere in memory store!")

            location_items = all_items  # All items should already have location. prefix

            if not location_items:
                return "No location events available."

            # If no LLM provided, generate structured summary
            if not llm:
                return self._generate_structured_location_summary(location_items)

            # Generate LLM-based narrative summary
            return await self._generate_llm_location_summary(location_items, llm)

        except Exception as e:
            logger.error(f"Failed to generate location summary: {e}")
            logger.error(f"Exception details: {type(e).__name__}: {e!s}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return "Error generating location summary."

    def _generate_structured_location_summary(self, location_items: list) -> str:
        """Generate a structured location summary without LLM."""
        summary_lines = ["=== USER LOCATION SUMMARY ===", ""]

        # Group and sort locations
        locations = {}
        for path, data in location_items:
            location_name = path.split(".", 1)[1].replace("_", " ").title()

            # Handle nested memory object structure from asearch results
            if isinstance(data, dict):
                # Check if this is a nested memory object with 'content' field
                if "content" in data and isinstance(data["content"], dict):
                    # Extract from nested structure: data['content']['raw_text']
                    content = data["content"].get("raw_text", str(data))
                else:
                    # Direct structure: data['raw_text']
                    content = data.get("raw_text", str(data))
            else:
                content = str(data)

            locations[location_name] = content

        # Sort locations alphabetically
        for location_name in sorted(locations.keys()):
            content = locations[location_name]
            summary_lines.append(f"{location_name}:")

            # Split multiple events and format nicely
            events = content.split(" | ")
            for event in events:
                if event.strip():
                    summary_lines.append(f"  - {event.strip()}")
            summary_lines.append("")

        return "\n".join(summary_lines)

    async def _generate_llm_location_summary(
        self, location_items: list, llm: Any
    ) -> str:
        """Generate an LLM-based narrative location summary."""
        # Prepare location data for LLM
        location_data = []
        for path, data in location_items:
            location_name = path.split(".", 1)[1].replace("_", " ").title()

            if isinstance(data, dict):
                content = data.get("raw_text", str(data))
            else:
                content = str(data)

            location_data.append(f"{location_name}: {content}")

        location_text = "\n".join(location_data)

        prompt = f"""Create a concise narrative summary of the user's location-related experiences and activities. Focus on places they've been, lived, worked, or had significant experiences.

Location Data:
{location_text}

Create a narrative summary that:
1. Groups related locations geographically when possible
2. Highlights significant places and experiences
3. Shows patterns in the user's movements or preferences
4. Keeps the summary concise but informative

Location Summary:"""

        try:
            response = await llm.ainvoke(prompt)
            return response.content.strip()
        except Exception as e:
            logger.error(f"LLM location summary failed: {e}")
            return self._generate_structured_location_summary(location_items)

    async def get_location_events_for_search(
        self, location_query: str, namespace: str = "default"
    ) -> list[dict]:
        """
        Get location events relevant to a search query.

        Args:
            location_query: Search query for locations
            namespace: Namespace to search for location data (default: "default")

        Returns:
            List of relevant location events
        """
        try:
            # namespace parameter is passed to function

            # Search for location events
            all_items = await self.memory_store.asearch(namespace, "location.")
            location_items = [
                (path, data) for path, data in all_items if path.startswith("location.")
            ]

            # Filter by relevance to query
            relevant_events = []
            query_lower = location_query.lower()

            for path, data in location_items:
                location_name = path.split(".", 1)[1].replace("_", " ")

                if isinstance(data, dict):
                    content = data.get("raw_text", str(data))
                else:
                    content = str(data)

                # Check if query matches location name or content
                if (
                    query_lower in location_name.lower()
                    or query_lower in content.lower()
                ):
                    relevant_events.append(
                        {
                            "location": location_name.title(),
                            "content": content,
                            "path": path,
                        }
                    )

            return relevant_events

        except Exception as e:
            logger.error(f"Failed to get location events for search: {e}")
            return []

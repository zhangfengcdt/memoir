"""
Timeline Memento for User Event History and Temporal Memory Management.

Handles chronological event storage, date-based organization, and timeline summaries.
Events are stored under timeline.YYYYMMDD keys with automatic merging of same-day events.
"""

import logging
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TimelineMemento:
    """Manages user timeline data and generates chronological event summaries."""

    def __init__(self, memory_store):
        """Initialize timeline memento with memory store."""
        self.memory_store = memory_store

    async def apply_timeline_events(
        self,
        timeline_events: list[dict[str, str]],
        metadata: Optional[dict] = None,
        original_content: Optional[str] = None,
    ) -> None:
        """
        Apply timeline events to the memory store.

        For same-day events, retrieves existing content and merges with new event.

        Args:
            timeline_events: List of timeline events with date and description
            metadata: Optional metadata to include with events
        """
        if not timeline_events:
            return

        for event in timeline_events:
            date_str = event.get("date", "")  # Format: YYYYMMDD
            description = event.get("description", "")

            if not date_str or not description:
                logger.warning(f"Invalid timeline event: {event}")
                continue

            # Validate date format
            if not self._validate_date_format(date_str):
                logger.warning(f"Invalid date format (expected YYYYMMDD): {date_str}")
                continue

            # Create the timeline path
            path = f"timeline.{date_str}"

            # Check if there's already an event for this date
            existing_events = await self.memory_store.asearch("memory:general", path)

            if existing_events:
                # Merge with existing event(s) for the same day
                existing_content = self._extract_existing_content(existing_events)
                merged_content = self._merge_events(existing_content, description)
            else:
                merged_content = description

            # Store the timeline event as a memory
            memory_data = {
                "raw_text": merged_content,
                "original_content": original_content
                or merged_content,  # Store original input if available
                "summary": f"Timeline event on {self._format_date_display(date_str)}",
                "structured_data": {
                    "timeline_date": date_str,
                    "timeline_content": merged_content,
                    "original_content": original_content or merged_content,
                    "update_type": "timeline_event",
                },
                "memory_type": "timeline_event",
            }

            logger.info(f"DEBUG: Storing timeline memory_data: {memory_data}")

            # Store directly using the memory store with correct signature (async)
            await self.memory_store.store_memory_async(
                "memory:general", memory_data, path
            )
            logger.info(f"Applied timeline event: {path} = {merged_content[:100]}...")

    async def get_timeline_summary(
        self, start_date: Optional[str] = None, end_date: Optional[str] = None, llm=None
    ) -> str:
        """
        Generate a comprehensive timeline summary from stored timeline data.

        Args:
            start_date: Optional start date (YYYYMMDD format)
            end_date: Optional end date (YYYYMMDD format)
            llm: Optional LLM for generating narrative summary

        Returns:
            Timeline summary string
        """
        try:
            # Search for all timeline memories
            timeline_memories = await self.memory_store.asearch(
                "memory:general", "timeline."
            )

            # Debug: log what we found
            logger.debug(f"Found {len(timeline_memories)} timeline memories")

            # Filter by date range if specified
            if start_date or end_date:
                timeline_memories = self._filter_by_date_range(
                    timeline_memories, start_date, end_date
                )

            # Limit results if too many
            if len(timeline_memories) > 1000:
                timeline_memories = timeline_memories[:1000]

            if not timeline_memories:
                return "No timeline events available."

            # Organize timeline data chronologically
            timeline_data = self._organize_timeline_data(timeline_memories)

            # Generate summary
            if llm:
                return await self._generate_llm_summary(timeline_data, llm)
            else:
                return self._generate_structured_summary(timeline_data)

        except Exception as e:
            import traceback

            logger.error(f"Failed to generate timeline summary: {e}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return f"Error generating timeline summary: {e}"

    def _validate_date_format(self, date_str: str) -> bool:
        """Validate that date string is in YYYYMMDD format."""
        if len(date_str) != 8:
            return False
        try:
            datetime.strptime(date_str, "%Y%m%d")
            return True
        except ValueError:
            return False

    def _format_date_display(self, date_str: str) -> str:
        """Format YYYYMMDD to human-readable date."""
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            return dt.strftime("%B %d, %Y")
        except ValueError:
            return date_str

    def _extract_existing_content(self, existing_events: list[tuple[str, Any]]) -> str:
        """Extract content from existing timeline events."""
        contents = []
        for _, data in existing_events:
            if isinstance(data, dict):
                # Check if this is a MemoryItem structure with content field
                if "content" in data and isinstance(data["content"], dict):
                    memory_data = data["content"]
                    structured_data = memory_data.get("structured_data", {})
                    timeline_content = structured_data.get("timeline_content", "")
                    if timeline_content:
                        contents.append(timeline_content)
                else:
                    # Try direct access
                    structured_data = data.get("structured_data", {})
                    timeline_content = structured_data.get("timeline_content", "")
                    if timeline_content:
                        contents.append(timeline_content)

        return " | ".join(contents) if contents else ""

    def _merge_events(self, existing_content: str, new_content: str) -> str:
        """Merge existing and new events for the same day."""
        if not existing_content:
            return new_content

        # Simple merge strategy - combine with separator
        # In production, you might want to use an LLM to create a better summary
        return f"{existing_content} | {new_content}"

    def _filter_by_date_range(
        self,
        memories: list[tuple[str, Any]],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> list[tuple[str, Any]]:
        """Filter timeline memories by date range."""
        filtered = []

        for semantic_key, data in memories:
            # Extract date from key (timeline.YYYYMMDD)
            if "." in semantic_key:
                date_str = semantic_key.split(".")[-1]
                if self._validate_date_format(date_str):
                    # Check if within range
                    if start_date and date_str < start_date:
                        continue
                    if end_date and date_str > end_date:
                        continue
                    filtered.append((semantic_key, data))

        return filtered

    def _organize_timeline_data(
        self, timeline_memories: list[tuple[str, Any]]
    ) -> dict[str, str]:
        """Organize timeline memories into a chronological structure."""
        organized = {}

        for semantic_key, data in timeline_memories:
            try:
                # Extract date from key
                if "." not in semantic_key:
                    continue

                date_str = semantic_key.split(".")[-1]
                if not self._validate_date_format(date_str):
                    continue

                # Handle the data format
                if isinstance(data, dict):
                    # Check if this is a MemoryItem structure with content field
                    if "content" in data and isinstance(data["content"], dict):
                        memory_data = data["content"]
                        structured_data = memory_data.get("structured_data", {})
                    else:
                        memory_data = data
                        structured_data = data.get("structured_data", {})

                    # Get the timeline content
                    timeline_content = structured_data.get("timeline_content")
                    update_type = structured_data.get("update_type")

                    # Only process memories that are actual timeline events
                    if update_type != "timeline_event":
                        logger.debug(
                            f"Skipping non-timeline-event memory: {semantic_key}"
                        )
                        continue

                    if timeline_content:
                        organized[date_str] = timeline_content

            except Exception as e:
                logger.warning(f"Failed to process timeline memory {semantic_key}: {e}")
                continue

        # Sort by date
        sorted_dates = sorted(organized.keys())
        return {date: organized[date] for date in sorted_dates}

    def _generate_structured_summary(self, timeline_data: dict[str, str]) -> str:
        """Generate a structured text summary of timeline data."""
        if not timeline_data:
            return "No timeline events available."

        summary_parts = ["=== USER TIMELINE ===\n"]

        # Group by year and month for better organization
        events_by_year = {}
        for date_str, content in timeline_data.items():
            year = date_str[:4]
            month = date_str[4:6]

            if year not in events_by_year:
                events_by_year[year] = {}
            if month not in events_by_year[year]:
                events_by_year[year][month] = []

            events_by_year[year][month].append((date_str, content))

        # Generate summary by year and month
        for year in sorted(events_by_year.keys(), reverse=True):
            summary_parts.append(f"\n{year}:")

            for month in sorted(events_by_year[year].keys(), reverse=True):
                month_name = datetime.strptime(f"{year}{month}01", "%Y%m%d").strftime(
                    "%B"
                )
                summary_parts.append(f"\n  {month_name}:")

                for date_str, content in sorted(
                    events_by_year[year][month], reverse=True
                ):
                    day = int(date_str[6:8])
                    summary_parts.append(f"    {day:2d}: {content}")

        return "\n".join(summary_parts)

    async def _generate_llm_summary(self, timeline_data: dict[str, str], llm) -> str:
        """Generate a narrative summary using LLM."""
        try:
            # Convert timeline data to a readable format for LLM
            structured_summary = self._generate_structured_summary(timeline_data)

            prompt = f"""Generate a comprehensive, narrative timeline summary based on the following chronological events. Create a natural, flowing description that captures the key events and their significance in the person's life.

Timeline Data:
{structured_summary}

Instructions:
- Write in third person
- Create a cohesive narrative that flows naturally through time
- Highlight significant events and patterns
- Group related events logically
- Keep it comprehensive but concise
- Focus on the progression and development over time

Generate a timeline narrative:"""

            response = await llm.ainvoke(prompt)

            if hasattr(response, "content"):
                narrative_summary = response.content
            else:
                narrative_summary = str(response)

            # Combine structured and narrative summaries
            return f"=== USER TIMELINE ===\n\n{narrative_summary}\n\n--- Detailed Timeline ---\n{structured_summary}"

        except Exception as e:
            logger.error(f"Failed to generate LLM summary: {e}")
            # Fallback to structured summary
            return self._generate_structured_summary(timeline_data)

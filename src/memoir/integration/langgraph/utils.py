"""Utility functions and helpers for LangGraph integration."""

import hashlib
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.store.base import NamespacePath

from .types import MemoryEntry, SearchResult

if TYPE_CHECKING:
    from .memory_store import LangGraphMemoryStore


def create_memory_namespace(
    agent_id: str,
    thread_id: str | None = None,
    user_id: str | None = None,
) -> NamespacePath:
    """Create a namespace path for memory storage.

    Args:
        agent_id: Unique identifier for the agent
        thread_id: Optional thread/conversation ID
        user_id: Optional user ID

    Returns:
        NamespacePath for the memory
    """
    parts = ["agents", agent_id]

    if user_id:
        parts.extend(["users", user_id])

    if thread_id:
        parts.extend(["threads", thread_id])

    # NamespacePath is a tuple type alias
    return tuple(parts)


def message_to_memory_entry(
    message: BaseMessage,
    agent_id: str,
    thread_id: str | None = None,
) -> MemoryEntry:
    """Convert a LangChain message to a memory entry.

    Args:
        message: LangChain message
        agent_id: Agent identifier
        thread_id: Optional thread identifier

    Returns:
        MemoryEntry
    """
    # Determine message type and role
    if isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, AIMessage):
        role = "assistant"
    elif isinstance(message, SystemMessage):
        role = "system"
    else:
        role = "unknown"

    # Extract metadata
    metadata = {
        "role": role,
        "agent_id": agent_id,
        "message_type": message.__class__.__name__,
    }

    if thread_id:
        metadata["thread_id"] = thread_id

    if hasattr(message, "additional_kwargs"):
        metadata.update(message.additional_kwargs)

    return MemoryEntry(
        content=message.content,
        metadata=metadata,
        timestamp=datetime.now(),
        thread_id=thread_id,
    )


def memory_entry_to_message(entry: MemoryEntry) -> BaseMessage:
    """Convert a memory entry back to a LangChain message.

    Args:
        entry: Memory entry

    Returns:
        LangChain message
    """
    role = entry.metadata.get("role", "unknown")

    if role == "user":
        return HumanMessage(content=entry.content)
    elif role == "assistant":
        return AIMessage(content=entry.content)
    elif role == "system":
        return SystemMessage(content=entry.content)
    else:
        # Default to human message
        return HumanMessage(content=entry.content)


def create_memory_key(
    content: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Create a unique key for a memory entry.

    Args:
        content: Memory content
        metadata: Optional metadata

    Returns:
        Unique key string
    """
    # Create hash from content and metadata
    data = {
        "content": content,
        "metadata": metadata or {},
        "timestamp": datetime.now().isoformat(),
    }

    data_str = json.dumps(data, sort_keys=True)
    return hashlib.sha256(data_str.encode()).hexdigest()[:16]


def filter_memories_by_time(
    memories: list[MemoryEntry],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> list[MemoryEntry]:
    """Filter memories by time range.

    Args:
        memories: List of memory entries
        start_time: Optional start time filter
        end_time: Optional end time filter

    Returns:
        Filtered list of memories
    """
    filtered = memories

    if start_time:
        filtered = [m for m in filtered if m.timestamp >= start_time]

    if end_time:
        filtered = [m for m in filtered if m.timestamp <= end_time]

    return filtered


def group_memories_by_thread(
    memories: list[MemoryEntry],
) -> dict[str, list[MemoryEntry]]:
    """Group memories by thread ID.

    Args:
        memories: List of memory entries

    Returns:
        Dictionary mapping thread IDs to memory lists
    """
    grouped: dict[str, list[MemoryEntry]] = {}

    for memory in memories:
        thread_id = memory.thread_id or "default"
        if thread_id not in grouped:
            grouped[thread_id] = []
        grouped[thread_id].append(memory)

    return grouped


def format_memory_for_prompt(
    memories: list[MemoryEntry | SearchResult | Any],
    max_tokens: int | None = None,
) -> str:
    """Format memories for inclusion in a prompt.

    Args:
        memories: List of memories or search results
        max_tokens: Optional maximum token limit

    Returns:
        Formatted string for prompt
    """
    formatted_parts = []

    for item in memories:
        if isinstance(item, SearchResult):
            memory = item.memory
            score = f" (relevance: {item.score:.2f})"
            timestamp = memory.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            role = memory.metadata.get("role", "unknown")
            content = memory.content
        elif hasattr(item, "timestamp") and hasattr(item, "content"):
            # MemoryEntry object
            timestamp = item.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            role = item.metadata.get("role", "unknown")
            content = item.content
            score = ""
        elif hasattr(item, "value") and hasattr(item, "created_at"):
            # LangGraph Item object
            timestamp = item.created_at.strftime("%Y-%m-%d %H:%M:%S")
            value = item.value or {}
            metadata = value.get("metadata", {}) if isinstance(value, dict) else {}
            role = metadata.get("role", "unknown")
            content = (
                value.get("content", str(value))
                if isinstance(value, dict)
                else str(value)
            )
            score = ""
        else:
            # Fallback for unknown object types
            timestamp = "unknown"
            role = "unknown"
            content = str(item)
            score = ""

        formatted_parts.append(f"[{timestamp}] {role.upper()}{score}: {content}")

    result = "\n".join(formatted_parts)

    # Truncate if needed (rough approximation)
    if max_tokens:
        # Roughly 4 characters per token
        max_chars = max_tokens * 4
        if len(result) > max_chars:
            result = result[:max_chars] + "..."

    return result


class MemoryEnabledGraph:
    """Helper class to create memory-enabled LangGraph workflows."""

    def __init__(
        self,
        memory_store: "LangGraphMemoryStore",
        agent_id: str,
    ):
        """Initialize memory-enabled graph.

        Args:
            memory_store: LangGraph memory store instance
            agent_id: Unique agent identifier
        """
        self.memory_store = memory_store
        self.agent_id = agent_id

    def create_memory_node(
        self,
        name: str = "memory",
        search_on_entry: bool = True,
        store_on_exit: bool = True,
    ):
        """Create a memory node for the graph.

        Args:
            name: Node name
            search_on_entry: Whether to search memories on entry
            store_on_exit: Whether to store memories on exit

        Returns:
            Node function
        """

        async def memory_node(state: dict[str, Any]) -> dict[str, Any]:
            """Memory node implementation."""
            thread_id = state.get("thread_id")
            namespace = create_memory_namespace(
                self.agent_id,
                thread_id=thread_id,
            )

            # Search for relevant memories on entry
            if search_on_entry and "query" in state:
                memories = await self.memory_store.asearch(
                    namespace,
                    query=state["query"],
                    limit=self.memory_store.memory_config.max_search_results,
                )

                # Add to state
                state["retrieved_memories"] = memories

            # Store new memories on exit
            if store_on_exit and "messages" in state:
                for message in state["messages"]:
                    if isinstance(message, BaseMessage):
                        memory_entry = message_to_memory_entry(
                            message,
                            self.agent_id,
                            thread_id,
                        )

                        await self.memory_store.aput(
                            namespace,
                            key=create_memory_key(
                                memory_entry.content,
                                memory_entry.metadata,
                            ),
                            value={
                                "content": memory_entry.content,
                                "metadata": memory_entry.metadata,
                            },
                            metadata=memory_entry.metadata,
                        )

            return state

        return memory_node

    def create_memory_retrieval_node(
        self,
        name: str = "retrieve_memories",
        query_key: str = "query",
        output_key: str = "memories",
    ):
        """Create a dedicated memory retrieval node.

        Args:
            name: Node name
            query_key: State key containing the search query
            output_key: State key to store retrieved memories

        Returns:
            Node function
        """

        async def retrieval_node(state: dict[str, Any]) -> dict[str, Any]:
            """Memory retrieval node."""
            query = state.get(query_key)
            if not query:
                state[output_key] = []
                return state

            thread_id = state.get("thread_id")
            namespace = create_memory_namespace(
                self.agent_id,
                thread_id=thread_id,
            )

            memories = await self.memory_store.asearch(
                namespace,
                query=query,
                limit=self.memory_store.memory_config.max_search_results,
            )

            state[output_key] = memories
            return state

        return retrieval_node

    def create_memory_storage_node(
        self,
        name: str = "store_memory",
        content_key: str = "content",
        metadata_key: str = "metadata",
    ):
        """Create a dedicated memory storage node.

        Args:
            name: Node name
            content_key: State key containing content to store
            metadata_key: State key containing metadata

        Returns:
            Node function
        """

        async def storage_node(state: dict[str, Any]) -> dict[str, Any]:
            """Memory storage node."""
            content = state.get(content_key)
            if not content:
                return state

            metadata = state.get(metadata_key, {})
            thread_id = state.get("thread_id")

            namespace = create_memory_namespace(
                self.agent_id,
                thread_id=thread_id,
            )

            await self.memory_store.aput(
                namespace,
                key=create_memory_key(content, metadata),
                value={"content": content, "metadata": metadata},
                metadata=metadata,
            )

            state["memory_stored"] = True
            return state

        return storage_node

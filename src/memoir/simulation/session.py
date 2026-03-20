"""
Session Management - Manage user sessions with namespaces.

Implements the namespace and session patterns from OpenClaw spec:
- Session keys follow pattern: agent:<agentId>:user:<userId>:session:<sessionId>
- Each user has isolated namespace: user:{userId}
- Sessions track conversation history and can be persisted
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A single message in a conversation."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Session:
    """
    A single conversation session.

    Tracks messages, manages namespace isolation, and provides
    the session key for hook integration.
    """

    session_id: str
    user_id: str
    agent_id: str = "main"
    messages: list[Message] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def session_key(self) -> str:
        """Generate OpenClaw-style session key."""
        return f"agent:{self.agent_id}:user:{self.user_id}:session:{self.session_id}"

    @property
    def user_namespace(self) -> str:
        """Get user namespace for memoir."""
        return f"user:{self.user_id}"

    def add_user_message(self, content: str, **metadata) -> Message:
        """Add a user message to the session."""
        msg = Message(role="user", content=content, metadata=metadata)
        self.messages.append(msg)
        self.last_active = time.time()
        return msg

    def add_assistant_message(self, content: str, **metadata) -> Message:
        """Add an assistant message to the session."""
        msg = Message(role="assistant", content=content, metadata=metadata)
        self.messages.append(msg)
        self.last_active = time.time()
        return msg

    def get_last_user_message(self) -> Optional[Message]:
        """Get the most recent user message."""
        for msg in reversed(self.messages):
            if msg.role == "user":
                return msg
        return None

    def get_last_assistant_message(self) -> Optional[Message]:
        """Get the most recent assistant message."""
        for msg in reversed(self.messages):
            if msg.role == "assistant":
                return msg
        return None

    def get_conversation_history(
        self,
        limit: Optional[int] = None,
        format: str = "list",
    ) -> list[dict] | str:
        """
        Get conversation history.

        Args:
            limit: Maximum messages to return (most recent)
            format: "list" for list of dicts, "text" for formatted string

        Returns:
            Conversation history in requested format
        """
        messages = self.messages[-limit:] if limit else self.messages

        if format == "text":
            lines = []
            for msg in messages:
                role = "User" if msg.role == "user" else "Assistant"
                lines.append(f"{role}: {msg.content}")
            return "\n".join(lines)

        return [msg.to_dict() for msg in messages]

    def to_dict(self) -> dict:
        """Serialize session to dict."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at,
            "last_active": self.last_active,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """Deserialize session from dict."""
        session = cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            agent_id=data.get("agent_id", "main"),
            created_at=data.get("created_at", time.time()),
            last_active=data.get("last_active", time.time()),
            metadata=data.get("metadata", {}),
        )
        session.messages = [Message.from_dict(m) for m in data.get("messages", [])]
        return session


class SessionManager:
    """
    Manage multiple user sessions.

    Provides session lifecycle management, user isolation,
    and persistence for simulation scenarios.

    Example:
        manager = SessionManager()

        # Create sessions for different users
        session1 = manager.create_session("user1")
        session2 = manager.create_session("user2")

        # Add messages
        session1.add_user_message("Hello!")
        session1.add_assistant_message("Hi there!")

        # Get all sessions for a user
        user_sessions = manager.get_user_sessions("user1")

        # Persist sessions
        manager.save_all("/tmp/sessions")
    """

    def __init__(self, persistence_dir: Optional[str] = None):
        """
        Initialize session manager.

        Args:
            persistence_dir: Directory for session persistence
        """
        self._sessions: dict[str, Session] = {}
        self._user_sessions: dict[str, list[str]] = {}  # user_id -> [session_ids]
        self.persistence_dir = Path(persistence_dir) if persistence_dir else None

        if self.persistence_dir:
            self.persistence_dir.mkdir(parents=True, exist_ok=True)
            self._load_persisted_sessions()

    def create_session(
        self,
        user_id: str,
        agent_id: str = "main",
        session_id: Optional[str] = None,
        **metadata,
    ) -> Session:
        """
        Create a new session.

        Args:
            user_id: User identifier
            agent_id: Agent identifier
            session_id: Optional session ID (auto-generated if not provided)
            **metadata: Additional metadata

        Returns:
            New Session instance
        """
        session_id = session_id or str(uuid.uuid4())[:8]

        session = Session(
            session_id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            metadata=metadata,
        )

        self._sessions[session.session_key] = session

        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
        self._user_sessions[user_id].append(session.session_key)

        logger.debug(f"Created session: {session.session_key}")
        return session

    def get_session(self, session_key: str) -> Optional[Session]:
        """Get session by session key."""
        return self._sessions.get(session_key)

    def get_or_create_session(
        self,
        user_id: str,
        agent_id: str = "main",
        session_id: Optional[str] = None,
    ) -> Session:
        """Get existing session or create new one."""
        if session_id:
            key = f"agent:{agent_id}:user:{user_id}:session:{session_id}"
            if key in self._sessions:
                return self._sessions[key]

        # Check for any existing session for this user/agent
        for _key, session in self._sessions.items():
            if session.user_id == user_id and session.agent_id == agent_id:
                return session

        # Create new session
        return self.create_session(user_id, agent_id, session_id)

    def get_user_sessions(self, user_id: str) -> list[Session]:
        """Get all sessions for a user."""
        session_keys = self._user_sessions.get(user_id, [])
        return [self._sessions[k] for k in session_keys if k in self._sessions]

    def get_active_sessions(self, timeout_seconds: float = 3600) -> list[Session]:
        """Get sessions active within timeout period."""
        cutoff = time.time() - timeout_seconds
        return [s for s in self._sessions.values() if s.last_active > cutoff]

    def end_session(self, session_key: str) -> bool:
        """
        End and remove a session.

        Args:
            session_key: Session to end

        Returns:
            True if session was ended
        """
        session = self._sessions.pop(session_key, None)
        if session:
            user_keys = self._user_sessions.get(session.user_id, [])
            if session_key in user_keys:
                user_keys.remove(session_key)
            logger.debug(f"Ended session: {session_key}")
            return True
        return False

    def list_sessions(self) -> list[dict]:
        """List all sessions with summary info."""
        return [
            {
                "session_key": s.session_key,
                "user_id": s.user_id,
                "agent_id": s.agent_id,
                "message_count": len(s.messages),
                "created_at": s.created_at,
                "last_active": s.last_active,
            }
            for s in self._sessions.values()
        ]

    def list_users(self) -> list[str]:
        """List all users with sessions."""
        return list(self._user_sessions.keys())

    # ==========================================================================
    # Persistence
    # ==========================================================================

    def save_session(self, session_key: str) -> bool:
        """
        Save a single session to disk.

        Args:
            session_key: Session to save

        Returns:
            True if saved successfully
        """
        if not self.persistence_dir:
            return False

        session = self._sessions.get(session_key)
        if not session:
            return False

        file_path = self.persistence_dir / f"{session.session_id}.json"
        try:
            with open(file_path, "w") as f:
                json.dump(session.to_dict(), f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save session {session_key}: {e}")
            return False

    def save_all(self, directory: Optional[str] = None) -> int:
        """
        Save all sessions to disk.

        Args:
            directory: Override persistence directory

        Returns:
            Number of sessions saved
        """
        save_dir = Path(directory) if directory else self.persistence_dir
        if not save_dir:
            return 0

        save_dir.mkdir(parents=True, exist_ok=True)

        saved = 0
        for session in self._sessions.values():
            file_path = save_dir / f"{session.session_id}.json"
            try:
                with open(file_path, "w") as f:
                    json.dump(session.to_dict(), f, indent=2)
                saved += 1
            except Exception as e:
                logger.error(f"Failed to save session: {e}")

        return saved

    def _load_persisted_sessions(self) -> int:
        """Load sessions from persistence directory."""
        if not self.persistence_dir or not self.persistence_dir.exists():
            return 0

        loaded = 0
        for file_path in self.persistence_dir.glob("*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)
                session = Session.from_dict(data)
                self._sessions[session.session_key] = session

                if session.user_id not in self._user_sessions:
                    self._user_sessions[session.user_id] = []
                self._user_sessions[session.user_id].append(session.session_key)

                loaded += 1
            except Exception as e:
                logger.error(f"Failed to load session from {file_path}: {e}")

        return loaded

    # ==========================================================================
    # Context for Hooks
    # ==========================================================================

    def get_hook_context(self, session_key: str) -> dict:
        """
        Get context data for hook execution.

        Args:
            session_key: Session key

        Returns:
            Context dict for hooks
        """
        session = self._sessions.get(session_key)
        if not session:
            return {}

        return {
            "session_key": session.session_key,
            "user_id": session.user_id,
            "agent_id": session.agent_id,
            "user_namespace": session.user_namespace,
            "message_count": len(session.messages),
            "messages": [m.to_dict() for m in session.messages[-10:]],  # Last 10
        }

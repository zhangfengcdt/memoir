"""
Real Dataset Loaders for LLM Proxy E2E Tests.

Downloads and converts real-world conversation datasets from Hugging Face
to validate proxy behavior against actual agent patterns.

Supported datasets:
- LMSYS-Chat-1M: 1M conversations from Chatbot Arena (25 LLMs)
- WildChat-1M: 1M ChatGPT conversations from real users
- WildChat-4.8M: Extended version with o1 reasoning models

Usage:
    from tests.fixtures.proxy.real_datasets import RealDatasetLoader

    loader = RealDatasetLoader(cache_dir="/tmp/memoir_datasets")
    sessions = loader.load_lmsys(num_samples=100)
    sessions = loader.load_wildchat(num_samples=100)
"""

import hashlib
import json
import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default cache directory
DEFAULT_CACHE_DIR = Path("/tmp/memoir_test_datasets")


@dataclass
class RealMessage:
    """Message from a real conversation dataset."""

    role: str  # "user", "assistant", "system"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RealConversation:
    """A real conversation from a public dataset."""

    conversation_id: str
    messages: list[RealMessage]
    model: str = ""
    language: str = "en"
    source: str = ""  # "lmsys", "wildchat", etc.
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def num_turns(self) -> int:
        """Number of conversation turns (user messages)."""
        return sum(1 for m in self.messages if m.role == "user")

    @property
    def total_chars(self) -> int:
        """Total characters in conversation."""
        return sum(len(m.content) for m in self.messages)

    @property
    def estimated_tokens(self) -> int:
        """Estimated token count (chars / 4)."""
        return self.total_chars // 4


class DatasetNotAvailableError(Exception):
    """Raised when a dataset cannot be loaded."""

    pass


class RealDatasetLoader:
    """
    Loads real conversation datasets from Hugging Face.

    Handles downloading, caching, and converting datasets to a common format
    for use in proxy e2e tests.

    Available datasets (by access level):
    - Public (no auth): everyday-conversations, OpenAssistant
    - Gated (requires HF auth): LMSYS-Chat-1M, WildChat-1M
    """

    # Dataset identifiers
    LMSYS_CHAT_1M = "lmsys/lmsys-chat-1m"
    WILDCHAT_1M = "allenai/WildChat-1M"
    WILDCHAT_4_8M = "allenai/WildChat-4.8M"

    # Public datasets (no authentication required)
    EVERYDAY_CONVERSATIONS = "HuggingFaceTB/everyday-conversations-llama3.1-2k"
    OPENASSISTANT = "OpenAssistant/oasst1"

    def __init__(self, cache_dir: Path | str | None = None):
        """
        Initialize the loader.

        Args:
            cache_dir: Directory to cache downloaded datasets.
                      Defaults to /tmp/memoir_test_datasets
        """
        self.cache_dir = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._datasets_available = None

    def _check_datasets_library(self) -> bool:
        """Check if the datasets library is available."""
        try:
            import datasets  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_cache_path(self, dataset_name: str, num_samples: int) -> Path:
        """Get cache file path for a dataset slice."""
        # Create a unique hash for this dataset configuration
        config_hash = hashlib.md5(f"{dataset_name}:{num_samples}".encode()).hexdigest()[
            :8
        ]
        safe_name = dataset_name.replace("/", "_")
        return self.cache_dir / f"{safe_name}_{num_samples}_{config_hash}.jsonl"

    def _save_to_cache(
        self, conversations: list[RealConversation], cache_path: Path
    ) -> None:
        """Save conversations to cache file."""
        with open(cache_path, "w") as f:
            for conv in conversations:
                data = {
                    "conversation_id": conv.conversation_id,
                    "messages": [
                        {"role": m.role, "content": m.content, "metadata": m.metadata}
                        for m in conv.messages
                    ],
                    "model": conv.model,
                    "language": conv.language,
                    "source": conv.source,
                    "metadata": conv.metadata,
                }
                f.write(json.dumps(data) + "\n")
        logger.info(f"Cached {len(conversations)} conversations to {cache_path}")

    def _load_from_cache(self, cache_path: Path) -> list[RealConversation]:
        """Load conversations from cache file."""
        conversations = []
        with open(cache_path) as f:
            for line in f:
                data = json.loads(line)
                messages = [
                    RealMessage(
                        role=m["role"],
                        content=m["content"],
                        metadata=m.get("metadata", {}),
                    )
                    for m in data["messages"]
                ]
                conversations.append(
                    RealConversation(
                        conversation_id=data["conversation_id"],
                        messages=messages,
                        model=data.get("model", ""),
                        language=data.get("language", "en"),
                        source=data.get("source", ""),
                        metadata=data.get("metadata", {}),
                    )
                )
        logger.info(f"Loaded {len(conversations)} conversations from cache")
        return conversations

    def load_lmsys(
        self,
        num_samples: int = 100,
        min_turns: int = 2,
        language: str | None = "English",
        use_cache: bool = True,
    ) -> list[RealConversation]:
        """
        Load conversations from LMSYS-Chat-1M dataset.

        Dataset contains 1M conversations from Chatbot Arena with 25 LLMs
        including GPT-4, Claude, Llama, Vicuna, etc.

        Args:
            num_samples: Number of conversations to load
            min_turns: Minimum conversation turns to include
            language: Filter by language (None for all)
            use_cache: Whether to use cached data

        Returns:
            List of RealConversation objects
        """
        cache_path = self._get_cache_path(self.LMSYS_CHAT_1M, num_samples)

        if use_cache and cache_path.exists():
            return self._load_from_cache(cache_path)

        if not self._check_datasets_library():
            raise DatasetNotAvailableError(
                "The 'datasets' library is required. Install with: pip install datasets"
            )

        try:
            from datasets import load_dataset

            logger.info(f"Loading {num_samples} samples from LMSYS-Chat-1M...")

            # Load dataset (streaming to avoid downloading entire dataset)
            dataset = load_dataset(
                self.LMSYS_CHAT_1M,
                split="train",
                streaming=True,
            )

            conversations = []
            for item in dataset:
                # Filter by language if specified
                if language and item.get("language") != language:
                    continue

                # Parse conversation from OpenAI format
                conv_data = item.get("conversation", [])
                if not conv_data:
                    continue

                messages = []
                for msg in conv_data:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role and content:
                        messages.append(RealMessage(role=role, content=content))

                # Filter by minimum turns
                user_turns = sum(1 for m in messages if m.role == "user")
                if user_turns < min_turns:
                    continue

                conv = RealConversation(
                    conversation_id=item.get(
                        "conversation_id", f"lmsys_{len(conversations)}"
                    ),
                    messages=messages,
                    model=item.get("model", ""),
                    language=item.get("language", "en"),
                    source="lmsys",
                    metadata={
                        "turn": item.get("turn", 0),
                        "toxic": item.get("toxic", False),
                        "redacted": item.get("redacted", False),
                    },
                )
                conversations.append(conv)

                if len(conversations) >= num_samples:
                    break

            if use_cache and conversations:
                self._save_to_cache(conversations, cache_path)

            return conversations

        except Exception as e:
            logger.warning(f"Failed to load LMSYS dataset: {e}")
            raise DatasetNotAvailableError(f"Could not load LMSYS-Chat-1M: {e}")

    def load_wildchat(
        self,
        num_samples: int = 100,
        min_turns: int = 2,
        include_toxic: bool = False,
        model_filter: str | None = None,
        use_cache: bool = True,
    ) -> list[RealConversation]:
        """
        Load conversations from WildChat-1M dataset.

        Dataset contains 1M real ChatGPT conversations from users who
        opted in to share their transcripts.

        Args:
            num_samples: Number of conversations to load
            min_turns: Minimum conversation turns to include
            include_toxic: Whether to include toxic conversations
            model_filter: Filter by model (e.g., "gpt-4", "gpt-3.5")
            use_cache: Whether to use cached data

        Returns:
            List of RealConversation objects
        """
        cache_path = self._get_cache_path(self.WILDCHAT_1M, num_samples)

        if use_cache and cache_path.exists():
            return self._load_from_cache(cache_path)

        if not self._check_datasets_library():
            raise DatasetNotAvailableError(
                "The 'datasets' library is required. Install with: pip install datasets"
            )

        try:
            from datasets import load_dataset

            logger.info(f"Loading {num_samples} samples from WildChat-1M...")

            # Load dataset (streaming)
            dataset = load_dataset(
                self.WILDCHAT_1M,
                split="train",
                streaming=True,
            )

            conversations = []
            for item in dataset:
                # Filter toxic if not wanted
                if not include_toxic and item.get("toxic", False):
                    continue

                # Filter by model if specified
                if model_filter and model_filter not in item.get("model", ""):
                    continue

                # Parse conversation
                conv_data = item.get("conversation", [])
                if not conv_data:
                    continue

                messages = []
                for msg in conv_data:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role and content:
                        messages.append(
                            RealMessage(
                                role=role,
                                content=content,
                                metadata={
                                    "language": msg.get("language", ""),
                                    "toxic": msg.get("toxic", False),
                                },
                            )
                        )

                # Filter by minimum turns
                user_turns = sum(1 for m in messages if m.role == "user")
                if user_turns < min_turns:
                    continue

                conv = RealConversation(
                    conversation_id=item.get(
                        "conversation_hash", f"wc_{len(conversations)}"
                    ),
                    messages=messages,
                    model=item.get("model", ""),
                    language=item.get("language", "en"),
                    source="wildchat",
                    metadata={
                        "turn": item.get("turn", 0),
                        "toxic": item.get("toxic", False),
                        "hashed_ip": item.get("hashed_ip", ""),
                        "country": item.get("country", ""),
                    },
                )
                conversations.append(conv)

                if len(conversations) >= num_samples:
                    break

            if use_cache and conversations:
                self._save_to_cache(conversations, cache_path)

            return conversations

        except Exception as e:
            logger.warning(f"Failed to load WildChat dataset: {e}")
            raise DatasetNotAvailableError(f"Could not load WildChat-1M: {e}")

    def load_wildchat_reasoning(
        self,
        num_samples: int = 100,
        use_cache: bool = True,
    ) -> list[RealConversation]:
        """
        Load reasoning model conversations from WildChat-4.8M.

        This subset includes o1-preview and o1-mini conversations
        which are valuable for testing high-reasoning intent routing.

        Args:
            num_samples: Number of conversations to load
            use_cache: Whether to use cached data

        Returns:
            List of RealConversation objects with reasoning models
        """
        cache_path = self._get_cache_path(
            f"{self.WILDCHAT_4_8M}_reasoning", num_samples
        )

        if use_cache and cache_path.exists():
            return self._load_from_cache(cache_path)

        if not self._check_datasets_library():
            raise DatasetNotAvailableError(
                "The 'datasets' library is required. Install with: pip install datasets"
            )

        try:
            from datasets import load_dataset

            logger.info(
                f"Loading {num_samples} reasoning samples from WildChat-4.8M..."
            )

            # Load dataset (streaming)
            dataset = load_dataset(
                self.WILDCHAT_4_8M,
                split="train",
                streaming=True,
            )

            conversations = []
            reasoning_models = ["o1-preview", "o1-mini", "o1"]

            for item in dataset:
                model = item.get("model", "")

                # Only include reasoning models
                if not any(rm in model for rm in reasoning_models):
                    continue

                conv_data = item.get("conversation", [])
                if not conv_data:
                    continue

                messages = []
                for msg in conv_data:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role and content:
                        messages.append(RealMessage(role=role, content=content))

                if not messages:
                    continue

                conv = RealConversation(
                    conversation_id=item.get(
                        "conversation_hash", f"wc_r_{len(conversations)}"
                    ),
                    messages=messages,
                    model=model,
                    language=item.get("language", "en"),
                    source="wildchat_reasoning",
                    metadata={
                        "reasoning_model": True,
                    },
                )
                conversations.append(conv)

                if len(conversations) >= num_samples:
                    break

            if use_cache and conversations:
                self._save_to_cache(conversations, cache_path)

            return conversations

        except Exception as e:
            logger.warning(f"Failed to load WildChat reasoning: {e}")
            raise DatasetNotAvailableError(f"Could not load reasoning data: {e}")

    def analyze_patterns(self, conversations: list[RealConversation]) -> dict[str, Any]:
        """
        Analyze conversations for proxy-relevant patterns.

        Detects:
        - Repetitive prefixes (heartbeat potential)
        - System prompt patterns
        - Multi-turn depth
        - Token distribution
        """
        if not conversations:
            return {}

        total_tokens = 0
        turn_counts = []
        models_seen = set()
        languages_seen = set()

        # Pattern detection
        first_messages = []  # For repetition analysis
        long_conversations = 0
        short_responses = 0

        for conv in conversations:
            total_tokens += conv.estimated_tokens
            turn_counts.append(conv.num_turns)
            models_seen.add(conv.model)
            languages_seen.add(conv.language)

            if conv.messages:
                first_msg = conv.messages[0].content[:500]
                first_messages.append(first_msg)

            if conv.num_turns > 5:
                long_conversations += 1

            # Check for short responses (status-check pattern)
            for msg in conv.messages:
                if msg.role == "assistant" and len(msg.content) < 50:
                    short_responses += 1

        # Detect repetitive prefixes
        prefix_counts: dict[str, int] = {}
        for msg in first_messages:
            prefix = msg[:200]  # First 200 chars
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

        repetitive_prefixes = sum(1 for c in prefix_counts.values() if c > 1)

        return {
            "total_conversations": len(conversations),
            "total_tokens": total_tokens,
            "avg_tokens_per_conv": total_tokens // len(conversations),
            "avg_turns": sum(turn_counts) / len(turn_counts),
            "max_turns": max(turn_counts),
            "models": list(models_seen),
            "languages": list(languages_seen)[:10],  # Top 10
            "long_conversations": long_conversations,
            "short_responses": short_responses,
            "repetitive_prefixes": repetitive_prefixes,
            "cache_potential": (
                repetitive_prefixes / len(conversations) if conversations else 0
            ),
        }

    def load_everyday_conversations(
        self,
        num_samples: int = 100,
        use_cache: bool = True,
    ) -> list[RealConversation]:
        """
        Load conversations from HuggingFace Everyday Conversations dataset.

        This is a PUBLIC dataset (no authentication required) with 2.2k
        multi-turn conversations generated by Llama-3.1-70B-Instruct.

        Good for quick testing without HuggingFace authentication.

        Args:
            num_samples: Number of conversations to load
            use_cache: Whether to use cached data

        Returns:
            List of RealConversation objects
        """
        cache_path = self._get_cache_path(self.EVERYDAY_CONVERSATIONS, num_samples)

        if use_cache and cache_path.exists():
            return self._load_from_cache(cache_path)

        if not self._check_datasets_library():
            raise DatasetNotAvailableError(
                "The 'datasets' library is required. Install with: pip install datasets"
            )

        try:
            from datasets import load_dataset

            logger.info(f"Loading {num_samples} samples from Everyday Conversations...")

            # This is a small dataset, load directly
            # Note: This dataset uses "train_sft" split, not "train"
            dataset = load_dataset(
                self.EVERYDAY_CONVERSATIONS,
                split="train_sft",
            )

            conversations = []
            for idx, item in enumerate(dataset):
                if idx >= num_samples:
                    break

                # Parse conversation - format is list of {"role": ..., "content": ...}
                conv_data = item.get("messages", [])
                if not conv_data:
                    continue

                messages = []
                for msg in conv_data:
                    role = msg.get("role", "")
                    content = msg.get("content", "")
                    if role and content:
                        messages.append(RealMessage(role=role, content=content))

                if not messages:
                    continue

                conv = RealConversation(
                    conversation_id=f"everyday_{idx}",
                    messages=messages,
                    model="llama-3.1-70b",
                    language="en",
                    source="everyday_conversations",
                    metadata={},
                )
                conversations.append(conv)

            if use_cache and conversations:
                self._save_to_cache(conversations, cache_path)

            return conversations

        except Exception as e:
            logger.warning(f"Failed to load Everyday Conversations: {e}")
            raise DatasetNotAvailableError(
                f"Could not load Everyday Conversations: {e}"
            )

    def load_openassistant(
        self,
        num_samples: int = 100,
        language: str = "en",
        use_cache: bool = True,
    ) -> list[RealConversation]:
        """
        Load conversations from OpenAssistant dataset.

        This is a PUBLIC dataset (no authentication required) with
        human-generated multi-turn conversations.

        Args:
            num_samples: Number of conversations to load
            language: Language code to filter (default: "en")
            use_cache: Whether to use cached data

        Returns:
            List of RealConversation objects
        """
        cache_path = self._get_cache_path(
            f"{self.OPENASSISTANT}_{language}", num_samples
        )

        if use_cache and cache_path.exists():
            return self._load_from_cache(cache_path)

        if not self._check_datasets_library():
            raise DatasetNotAvailableError(
                "The 'datasets' library is required. Install with: pip install datasets"
            )

        try:
            from datasets import load_dataset

            logger.info(f"Loading {num_samples} samples from OpenAssistant...")

            # Load the dataset
            dataset = load_dataset(
                self.OPENASSISTANT,
                split="train",
            )

            # OpenAssistant has a tree structure - we need to reconstruct conversations
            # Group by parent_id to build conversation threads
            conversations = []
            messages_by_id: dict[str, dict] = {}
            root_messages = []

            for item in dataset:
                msg_id = item.get("message_id", "")
                parent_id = item.get("parent_id")
                lang = item.get("lang", "")

                if language and lang != language:
                    continue

                messages_by_id[msg_id] = item
                if parent_id is None:
                    root_messages.append(item)

            # Build conversations from root messages
            for root in root_messages[: num_samples * 2]:  # Get more roots to filter
                thread = [root]
                current_id = root.get("message_id")

                # Find replies (simplified - just get first reply chain)
                for _ in range(10):  # Max depth
                    found_reply = False
                    for msg_id, msg in messages_by_id.items():
                        if msg.get("parent_id") == current_id:
                            thread.append(msg)
                            current_id = msg_id
                            found_reply = True
                            break
                    if not found_reply:
                        break

                if len(thread) < 2:
                    continue

                messages = []
                for i, msg in enumerate(thread):
                    # Alternate roles based on position
                    role = "user" if i % 2 == 0 else "assistant"
                    content = msg.get("text", "")
                    if content:
                        messages.append(RealMessage(role=role, content=content))

                if len(messages) >= 2:
                    conv = RealConversation(
                        conversation_id=root.get(
                            "message_id", f"oasst_{len(conversations)}"
                        ),
                        messages=messages,
                        model="human",
                        language=language,
                        source="openassistant",
                        metadata={
                            "message_tree_id": root.get("message_tree_id", ""),
                        },
                    )
                    conversations.append(conv)

                if len(conversations) >= num_samples:
                    break

            if use_cache and conversations:
                self._save_to_cache(conversations, cache_path)

            return conversations

        except Exception as e:
            logger.warning(f"Failed to load OpenAssistant: {e}")
            raise DatasetNotAvailableError(f"Could not load OpenAssistant: {e}")

    def load_any_available(
        self,
        num_samples: int = 100,
        use_cache: bool = True,
    ) -> tuple[str, list[RealConversation]]:
        """
        Load conversations from any available dataset.

        Tries datasets in order of preference, returning the first
        that successfully loads. Useful for CI environments where
        authentication may not be available.

        Order of preference:
        1. Everyday Conversations (small, fast, public)
        2. OpenAssistant (public, human-generated)
        3. LMSYS-Chat-1M (gated, requires auth)
        4. WildChat-1M (gated, requires auth)

        Args:
            num_samples: Number of conversations to load
            use_cache: Whether to use cached data

        Returns:
            Tuple of (dataset_name, conversations)
        """
        datasets_to_try = [
            ("everyday_conversations", self.load_everyday_conversations),
            ("openassistant", self.load_openassistant),
            ("lmsys", self.load_lmsys),
            ("wildchat", self.load_wildchat),
        ]

        errors = []
        for name, loader_func in datasets_to_try:
            try:
                logger.info(f"Trying to load {name}...")
                convs = loader_func(num_samples=num_samples, use_cache=use_cache)
                if convs:
                    logger.info(f"Successfully loaded {len(convs)} from {name}")
                    return name, convs
            except Exception as e:
                errors.append(f"{name}: {e}")
                continue

        raise DatasetNotAvailableError(
            f"Could not load any dataset. Errors: {'; '.join(errors)}"
        )

    def iter_conversations(
        self,
        dataset: str = "lmsys",
        batch_size: int = 100,
        **kwargs,
    ) -> Iterator[list[RealConversation]]:
        """
        Iterate over conversations in batches.

        Useful for processing large datasets without loading all into memory.

        Args:
            dataset: "lmsys", "wildchat", "wildchat_reasoning", "everyday", "openassistant"
            batch_size: Number of conversations per batch
            **kwargs: Additional arguments passed to load function

        Yields:
            Batches of RealConversation objects
        """
        offset = 0
        while True:
            kwargs["num_samples"] = batch_size
            kwargs["use_cache"] = False  # Don't cache partial batches

            if dataset == "lmsys":
                batch = self.load_lmsys(**kwargs)
            elif dataset == "wildchat":
                batch = self.load_wildchat(**kwargs)
            elif dataset == "wildchat_reasoning":
                batch = self.load_wildchat_reasoning(**kwargs)
            elif dataset == "everyday":
                batch = self.load_everyday_conversations(**kwargs)
            elif dataset == "openassistant":
                batch = self.load_openassistant(**kwargs)
            else:
                raise ValueError(f"Unknown dataset: {dataset}")

            if not batch:
                break

            yield batch
            offset += batch_size

            # Safety limit
            if offset >= 10000:
                break


def convert_to_session_format(
    conversation: RealConversation,
) -> dict[str, Any]:
    """
    Convert RealConversation to the Session JSONL format used by tests.

    This allows real conversations to be processed by the same
    TokenAnalyzer used for synthetic fixtures.
    """
    messages = []

    # Add a synthetic system message if none exists
    has_system = any(m.role == "system" for m in conversation.messages)
    if not has_system:
        # Create a minimal system prompt
        messages.append(
            {
                "type": "message",
                "timestamp": "",
                "message": {
                    "role": "system",
                    "content": [
                        {"type": "text", "text": f"[MODEL: {conversation.model}]"}
                    ],
                },
            }
        )

    for msg in conversation.messages:
        messages.append(
            {
                "type": "message",
                "timestamp": "",
                "message": {
                    "role": msg.role,
                    "content": [{"type": "text", "text": msg.content}],
                },
            }
        )

    return {
        "session": {
            "type": "session",
            "session_id": conversation.conversation_id,
            "agent_id": conversation.model or "unknown",
            "created_at": "",
            "metadata": {
                "test_category": f"real_{conversation.source}",
                "source": conversation.source,
                "model": conversation.model,
                "language": conversation.language,
                **conversation.metadata,
            },
        },
        "messages": messages,
    }

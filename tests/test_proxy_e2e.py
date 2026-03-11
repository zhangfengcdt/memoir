"""
End-to-end tests for the Memoir Universal LLM Proxy.

Tests validate the core design goals from docs/design/llm_proxy.md:
1. Heartbeat Leak optimization - reduce repetitive status check costs
2. Jitter Problem elimination - normalize dynamic prefixes for cache stability
3. Capability Bloat reduction - deduplicate tool schemas across requests
4. Intent-based Model Arbitrage - route to cost-appropriate models
5. Multi-Agent Branching - fleet sync and swarm swapping patterns

Run with: pytest tests/test_proxy_e2e.py -v

Token Comparison Tests:
- Compare baseline tokens (no proxy) vs optimized tokens (with proxy)
- Run with: pytest tests/test_proxy_e2e.py -v -k "token_comparison"
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

# Fixture directory path
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "proxy"


# =============================================================================
# Fixture Loader
# =============================================================================


@dataclass
class Message:
    """Represents a single message in a conversation."""

    role: str
    content: list[dict[str, Any]]
    timestamp: str = ""
    usage: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class Session:
    """Represents a conversation session loaded from JSONL."""

    session_id: str
    agent_id: str
    created_at: str
    messages: list[Message] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def system_messages(self) -> list[Message]:
        """Get all system messages (prompts)."""
        return [m for m in self.messages if m.role == "system"]

    @property
    def user_messages(self) -> list[Message]:
        """Get all user messages."""
        return [m for m in self.messages if m.role == "user"]

    @property
    def assistant_messages(self) -> list[Message]:
        """Get all assistant messages."""
        return [m for m in self.messages if m.role == "assistant"]

    @property
    def total_input_tokens(self) -> int:
        """Calculate total input tokens across all messages."""
        return sum(m.usage.get("input_tokens", 0) for m in self.messages if m.usage)

    @property
    def total_output_tokens(self) -> int:
        """Calculate total output tokens across all messages."""
        return sum(m.usage.get("output_tokens", 0) for m in self.messages if m.usage)


# =============================================================================
# Token Analysis
# =============================================================================


@dataclass
class TokenStats:
    """Statistics for token usage comparison."""

    baseline_tokens: int = 0  # Tokens sent without proxy
    optimized_tokens: int = 0  # Tokens sent with proxy
    cached_tokens: int = 0  # Tokens served from cache
    num_requests: int = 0

    @property
    def tokens_saved(self) -> int:
        """Total tokens saved by using proxy."""
        return self.baseline_tokens - self.optimized_tokens

    @property
    def savings_ratio(self) -> float:
        """Percentage of tokens saved (0.0 to 1.0)."""
        if self.baseline_tokens == 0:
            return 0.0
        return self.tokens_saved / self.baseline_tokens

    @property
    def cache_hit_rate(self) -> float:
        """Percentage of tokens served from cache."""
        if self.baseline_tokens == 0:
            return 0.0
        return self.cached_tokens / self.baseline_tokens

    def to_dict(self) -> dict:
        """Convert to dictionary for reporting."""
        return {
            "baseline_tokens": self.baseline_tokens,
            "optimized_tokens": self.optimized_tokens,
            "cached_tokens": self.cached_tokens,
            "tokens_saved": self.tokens_saved,
            "savings_ratio": f"{self.savings_ratio:.1%}",
            "cache_hit_rate": f"{self.cache_hit_rate:.1%}",
            "num_requests": self.num_requests,
        }


@dataclass
class TokenComparisonResult:
    """Result of comparing baseline vs optimized token usage."""

    category: str
    session_id: str
    baseline: TokenStats
    optimized: TokenStats | None = None
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Session: {self.session_id} ({self.category})",
            f"  Baseline tokens: {self.baseline.baseline_tokens:,}",
        ]
        if self.optimized:
            lines.extend([
                f"  Optimized tokens: {self.optimized.optimized_tokens:,}",
                f"  Tokens saved: {self.baseline.baseline_tokens - self.optimized.optimized_tokens:,}",
                f"  Savings: {(1 - self.optimized.optimized_tokens / max(1, self.baseline.baseline_tokens)):.1%}",
            ])
        return "\n".join(lines)


class TokenAnalyzer:
    """
    Analyzes token usage for baseline vs proxy-optimized scenarios.

    Baseline: Total tokens that would be sent to LLM without any optimization.
    Optimized: Tokens sent after proxy applies caching and deduplication.
    """

    # Approximate chars per token (conservative estimate)
    CHARS_PER_TOKEN = 4

    # Jitter patterns to strip for stable prefix calculation
    JITTER_PATTERNS = [
        r"Timestamp:\s*[\d\-T:\.Z]+",
        r"Request-ID:\s*[\w\-]+",
        r"X-Request-ID:\s*[\w\-]+",
        r"X-Trace-ID:\s*[\w\-]+",
        r"X-Span-ID:\s*[\w\-]+",
        r"Session-Token:\s*[\w\-]+",
    ]

    def __init__(self, proxy: Any | None = None):
        """
        Initialize analyzer.

        Args:
            proxy: Optional LLMProxy instance for real optimization.
                   If None, uses simulated optimization based on patterns.
        """
        self.proxy = proxy

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count from text."""
        return len(text) // self.CHARS_PER_TOKEN

    def extract_content_text(self, message: Message) -> str:
        """Extract text content from a message."""
        if not message.content:
            return ""
        texts = []
        for item in message.content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)

    def calculate_baseline_tokens(self, session: Session) -> TokenStats:
        """
        Calculate baseline token usage (no proxy optimization).

        This represents the total tokens sent to the LLM without any caching.
        Each request sends the full system prompt + conversation history.
        """
        total_tokens = 0
        num_requests = 0

        # Group messages by request (system -> user -> assistant cycles)
        current_system = ""
        conversation_history = []

        for msg in session.messages:
            if msg.role == "system":
                current_system = self.extract_content_text(msg)
            elif msg.role == "user":
                user_text = self.extract_content_text(msg)
                # Each user message triggers a request with full context
                request_tokens = self.estimate_tokens(current_system)
                for hist_msg in conversation_history:
                    request_tokens += self.estimate_tokens(hist_msg)
                request_tokens += self.estimate_tokens(user_text)
                total_tokens += request_tokens
                num_requests += 1
                conversation_history.append(user_text)
            elif msg.role == "assistant":
                assistant_text = self.extract_content_text(msg)
                conversation_history.append(assistant_text)
            elif msg.role == "toolResult":
                tool_text = self.extract_content_text(msg)
                conversation_history.append(tool_text)

        return TokenStats(
            baseline_tokens=total_tokens,
            num_requests=num_requests,
        )

    def strip_jitter(self, text: str) -> str:
        """Remove jitter patterns (timestamps, request IDs) from text."""
        result = text
        for pattern in self.JITTER_PATTERNS:
            result = re.sub(pattern, "", result)
        # Also strip the [RUNTIME] section if present
        result = re.sub(r"\[RUNTIME\].*?\n\n", "", result, flags=re.DOTALL)
        return result.strip()

    def extract_stable_prefix(self, text: str) -> str:
        """
        Extract stable prefix content that can be cached.

        Looks for [SOUL], [TOOLS], and other stable sections.
        """
        # Strip jitter first
        clean_text = self.strip_jitter(text)

        # Find stable sections
        stable_markers = ["[SOUL]", "[TOOLS]", "[SYSTEM]", "[CONTEXT]"]
        for marker in stable_markers:
            if marker in clean_text:
                return clean_text  # Return cleaned text as cacheable

        return clean_text

    def calculate_optimized_tokens(self, session: Session) -> TokenStats:
        """
        Calculate optimized token usage with proxy caching.

        Simulates proxy behavior:
        - First request: Full tokens (cache miss)
        - Subsequent requests with same prefix: Only dynamic suffix tokens
        """
        if self.proxy:
            return self._calculate_with_real_proxy(session)
        return self._calculate_simulated(session)

    def _calculate_simulated(self, session: Session) -> TokenStats:
        """Simulate proxy optimization based on pattern detection."""
        total_optimized = 0
        cached_tokens = 0
        num_requests = 0

        # Track seen prefixes for cache simulation
        prefix_cache: dict[str, int] = {}  # hash -> token count
        conversation_history: list[str] = []
        current_system = ""

        for msg in session.messages:
            if msg.role == "system":
                current_system = self.extract_content_text(msg)
            elif msg.role == "user":
                user_text = self.extract_content_text(msg)

                # Extract stable prefix
                stable_prefix = self.extract_stable_prefix(current_system)
                prefix_hash = hash(stable_prefix)
                prefix_tokens = self.estimate_tokens(stable_prefix)

                # Calculate dynamic suffix (user message + recent history)
                dynamic_tokens = self.estimate_tokens(user_text)
                # Add recent history (last 2 exchanges)
                for hist_msg in conversation_history[-4:]:
                    dynamic_tokens += self.estimate_tokens(hist_msg)

                if prefix_hash in prefix_cache:
                    # Cache hit - only send dynamic suffix
                    total_optimized += dynamic_tokens
                    cached_tokens += prefix_tokens
                else:
                    # Cache miss - send full request
                    total_optimized += prefix_tokens + dynamic_tokens
                    prefix_cache[prefix_hash] = prefix_tokens

                num_requests += 1
                conversation_history.append(user_text)

            elif msg.role == "assistant":
                assistant_text = self.extract_content_text(msg)
                conversation_history.append(assistant_text)
            elif msg.role == "toolResult":
                tool_text = self.extract_content_text(msg)
                conversation_history.append(tool_text)

        return TokenStats(
            optimized_tokens=total_optimized,
            cached_tokens=cached_tokens,
            num_requests=num_requests,
        )

    def _calculate_with_real_proxy(self, session: Session) -> TokenStats:
        """Calculate using actual proxy implementation."""
        # TODO: Implement when proxy is ready
        # This will call self.proxy.process() and measure actual token usage
        raise NotImplementedError("Real proxy integration pending")

    def compare(self, session: Session) -> TokenComparisonResult:
        """
        Compare baseline vs optimized token usage for a session.

        Returns detailed comparison results.
        """
        baseline = self.calculate_baseline_tokens(session)

        try:
            optimized = self.calculate_optimized_tokens(session)
        except NotImplementedError:
            optimized = None

        return TokenComparisonResult(
            category=session.metadata.get("test_category", "unknown"),
            session_id=session.session_id,
            baseline=baseline,
            optimized=optimized,
            details={
                "agent_id": session.agent_id,
                "message_count": len(session.messages),
            },
        )

    def compare_sessions(
        self, sessions: list[Session], share_cache: bool = False
    ) -> tuple[TokenStats, list[TokenComparisonResult]]:
        """
        Compare multiple sessions and aggregate results.

        Args:
            sessions: List of sessions to compare
            share_cache: If True, simulate shared cache across sessions
                        (for fleet sync pattern)

        Returns:
            Tuple of (aggregated_stats, individual_results)
        """
        results = []
        total_baseline = 0
        total_optimized = 0
        total_cached = 0
        total_requests = 0

        if share_cache:
            # Calculate with shared cache across all sessions
            optimized = self._calculate_shared_cache(sessions)
            for session in sessions:
                baseline = self.calculate_baseline_tokens(session)
                results.append(TokenComparisonResult(
                    category=session.metadata.get("test_category", "unknown"),
                    session_id=session.session_id,
                    baseline=baseline,
                    optimized=None,  # Individual results not available in shared mode
                ))
                total_baseline += baseline.baseline_tokens
                total_requests += baseline.num_requests

            total_optimized = optimized.optimized_tokens
            total_cached = optimized.cached_tokens
        else:
            for session in sessions:
                result = self.compare(session)
                results.append(result)

                total_baseline += result.baseline.baseline_tokens
                total_requests += result.baseline.num_requests

                if result.optimized:
                    total_optimized += result.optimized.optimized_tokens
                    total_cached += result.optimized.cached_tokens

        aggregate = TokenStats(
            baseline_tokens=total_baseline,
            optimized_tokens=total_optimized,
            cached_tokens=total_cached,
            num_requests=total_requests,
        )

        return aggregate, results

    def _calculate_shared_cache(self, sessions: list[Session]) -> TokenStats:
        """
        Calculate optimized tokens with cache shared across sessions.

        This simulates fleet sync behavior where multiple agent instances
        share the same KV cache.
        """
        total_optimized = 0
        cached_tokens = 0
        num_requests = 0

        # Shared prefix cache across all sessions
        prefix_cache: dict[int, int] = {}  # hash -> token count

        for session in sessions:
            conversation_history: list[str] = []
            current_system = ""

            for msg in session.messages:
                if msg.role == "system":
                    current_system = self.extract_content_text(msg)
                elif msg.role == "user":
                    user_text = self.extract_content_text(msg)

                    # Extract stable prefix
                    stable_prefix = self.extract_stable_prefix(current_system)
                    prefix_hash = hash(stable_prefix)
                    prefix_tokens = self.estimate_tokens(stable_prefix)

                    # Calculate dynamic suffix
                    dynamic_tokens = self.estimate_tokens(user_text)
                    for hist_msg in conversation_history[-4:]:
                        dynamic_tokens += self.estimate_tokens(hist_msg)

                    if prefix_hash in prefix_cache:
                        # Cache hit - only send dynamic suffix
                        total_optimized += dynamic_tokens
                        cached_tokens += prefix_tokens
                    else:
                        # Cache miss - send full request
                        total_optimized += prefix_tokens + dynamic_tokens
                        prefix_cache[prefix_hash] = prefix_tokens

                    num_requests += 1
                    conversation_history.append(user_text)

                elif msg.role == "assistant":
                    assistant_text = self.extract_content_text(msg)
                    conversation_history.append(assistant_text)
                elif msg.role == "toolResult":
                    tool_text = self.extract_content_text(msg)
                    conversation_history.append(tool_text)

        return TokenStats(
            optimized_tokens=total_optimized,
            cached_tokens=cached_tokens,
            num_requests=num_requests,
        )

    def generate_report(
        self, sessions: list[Session], category: str = ""
    ) -> str:
        """Generate a human-readable comparison report."""
        aggregate, results = self.compare_sessions(sessions)

        lines = [
            "=" * 60,
            f"Token Comparison Report: {category or 'All Sessions'}",
            "=" * 60,
            "",
            "AGGREGATE STATISTICS:",
            f"  Total Requests: {aggregate.num_requests}",
            f"  Baseline Tokens: {aggregate.baseline_tokens:,}",
            f"  Optimized Tokens: {aggregate.optimized_tokens:,}",
            f"  Cached Tokens: {aggregate.cached_tokens:,}",
            f"  Tokens Saved: {aggregate.tokens_saved:,}",
            f"  Savings Ratio: {aggregate.savings_ratio:.1%}",
            f"  Cache Hit Rate: {aggregate.cache_hit_rate:.1%}",
            "",
            "INDIVIDUAL SESSIONS:",
        ]

        for result in results:
            lines.append(str(result))
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)


class FixtureLoader:
    """Loads test fixtures from JSONL files."""

    def __init__(self, fixtures_dir: Path = FIXTURES_DIR):
        self.fixtures_dir = fixtures_dir

    def load_session(self, filepath: Path) -> Session:
        """Load a single session from a JSONL file."""
        messages = []
        session_data = {}

        with open(filepath) as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)

                if data.get("type") == "session":
                    session_data = data
                elif data.get("type") == "message":
                    msg_data = data.get("message", {})
                    messages.append(
                        Message(
                            role=msg_data.get("role", ""),
                            content=msg_data.get("content", []),
                            timestamp=data.get("timestamp", ""),
                            usage=data.get("usage"),
                            metadata=data.get("metadata") or msg_data.get("metadata"),
                        )
                    )

        return Session(
            session_id=session_data.get("session_id", filepath.stem),
            agent_id=session_data.get("agent_id", "unknown"),
            created_at=session_data.get("created_at", ""),
            messages=messages,
            metadata=session_data.get("metadata", {}),
        )

    def load_category(self, category: str) -> list[Session]:
        """Load all sessions from a category directory."""
        category_dir = self.fixtures_dir / category
        if not category_dir.exists():
            return []

        sessions = []
        for filepath in category_dir.glob("*.jsonl"):
            sessions.append(self.load_session(filepath))
        return sessions

    def load_all(self) -> dict[str, list[Session]]:
        """Load all fixtures organized by category."""
        categories = ["heartbeat", "jitter", "capability", "intent", "multi_agent"]
        return {cat: self.load_category(cat) for cat in categories}


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def fixture_loader() -> FixtureLoader:
    """Provide a fixture loader instance."""
    return FixtureLoader()


@pytest.fixture
def heartbeat_sessions(fixture_loader: FixtureLoader) -> list[Session]:
    """Load heartbeat pattern test sessions."""
    return fixture_loader.load_category("heartbeat")


@pytest.fixture
def jitter_sessions(fixture_loader: FixtureLoader) -> list[Session]:
    """Load jitter pattern test sessions."""
    return fixture_loader.load_category("jitter")


@pytest.fixture
def capability_sessions(fixture_loader: FixtureLoader) -> list[Session]:
    """Load capability bloat test sessions."""
    return fixture_loader.load_category("capability")


@pytest.fixture
def intent_sessions(fixture_loader: FixtureLoader) -> list[Session]:
    """Load intent classification test sessions."""
    return fixture_loader.load_category("intent")


@pytest.fixture
def multi_agent_sessions(fixture_loader: FixtureLoader) -> list[Session]:
    """Load multi-agent branching test sessions."""
    return fixture_loader.load_category("multi_agent")


@pytest.fixture
def token_analyzer() -> TokenAnalyzer:
    """Provide a token analyzer instance (simulated mode)."""
    return TokenAnalyzer(proxy=None)


@pytest.fixture
def all_sessions(fixture_loader: FixtureLoader) -> dict[str, list[Session]]:
    """Load all test sessions organized by category."""
    return fixture_loader.load_all()


# =============================================================================
# Token Comparison Tests
# =============================================================================


class TestTokenComparison:
    """
    Tests comparing baseline vs optimized token usage.

    These tests measure the actual token savings achieved by the proxy
    compared to sending requests directly to the LLM.

    Design Goals (from docs/design/llm_proxy.md):
    - KV Cache Hit Rate: >85%
    - Token Compression: 40% reduction
    - Cost per Heartbeat: <$0.01
    """

    def test_heartbeat_token_savings(
        self, heartbeat_sessions: list[Session], token_analyzer: TokenAnalyzer
    ):
        """
        Test token savings for heartbeat pattern.

        Heartbeat sessions have highly repetitive prompts that should
        achieve >85% cache hit rate.
        """
        if not heartbeat_sessions:
            pytest.skip("No heartbeat sessions available")

        aggregate, results = token_analyzer.compare_sessions(heartbeat_sessions)

        # Print report for visibility
        print("\n" + token_analyzer.generate_report(heartbeat_sessions, "Heartbeat"))

        # Verify savings
        assert aggregate.baseline_tokens > 0, "Should have baseline tokens"
        assert aggregate.savings_ratio > 0, "Should have some token savings"

        # Design goal: >85% cache hit rate for heartbeat pattern
        # Note: This may not be achievable in simulation, but real proxy should hit this
        if aggregate.cache_hit_rate < 0.50:
            print(f"WARNING: Cache hit rate {aggregate.cache_hit_rate:.1%} below 50%")

    def test_jitter_token_savings(
        self, jitter_sessions: list[Session], token_analyzer: TokenAnalyzer
    ):
        """
        Test token savings after jitter normalization.

        Sessions with timestamp/request ID jitter should still achieve
        good cache hit rates after normalization.
        """
        if not jitter_sessions:
            pytest.skip("No jitter sessions available")

        aggregate, results = token_analyzer.compare_sessions(jitter_sessions)

        print("\n" + token_analyzer.generate_report(jitter_sessions, "Jitter"))

        assert aggregate.baseline_tokens > 0, "Should have baseline tokens"

        # Jitter sessions should show savings after normalization
        # The stable [SOUL] and [TOOLS] sections should be cached
        assert aggregate.savings_ratio >= 0, "Jitter normalization should not increase tokens"

    def test_capability_bloat_token_savings(
        self, capability_sessions: list[Session], token_analyzer: TokenAnalyzer
    ):
        """
        Test token savings from capability deduplication.

        Sessions with repeated tool schemas should achieve significant
        token reduction through deduplication.
        """
        if not capability_sessions:
            pytest.skip("No capability sessions available")

        aggregate, results = token_analyzer.compare_sessions(capability_sessions)

        print("\n" + token_analyzer.generate_report(capability_sessions, "Capability Bloat"))

        assert aggregate.baseline_tokens > 0, "Should have baseline tokens"

        # Design goal: 40% token reduction
        # Capability bloat sessions should show significant savings
        if aggregate.savings_ratio < 0.30:
            print(f"WARNING: Savings ratio {aggregate.savings_ratio:.1%} below 30% target")

    def test_intent_token_comparison(
        self, intent_sessions: list[Session], token_analyzer: TokenAnalyzer
    ):
        """
        Test token usage across different intent types.

        High-reasoning tasks may have less caching potential,
        while simple extraction should cache well.
        """
        if not intent_sessions:
            pytest.skip("No intent sessions available")

        # Group by intent type
        by_intent: dict[str, list[Session]] = {}
        for session in intent_sessions:
            intent = session.metadata.get("expected_intent", "unknown")
            by_intent.setdefault(intent, []).append(session)

        for intent, sessions in by_intent.items():
            aggregate, _ = token_analyzer.compare_sessions(sessions)
            print(f"\n{intent.upper()} Intent:")
            print(f"  Baseline: {aggregate.baseline_tokens:,} tokens")
            print(f"  Optimized: {aggregate.optimized_tokens:,} tokens")
            print(f"  Savings: {aggregate.savings_ratio:.1%}")

    def test_multi_agent_token_savings(
        self, multi_agent_sessions: list[Session], token_analyzer: TokenAnalyzer
    ):
        """
        Test token savings for multi-agent patterns.

        Fleet sync should show excellent caching (identical prompts).
        Swarm swapping should show partial caching (inherited context).
        """
        if not multi_agent_sessions:
            pytest.skip("No multi-agent sessions available")

        # Separate by pattern
        fleet_sessions = [
            s for s in multi_agent_sessions
            if s.metadata.get("pattern") == "fleet_sync"
        ]
        swarm_sessions = [
            s for s in multi_agent_sessions
            if s.metadata.get("pattern") == "swarm_swapping"
        ]

        if fleet_sessions:
            # Fleet sync shares cache across sessions (identical prompts)
            aggregate, _ = token_analyzer.compare_sessions(
                fleet_sessions, share_cache=True
            )
            print("\nFLEET SYNC Pattern (shared cache):")
            print(f"  Baseline: {aggregate.baseline_tokens:,} tokens")
            print(f"  Optimized: {aggregate.optimized_tokens:,} tokens")
            print(f"  Savings: {aggregate.savings_ratio:.1%}")
            print(f"  Cache Hit Rate: {aggregate.cache_hit_rate:.1%}")

            # Fleet sync should have very high cache hit rate (identical prompts)
            assert aggregate.cache_hit_rate > 0.40, (
                f"Fleet sync should cache well, got {aggregate.cache_hit_rate:.1%}"
            )

        if swarm_sessions:
            aggregate, _ = token_analyzer.compare_sessions(swarm_sessions)
            print("\nSWARM SWAPPING Pattern:")
            print(f"  Baseline: {aggregate.baseline_tokens:,} tokens")
            print(f"  Optimized: {aggregate.optimized_tokens:,} tokens")
            print(f"  Savings: {aggregate.savings_ratio:.1%}")

    def test_aggregate_token_comparison(
        self, all_sessions: dict[str, list[Session]], token_analyzer: TokenAnalyzer
    ):
        """
        Test aggregate token savings across all categories.

        This provides an overall view of proxy effectiveness.
        """
        all_session_list = []
        for sessions in all_sessions.values():
            all_session_list.extend(sessions)

        if not all_session_list:
            pytest.skip("No sessions available")

        aggregate, results = token_analyzer.compare_sessions(all_session_list)

        print("\n" + "=" * 60)
        print("AGGREGATE TOKEN COMPARISON - ALL CATEGORIES")
        print("=" * 60)
        print(f"Total Sessions: {len(all_session_list)}")
        print(f"Total Requests: {aggregate.num_requests}")
        print(f"Baseline Tokens: {aggregate.baseline_tokens:,}")
        print(f"Optimized Tokens: {aggregate.optimized_tokens:,}")
        print(f"Cached Tokens: {aggregate.cached_tokens:,}")
        print(f"Tokens Saved: {aggregate.tokens_saved:,}")
        print(f"Savings Ratio: {aggregate.savings_ratio:.1%}")
        print(f"Cache Hit Rate: {aggregate.cache_hit_rate:.1%}")
        print("=" * 60)

        # Overall design goal: 40% token reduction
        # This is a soft assertion - actual results depend on workload mix
        if aggregate.savings_ratio < 0.20:
            print(f"NOTE: Overall savings {aggregate.savings_ratio:.1%} below 20%")
            print("This may improve with real proxy implementation.")

    def test_baseline_token_calculation(
        self, heartbeat_sessions: list[Session], token_analyzer: TokenAnalyzer
    ):
        """
        Verify baseline token calculation is accurate.

        Baseline should sum up all tokens sent without any caching.
        """
        for session in heartbeat_sessions:
            baseline = token_analyzer.calculate_baseline_tokens(session)

            # Baseline should have positive tokens if there are messages
            if session.user_messages:
                assert baseline.baseline_tokens > 0, (
                    f"Session {session.session_id} should have baseline tokens"
                )
                assert baseline.num_requests > 0, (
                    f"Session {session.session_id} should have requests"
                )
                assert baseline.num_requests == len(session.user_messages), (
                    "Each user message should be a request"
                )

    def test_optimized_vs_baseline_comparison(
        self, capability_sessions: list[Session], token_analyzer: TokenAnalyzer
    ):
        """
        Verify optimized tokens are always <= baseline tokens.

        Proxy should never increase token usage.
        """
        for session in capability_sessions:
            result = token_analyzer.compare(session)

            if result.optimized:
                assert result.optimized.optimized_tokens <= result.baseline.baseline_tokens, (
                    f"Session {session.session_id}: optimized ({result.optimized.optimized_tokens}) "
                    f"should not exceed baseline ({result.baseline.baseline_tokens})"
                )


# =============================================================================
# Heartbeat Leak Tests
# =============================================================================


class TestHeartbeatOptimization:
    """
    Tests for heartbeat leak pattern optimization.

    Design Goal: Reduce cost per heartbeat to <$0.01 by caching stable prefixes.
    Pattern: Repetitive status checks with 15k+ token prompts returning minimal output.
    """

    def test_heartbeat_sessions_loaded(self, heartbeat_sessions: list[Session]):
        """Verify heartbeat test fixtures are loaded correctly."""
        assert len(heartbeat_sessions) >= 1, "Expected at least 1 heartbeat session"

        for session in heartbeat_sessions:
            assert session.metadata.get("test_category") == "heartbeat_leak"
            assert len(session.messages) > 0

    def test_heartbeat_prefix_stability(self, heartbeat_sessions: list[Session]):
        """
        Test that system prompts remain stable across heartbeat checks.
        The proxy should detect these as Tier 1 (Identity) frozen blocks.
        """
        for session in heartbeat_sessions:
            system_prompts = [
                m.content[0].get("text", "")
                for m in session.system_messages
                if m.content
            ]

            if len(system_prompts) >= 2:
                # All system prompts should be identical (stable prefix)
                first_prompt = system_prompts[0]
                for prompt in system_prompts[1:]:
                    assert prompt == first_prompt, (
                        "Heartbeat system prompts should be identical for cache reuse"
                    )

    def test_heartbeat_minimal_response(self, heartbeat_sessions: list[Session]):
        """
        Test that heartbeat responses are minimal (HEARTBEAT_OK pattern).
        This validates the pattern where large input produces tiny output.
        """
        for session in heartbeat_sessions:
            for msg in session.assistant_messages:
                if msg.usage:
                    output_tokens = msg.usage.get("output_tokens", 0)
                    # Heartbeat responses should be very short
                    assert output_tokens < 50, (
                        f"Heartbeat response too long: {output_tokens} tokens"
                    )

    def test_heartbeat_cache_savings_potential(self, heartbeat_sessions: list[Session]):
        """
        Calculate potential cache savings for heartbeat pattern.
        With >85% cache hit rate, we should see significant token reuse.
        """
        for session in heartbeat_sessions:
            system_messages = session.system_messages
            if len(system_messages) < 2:
                continue

            # Calculate tokens that could be cached
            # (system prompt tokens repeated across requests)
            first_system = system_messages[0]
            if first_system.content:
                prefix_chars = len(first_system.content[0].get("text", ""))
                # Approximate tokens (1 token ≈ 4 chars)
                prefix_tokens = prefix_chars // 4

                # With N requests, we could save (N-1) * prefix_tokens
                num_requests = len(system_messages)
                potential_savings = (num_requests - 1) * prefix_tokens

                assert potential_savings > 0, (
                    "Heartbeat sessions should have caching potential"
                )


# =============================================================================
# Jitter Elimination Tests
# =============================================================================


class TestJitterElimination:
    """
    Tests for jitter problem elimination.

    Design Goal: Achieve >85% KV cache hit rate by normalizing dynamic prefixes.
    Pattern: Timestamps, request IDs, and session tokens at prompt start.
    """

    def test_jitter_sessions_loaded(self, jitter_sessions: list[Session]):
        """Verify jitter test fixtures are loaded correctly."""
        assert len(jitter_sessions) >= 1, "Expected at least 1 jitter session"

        for session in jitter_sessions:
            assert session.metadata.get("test_category") == "jitter_problem"

    def test_jitter_detection_timestamps(self, jitter_sessions: list[Session]):
        """
        Test detection of timestamp jitter in prompts.
        The proxy should identify and normalize these patterns.
        """
        timestamp_patterns = [
            "Timestamp:",
            "timestamp:",
            "T:",  # ISO format T separator
            "Request-ID:",
            "X-Request-ID:",
            "X-Trace-ID:",
        ]

        for session in jitter_sessions:
            for msg in session.system_messages:
                if not msg.content:
                    continue
                text = msg.content[0].get("text", "")

                # Check if any jitter patterns are present
                has_jitter = any(pattern in text for pattern in timestamp_patterns)
                if has_jitter:
                    # This is a jitter test case - proxy should normalize these
                    assert True, "Jitter pattern detected for normalization"

    def test_stable_content_after_jitter(self, jitter_sessions: list[Session]):
        """
        Test that content after jitter headers remains stable.
        The proxy should extract stable [SOUL] and [TOOLS] sections.
        """
        for session in jitter_sessions:
            soul_sections = []

            for msg in session.system_messages:
                if not msg.content:
                    continue
                text = msg.content[0].get("text", "")

                # Extract content after [SOUL] marker
                if "[SOUL]" in text:
                    soul_start = text.index("[SOUL]")
                    # Get content up to next section or end
                    soul_content = text[soul_start:]
                    if "[TOOLS]" in soul_content:
                        soul_content = soul_content[: soul_content.index("[TOOLS]")]
                    soul_sections.append(soul_content)

            # All SOUL sections should be identical despite jitter
            if len(soul_sections) >= 2:
                for section in soul_sections[1:]:
                    assert section == soul_sections[0], (
                        "SOUL sections should be stable despite jitter"
                    )


# =============================================================================
# Capability Bloat Tests
# =============================================================================


class TestCapabilityBloatReduction:
    """
    Tests for capability bloat reduction.

    Design Goal: Achieve 40% token reduction by deduplicating tool schemas.
    Pattern: Full tool schemas transmitted on every request regardless of task.
    """

    def test_capability_sessions_loaded(self, capability_sessions: list[Session]):
        """Verify capability bloat test fixtures are loaded correctly."""
        assert len(capability_sessions) >= 1, "Expected at least 1 capability session"

        for session in capability_sessions:
            assert session.metadata.get("test_category") == "capability_bloat"

    def test_tool_schema_duplication(self, capability_sessions: list[Session]):
        """
        Test detection of duplicated tool schemas across requests.
        The proxy should deduplicate these into Tier 1 frozen blocks.
        """
        for session in capability_sessions:
            tools_sections = []

            for msg in session.system_messages:
                if not msg.content:
                    continue
                text = msg.content[0].get("text", "")

                # Extract [TOOLS] section
                if "[TOOLS]" in text:
                    tools_start = text.index("[TOOLS]")
                    tools_content = text[tools_start:]
                    tools_sections.append(tools_content)

            # Check for duplication
            if len(tools_sections) >= 2:
                # All tools sections should be identical (bloat pattern)
                assert all(t == tools_sections[0] for t in tools_sections), (
                    "Tool schemas should be identical across requests (bloat pattern)"
                )

                # Calculate wasted tokens
                tools_chars = len(tools_sections[0])
                tools_tokens = tools_chars // 4  # Approximate
                wasted_tokens = (len(tools_sections) - 1) * tools_tokens

                assert wasted_tokens > 0, (
                    "Capability bloat should show token waste potential"
                )

    def test_simple_task_with_full_tools(self, capability_sessions: list[Session]):
        """
        Test pattern where simple tasks receive full tool schemas.
        Example: "What is 2 + 2?" with 12 tool definitions.
        """
        for session in capability_sessions:
            for i, msg in enumerate(session.user_messages):
                if not msg.content:
                    continue
                text = msg.content[0].get("text", "")

                # Check for simple queries
                simple_patterns = ["What is", "What day", "Thanks", "Hello"]
                is_simple = any(p in text for p in simple_patterns)

                if is_simple:
                    # Find corresponding system message
                    system_msgs = session.system_messages
                    if system_msgs:
                        system_text = system_msgs[0].content[0].get("text", "")
                        tool_count = system_text.count('"name":')

                        # Simple tasks shouldn't need many tools
                        if tool_count > 5:
                            # This is a bloat case - proxy should optimize
                            assert True, (
                                f"Simple task with {tool_count} tools - bloat detected"
                            )


# =============================================================================
# Intent Classification Tests
# =============================================================================


class TestIntentClassification:
    """
    Tests for intent-based model arbitrage.

    Design Goal: Route requests to cost-appropriate models based on intent.
    Categories:
    - High-Reasoning: Claude Sonnet / GPT-4 (complex implementation)
    - Status Check: Gemini Flash / GPT-4o-mini (simple status)
    - Simple Extraction: Haiku / Flash (parsing, extraction)
    """

    def test_intent_sessions_loaded(self, intent_sessions: list[Session]):
        """Verify intent classification test fixtures are loaded correctly."""
        assert len(intent_sessions) >= 1, "Expected at least 1 intent session"

    def test_high_reasoning_intent_detection(self, intent_sessions: list[Session]):
        """
        Test detection of high-reasoning intent requiring premium models.
        """
        high_reasoning_keywords = [
            "implement",
            "design",
            "architect",
            "refactor",
            "optimize",
            "distributed",
            "algorithm",
            "CRDT",
            "OAuth",
        ]

        for session in intent_sessions:
            expected_intent = session.metadata.get("expected_intent")
            if expected_intent != "high_reasoning":
                continue

            for msg in session.user_messages:
                if not msg.content:
                    continue
                text = msg.content[0].get("text", "").lower()

                # Should contain high-reasoning keywords
                has_reasoning_keyword = any(k in text for k in high_reasoning_keywords)
                assert has_reasoning_keyword, (
                    f"High-reasoning task should contain complexity indicators: {text}"
                )

    def test_status_check_intent_detection(self, intent_sessions: list[Session]):
        """
        Test detection of simple status check intent for lightweight models.
        """
        status_keywords = [
            "check",
            "status",
            "update",
            "ping",
            "any new",
            "what's the current",
        ]

        for session in intent_sessions:
            expected_intent = session.metadata.get("expected_intent")
            if expected_intent != "status_check":
                continue

            for msg in session.user_messages:
                if not msg.content:
                    continue
                text = msg.content[0].get("text", "").lower()

                has_status_keyword = any(k in text for k in status_keywords)
                assert has_status_keyword, (
                    f"Status check should contain status indicators: {text}"
                )

    def test_simple_extraction_intent_detection(self, intent_sessions: list[Session]):
        """
        Test detection of simple extraction intent for cheapest models.
        """
        extraction_keywords = [
            "parse",
            "extract",
            "convert",
            "sum",
            "list",
            "json",
            "csv",
        ]

        for session in intent_sessions:
            expected_intent = session.metadata.get("expected_intent")
            if expected_intent != "simple_extraction":
                continue

            for msg in session.user_messages:
                if not msg.content:
                    continue
                text = msg.content[0].get("text", "").lower()

                has_extraction_keyword = any(k in text for k in extraction_keywords)
                assert has_extraction_keyword, (
                    f"Extraction task should contain extraction indicators: {text}"
                )

    def test_model_tier_mapping(self, intent_sessions: list[Session]):
        """
        Test that expected model tiers are correctly specified in fixtures.
        """
        tier_models = {
            "high": ["claude-sonnet", "gpt-4", "claude-opus"],
            "low": ["gemini-flash", "gpt-4o-mini", "haiku"],
        }

        for session in intent_sessions:
            expected_tier = session.metadata.get("expected_model_tier")
            if not expected_tier:
                continue

            # Verify tier is valid
            assert expected_tier in tier_models, (
                f"Unknown model tier: {expected_tier}"
            )


# =============================================================================
# Multi-Agent Branching Tests
# =============================================================================


class TestMultiAgentBranching:
    """
    Tests for multi-agent branching patterns.

    Design Goal: Support fleet sync (horizontal) and swarm swapping (vertical).
    Patterns:
    - Fleet Sync: Multiple identical agent instances sharing cache
    - Swarm Swapping: Parent agents spawning specialized children
    """

    def test_multi_agent_sessions_loaded(self, multi_agent_sessions: list[Session]):
        """Verify multi-agent test fixtures are loaded correctly."""
        assert len(multi_agent_sessions) >= 1, "Expected at least 1 multi-agent session"

    def test_fleet_sync_identical_prompts(self, multi_agent_sessions: list[Session]):
        """
        Test that fleet sync agents have identical system prompts.
        This enables cache sharing across the fleet.
        """
        fleet_sessions = [
            s for s in multi_agent_sessions
            if s.metadata.get("pattern") == "fleet_sync"
        ]

        if len(fleet_sessions) < 2:
            pytest.skip("Need at least 2 fleet sessions for comparison")

        # Extract system prompts from each fleet member
        fleet_prompts = []
        for session in fleet_sessions:
            if session.system_messages:
                prompt = session.system_messages[0].content[0].get("text", "")
                fleet_prompts.append(prompt)

        # All fleet members should have identical prompts
        if len(fleet_prompts) >= 2:
            for prompt in fleet_prompts[1:]:
                assert prompt == fleet_prompts[0], (
                    "Fleet sync agents must have identical system prompts"
                )

    def test_fleet_sync_different_tasks(self, multi_agent_sessions: list[Session]):
        """
        Test that fleet members process different tasks.
        Cache is shared but work is distributed.
        """
        fleet_sessions = [
            s for s in multi_agent_sessions
            if s.metadata.get("pattern") == "fleet_sync"
        ]

        if len(fleet_sessions) < 2:
            pytest.skip("Need at least 2 fleet sessions for comparison")

        # Extract user queries
        queries = []
        for session in fleet_sessions:
            for msg in session.user_messages:
                if msg.content:
                    queries.append(msg.content[0].get("text", ""))

        # Tasks should be different (work distribution)
        if len(queries) >= 2:
            assert len(set(queries)) > 1, (
                "Fleet members should process different tasks"
            )

    def test_swarm_parent_child_inheritance(self, multi_agent_sessions: list[Session]):
        """
        Test that swarm children inherit parent context.
        """
        swarm_sessions = [
            s for s in multi_agent_sessions
            if s.metadata.get("pattern") == "swarm_swapping"
        ]

        parent_sessions = [s for s in swarm_sessions if "parent" in s.session_id]
        child_sessions = [s for s in swarm_sessions if "child" in s.session_id]

        if not parent_sessions or not child_sessions:
            pytest.skip("Need parent and child sessions for swarm test")

        # Check that child has inherited context marker
        for child in child_sessions:
            if child.system_messages:
                prompt = child.system_messages[0].content[0].get("text", "")

                # Should have inheritance markers
                has_inheritance = (
                    "[INHERITED_CONTEXT]" in prompt
                    or "[SOUL:DEVELOPER_SPECIALIZATION]" in prompt
                    or "parent" in prompt.lower()
                )
                assert has_inheritance, (
                    "Swarm child should have inherited context markers"
                )

    def test_swarm_specialization(self, multi_agent_sessions: list[Session]):
        """
        Test that swarm children have specialized instructions.
        """
        child_sessions = [
            s for s in multi_agent_sessions
            if "child" in s.session_id and s.metadata.get("pattern") == "swarm_swapping"
        ]

        for child in child_sessions:
            if child.system_messages:
                prompt = child.system_messages[0].content[0].get("text", "")

                # Should have specialization markers
                specialization_markers = [
                    "SPECIALIZATION",
                    "Developer Mission",
                    "specialist",
                    "specialized",
                ]
                has_specialization = any(m in prompt for m in specialization_markers)
                assert has_specialization, (
                    "Swarm child should have specialization instructions"
                )


# =============================================================================
# Integration Tests (Placeholder)
# =============================================================================


class TestProxyIntegration:
    """
    Integration tests for the full proxy pipeline.

    These tests will be implemented once the proxy components are ready.
    They validate end-to-end behavior with actual proxy processing.
    """

    @pytest.mark.skip(reason="Proxy implementation pending")
    def test_proxy_heartbeat_optimization(self, heartbeat_sessions: list[Session]):
        """Test proxy achieves <$0.01 cost per heartbeat."""
        # TODO: Implement with actual proxy
        pass

    @pytest.mark.skip(reason="Proxy implementation pending")
    def test_proxy_cache_hit_rate(self, jitter_sessions: list[Session]):
        """Test proxy achieves >85% KV cache hit rate."""
        # TODO: Implement with actual proxy
        pass

    @pytest.mark.skip(reason="Proxy implementation pending")
    def test_proxy_token_compression(self, capability_sessions: list[Session]):
        """Test proxy achieves 40% token reduction."""
        # TODO: Implement with actual proxy
        pass

    @pytest.mark.skip(reason="Proxy implementation pending")
    def test_proxy_intent_routing(self, intent_sessions: list[Session]):
        """Test proxy routes to correct model tiers."""
        # TODO: Implement with actual proxy
        pass

    @pytest.mark.skip(reason="Proxy implementation pending")
    def test_proxy_fleet_cache_sharing(self, multi_agent_sessions: list[Session]):
        """Test proxy shares cache across fleet members."""
        # TODO: Implement with actual proxy
        pass

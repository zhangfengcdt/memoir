"""
Predictive Cache Warming.

Pre-emptively warms LLM provider caches when vector search returns
"near hits" to ensure optimal cache utilization.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


@dataclass
class WarmingRequest:
    """A cache warming request."""

    anchor_hash: str
    prefix_content: str
    provider: str
    priority: int = 0  # Higher = more urgent
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


@dataclass
class WarmingResult:
    """Result of a warming attempt."""

    anchor_hash: str
    success: bool
    latency_ms: float
    provider_response: Optional[dict] = None
    error: Optional[str] = None


class ProviderWarmer(Protocol):
    """Protocol for provider-specific warming implementations."""

    async def warm(self, prefix: str) -> dict:
        """Send a warming request to the provider."""
        ...


class CacheWarmer:
    """
    Manages predictive cache warming.

    When vector search returns a "near hit" (high similarity but not exact),
    preemptively sends warming requests to ensure the cache is hot.
    """

    # Default TTL for warming requests
    DEFAULT_TTL_SECONDS = 300  # 5 minutes

    # Maximum concurrent warming requests
    MAX_CONCURRENT = 5

    # Similarity threshold for "near hit" warming
    NEAR_HIT_THRESHOLD = 0.85

    def __init__(
        self,
        max_queue_size: int = 100,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """
        Initialize the cache warmer.

        Args:
            max_queue_size: Maximum pending warming requests.
            ttl_seconds: Time-to-live for warming requests.
        """
        self._queue: asyncio.Queue[WarmingRequest] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._ttl = timedelta(seconds=ttl_seconds)
        self._warmers: dict[str, ProviderWarmer] = {}
        self._active_tasks: set[asyncio.Task] = set()
        self._warmed_cache: dict[str, datetime] = {}  # hash -> last warmed time
        self._running = False

    def register_provider(self, name: str, warmer: ProviderWarmer) -> None:
        """
        Register a provider-specific warmer.

        Args:
            name: Provider name (e.g., "anthropic", "google").
            warmer: ProviderWarmer implementation.
        """
        self._warmers[name] = warmer

    async def schedule_warming(
        self,
        anchor_hash: str,
        prefix_content: str,
        provider: str,
        similarity: float,
        priority: int = 0,
    ) -> bool:
        """
        Schedule a cache warming request.

        Args:
            anchor_hash: The cache anchor hash.
            prefix_content: The prefix content to warm.
            provider: Target provider name.
            similarity: Similarity score (0-1) from vector search.
            priority: Request priority (higher = more urgent).

        Returns:
            True if request was queued, False if skipped.
        """
        # Check if similarity warrants warming
        if similarity < self.NEAR_HIT_THRESHOLD:
            logger.debug(
                f"Skipping warming for {anchor_hash[:8]}: similarity {similarity:.2f} below threshold"
            )
            return False

        # Check if recently warmed
        if anchor_hash in self._warmed_cache:
            last_warmed = self._warmed_cache[anchor_hash]
            if datetime.utcnow() - last_warmed < self._ttl:
                logger.debug(f"Skipping warming for {anchor_hash[:8]}: recently warmed")
                return False

        # Check if provider is registered
        if provider not in self._warmers:
            logger.warning(f"No warmer registered for provider: {provider}")
            return False

        # Create and queue the request
        request = WarmingRequest(
            anchor_hash=anchor_hash,
            prefix_content=prefix_content,
            provider=provider,
            priority=priority,
            expires_at=datetime.utcnow() + self._ttl,
        )

        try:
            self._queue.put_nowait(request)
            logger.info(f"Queued warming request for {anchor_hash[:8]} on {provider}")
            return True
        except asyncio.QueueFull:
            logger.warning("Warming queue full, dropping request")
            return False

    async def warm_now(
        self,
        anchor_hash: str,
        prefix_content: str,
        provider: str,
    ) -> WarmingResult:
        """
        Immediately warm a cache (synchronous warming).

        Args:
            anchor_hash: The cache anchor hash.
            prefix_content: The prefix content to warm.
            provider: Target provider name.

        Returns:
            WarmingResult with success status.
        """
        if provider not in self._warmers:
            return WarmingResult(
                anchor_hash=anchor_hash,
                success=False,
                latency_ms=0,
                error=f"Unknown provider: {provider}",
            )

        warmer = self._warmers[provider]
        start_time = datetime.utcnow()

        try:
            response = await warmer.warm(prefix_content)
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            self._warmed_cache[anchor_hash] = datetime.utcnow()

            return WarmingResult(
                anchor_hash=anchor_hash,
                success=True,
                latency_ms=latency,
                provider_response=response,
            )
        except Exception as e:
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error(f"Warming failed for {anchor_hash[:8]}: {e}")

            return WarmingResult(
                anchor_hash=anchor_hash,
                success=False,
                latency_ms=latency,
                error=str(e),
            )

    async def start(self) -> None:
        """Start the background warming worker."""
        if self._running:
            return

        self._running = True
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("Cache warmer started")

    async def stop(self) -> None:
        """Stop the background warming worker."""
        self._running = False

        # Cancel active tasks
        for task in self._active_tasks:
            task.cancel()

        # Wait for tasks to complete
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)

        self._active_tasks.clear()
        logger.info("Cache warmer stopped")

    async def _worker(self) -> None:
        """Background worker that processes warming requests."""
        while self._running:
            try:
                # Wait for a request with timeout
                try:
                    request = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                # Check if request expired
                if request.expires_at and datetime.utcnow() > request.expires_at:
                    logger.debug(f"Warming request expired: {request.anchor_hash[:8]}")
                    continue

                # Limit concurrent tasks
                while len(self._active_tasks) >= self.MAX_CONCURRENT:
                    _done, self._active_tasks = await asyncio.wait(
                        self._active_tasks, return_when=asyncio.FIRST_COMPLETED
                    )

                # Create warming task
                task = asyncio.create_task(
                    self.warm_now(
                        request.anchor_hash,
                        request.prefix_content,
                        request.provider,
                    )
                )
                self._active_tasks.add(task)

            except Exception as e:
                logger.error(f"Warming worker error: {e}")

    def get_stats(self) -> dict:
        """
        Get warming statistics.

        Returns:
            Dict with queue size, active tasks, and cache stats.
        """
        return {
            "queue_size": self._queue.qsize(),
            "active_tasks": len(self._active_tasks),
            "warmed_entries": len(self._warmed_cache),
            "registered_providers": list(self._warmers.keys()),
            "running": self._running,
        }

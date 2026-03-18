"""
Memory service for remember, forget, and recall operations.

This service extracts the business logic from ui/handlers/memory_handler.py
to be shared by CLI, TUI, SDK, and HTTP handlers.
"""

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from memoir.services.base import BaseService, StoreNotFoundError
from memoir.services.models import DeleteResult, Memory, RecallResult, RememberResult

logger = logging.getLogger(__name__)


class MemoryService(BaseService):
    """
    Service for memory operations: remember, forget, recall.

    This implements the core memory operations with a 5-step pipeline
    for remember and intelligent search for recall.
    """

    def __init__(self, store_path: str, llm_model: str = "gpt-4o-mini"):
        """
        Initialize memory service.

        Args:
            store_path: Path to the memory store directory
            llm_model: LLM model to use for classification and search
        """
        super().__init__(store_path)
        self.llm_model = llm_model
        self._classifier = None
        self._search_engine = None
        self._llm = None
        self._taxonomy_loader = None

    def _get_llm(self):
        """Lazily initialize and return the LLM."""
        if self._llm is None:
            from memoir.llm import get_llm

            self._llm = get_llm(model=self.llm_model, temperature=0)
        return self._llm

    def _get_taxonomy_loader(self):
        """Lazily initialize and return the taxonomy loader."""
        if self._taxonomy_loader is None:
            from memoir.taxonomy.loader import TaxonomyLoader

            store = self._get_store()
            self._taxonomy_loader = TaxonomyLoader(store)

            # Initialize taxonomy if not already present
            if not self._taxonomy_loader.has_taxonomy_in_store():
                logger.info("Initializing taxonomy in store...")
                self._taxonomy_loader.init_store(include_builtin=True)

        return self._taxonomy_loader

    def _get_classifier(self):
        """Lazily initialize and return the classifier."""
        if self._classifier is None:
            from memoir.classifier.intelligent import IntelligentClassifier
            from memoir.taxonomy.taxonomy import TaxonomyVersion

            self._classifier = IntelligentClassifier(
                llm=self._get_llm(),
                taxonomy_version=TaxonomyVersion.GENERAL,
                confidence_thresholds={
                    "high": 0.8,
                    "medium": 0.5,
                    "low": 0.0,
                },
                min_items_for_expansion=2,
                taxonomy_loader=self._get_taxonomy_loader(),
            )
        return self._classifier

    def _get_search_engine(self):
        """Lazily initialize and return the search engine."""
        if self._search_engine is None:
            from memoir.search.intelligent import IntelligentSearchEngine

            self._search_engine = IntelligentSearchEngine(
                llm=self._get_llm(),
                store=self._get_store(),
                taxonomy_loader=self._get_taxonomy_loader(),
            )
        return self._search_engine

    async def remember(
        self,
        content: str,
        namespace: str = "default",
    ) -> RememberResult:
        """
        Classify and store content in memory.

        This implements the 5-step pipeline:
        1. Store initialization
        2. Classification & path generation
        3. Memory storage
        4. Timeline processing
        5. Location processing

        Args:
            content: The content to store
            namespace: Namespace for organization

        Returns:
            RememberResult with classification info and commit details
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        step_timings = {}
        remember_start = time.time()

        # Step 1: Store Initialization
        step1_start = time.time()
        store = self._get_store()
        step_timings["step1_store_initialization"] = round(time.time() - step1_start, 3)

        # Step 2: Classification & Path Generation
        step2_start = time.time()
        key = None
        keys = []
        confidence = 0.0
        reasoning = ""
        timeline_events = None
        location_events = None

        try:
            classifier = self._get_classifier()
            current_date = datetime.now().strftime("%Y-%m-%d")

            result = await classifier.classify_input(
                content,
                metadata={"session_date": current_date},
                return_prompt=True,
            )

            confidence = result.confidence

            # Handle multi-label classification
            if result.paths and len(result.paths) > 1:
                keys = result.paths
                key = keys[0]
                reasoning = (
                    f"Multi-label classified as {keys} (confidence: {confidence:.2f})"
                )
            else:
                key = result.path if result.path else "context.current.session"
                keys = [key]
                reasoning = f"Classified as {key} (confidence: {confidence:.2f})"

            timeline_events = result.timeline_events
            location_events = result.location_events

        except Exception as e:
            logger.warning(f"LLM classification failed: {e}, using pattern matching")
            try:
                from memoir.classifier.semantic import SemanticClassifier

                semantic_classifier = SemanticClassifier()
                result = semantic_classifier.classify(content)
                key = result.path
                keys = [key]
                confidence = result.confidence
                reasoning = f"Pattern-matched as {key} (confidence: {confidence:.2f})"
            except Exception as e2:
                logger.warning(
                    f"Pattern matching failed: {e2}, using timestamp fallback"
                )
                key = f"memory.{int(time.time())}"
                keys = [key]
                confidence = 1.0
                reasoning = "Fallback to timestamp key due to classification error"

        step_timings["step2_classification"] = round(time.time() - step2_start, 3)

        # Step 3: Memory Storage
        step3_start = time.time()
        namespace_tuple = self.namespace_to_tuple(namespace)

        memory_item = {
            "content": content,
            "key": key,
            "namespace": namespace,
            "confidence": confidence,
            "timestamp": time.time(),
        }

        # Store under all classified paths
        for storage_key in keys:
            memory_item_copy = memory_item.copy()
            memory_item_copy["key"] = storage_key
            store.put(namespace_tuple, storage_key, memory_item_copy)

        # Get commit information
        commit_hash, commit_date = self._get_current_commit_info()
        step_timings["step3_memory_storage"] = round(time.time() - step3_start, 3)

        # Step 4: Timeline Processing
        step4_start = time.time()
        timeline_applied = False
        if timeline_events and isinstance(timeline_events, list):
            try:
                from memoir.memento.timeline import TimelineMemento

                timeline_memento = TimelineMemento(store)
                await timeline_memento.apply_timeline_events(
                    timeline_events, original_content=content
                )
                timeline_applied = True
            except Exception as e:
                logger.warning(f"Failed to apply timeline events: {e}")

        step_timings["step4_timeline_processing"] = round(time.time() - step4_start, 3)

        # Step 5: Location Processing
        step5_start = time.time()
        location_applied = False
        if location_events and isinstance(location_events, list):
            try:
                from memoir.memento.location import LocationMemento

                location_memento = LocationMemento(store)
                await location_memento.apply_location_events(
                    location_events, namespace=namespace
                )
                location_applied = True
            except Exception as e:
                logger.warning(f"Failed to apply location events: {e}")

        step_timings["step5_location_processing"] = round(time.time() - step5_start, 3)
        step_timings["total_remember"] = round(time.time() - remember_start, 3)

        return RememberResult(
            success=True,
            key=key,
            keys=keys,
            confidence=confidence,
            reasoning=reasoning,
            commit_hash=commit_hash,
            commit_date=commit_date,
            timings=step_timings,
            timeline_events=timeline_events,
            location_events=location_events,
            timeline_applied=timeline_applied,
            location_applied=location_applied,
            namespace=namespace,
            content=content,
        )

    def remember_sync(
        self,
        content: str,
        namespace: str = "default",
    ) -> RememberResult:
        """
        Synchronous wrapper for remember().

        Args:
            content: The content to store
            namespace: Namespace for organization

        Returns:
            RememberResult with classification info and commit details
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.remember(content, namespace))
        finally:
            loop.close()

    async def forget(
        self,
        key: str,
        namespace: str = "default",
    ) -> DeleteResult:
        """
        Delete a memory by key.

        Args:
            key: The memory key/path to delete
            namespace: Namespace containing the memory

        Returns:
            DeleteResult with deletion confirmation
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        try:
            store = self._get_store()
            namespace_tuple = self.namespace_to_tuple(namespace)

            # Delete the memory
            store.delete(namespace_tuple, key)

            # Get commit info after deletion
            commit_hash, _ = self._get_current_commit_info()

            return DeleteResult(
                success=True,
                key=key,
                namespace=namespace,
                commit_hash=commit_hash,
                message=f"Memory deleted: {key}",
            )

        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return DeleteResult(
                success=False,
                key=key,
                namespace=namespace,
                message="",
                error=str(e),
            )

    def forget_sync(
        self,
        key: str,
        namespace: str = "default",
    ) -> DeleteResult:
        """
        Synchronous wrapper for forget().

        Args:
            key: The memory key/path to delete
            namespace: Namespace containing the memory

        Returns:
            DeleteResult with deletion confirmation
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self.forget(key, namespace))
        finally:
            loop.close()

    async def recall(
        self,
        query: str,
        limit: int = 10,
        namespace: Optional[str] = None,
        person_filter: Optional[str] = None,
    ) -> RecallResult:
        """
        Search memories using intelligent search engine.

        Args:
            query: Natural language search query
            limit: Maximum results to return
            namespace: Namespace to search (None = try all)
            person_filter: Filter by person name

        Returns:
            RecallResult with matching memories
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        start_time = time.time()
        timing_info = {}

        try:
            search_engine = self._get_search_engine()

            # Stage 1: Search in specified or default namespace
            search_start = time.time()
            search_namespace = namespace or "default"

            results = await search_engine.search(
                query,
                namespace=search_namespace,
                limit=limit,
                return_prompts=True,
                person_filter=person_filter,
            )

            timing_info["primary_search"] = round(time.time() - search_start, 3)

            # If no results and no specific namespace, try other namespaces
            if not results and namespace is None:
                fallback_start = time.time()
                store = self._get_store()

                # Discover available namespaces
                all_keys = store.tree.list_keys() if hasattr(store, "tree") else []
                namespaces = set()
                for key in all_keys:
                    key_str = (
                        key.decode("utf-8") if isinstance(key, bytes) else str(key)
                    )
                    key_parts = key_str.split(":")
                    if len(key_parts) >= 2:
                        ns = key_parts[0]
                        namespaces.add(ns)

                # Try each namespace until we find results
                for ns in namespaces:
                    if ns != "default":
                        ns_results = await search_engine.search(
                            query,
                            namespace=ns,
                            limit=limit,
                            return_prompts=True,
                            person_filter=person_filter,
                        )
                        if ns_results:
                            results.extend(ns_results)
                            break

                timing_info["namespace_fallback"] = round(
                    time.time() - fallback_start, 3
                )

            # Format results
            memories = []
            step_timings = None
            llm_prompts = None

            for result in results:
                # Extract metadata
                if hasattr(result, "metadata") and result.metadata:
                    if result.metadata.get("step_timings"):
                        step_timings = result.metadata.get("step_timings")
                    if result.metadata.get("llm_prompts"):
                        llm_prompts = result.metadata.get("llm_prompts")

                    # Skip timing-only dummy results
                    if result.metadata.get("is_timing_only", False):
                        continue

                memories.append(
                    Memory(
                        path=result.path,
                        content=result.content,
                        namespace=result.namespace,
                        relevance_score=result.relevance_score,
                        metadata=result.metadata or {},
                    )
                )

            total_time = time.time() - start_time

            return RecallResult(
                success=True,
                memories=memories,
                query=query,
                timing_ms=total_time * 1000,
                metadata={
                    "store_path": self.store_path,
                    "timing_breakdown": timing_info,
                    "step_timings": step_timings,
                    "llm_prompts": llm_prompts,
                },
            )

        except Exception as e:
            logger.error(f"Recall search failed: {e}")
            return RecallResult(
                success=False,
                memories=[],
                query=query,
                timing_ms=(time.time() - start_time) * 1000,
                error=str(e),
            )

    def recall_sync(
        self,
        query: str,
        limit: int = 10,
        namespace: Optional[str] = None,
        person_filter: Optional[str] = None,
    ) -> RecallResult:
        """
        Synchronous wrapper for recall().

        Args:
            query: Natural language search query
            limit: Maximum results to return
            namespace: Namespace to search
            person_filter: Filter by person name

        Returns:
            RecallResult with matching memories
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.recall(query, limit, namespace, person_filter)
            )
        finally:
            loop.close()

    def warmup(self) -> float:
        """
        Pre-load models for faster subsequent calls.

        This is useful for agents that need fast response times.

        Returns:
            Time taken to warm up in seconds
        """
        start = time.time()
        try:
            # Force initialization of LLM and classifier
            self._get_llm()
            self._get_classifier()
            self._get_search_engine()
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")
        return time.time() - start

# SPDX-License-Identifier: Apache-2.0
"""
Memory service for remember, forget, and recall operations.

This service extracts the business logic from ui/handlers/memory_handler.py
to be shared by CLI, TUI, SDK, and HTTP handlers.
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path

from memoir.services.base import BaseService, StoreNotFoundError
from memoir.services.merge_policy import (
    SCHEMA_VERSION,
    ConflictStrategy,
    apply_strategy,
    facet_max_entries,
    make_entry,
    project_entries,
    resolve_policy,
    upgrade_blob,
)
from memoir.services.models import (
    DeleteResult,
    GetResult,
    Memory,
    RecallResult,
    RememberResult,
)

logger = logging.getLogger(__name__)


class MemoryService(BaseService):
    """
    Service for memory operations: remember, forget, recall.

    This implements the core memory operations with a 5-step pipeline
    for remember and intelligent search for recall.
    """

    def __init__(self, store_path: str, llm_model: str | None = None):
        """
        Initialize memory service.

        Args:
            store_path: Path to the memory store directory
            llm_model: LLM model to use for classification and search.
                Resolution order when None: MEMOIR_LLM_MODEL env var →
                "claude-haiku-4-5" default. Matches the UI default exposed
                by ``memoir.llm.default_ui_model`` so CLI and UI agree.
                Set MEMOIR_LLM_MODEL=gpt-4o-mini (with OPENAI_API_KEY) for
                the previous OpenAI-based behavior.
        """
        super().__init__(store_path)
        if llm_model is None:
            llm_model = os.environ.get("MEMOIR_LLM_MODEL", "claude-haiku-4-5")
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

    def _merge_prompt_template(self) -> str:
        """Read the LLM_MERGE consolidation prompt template (single source)."""
        import memoir.llm as _llm_pkg

        tmpl = Path(_llm_pkg.__file__).parent / "prompts" / "merge_consolidate.tmpl"
        return tmpl.read_text(encoding="utf-8")

    async def _llm_consolidate(self, existing_content: str, new_content: str) -> str:
        """Consolidate prior + new content into one statement (LLM_MERGE).

        Reuses the classifier LLM (already temperature=0). Best-effort: on any
        error it falls back to the new content (replace semantics) so a write
        never fails because consolidation did.
        """
        try:
            template = self._merge_prompt_template()
            prompt = template.replace("<<EXISTING>>", existing_content).replace(
                "<<NEW>>", new_content
            )
            resp = await self._get_llm().ainvoke(prompt)
            merged = (getattr(resp, "content", None) or "").strip()
            return merged or new_content
        except Exception as e:
            logger.warning("LLM_MERGE consolidation failed (%s); replacing instead", e)
            return new_content

    @staticmethod
    def _recall_merge_enabled() -> bool:
        """Whether merge-on-read LLM consolidation is on (MEMOIR_RECALL_MERGE)."""
        return os.environ.get("MEMOIR_RECALL_MERGE", "").strip().lower() in {
            "llm",
            "1",
            "true",
            "on",
        }

    def _consolidate_read(self, contents: list[str]) -> str:
        """Consolidate several facet contents into one string for retrieval.

        Synchronous (uses the LLM's sync invoke). Best-effort: returns "" on any
        error so the caller falls back to the deterministic projection.
        """
        try:
            import memoir.llm as _llm_pkg

            tmpl = (
                Path(_llm_pkg.__file__).parent / "prompts" / "consolidate_read.tmpl"
            ).read_text(encoding="utf-8")
            numbered = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(contents))
            prompt = tmpl.replace("<<ENTRIES>>", numbered)
            resp = self._get_llm().invoke(prompt)
            return (getattr(resp, "content", None) or "").strip()
        except Exception as e:
            logger.warning("merge-on-read consolidation failed (%s)", e)
            return ""

    def _maybe_consolidate_value(self, value):
        """Overwrite a v2 blob's projected content with an LLM consolidation of
        its active entries. No-op for v1 / single-entry blobs, and a safe
        deterministic fallback when already inside an event loop (the sync LLM
        call can't run there)."""
        if not isinstance(value, dict):
            return value
        entries = value.get("entries")
        if not isinstance(entries, list):
            return value
        active = [e for e in entries if e.get("status", "active") == "active"]
        if len(active) <= 1:
            return value
        try:
            import asyncio

            asyncio.get_running_loop()
            return value  # inside a loop — keep deterministic projection
        except RuntimeError:
            pass  # no running loop; safe to call the sync LLM
        merged = self._consolidate_read([e.get("content", "") for e in active])
        if merged:
            consolidated = dict(value)
            consolidated["content"] = merged
            return consolidated
        return value

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
        path: str | None = None,
        paths: list[str] | None = None,
        replace: bool = False,
        merge_policy: str | ConflictStrategy | None = None,
        extra_metadata: dict | None = None,
    ) -> RememberResult:
        """
        Classify and store content in memory.

        This implements the 5-step pipeline:
        1. Store initialization
        2. Classification & path generation  (skipped when `path`/`paths` are provided)
        3. Memory storage
        4. Timeline processing                (skipped when `path`/`paths` are provided)
        5. Location processing                (skipped when `path`/`paths` are provided)

        Args:
            content: The content to store
            namespace: Namespace for organization
            path: Optional pre-classified taxonomy path. Single-key shortcut for
                `paths=[path]`; kept for backward compatibility with existing callers.
            paths: Optional list of pre-classified taxonomy paths. When provided,
                the LLM classifier is bypassed and the content is stored at every
                listed path; each blob's ``related_keys`` field lists the *other*
                sibling paths from the same write. Pre-existing ``related_keys``
                on a target path are merged in (a path-provided write does not
                clobber siblings recorded by an earlier multi-key call).
            replace: Back-compat alias for ``merge_policy="replace"``. When True
                (and ``merge_policy`` is unset), overwrites the existing value at
                each target instead of appending. Use for callers that own their
                own read-merge-write cycle (e.g. the plugin metrics writers,
                scalar onboard pointers).
            merge_policy: Conflict-resolution strategy when the target key is
                already occupied (one of ``ConflictStrategy``: append, replace,
                confidence_gated, llm_merge, merge_on_read, reject). Precedence:
                this arg > ``MEMOIR_MERGE_POLICY`` env > per-type default. When
                unset, the default is derived from the key's memory type
                (semantic → confidence_gated, episodic → append, procedural →
                llm_merge, working → replace); ``MEMOIR_MERGE_POLICY=replace``
                restores the old overwrite-everywhere behaviour. Writes are
                stored as a timestamped-facet list (``schema_version`` 2) with a
                projected top-level ``content`` so legacy readers are unaffected.
            extra_metadata: Optional caller-supplied metadata dict merged into
                the stored value alongside ``content``/``key``/etc. Reserved
                keys (``content``, ``key``, ``namespace``, ``confidence``,
                ``timestamp``, ``related_keys``) cannot be overwritten — those
                are silently dropped. On non-replace path-provided writes the
                merge happens after the read-merge-write cycle for
                ``related_keys``, so prior extra_metadata is overwritten by
                this call's (caller-owned semantics; merging arbitrary
                metadata is a footgun). Used by ``memoir watch`` to stamp
                each per-file memory with its source provenance.

        Returns:
            RememberResult with classification info and commit details. When
            `path`/`paths` are provided, confidence is reported as 1.0 and
            reasoning notes that the caller supplied the path(s).
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

        # Normalize the path-provided shorthand: ``paths`` wins; otherwise lift
        # ``path`` into a one-element list. Empty list = no path provided.
        provided_paths: list[str] = []
        if paths:
            # Preserve order, drop dupes (first occurrence wins).
            seen: set[str] = set()
            for p in paths:
                if p and p not in seen:
                    seen.add(p)
                    provided_paths.append(p)
        elif path:
            provided_paths = [path]

        if provided_paths:
            # Caller provided the path(s) — skip the entire LLM classification chain.
            # Big latency win when invoked from a plugin that has already done its
            # own classification (e.g. via `claude -p`), since memoir's classifier
            # otherwise fires several sequential LLM calls (classify, decide-action,
            # extract-metadata, etc.).
            keys = provided_paths
            key = keys[0]
            confidence = 1.0
            reasoning = (
                f"Path provided by caller; classifier skipped: {keys}"
                if len(keys) > 1
                else f"Path provided by caller; classifier skipped: {key}"
            )
        else:
            classifier = self._get_classifier()
            current_date = datetime.now().strftime("%Y-%m-%d")

            result = await classifier.classify_input(
                content,
                metadata={"session_date": current_date},
                return_prompt=True,
            )

            confidence = result.confidence

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
        # Caller-supplied metadata (e.g. ``source`` from ``memoir watch``).
        # Reserved keys are silently dropped so callers can't spoof core
        # fields like ``content`` or ``key`` via the extra_metadata channel.
        if extra_metadata:
            _RESERVED = {
                "content",
                "key",
                "namespace",
                "confidence",
                "timestamp",
                "related_keys",
            }
            for _k, _v in extra_metadata.items():
                if _k in _RESERVED:
                    logger.debug("Ignoring reserved extra_metadata key: %s", _k)
                    continue
                memory_item[_k] = _v

        # Store under all classified paths as a timestamped-facet blob
        # (schema_version 2). Each blob carries `related_keys` listing the
        # *other* sibling paths from this write (excludes self), plus a projected
        # top-level `content`/`confidence`/`timestamp` so legacy readers are
        # unaffected. Conflict resolution against an already-occupied key is
        # delegated to the merge-policy module:
        #   - related_keys are unioned on path-provided writes so an earlier
        #     multi-key write isn't clobbered by a single-path edit;
        #   - the effective strategy decides whether to append a facet, replace,
        #     gate on confidence, consolidate via LLM, etc. `merge_policy` (or
        #     the `replace` alias) overrides; otherwise the per-type default is
        #     used (semantic → confidence_gated, episodic → append, procedural →
        #     llm_merge, working → replace).
        path_provided = bool(provided_paths)
        new_source = memory_item.get("source")
        explicit_policy: str | ConflictStrategy | None = merge_policy
        if explicit_policy is None and replace:
            explicit_policy = ConflictStrategy.REPLACE

        max_entries = facet_max_entries()
        conflicts: list[dict] = []
        wrote_any = False
        for storage_key in keys:
            siblings = [k for k in keys if k != storage_key]
            related_keys = list(siblings)
            try:
                existing = store.get(namespace_tuple, storage_key)
            except Exception:
                existing = None

            if path_provided and isinstance(existing, dict):
                prior = existing.get("related_keys")
                if isinstance(prior, list):
                    # Union, preserving the new siblings' order first.
                    seen_rel: set[str] = set(related_keys)
                    for k in prior:
                        if isinstance(k, str) and k not in seen_rel:
                            seen_rel.add(k)
                            related_keys.append(k)

            existing_v2 = upgrade_blob(existing) if isinstance(existing, dict) else None
            strategy = resolve_policy(
                explicit_policy,
                storage_key,
                path_provided=path_provided,
            )

            entry_content = content
            # LLM_MERGE consolidates prior + new into one statement before the
            # (pure) strategy collapses it to a single entry. Best-effort: the
            # helper falls back to replace semantics on any LLM error.
            if strategy == ConflictStrategy.LLM_MERGE and existing_v2 is not None:
                existing_text = project_entries(existing_v2["entries"])["content"]
                if existing_text.strip():
                    entry_content = await self._llm_consolidate(existing_text, content)

            new_entry = make_entry(
                content=entry_content,
                confidence=confidence,
                timestamp=memory_item["timestamp"],
                source=new_source,
            )
            outcome = apply_strategy(
                strategy,
                existing_v2,
                new_entry,
                key=storage_key,
                namespace=namespace,
                max_entries=max_entries,
            )
            if outcome.action == "reject":
                if outcome.conflict is not None:
                    conflicts.append(outcome.conflict.to_dict())
                continue
            if outcome.action == "noop":
                continue

            proj = project_entries(outcome.entries)
            blob = memory_item.copy()
            blob["key"] = storage_key
            blob["related_keys"] = related_keys
            blob["entries"] = outcome.entries
            blob["schema_version"] = SCHEMA_VERSION
            blob["content"] = proj["content"]
            blob["confidence"] = proj["confidence"]
            blob["timestamp"] = proj["timestamp"]
            store.put(namespace_tuple, storage_key, blob)
            wrote_any = True

        # Get commit information (only if something was actually written)
        if wrote_any:
            commit_hash, commit_date = self._get_current_commit_info()
        else:
            commit_hash, commit_date = None, None
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
            success=not conflicts,
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
            conflicts=conflicts or None,
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

    def get(
        self,
        keys: list[str],
        namespace: str = "default",
        consolidate: bool | None = None,
    ) -> GetResult:
        """
        Directly fetch one or more memories by key.

        This is a fast path — no LLM, no semantic search. Use when the caller
        already knows the exact taxonomy path(s) (e.g. from a prior `recall` or
        `summarize --keys` call) and just needs to read the stored value.

        Args:
            keys: List of taxonomy paths to fetch (e.g. ["preferences.coding.style"]).
            namespace: Namespace to look in. Defaults to "default".
            consolidate: Merge-on-read. When True (or None and
                MEMOIR_RECALL_MERGE is set), a multi-entry facet blob's returned
                ``content`` is replaced with an LLM consolidation of its active
                entries. Off by default — the deterministic projection is
                already a coherent read. Falls back to the projection inside an
                event loop or on LLM error.

        Returns:
            GetResult with one entry per requested key. Missing keys are marked
            with `found=False` and `value=None`.
        """
        if not Path(self.store_path).exists():
            raise StoreNotFoundError(self.store_path)

        start = time.time()
        do_consolidate = (
            self._recall_merge_enabled() if consolidate is None else consolidate
        )

        try:
            store = self._get_store()
            namespace_tuple = self.namespace_to_tuple(namespace)

            items = []
            for key in keys:
                value = store.get(namespace_tuple, key)
                if do_consolidate and value is not None:
                    value = self._maybe_consolidate_value(value)
                items.append(
                    {
                        "key": key,
                        "namespace": namespace,
                        "full_key": f"{namespace}:{key}",
                        "found": value is not None,
                        "value": value,
                    }
                )

            return GetResult(
                success=True,
                items=items,
                timing_ms=(time.time() - start) * 1000,
            )

        except Exception as e:
            logger.error(f"Get failed: {e}")
            return GetResult(
                success=False,
                items=[],
                timing_ms=(time.time() - start) * 1000,
                error=str(e),
            )

    async def recall(
        self,
        query: str,
        limit: int = 10,
        namespace: str | None = None,
        person_filter: str | None = None,
        mode: str = "single",
    ) -> RecallResult:
        """
        Search memories using intelligent search engine.

        Args:
            query: Natural language search query
            limit: Maximum results to return
            namespace: Namespace to search (None = try all)
            person_filter: Filter by person name
            mode: "single" (default) or "tiered" — see IntelligentSearchEngine.

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
                mode=mode,
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
                            mode=mode,
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
        namespace: str | None = None,
        person_filter: str | None = None,
        mode: str = "single",
    ) -> RecallResult:
        """
        Synchronous wrapper for recall().

        Args:
            query: Natural language search query
            limit: Maximum results to return
            namespace: Namespace to search
            person_filter: Filter by person name
            mode: "single" or "tiered" — see recall().

        Returns:
            RecallResult with matching memories
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.recall(query, limit, namespace, person_filter, mode=mode)
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

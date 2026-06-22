# SPDX-License-Identifier: Apache-2.0
"""
memoir ingest + recall + answer generation for the LoCoMo benchmark.

Speaker separation: each speaker's memories live in their own namespace
(``lc_<ingest_key>_<mode>_<speaker>``) so two speakers never overwrite each
other, and every memory's content is speaker-prefixed ("Caroline: ...") so the
generator can attribute who said what. Recall queries every speaker namespace
and merges the top-k by relevance.

Two ingest modes:
- ``native``: ``remember(content)`` — memoir auto-classifies each utterance into
  its fixed taxonomy with the default per-type merge policy (so taxonomy
  collisions + confidence-gating happen exactly as shipped). One LLM call/turn.
- ``raw``: ``remember(content, path="turn.NNNN", merge_policy="append")`` — one
  unique path per utterance, no classification (no LLM, loss-free control).
"""

from __future__ import annotations

import asyncio
import re
import time

# Official task instructions / conversation preamble — imported lazily so the
# repo path is on sys.path (data.load_tasks does that) before we import.
_INSTR = {}


def _load_official_instructions():
    if _INSTR:
        return _INSTR
    from task_eval.utils import (
        CONV_START_PROMPT,
        INSTRUCTION_COGNITIVE,
        INSTRUCTION_QA,
    )

    _INSTR.update(
        conv_start=CONV_START_PROMPT,
        qa=INSTRUCTION_QA,
        cognitive=INSTRUCTION_COGNITIVE,
    )
    return _INSTR


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "x").lower()).strip("_") or "x"


def turn_content(turn: dict) -> str:
    """Memory content for one utterance.

    Embeds the session date when present so retrieved memories stay temporally
    grounded ("when did X happen?"). Without this, recall surfaces the right
    utterance but the model can only answer relatively ("yesterday").
    """
    speaker = turn["speaker"]
    text = turn["text"]
    date = turn.get("date")
    if date:
        return f"[{date}] {speaker}: {text}"
    return f"{speaker}: {text}"


def ns_for(ingest_key: str, mode: str) -> str:
    # One namespace per (conversation, mode). Both speakers share it: the speaker
    # is kept in each memory's content + metadata, and native uses `append`, so
    # they coexist without overwriting. This halves recall calls vs per-speaker
    # namespaces (one recall instead of one-per-speaker).
    return f"lc_{ingest_key}_{mode}"


async def ingest_turns(svc, turns, ingest_key, mode, sem, native_merge_policy=None):
    """Ingest one conversation's turns; return per-speaker stats.

    ``sem`` bounds concurrent claude-cli subprocesses (native mode only).
    ``native_merge_policy`` overrides the default per-type merge for native mode
    (e.g. ``"append"`` keeps colliding facts as coexisting timestamped facets
    instead of confidence-gating/merging them away).
    """
    t0 = time.time()
    namespace = ns_for(ingest_key, mode)
    distinct: set = set()
    write_latencies: list[float] = []
    n_written = 0

    async def _one(idx, turn):
        nonlocal n_written
        speaker = turn["speaker"]
        content = turn_content(turn)
        async with sem:
            w0 = time.time()
            if mode == "raw":
                r = await svc.remember(
                    content,
                    namespace=namespace,
                    path=f"turn.{idx:04d}",
                    merge_policy="append",
                    extra_metadata={"speaker": speaker},
                )
            else:  # native
                r = await svc.remember(
                    content,
                    namespace=namespace,
                    merge_policy=native_merge_policy,
                    extra_metadata={"speaker": speaker},
                )
            write_latencies.append(time.time() - w0)
        n_written += 1
        keys = r.keys if getattr(r, "keys", None) else ([r.key] if r.key else [])
        for k in keys:
            distinct.add(k)

    await asyncio.gather(*(_one(i, t) for i, t in enumerate(turns)))

    distinct_keys = len(distinct)
    return {
        "ingest_key": ingest_key,
        "mode": mode,
        "n_turns": len(turns),
        "n_written": n_written,
        "distinct_keys": distinct_keys,
        # In native mode, fewer distinct keys than turns => taxonomy collisions.
        "collision_ratio": (
            round(1 - distinct_keys / max(1, len(turns)), 3)
            if mode == "native"
            else 0.0
        ),
        "ingest_seconds": round(time.time() - t0, 2),
        "mean_write_ms": (
            round(1000 * sum(write_latencies) / len(write_latencies), 1)
            if write_latencies
            else 0.0
        ),
    }


async def recall_context(svc, query, ingest_key, mode, limit, sem):
    """Recall the top-k memories from the conversation's single namespace."""
    t0 = time.time()
    namespace = ns_for(ingest_key, mode)
    async with sem:
        rc = await svc.recall(query, namespace=namespace, mode="single", limit=limit)
    top = rc.memories[:limit]
    return {
        "memories": [{"path": m.path, "content": m.content} for m in top],
        "n_retrieved": len(top),
        "recall_seconds": round(time.time() - t0, 2),
    }


def _memory_block(memories: list[dict]) -> str:
    if not memories:
        return "(no relevant memories were retrieved)"
    return "\n".join(f"- {m['content']}" for m in memories)


# Neutral continuation cue for cognitive tasks under the unified-input protocol
# (paper sec 5.1/5.3): present the trigger as a natural dialogue turn with NO
# hint that memory is being tested. The disclosed variant uses the official
# INSTRUCTION_COGNITIVE ("show that you are aware of the relevant memory").
_UNIFIED_COGNITIVE_TAIL = "\n\nWrite the next reply to continue this conversation."


def _cognitive_section(unified: bool):
    instr = _load_official_instructions()
    return ("", _UNIFIED_COGNITIVE_TAIL) if unified else (instr["cognitive"], "")


def build_memoir_prompt(query, memories, is_cognitive, speakers, unified=True):
    instr = _load_official_instructions()
    head = instr["conv_start"].format(speakers[0], speakers[1])
    block = _memory_block(memories)
    body = f"Relevant memories retrieved from the earlier conversation:\n{block}\n\n"
    if is_cognitive:
        pre, post = _cognitive_section(unified)
        return head + pre + body + query.strip() + post
    return head + instr["qa"] + body + "Question: " + query.strip()


def build_baseline_prompt(query, full_context, is_cognitive, speakers, unified=True):
    instr = _load_official_instructions()
    head = instr["conv_start"].format(speakers[0], speakers[1])
    body = (full_context or "").strip() + "\n\n"
    if is_cognitive:
        pre, post = _cognitive_section(unified)
        return head + pre + body + query.strip() + post
    return head + instr["qa"] + body + "Question: " + query.strip()


async def generate(llm, prompt, sem):
    t0 = time.time()
    async with sem:
        resp = await llm.ainvoke(prompt)
    return (resp.content or "").strip(), round(time.time() - t0, 2)

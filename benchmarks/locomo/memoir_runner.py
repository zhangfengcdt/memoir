# SPDX-License-Identifier: Apache-2.0
"""
memoir ingest + recall + answer generation for the LoCoMo benchmark.

Speaker separation: both speakers share one namespace per (conversation, mode)
(``lc_<ingest_key>_<mode>``); every memory's content is speaker-prefixed
("Caroline: ...") and append-merged so the two never overwrite each other and
the generator can attribute who said what. One recall call per query.

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


async def recall_context(
    svc, query, ingest_key, mode, limit, sem, recall_mode="single"
):
    """Recall the top-k memories from the conversation's single namespace.

    ``recall_mode`` selects memoir's search pipeline: ``single`` (one flat
    LLM pass over all keys — O(n), fine for small stores) or ``tiered``
    (L1 histogram -> L1 pick -> optional L2 -> key pick — scales to large
    stores, but only meaningful when keys carry a taxonomy hierarchy, i.e.
    native ingest; flat raw `turn.NNNN` keys collapse to one L1 bucket).
    """
    t0 = time.time()
    namespace = ns_for(ingest_key, mode)
    async with sem:
        rc = await svc.recall(query, namespace=namespace, mode=recall_mode, limit=limit)
    top = rc.memories[:limit]
    return {
        "memories": [{"path": m.path, "content": m.content} for m in top],
        "n_retrieved": len(top),
        "recall_seconds": round(time.time() - t0, 2),
    }


# ---------------------------------------------------------------------------
# Branching optimization for cognitive instances.
#
# All cognitive instances that share a base LoCoMo conversation are ingested into
# ONE store on `main` (the base conversation, ingested once). Each instance then
# lives on its own branch off `main` carrying just its cue turns (a cheap
# structural-sharing delta instead of re-ingesting ~588 turns). Recall checks out
# the instance branch on the SAME store handle recall reads from (a per-store lock
# keeps checkout+recall atomic so instances on one base serialize while different
# bases run in parallel).
# ---------------------------------------------------------------------------


def base_ns(base_index: int, mode: str) -> str:
    return f"lc_cogbase{base_index}_{mode}"


def _tree(svc):
    return svc._get_search_engine().store.tree


async def ingest_base(svc, base_turns, base_index, mode, sem, native_merge_policy=None):
    """Ingest the shared base conversation once on `main`."""
    _tree(svc).checkout("main")
    namespace = base_ns(base_index, mode)
    t0 = time.time()

    async def _one(idx, turn):
        content = turn_content(turn)
        async with sem:
            if mode == "raw":
                await svc.remember(
                    content,
                    namespace=namespace,
                    path=f"turn.{idx:04d}",
                    merge_policy="append",
                    extra_metadata={"speaker": turn["speaker"]},
                )
            else:
                await svc.remember(
                    content,
                    namespace=namespace,
                    merge_policy=native_merge_policy,
                    extra_metadata={"speaker": turn["speaker"]},
                )

    await asyncio.gather(*(_one(i, t) for i, t in enumerate(base_turns)))
    return {
        "base_index": base_index,
        "n_base_turns": len(base_turns),
        "ingest_seconds": round(time.time() - t0, 2),
    }


async def make_branch_with_cue(
    svc, branch, cue_turns, base_index, mode, sem, native_merge_policy=None
):
    """Create `branch` off main and commit only this instance's cue turns."""
    tree = _tree(svc)
    tree.checkout("main")
    tree.create_branch(branch)
    tree.checkout(branch)
    namespace = base_ns(base_index, mode)
    for k, turn in enumerate(cue_turns):
        content = turn_content(turn)
        async with sem:
            if mode == "raw":
                await svc.remember(
                    content,
                    namespace=namespace,
                    path=f"cue.{k:02d}",
                    merge_policy="append",
                    extra_metadata={"speaker": turn["speaker"]},
                )
            else:
                await svc.remember(
                    content,
                    namespace=namespace,
                    merge_policy=native_merge_policy,
                    extra_metadata={"speaker": turn["speaker"]},
                )


async def recall_branch(
    svc, lock, branch, query, base_index, mode, limit, sem, recall_mode="single"
):
    """Checkout `branch` and recall — atomic per store via `lock`."""
    t0 = time.time()
    namespace = base_ns(base_index, mode)
    async with lock:
        _tree(svc).checkout(branch)
        async with sem:
            rc = await svc.recall(
                query, namespace=namespace, mode=recall_mode, limit=limit
            )
        top = rc.memories[:limit]
    return {
        "memories": [{"path": m.path, "content": m.content} for m in top],
        "n_retrieved": len(top),
        "recall_seconds": round(time.time() - t0, 2),
    }


# ---------------------------------------------------------------------------
# Context-aware ("constraint-aware") remember.
#
# Instead of indexing raw utterances by surface text, a write-time LLM pass
# extracts each speaker's DURABLE implied constraints (state / goal / value /
# causal — LoCoMo-Plus's four cognitive relation types) and indexes the
# normalized *implication*. This (a) shrinks the index to a handful of salient
# constraints per conversation (most chit-chat implies nothing), and (b) lets a
# later trigger match by behavioral implication rather than surface words — the
# only way to retrieve a cue that is lexically/embedding-dissimilar by design.
# Paths: `constraint.<type>.<slug>` (L1 `constraint`, L2 = the 4 types).
# ---------------------------------------------------------------------------

CONSTRAINT_EXTRACT_PROMPT = """\
You extract DURABLE, behaviorally-constraining facts about a speaker from \
conversation turns — the kind of latent state/goal/value/causal context that \
should shape how an assistant responds to that speaker LATER, even in an \
unrelated situation.

For each turn that establishes such a constraint, emit one JSON object:
  {{"speaker": "<name>", "type": "state|goal|value|causal",
   "constraint": "<normalized implication as a general rule, e.g. 'values \
protecting personal time and avoiding overcommitment to manage stress'>"}}

Rules:
- MOST turns imply nothing durable — skip logistics, chit-chat, one-off events, \
and anything an assistant wouldn't need to recall weeks later. Err toward fewer.
- The constraint must be a GENERAL implication, not a restatement of the turn.
- Return ONLY a JSON array (possibly empty). No prose.

Turns:
{turns}

JSON array:"""


def _slug40(s: str) -> str:
    return _slug(s)[:40] or "x"


async def extract_constraints(llm, turns, sem, chunk_size=40):
    """Write-time pass: turns -> list of {speaker,type,constraint} constraints."""
    import json

    out = []
    chunks = [turns[i : i + chunk_size] for i in range(0, len(turns), chunk_size)]

    async def _one(chunk):
        text = "\n".join(f"{t['speaker']}: {t['text']}" for t in chunk if t.get("text"))
        prompt = CONSTRAINT_EXTRACT_PROMPT.format(turns=text)
        async with sem:
            resp = await llm.ainvoke(prompt)
        raw = (resp.content or "").strip()
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            return []
        try:
            arr = json.loads(m.group(0))
        except Exception:
            return []
        good = []
        for o in arr:
            if (
                isinstance(o, dict)
                and o.get("type") in {"state", "goal", "value", "causal"}
                and (o.get("constraint") or "").strip()
            ):
                good.append(o)
        return good

    for res in await asyncio.gather(*(_one(c) for c in chunks)):
        out.extend(res)
    return out


async def ingest_constraints(svc, constraints, namespace, sem):
    """Store extracted constraints at `constraint.<type>.<slug>` (append)."""
    seen: dict[str, int] = {}

    async def _one(c):
        statement = c["constraint"].strip()
        speaker = c.get("speaker", "?")
        slug = _slug40(statement)
        key = f"constraint.{c['type']}.{slug}"
        # disambiguate identical slugs
        n = seen.get(key, 0)
        seen[key] = n + 1
        path = key if n == 0 else f"{key}_{n}"
        async with sem:
            await svc.remember(
                f"{speaker}: {statement}",
                namespace=namespace,
                path=path,
                merge_policy="append",
                extra_metadata={"speaker": speaker, "constraint_type": c["type"]},
            )

    await asyncio.gather(*(_one(c) for c in constraints))
    return {"n_constraints": len(constraints)}


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

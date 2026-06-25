# SPDX-License-Identifier: Apache-2.0
"""
memoir ingest + recall + answer generation for the LoCoMo benchmark.

Speaker separation: both speakers share one namespace per (conversation, mode)
(``lc_<ingest_key>_<mode>``); every memory's content is speaker-prefixed
("Caroline: ...") and append-merged so the two never overwrite each other and
the generator can attribute who said what. One recall call per query.

Factual ingest is ``native``: ``remember(content)`` auto-classifies each
utterance into memoir's fixed taxonomy (one LLM call/turn). Use append merge so
colliding facts coexist as timestamped facets instead of being dropped.
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

    async def _one(turn):
        nonlocal n_written
        speaker = turn["speaker"]
        content = turn_content(turn)
        async with sem:
            w0 = time.time()
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

    await asyncio.gather(*(_one(t) for t in turns))

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
# Per-instance namespaces for cognitive instances.
#
# All instances that share a base LoCoMo conversation are indexed ONCE into that
# base's constraint namespace (``base_ns``, the conversation ingested a single
# time). Each instance's inserted cue is small and instance-specific, so it goes
# in its own ``cue_ns``; recall reads base + cue together and ranks the union.
# (This replaces a git-branch-per-instance scheme whose cue writes did not
# survive checkout, silently dropping every cue from the index.)
# ---------------------------------------------------------------------------


def base_ns(base_index: int, mode: str) -> str:
    return f"lc_cogbase{base_index}_{mode}"


def cue_ns(task_id: str, mode: str) -> str:
    """Per-instance namespace for that instance's inserted cue constraint(s)."""
    return f"lc_cue_{task_id}_{mode}"


def _read_constraints(svc, namespace):
    """Read every constraint entry (content + verbatim source) for a namespace
    straight from the store, on the currently-checked-out branch.

    Why not go through ``svc.recall``: the constraint index is a small (~50)
    flat set, and the intelligent search engine's taxonomy *path-selection*
    returns nothing when a trigger has no surface overlap with a constraint path
    — exactly the cue->trigger disconnect this benchmark targets. We instead
    pull the raw entries here and rank them by behavioral implication
    (:func:`recall_branch_ranked`). Reading raw also recovers the true ``source``
    metadata, which the search engine overwrites with a literal "single".
    """
    store = svc._get_search_engine().store
    out = []
    for _, path, data in store.search((namespace,), limit=10000):
        if isinstance(data, dict) and "memories" in data:
            entries = data["memories"]
        elif isinstance(data, dict):
            entries = [data]
        else:
            entries = [{"content": str(data), "metadata": {}}]
        for e in entries:
            if not isinstance(e, dict):
                continue
            content = (e.get("content") or "").strip()
            if not content:
                continue
            # source is stored flat on the entry (not nested under "metadata")
            src = e.get("source") or (e.get("metadata") or {}).get("source") or ""
            out.append({"path": path, "content": content, "source": src.strip()})
    return out


CONSTRAINT_RANK_PROMPT = """\
You are selecting which of a person's STANDING CONSTRAINTS are implicated by \
their latest message in an ongoing conversation.

The link is by BEHAVIORAL IMPLICATION and shared underlying SITUATION or \
EMOTIONAL STATE — NOT shared words. Ask WHY the speaker might feel or act this \
way given their history, then find the constraint that explains it. The right \
constraint usually has little vocabulary overlap with the message. For example, \
a message like "I keep double-checking the stove before I leave" is implicated \
by a past constraint such as "became cautious about fire hazards after a \
kitchen accident" — different words, same underlying concern.

Latest message:
{query}

Standing constraints (numbered):
{numbered}

Return ONLY a JSON array of the 0-based indices of the constraints most \
implicated by the latest message, most-relevant first, at most {limit}. \
Always return at least one index (your single best guess) even if the link is \
weak. Example: [3, 7, 1]"""


async def _rank_constraints(rank_llm, query, items, limit, sem):
    """One LLM call ranking constraint entries by implication; never empty."""
    import json

    numbered = "\n".join(f"{i}: {it['content']}" for i, it in enumerate(items))
    prompt = CONSTRAINT_RANK_PROMPT.format(query=query, numbered=numbered, limit=limit)
    raw = ""
    for attempt in range(8):
        try:
            async with sem:
                resp = await rank_llm.ainvoke(prompt)
            raw = (resp.content or "").strip()
            break
        except Exception:
            if attempt == 7:
                return items[:limit]  # fall back to arbitrary-but-nonempty
            await asyncio.sleep(min(30, 4 * (attempt + 1)))
    idxs = []
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            for x in json.loads(m.group(0)):
                i = int(x)
                if 0 <= i < len(items) and i not in idxs:
                    idxs.append(i)
        except Exception:
            idxs = []
    if not idxs:
        idxs = list(range(min(limit, len(items))))
    return [items[i] for i in idxs[:limit]]


async def recall_ranked(svc, task_id, query, base_index, mode, limit, sem):
    """Constraint-aware recall over the base + this instance's cue namespaces,
    ranked by implication to the trigger (top-K, never empty).

    The base conversation's constraints are indexed once (``base_ns``); the
    instance's inserted cue lives in ``cue_ns``. Reading both and ranking the
    union is the right retrieval for a small flat constraint set, where taxonomy
    path-selection silently returns nothing across the cue->trigger disconnect.
    """
    t0 = time.time()
    items = _read_constraints(svc, base_ns(base_index, mode))
    items += _read_constraints(svc, cue_ns(task_id, mode))
    if len(items) <= limit:
        chosen = items
    else:
        chosen = await _rank_constraints(
            svc._get_search_engine().llm, query, items, limit, sem
        )
    return {
        "memories": chosen,
        "n_retrieved": len(chosen),
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
protecting personal time and avoiding overcommitment to manage stress'>",
   "source": "<the verbatim utterance text this implication is drawn from>"}}

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
        # Retry+backoff so a TPM/RPM 429 paces instead of crashing the run; the
        # semaphore is released between attempts so the token budget can recover.
        raw = ""
        for attempt in range(8):
            try:
                async with sem:
                    resp = await llm.ainvoke(prompt)
                raw = (resp.content or "").strip()
                break
            except Exception:
                if attempt == 7:
                    return []  # give up this chunk (contributes no constraints)
                await asyncio.sleep(min(30, 4 * (attempt + 1)))
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
                # carry the verbatim source utterance for grounded (hybrid) gen
                o["source"] = (o.get("source") or "").strip()
                good.append(o)
        return good

    for res in await asyncio.gather(*(_one(c) for c in chunks)):
        out.extend(res)
    return out


CUE_EXTRACT_PROMPT = """\
The turns below are a short exchange in which a speaker states a DURABLE \
behavioral change, preference, constraint, or hard-won lesson — the kind of \
latent state/goal/value/causal context that should shape how an assistant \
responds to that speaker later, even in an unrelated situation.

Extract the underlying constraint as a GENERAL implication (not a restatement). \
Emit one JSON object per speaker who expresses such a constraint:
  {{"speaker": "<name>", "type": "state|goal|value|causal",
   "constraint": "<normalized implication, e.g. 'prioritizes home safety after \
an accident and proactively childproofs'>",
   "source": "<the verbatim utterance this is drawn from>"}}

Always extract at least one constraint for the primary speaker. Return ONLY a \
JSON array. No prose.

Turns:
{turns}

JSON array:"""


async def extract_cue_constraint(llm, cue_turns, sem):
    """Extraction tuned for an instance's *cue* (a deliberate constraint
    statement). Unlike the base-conversation pass it does NOT err toward fewer —
    the cue is a constraint by construction, so a conservative prompt that drops
    it (observed on ~half of cues) defeats the whole retrieval test."""
    import json

    text = "\n".join(f"{t['speaker']}: {t['text']}" for t in cue_turns if t.get("text"))
    prompt = CUE_EXTRACT_PROMPT.format(turns=text)
    raw = ""
    for attempt in range(8):
        try:
            async with sem:
                resp = await llm.ainvoke(prompt)
            raw = (resp.content or "").strip()
            break
        except Exception:
            if attempt == 7:
                return []
            await asyncio.sleep(min(30, 4 * (attempt + 1)))
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
            o["source"] = (o.get("source") or "").strip()
            good.append(o)
    return good


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
                extra_metadata={
                    "speaker": speaker,
                    "constraint_type": c["type"],
                    # verbatim source utterance, surfaced at recall for hybrid
                    # (grounded) generation; content stays the abstraction so
                    # retrieval still ranks by implication.
                    "source": f"{speaker}: {c.get('source', '')}".strip(),
                },
            )

    await asyncio.gather(*(_one(c) for c in constraints))
    return {"n_constraints": len(constraints)}


def _memory_block(memories: list[dict]) -> str:
    if not memories:
        return "(no relevant memories were retrieved)"
    return "\n".join(f"- {m['content']}" for m in memories)


# In-character role directive for cognitive generation. The generator (Haiku via
# the Claude Code CLI) otherwise inherits a coding-assistant identity and
# sometimes refuses to continue a personal conversation ("I'm built to help with
# software engineering..."). We can't pass it as a CLI --system-prompt (that path
# forces JSON-only output), so it leads the user prompt instead.
_COGNITIVE_ROLE = (
    "You are the user's personal AI assistant in an ongoing conversation. Reply "
    "helpfully and naturally to the user's latest message, taking into account "
    "what you already know about the user from earlier in the conversation. "
    "Respond with only your reply.\n\n"
)

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
        return _COGNITIVE_ROLE + head + pre + body + query.strip() + post
    return head + instr["qa"] + body + "Question: " + query.strip()


def build_baseline_prompt(query, full_context, is_cognitive, speakers, unified=True):
    instr = _load_official_instructions()
    head = instr["conv_start"].format(speakers[0], speakers[1])
    body = (full_context or "").strip() + "\n\n"
    if is_cognitive:
        pre, post = _cognitive_section(unified)
        return _COGNITIVE_ROLE + head + pre + body + query.strip() + post
    return head + instr["qa"] + body + "Question: " + query.strip()


async def generate(llm, prompt, sem, max_attempts=8):
    """Generate with retry+backoff so a TPM 429 paces (and never crashes the run).

    The semaphore is released between attempts so other coroutines proceed while
    this one backs off — which lets the per-minute token budget recover.
    """
    t0 = time.time()
    for attempt in range(max_attempts):
        try:
            async with sem:
                resp = await llm.ainvoke(prompt)
            return (resp.content or "").strip(), round(time.time() - t0, 2)
        except Exception:
            if attempt == max_attempts - 1:
                return "", round(time.time() - t0, 2)
            await asyncio.sleep(min(30, 4 * (attempt + 1)))

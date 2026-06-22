# SPDX-License-Identifier: Apache-2.0
"""
Dataset loader for the LoCoMo / LoCoMo-Plus memoir benchmark.

Reuses the *official* Locomo-Plus repo for conversation stitching, evidence
formatting, and category names so our inputs match the paper's harness exactly.
Point ``--repo-dir`` at a local checkout of https://github.com/xjtuleeyf/Locomo-Plus
(it ships ``data/locomo10.json`` + ``data/locomo_plus.json``).

Each task we emit has everything the runner needs:
- ``ingest_key``  : turns sharing this key are ingested into one store (factual
                    tasks of the same conversation share it; each cognitive
                    instance gets its own stitched dialogue).
- ``turns``       : [{speaker, text}] to ingest (cue included, trigger excluded).
- ``query``       : the question (factual) or trigger_query (cognitive).
- ``category``    : official category name (single-hop/.../adversarial/Cognitive).
- ``gold``        : reference answer ("" for adversarial + cognitive).
- ``evidence``    : human-readable evidence text fed to the judge.
- ``is_cognitive``: routes the judge prompt + instruction.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _add_repo_to_path(repo_dir: Path) -> None:
    """Make the official repo's data/ and evaluation_framework/ importable."""
    for sub in ("data", "evaluation_framework"):
        p = str((repo_dir / sub).resolve())
        if p not in sys.path:
            sys.path.insert(0, p)


def _factual_tasks(repo_dir: Path, conversations: list[int] | None) -> list[dict]:
    import json

    from unified_input import (  # official helpers
        LOCOMO_CATEGORY_NAMES,
        _build_conversation_context,
        _evidence_to_text,
        _parse_evidence_list,
    )

    raw = json.loads((repo_dir / "data" / "locomo10.json").read_text())
    tasks: list[dict] = []
    for conv_idx, item in enumerate(raw):
        if conversations is not None and conv_idx not in conversations:
            continue
        conv = item.get("conversation") or {}
        speaker_a = conv.get("speaker_a", "A")
        speaker_b = conv.get("speaker_b", "B")

        # Turns to ingest: every session utterance, in session order.
        sessions = sorted(
            (
                k
                for k in conv
                if k.startswith("session_") and not k.endswith("_date_time")
            ),
            key=lambda x: int(x.split("_")[-1]),
        )
        turns = []
        for s in sessions:
            date = conv.get(f"{s}_date_time", "")
            for d in conv.get(s, []):
                text = (d.get("text") or "").strip()
                if text:
                    turns.append(
                        {
                            "speaker": d.get("speaker", "?"),
                            "text": text,
                            "date": date,
                        }
                    )

        ingest_key = f"conv{conv_idx}"
        # Keep full-context baseline material alongside the task.
        ctx_text = _build_conversation_context(conv)

        for qi, qa in enumerate(item.get("qa") or []):
            cat_id = qa.get("category")
            category = LOCOMO_CATEGORY_NAMES.get(cat_id, f"category_{cat_id}")
            evidence_text = _evidence_to_text(
                conv, _parse_evidence_list(qa.get("evidence") or [])
            )
            answer = qa.get("answer")
            gold = "" if answer is None else str(answer)
            tasks.append(
                {
                    "task_id": f"{ingest_key}_qa{qi}",
                    "ingest_key": ingest_key,
                    "conversation_id": ingest_key,
                    "speakers": [speaker_a, speaker_b],
                    "turns": turns,
                    "full_context": ctx_text,
                    "query": qa.get("question", ""),
                    "category": category,
                    "gold": gold,
                    "evidence": evidence_text,
                    "is_cognitive": False,
                    "time_gap": None,
                }
            )
    return tasks


def _cognitive_tasks(repo_dir: Path, limit: int | None) -> list[dict]:
    import json

    from build_conv import build_context  # official stitcher
    from unified_input import _cue_dialogue_to_evidence

    plus = json.loads((repo_dir / "data" / "locomo_plus.json").read_text())
    locomo = json.loads((repo_dir / "data" / "locomo10.json").read_text())

    if limit is not None:
        plus = plus[:limit]

    tasks: list[dict] = []
    for i, p in enumerate(plus):
        locomo_item = locomo[i % len(locomo)]
        ctx = build_context(p, locomo_item)
        dialogue = ctx.get("dialogue") or []
        query_turns = ctx.get("query_turns") or []
        # Ingest everything EXCEPT the trailing trigger-query turns.
        n_q = len(query_turns)
        ingest_turns = dialogue[:-n_q] if n_q else dialogue
        turns = [
            {"speaker": t.get("speaker", "?"), "text": (t.get("text") or "").strip()}
            for t in ingest_turns
            if (t.get("text") or "").strip()
        ]
        evidence = _cue_dialogue_to_evidence(p.get("cue_dialogue", ""), locomo_item)
        # Build full-context baseline text from the stitched dialogue.
        full_ctx = "\n".join(
            f'{t.get("speaker", "?")} said, "{(t.get("text") or "").strip()}"'
            for t in ingest_turns
        )
        tasks.append(
            {
                "task_id": f"cog{i}",
                "ingest_key": f"cog{i}",
                "conversation_id": f"cog{i}",
                "speakers": [ctx.get("speaker_a", "A"), ctx.get("speaker_b", "B")],
                "turns": turns,
                "full_context": full_ctx,
                "query": p.get("trigger_query", ""),
                "category": "Cognitive",
                "gold": "",
                "evidence": evidence,
                "is_cognitive": True,
                "time_gap": p.get("time_gap", ""),
                "relation_type": p.get("relation_type", ""),
            }
        )
    return tasks


def load_tasks(
    repo_dir: str,
    conversations: list[int] | None = None,
    max_factual_per_category: int | None = None,
    cognitive_limit: int | None = None,
    include_factual: bool = True,
    include_cognitive: bool = True,
) -> list[dict]:
    """Load benchmark tasks from a local Locomo-Plus checkout.

    ``conversations``            : restrict factual tasks to these conv indices.
    ``max_factual_per_category`` : sample at most N factual queries per category
                                   (per conversation) — keeps subset runs cheap.
    ``cognitive_limit``          : use only the first N cognitive instances.
    """
    repo = Path(repo_dir)
    _add_repo_to_path(repo)

    tasks: list[dict] = []
    if include_factual:
        factual = _factual_tasks(repo, conversations)
        if max_factual_per_category is not None:
            capped: list[dict] = []
            seen: dict[tuple, int] = {}
            for t in factual:
                key = (t["conversation_id"], t["category"])
                if seen.get(key, 0) >= max_factual_per_category:
                    continue
                seen[key] = seen.get(key, 0) + 1
                capped.append(t)
            factual = capped
        tasks.extend(factual)
    if include_cognitive:
        tasks.extend(_cognitive_tasks(repo, cognitive_limit))
    return tasks

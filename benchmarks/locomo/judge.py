# SPDX-License-Identifier: Apache-2.0
"""
Constraint-consistency judge — reuses the *official* Locomo-Plus judge prompts,
label->score map, and summary aggregation (imported from the local repo
checkout) so scores are computed as in the paper. Only the model call is swapped
to memoir's claude-cli backend (no API key needed).

Two modes:
- ``judge_one``   : one model call per prediction (byte-identical to the official
                    per-item judge).
- ``judge_batch`` : packs many same-category predictions into ONE call returning
                    a JSON array — ~Nx fewer (expensive) judge calls. Reuses each
                    category's official rubric head + label set + scoring.

Scoring: correct=1, partial=0.5, wrong=0.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

# Field markers that begin the per-item body in the official templates; the text
# before the first one is the shared rubric head (role + label definitions).
_BODY_MARKERS = ("Reference Answer:", "Memory/Evidence:", "Model Prediction:")


def _official():
    from task_eval.llm_as_judge import (
        _compute_summary,
        _parse_judge_response,
        get_judge_prompt,
        label_to_score,
    )
    from task_eval.prompt import PROMPT_TEMPLATES

    return (
        get_judge_prompt,
        _parse_judge_response,
        label_to_score,
        _compute_summary,
        PROMPT_TEMPLATES,
    )


async def judge_one(llm, record: dict, sem) -> dict:
    """Judge one prediction record (category/evidence/prediction/ground_truth)."""
    get_judge_prompt, parse, to_score, _, _ = _official()
    cat = record.get("category") or "default"
    prompt = get_judge_prompt(
        cat,
        record.get("evidence", ""),
        record.get("prediction", ""),
        record.get("ground_truth") or record.get("gold", "") or "",
    )
    async with sem:
        resp = await llm.ainvoke(prompt)
    label, reason = parse(resp.content or "")
    out = dict(record)
    out["judge_label"] = label
    out["judge_reason"] = reason
    out["judge_score"] = to_score(label)
    return out


def _rubric_head(template: str) -> str:
    """The role + label-definition preamble (everything before the first field)."""
    positions = [template.find(m) for m in _BODY_MARKERS if template.find(m) != -1]
    return template[: min(positions)].strip() if positions else template.strip()


def _build_batch_prompt(category: str, records: list[dict], templates: dict) -> str:
    head = _rubric_head(templates.get(category) or templates["default"])
    parts = [
        head,
        f"\n\nYou are scoring {len(records)} responses of the SAME task type. "
        "Apply the labels defined above to EACH item independently.\n"
        "Return ONLY a JSON array, one object per item: "
        '[{"i": 0, "label": "<label>", "reason": "<short>"}, ...]\n',
    ]
    for i, r in enumerate(records):
        gold = r.get("ground_truth") or r.get("gold", "") or ""
        parts.append(
            f"\nItem {i}:\n"
            f"Reference Answer: {gold}\n"
            f"Model Prediction: {r.get('prediction', '')}\n"
            f"Relevant Evidence: {r.get('evidence', '')}"
        )
    return "\n".join(parts)


def _parse_batch(raw: str, n: int) -> list[str]:
    """Extract n labels from a JSON array response; '' for any missing item."""
    labels = [""] * n
    text = (raw or "").strip()
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if m:
        try:
            arr = json.loads(m.group(0))
            for obj in arr:
                if isinstance(obj, dict) and "i" in obj:
                    idx = int(obj["i"])
                    if 0 <= idx < n:
                        labels[idx] = str(obj.get("label", "")).strip().lower()
        except Exception:
            pass
    return labels


async def judge_batch(
    llm, records: list[dict], sem, batch_size: int = 10
) -> list[dict]:
    """Judge records in same-category batches (one model call per batch)."""
    _, parse, to_score, _, templates = _official()

    by_cat: dict[str, list[int]] = defaultdict(list)
    for idx, r in enumerate(records):
        by_cat[r.get("category") or "default"].append(idx)

    out: list[dict] = [dict(r) for r in records]

    async def _run_batch(cat: str, idxs: list[int]):
        batch = [records[i] for i in idxs]
        prompt = _build_batch_prompt(cat, batch, templates)
        try:
            async with sem:
                resp = await llm.ainvoke(prompt)
            raw = resp.content or ""
        except Exception as e:  # don't let one batch crash the whole judge pass
            print(f"  judge batch ({cat}, {len(idxs)} items) failed: {str(e)[:80]}")
            raw = ""
        labels = _parse_batch(raw, len(batch))
        for local_i, global_i in enumerate(idxs):
            label = labels[local_i]
            if not label:
                # Fall back to the official single-item keyword parser.
                label, _ = parse(raw)
            out[global_i]["judge_label"] = label
            out[global_i]["judge_score"] = to_score(label)

    jobs = []
    for cat, idxs in by_cat.items():
        for start in range(0, len(idxs), batch_size):
            jobs.append(_run_batch(cat, idxs[start : start + batch_size]))
    import asyncio

    await asyncio.gather(*jobs)
    return out


def summarize(records: list[dict]) -> dict:
    """Aggregate judged records by category (official _compute_summary)."""
    _, _, _, compute_summary, _ = _official()
    return compute_summary(records)

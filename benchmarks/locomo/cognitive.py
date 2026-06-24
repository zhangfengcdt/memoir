# SPDX-License-Identifier: Apache-2.0
"""
Cognitive (LoCoMo-Plus) runner with the branching + context-aware layers.

Why a separate runner from run.py: the cognitive set needs machinery the flat
factual fan-out doesn't —
  * branching: each base LoCoMo conversation is ingested ONCE; every instance is
    a branch off it carrying only its cue (structural sharing, not re-ingest);
  * context-aware ("constraint") ingest: a write-time LLM pass indexes each
    speaker's durable state/goal/value/causal constraints instead of raw turns,
    so the deliberately-disconnected cue is retrievable by implication;
  * branch-pinned recall: checkout the instance branch on the same store handle
    recall reads from (serialized per base store, parallel across bases).

Two cognitive ingest modes:
  --cog-mode raw         : base turns + cue turns as raw memories (control).
  --cog-mode constraint  : extracted constraints for base + cue (context-aware).

Systems scored: `baseline` (full stitched context, no memoir) and
`memoir_<cog-mode>`. Output schema matches run.py so judged.json is comparable.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("MEMOIR_LLM_BACKEND", "claude-cli")
os.environ.setdefault("MEMOIR_LLM_MODEL", "claude-haiku-4-5")
os.environ.setdefault("MEMOIR_NO_CAPTURE", "1")

import data as data_mod
import judge as judge_mod
import memoir_runner as mr


def _make_service(store_path: str):
    from memoir.services.memory_service import MemoryService
    from memoir.services.store_service import StoreService

    Path(store_path).mkdir(parents=True, exist_ok=True)
    StoreService(store_path).create_store(store_path)
    return MemoryService(store_path)


def _ns_count(svc, ns):
    """How many keys already live in a namespace (0 if none/new)."""
    try:
        return len(svc._get_search_engine().store.search((ns,), limit=100000))
    except Exception:
        return 0


async def _ingest_base_layer(svc, base_turns, base_index, cog_mode, llm, sem):
    """Populate `main` with the base conversation (raw turns or constraints).

    Idempotent: if the base namespace is already populated (a prior run that was
    interrupted), skip re-ingest/re-extract so --resume doesn't duplicate or
    re-pay the extraction cost.
    """
    ns = mr.base_ns(base_index, cog_mode)
    mr._tree(svc).checkout("main")
    existing = _ns_count(svc, ns)
    if existing:
        return existing
    if cog_mode == "constraint":
        cons = await mr.extract_constraints(llm, base_turns, sem)
        await mr.ingest_constraints(svc, cons, ns, sem)
        return len(cons)
    await mr.ingest_base(svc, base_turns, base_index, "raw", sem)
    return len(base_turns)


async def _add_instance_branch(svc, branch, cue_turns, base_index, cog_mode, llm, sem):
    """Branch off main and add this instance's cue (raw turns or constraints)."""
    tree = mr._tree(svc)
    tree.checkout("main")
    # Idempotent: a prior interrupted run may have left this branch (with its cue
    # already committed). Recreate only when fresh; otherwise just check it out.
    try:
        tree.create_branch(branch)
        tree.checkout(branch)
        fresh = True
    except Exception:
        tree.checkout(branch)
        fresh = False
    if not fresh:
        return
    ns = mr.base_ns(base_index, cog_mode)
    if cog_mode == "constraint":
        cons = await mr.extract_constraints(llm, cue_turns, sem)
        await mr.ingest_constraints(svc, cons, ns, sem)
    else:
        for k, turn in enumerate(cue_turns):
            async with sem:
                await svc.remember(
                    mr.turn_content(turn),
                    namespace=ns,
                    path=f"cue.{k:02d}",
                    merge_policy="append",
                    extra_metadata={"speaker": turn["speaker"]},
                )


async def _process_base(b, group, cog_mode, llm, sem, recall_limit, recall_mode, done):
    """Ingest one base + all its instances (serial: branch checkout is stateful)."""
    from pathlib import Path as _P

    store_path = str(_P(group["stores_dir"]) / f"cogbase{b}_{cog_mode}")
    svc = _make_service(store_path)
    lock = asyncio.Lock()
    n_index = await _ingest_base_layer(svc, group["base_turns"], b, cog_mode, llm, sem)
    records = []
    for task in group["instances"]:
        if task["task_id"] in done:
            continue
        await _add_instance_branch(
            svc, task["task_id"], task["cue_turns"], b, cog_mode, llm, sem
        )
        r = await mr.recall_branch(
            svc,
            lock,
            task["task_id"],
            task["query"],
            b,
            cog_mode,
            recall_limit,
            sem,
            recall_mode=recall_mode,
        )
        m_prompt = mr.build_memoir_prompt(
            task["query"], r["memories"], True, task["speakers"], unified=True
        )
        pred, gs = await mr.generate(llm, m_prompt, sem)
        records.append(_rec(task, f"memoir_{cog_mode}", pred, r, gs))

        b_prompt = mr.build_baseline_prompt(
            task["query"], task["full_context"], True, task["speakers"], unified=True
        )
        bpred, bgs = await mr.generate(llm, b_prompt, sem)
        records.append(_rec(task, "baseline", bpred, None, bgs))
    return records, {
        "base_index": b,
        "index_size": n_index,
        "n_instances": len(group["instances"]),
    }


def _rec(task, system, prediction, r, gen_s):
    return {
        "task_id": task["task_id"],
        "system": system,
        "category": "Cognitive",
        "is_cognitive": True,
        "evidence": task["evidence"],
        "ground_truth": "",
        "query": task["query"],
        "prediction": prediction,
        "n_retrieved": (r["n_retrieved"] if r else None),
        "recall_seconds": (r["recall_seconds"] if r else 0.0),
        "gen_seconds": gen_s,
    }


async def main_async(args):
    from memoir.llm.claude_cli_client import ClaudeCLIWrapper

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stores_dir = out_dir / "stores"

    tasks = data_mod.load_tasks(
        args.repo_dir,
        include_factual=False,
        cognitive_offset=args.offset,
        cognitive_limit=args.limit,
    )
    groups = defaultdict(
        lambda: {"base_turns": None, "instances": [], "stores_dir": str(stores_dir)}
    )
    for t in tasks:
        g = groups[t["base_index"]]
        g["base_turns"] = t["base_turns"]
        g["instances"].append(t)
    print(
        f"{len(tasks)} cognitive instances over {len(groups)} base conversations "
        f"| cog-mode={args.cog_mode}",
        flush=True,
    )

    # Resume: skip task_ids already predicted (both systems present).
    pred_cache = {}
    pred_path = out_dir / "cog_predictions.json"
    if args.resume and pred_path.exists():
        for rrec in json.loads(pred_path.read_text()):
            pred_cache[(rrec["system"], rrec["task_id"])] = rrec
    done = {
        t
        for t in {r[1] for r in pred_cache}
        if (f"memoir_{args.cog_mode}", t) in pred_cache
        and ("baseline", t) in pred_cache
    }

    llm = ClaudeCLIWrapper(model=args.gen_model)
    # Judge can be a non-Claude model (e.g. gpt-4o): route those through litellm
    # (OpenAI) directly, bypassing the claude-cli backend used by the generator.
    if "gpt" in args.judge_model.lower():
        import litellm

        from memoir.llm.litellm_client import LiteLLMWrapper

        # OpenAI tier limits (e.g. 30K TPM) → let litellm retry 429s with backoff.
        litellm.num_retries = 10
        judge_llm = LiteLLMWrapper(model=args.judge_model)
    else:
        judge_llm = ClaudeCLIWrapper(model=args.judge_model)
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.time()

    base_tasks = [
        asyncio.ensure_future(
            _process_base(
                b, g, args.cog_mode, llm, sem, args.recall_limit, args.recall_mode, done
            )
        )
        for b, g in groups.items()
    ]
    # Flush predictions after each base completes — crash-safe + resumable.
    new_count, index_stats = 0, []
    for fut in asyncio.as_completed(base_tasks):
        recs, st = await fut
        index_stats.append(st)
        new_count += len(recs)
        for r in recs:
            pred_cache[(r["system"], r["task_id"])] = r
        pred_path.write_text(
            json.dumps(list(pred_cache.values()), indent=2, ensure_ascii=False)
        )
        print(
            f"  base {st['base_index']} done (+{len(recs)} recs, "
            f"index={st['index_size']}); flushed",
            flush=True,
        )
    records = list(pred_cache.values())
    print(
        f"predict: {len(records)} ({new_count} new) in {time.time()-t0:.0f}s",
        flush=True,
    )

    judged = await judge_mod.judge_batch(
        judge_llm, records, sem, batch_size=args.judge_batch
    )
    (out_dir / "cog_judged.json").write_text(
        json.dumps(judged, indent=2, ensure_ascii=False)
    )

    summ = {}
    for sysname in sorted({r["system"] for r in judged}):
        recs = [r for r in judged if r["system"] == sysname]
        summ[sysname] = judge_mod.summarize(recs)
    avg_index = round(
        sum(s["index_size"] for s in index_stats) / max(1, len(index_stats)), 1
    )
    report = {
        "cog_mode": args.cog_mode,
        "recall_mode": args.recall_mode,
        "n_instances": len(tasks),
        "avg_index_size": avg_index,
        "wall_seconds": round(time.time() - t0, 1),
        "summaries": summ,
    }
    (out_dir / "cog_summary.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                s: {"avg": v["overall_avg"], "n": v["total_samples"]}
                for s, v in summ.items()
            },
            indent=2,
        )
    )
    print(f"avg index size/base: {avg_index} | wall {report['wall_seconds']}s")


def parse_args():
    p = argparse.ArgumentParser(
        description="LoCoMo-Plus cognitive runner (branching + context-aware)"
    )
    p.add_argument("--repo-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--cog-mode", choices=["raw", "constraint"], default="constraint")
    p.add_argument("--recall-mode", choices=["single", "tiered"], default="single")
    p.add_argument("--recall-limit", type=int, default=6)
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--gen-model", default="haiku")
    p.add_argument("--judge-model", default="claude-opus-4-8")
    p.add_argument("--judge-batch", type=int, default=10)
    p.add_argument("--resume", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))

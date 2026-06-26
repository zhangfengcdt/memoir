# SPDX-License-Identifier: Apache-2.0
"""
Cognitive (LoCoMo-Plus) runner with the context-aware constraint layer.

Why a separate runner from run.py: the cognitive set needs machinery the flat
factual fan-out doesn't —
  * shared base index: each base LoCoMo conversation's constraints are indexed
    ONCE (``base_ns``); every instance only adds its own small cue (``cue_ns``),
    not a re-ingest of the whole conversation;
  * context-aware ("constraint") ingest: a write-time LLM pass indexes each
    speaker's durable state/goal/value/causal constraints instead of raw turns,
    so the deliberately-disconnected cue is retrievable by implication;
  * ranked recall: read base + cue constraints and rank them by behavioral
    implication to the trigger (top-K, never empty), since taxonomy
    path-selection silently returns nothing across the cue->trigger disconnect.

Cognitive ingest modes:
  --cog-mode constraint  : extracted constraints for base + cue (context-aware).
  --cog-mode hybrid      : constraint retrieval, generation from cue source text.

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

# All LLMs go through litellm (OpenAI key), no claude-cli. Internal recall runs
# on gpt-4o-mini — recall sends the whole store per query, so big prompts make a
# pricier model the dominant cost.
os.environ.setdefault("MEMOIR_LLM_BACKEND", "litellm")
os.environ.setdefault("MEMOIR_LLM_MODEL", "gpt-4o-mini")
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


async def _ingest_base_layer(
    svc, base_turns, base_index, cog_mode, llm, sem, chunk_size=40
):
    """Index the base conversation's constraints once (shared by all instances).

    Idempotent: if the base namespace is already populated (a prior run that was
    interrupted), skip re-ingest/re-extract so --resume doesn't duplicate or
    re-pay the extraction cost. ``chunk_size`` controls extraction granularity.
    """
    ns = mr.base_ns(base_index, cog_mode)
    existing = _ns_count(svc, ns)
    if existing:
        return existing
    cons = await mr.extract_constraints(llm, base_turns, sem, chunk_size=chunk_size)
    await mr.ingest_constraints(svc, cons, ns, sem)
    return len(cons)


async def _add_instance_cue(svc, task_id, cue_turns, cog_mode, llm, sem):
    """Index this instance's inserted cue in its own namespace (idempotent)."""
    ns = mr.cue_ns(task_id, cog_mode)
    if _ns_count(svc, ns):
        return
    cons = await mr.extract_cue_constraint(llm, cue_turns, sem)
    await mr.ingest_constraints(svc, cons, ns, sem)


async def _process_base(
    b,
    group,
    cog_mode,
    gen_llm,
    extract_llm,
    sem,
    recall_limit,
    done,
    run_systems,
    chunk_size=40,
):
    """Index one base + score all its instances (serial within a base store).

    ``extract_llm`` does write-time constraint extraction; ``gen_llm`` produces
    the answer (both gpt-4o-mini).
    """
    from pathlib import Path as _P

    run_memoir = "memoir" in run_systems
    run_baseline = "baseline" in run_systems

    # Only the memoir path needs the constraint store / base layer. Decoupling
    # the two systems into separate passes keeps each pass's per-call token
    # volume low: baseline's full-context prompts (~20K tokens) would otherwise
    # saturate the shared TPM budget and starve the small recall calls.
    n_index = 0
    if run_memoir:
        store_path = str(_P(group["stores_dir"]) / f"cogbase{b}_{cog_mode}")
        svc = _make_service(store_path)
        n_index = await _ingest_base_layer(
            svc, group["base_turns"], b, cog_mode, extract_llm, sem, chunk_size
        )
    records = []
    for task in group["instances"]:
        if task["task_id"] in done:
            continue
        if run_memoir:
            await _add_instance_cue(
                svc, task["task_id"], task["cue_turns"], cog_mode, extract_llm, sem
            )
            r = await mr.recall_ranked(
                svc,
                task["task_id"],
                task["query"],
                b,
                cog_mode,
                recall_limit,
                sem,
            )
            # Hybrid: retrieve via the constraint index (ranks by implication)
            # but generate from each retrieved item's verbatim source utterance,
            # so the answer is grounded in concrete evidence not the abstraction.
            if cog_mode == "hybrid":
                for m in r["memories"]:
                    if m.get("source"):
                        m["content"] = m["source"]
            m_prompt = mr.build_memoir_prompt(
                task["query"], r["memories"], True, task["speakers"], unified=True
            )
            pred, gs = await mr.generate(gen_llm, m_prompt, sem)
            records.append(_rec(task, f"memoir_{cog_mode}", pred, r, gs))

        if run_baseline:
            b_prompt = mr.build_baseline_prompt(
                task["query"],
                task["full_context"],
                True,
                task["speakers"],
                unified=True,
            )
            bpred, bgs = await mr.generate(gen_llm, b_prompt, sem)
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

    run_systems = {"memoir", "baseline"} if args.systems == "both" else {args.systems}
    required = set()
    if "memoir" in run_systems:
        required.add(f"memoir_{args.cog_mode}")
    if "baseline" in run_systems:
        required.add("baseline")

    # Resume: skip task_ids already predicted for every system this pass runs.
    pred_cache = {}
    pred_path = out_dir / "cog_predictions.json"
    if args.resume and pred_path.exists():
        for rrec in json.loads(pred_path.read_text()):
            pred_cache[(rrec["system"], rrec["task_id"])] = rrec
    done = {
        t
        for t in {r[1] for r in pred_cache}
        if all((sysname, t) in pred_cache for sysname in required)
    }

    import litellm

    from memoir.llm.litellm_client import LiteLLMWrapper

    # OpenAI 30K-TPM tier (gpt-4o judge) → let litellm retry 429s with backoff.
    litellm.num_retries = 3

    # Everything via litellm API: generator (gpt-4o-mini, no persona refusals),
    # extractor (haiku-4.5), judge (gpt-4o).
    gen_llm = LiteLLMWrapper(model=args.gen_model)
    extract_llm = LiteLLMWrapper(model=args.extract_model)
    judge_llm = LiteLLMWrapper(model=args.judge_model)
    print(
        f"gen={args.gen_model} · extract={args.extract_model} · "
        f"judge={args.judge_model}",
        flush=True,
    )
    sem = asyncio.Semaphore(args.concurrency)
    t0 = time.time()

    base_tasks = [
        asyncio.ensure_future(
            _process_base(
                b,
                g,
                args.cog_mode,
                gen_llm,
                extract_llm,
                sem,
                args.recall_limit,
                done,
                run_systems,
                args.chunk_size,
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

    # gpt-4o judge has a tight 30K TPM budget and corrupts (empty labels) when
    # batches fire concurrently — judge on its own (serial-by-default) semaphore,
    # independent of the generation concurrency above.
    judge_sem = asyncio.Semaphore(args.judge_concurrency)
    judged = await judge_mod.judge_batch(
        judge_llm, records, judge_sem, batch_size=args.judge_batch
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
    p.add_argument("--cog-mode", choices=["constraint", "hybrid"], default="hybrid")
    p.add_argument(
        "--systems",
        choices=["both", "memoir", "baseline"],
        default="both",
        help="Run memoir + baseline together (default) or one in isolation. "
        "Splitting into two passes keeps baseline's heavy full-context prompts "
        "from starving memoir recall on a shared per-minute token budget.",
    )
    p.add_argument("--recall-mode", choices=["single", "tiered"], default="single")
    p.add_argument("--recall-limit", type=int, default=6)
    p.add_argument(
        "--chunk-size",
        type=int,
        default=40,
        help="Turns per base-extraction LLM call (granularity knob: smaller "
        "chunk -> more, finer constraints).",
    )
    p.add_argument("--concurrency", type=int, default=10)
    p.add_argument("--gen-model", default="gpt-4o-mini")
    p.add_argument("--extract-model", default="gpt-4o-mini")
    p.add_argument("--judge-model", default="gpt-4o")
    p.add_argument("--judge-batch", type=int, default=10)
    p.add_argument(
        "--judge-concurrency",
        type=int,
        default=1,
        help="Concurrent judge batches (default 1 — gpt-4o's 30K TPM corrupts "
        "labels above 1).",
    )
    p.add_argument("--resume", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))

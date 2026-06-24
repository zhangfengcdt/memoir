# SPDX-License-Identifier: Apache-2.0
"""
LoCoMo / LoCoMo-Plus benchmark runner for the memoir memory system.

Pipeline per task: ingest the dialogue into a memoir store (once per
conversation x mode), recall memories for the query, generate an answer from the
retrieved context, and score it with the official constraint-consistency judge.
A full-context baseline (no memoir) is the within-backbone comparison anchor.

All LLM calls (memoir's internal classify/recall, answer generation, and the
judge) run on the claude-cli backend — no API key required. Numbers are
therefore comparable to the baseline we run here, NOT directly to the paper's
GPT-4o "Memory Systems" rows.

Usage (diagnostic subset):
    python benchmarks/locomo/run.py \
        --repo-dir /tmp/locomo-bench/Locomo-Plus \
        --conversations 0 --max-factual-per-category 3 \
        --cognitive-limit 8 --modes raw native --baseline \
        --concurrency 8 --out /tmp/locomo-bench/out
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
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


async def _ingest_all(tasks, modes, stores_dir, sem, native_merge_policy=None):
    """Ingest each (ingest_key, mode) store once. Returns (services, stats)."""
    from memoir.services.memory_service import MemoryService
    from memoir.services.store_service import StoreService

    # Unique ingest keys with their turns/speakers (first task wins; identical).
    by_key: dict[str, dict] = {}
    for t in tasks:
        by_key.setdefault(
            t["ingest_key"], {"turns": t["turns"], "speakers": t["speakers"]}
        )

    services: dict[tuple, object] = {}
    stats: list[dict] = []
    for mode in modes:
        for key, info in by_key.items():
            store_path = str(Path(stores_dir) / f"{key}_{mode}")
            Path(store_path).mkdir(parents=True, exist_ok=True)
            StoreService(store_path).create_store(store_path)
            svc = MemoryService(store_path)
            services[(key, mode)] = svc
            print(
                f"  ingest {key} [{mode}] ({len(info['turns'])} turns)...", flush=True
            )
            st = await mr.ingest_turns(
                svc,
                info["turns"],
                key,
                mode,
                sem,
                native_merge_policy=native_merge_policy,
            )
            print(
                f"    -> {st['distinct_keys']} keys, "
                f"collision={st['collision_ratio']}, {st['ingest_seconds']}s",
                flush=True,
            )
            stats.append(st)
    return services, stats


async def _predict(
    task, system, mode, services, llm, recall_limit, sem, unified, recall_mode
):
    """Produce one prediction record for (task, system)."""
    rec = {
        "task_id": task["task_id"],
        "system": system,
        "category": task["category"],
        "is_cognitive": task["is_cognitive"],
        "evidence": task["evidence"],
        "ground_truth": task["gold"],
        "query": task["query"],
    }
    if system == "baseline":
        prompt = mr.build_baseline_prompt(
            task["query"],
            task["full_context"],
            task["is_cognitive"],
            task["speakers"],
            unified=unified,
        )
        pred, gen_s = await mr.generate(llm, prompt, sem)
        rec.update(
            prediction=pred, n_retrieved=None, recall_seconds=0.0, gen_seconds=gen_s
        )
        return rec

    svc = services[(task["ingest_key"], mode)]
    r = await mr.recall_context(
        svc,
        task["query"],
        task["ingest_key"],
        mode,
        recall_limit,
        sem,
        recall_mode=recall_mode,
    )
    prompt = mr.build_memoir_prompt(
        task["query"],
        r["memories"],
        task["is_cognitive"],
        task["speakers"],
        unified=unified,
    )
    pred, gen_s = await mr.generate(llm, prompt, sem)
    rec.update(
        prediction=pred,
        n_retrieved=r["n_retrieved"],
        recall_seconds=r["recall_seconds"],
        gen_seconds=gen_s,
    )
    return rec


def _markdown(summaries: dict, ingest_stats: list[dict], meta: dict) -> str:
    cats = [
        "single-hop",
        "multi-hop",
        "temporal",
        "common-sense",
        "adversarial",
        "Cognitive",
    ]
    systems = list(summaries.keys())
    lines = ["# LoCoMo / LoCoMo-Plus — memoir benchmark", ""]
    lines.append(f"- backend: `{meta['backend']}` · model: `{meta['model']}`")
    lines.append(f"- tasks: {meta['n_tasks']} · recall_limit: {meta['recall_limit']}")
    lines.append(
        f"- wall-clock: {meta['wall_seconds']}s · LLM calls: ~{meta['note_calls']}"
    )
    lines.append("")
    lines.append("## Constraint-consistency score by category (avg, 0-1)")
    lines.append("")
    header = "| system | " + " | ".join(cats) + " | **overall** |"
    sep = "|" + "---|" * (len(cats) + 2)
    lines += [header, sep]
    for sysname in systems:
        s = summaries[sysname]
        bc = s.get("by_category", {})
        row = [sysname]
        for c in cats:
            v = bc.get(c)
            row.append(f"{v['avg']:.3f} ({v['count']})" if v else "—")
        row.append(f"**{s.get('overall_avg', 0):.3f}**")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Ingest stats")
    lines.append("")
    lines.append(
        "| store | mode | turns | distinct keys | collision | seconds | mean write ms |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for st in ingest_stats:
        lines.append(
            f"| {st['ingest_key']} | {st['mode']} | {st['n_turns']} | "
            f"{st['distinct_keys']} | {st['collision_ratio']} | "
            f"{st['ingest_seconds']} | {st['mean_write_ms']} |"
        )
    lines.append("")
    return "\n".join(lines)


async def main_async(args):
    from memoir.llm.claude_cli_client import ClaudeCLIWrapper

    # Raise the facet cap so long conversations aren't truncated when native mode
    # uses an append policy (default cap is 50; a 400-turn conversation needs more).
    if args.facet_cap:
        os.environ["MEMOIR_FACET_MAX_ENTRIES"] = str(args.facet_cap)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stores_dir = out_dir / "stores"

    tasks = data_mod.load_tasks(
        args.repo_dir,
        conversations=args.conversations,
        max_factual_per_category=args.max_factual_per_category,
        cognitive_limit=args.cognitive_limit,
        cognitive_offset=args.cognitive_offset,
        include_factual=not args.no_factual,
        include_cognitive=not args.no_cognitive,
    )
    print(
        f"Loaded {len(tasks)} tasks "
        f"({sum(not t['is_cognitive'] for t in tasks)} factual, "
        f"{sum(t['is_cognitive'] for t in tasks)} cognitive)"
    )

    sem = asyncio.Semaphore(args.concurrency)
    llm = ClaudeCLIWrapper(model=args.gen_model)
    judge_llm = ClaudeCLIWrapper(model=args.judge_model)
    unified = args.prompt_style == "unified"
    print(
        f"gen/memoir model: {args.gen_model} · judge model: {args.judge_model} "
        f"· prompt style: {args.prompt_style}"
    )
    t_start = time.time()

    print("== Ingesting ==", flush=True)
    services, ingest_stats = await _ingest_all(
        tasks, args.modes, stores_dir, sem, native_merge_policy=args.native_merge_policy
    )

    systems = []
    if args.baseline:
        systems.append(("baseline", None))
    for mode in args.modes:
        systems.append((f"memoir_{mode}", mode))

    print("== Predicting ==", flush=True)
    # Resume: reuse predictions already on disk, keyed by (system, task_id).
    pred_cache: dict[tuple, dict] = {}
    pred_path = out_dir / "predictions.json"
    if args.resume and pred_path.exists():
        for r in json.loads(pred_path.read_text()):
            pred_cache[(r["system"], r["task_id"])] = r
        print(f"  resume: {len(pred_cache)} cached predictions", flush=True)

    jobs = []
    for task in tasks:
        for sysname, mode in systems:
            if (sysname, task["task_id"]) in pred_cache:
                continue
            jobs.append(
                _predict(
                    task,
                    sysname,
                    mode,
                    services,
                    llm,
                    args.recall_limit,
                    sem,
                    unified,
                    args.recall_mode,
                )
            )

    def _flush_predictions():
        # Cumulative union (all prior chunks + done-so-far this chunk), so a
        # killed/timed-out chunk still persists progress and --resume continues.
        pred_path.write_text(
            json.dumps(list(pred_cache.values()), indent=2, ensure_ascii=False)
        )

    for done, fut in enumerate(asyncio.as_completed(jobs), start=1):
        rec = await fut
        pred_cache[(rec["system"], rec["task_id"])] = rec
        if done % 25 == 0:
            _flush_predictions()
            print(f"  ... {done}/{len(jobs)} new predictions", flush=True)
    records = list(pred_cache.values())
    _flush_predictions()
    print(f"  {len(records)} predictions ({len(jobs)} new)", flush=True)

    print("== Judging ==", flush=True)
    # Resume: reuse judgments already on disk; judge only the rest (batched).
    judged_cache: dict[tuple, dict] = {}
    judged_path = out_dir / "judged.json"
    if args.resume and judged_path.exists():
        for r in json.loads(judged_path.read_text()):
            if r.get("judge_label"):
                judged_cache[(r["system"], r["task_id"])] = r
    to_judge = [r for r in records if (r["system"], r["task_id"]) not in judged_cache]
    if args.judge_batch > 1:
        newly = await judge_mod.judge_batch(
            judge_llm, to_judge, sem, batch_size=args.judge_batch
        )
    else:
        newly = await asyncio.gather(
            *(judge_mod.judge_one(judge_llm, r, sem) for r in to_judge)
        )
    for r in newly:
        judged_cache[(r["system"], r["task_id"])] = r
    judged = list(judged_cache.values())
    judged_path.write_text(json.dumps(judged, indent=2, ensure_ascii=False))
    print(f"  {len(judged)} judged ({len(to_judge)} new)", flush=True)

    # Summarize every system present in the cumulative judged set (not just this
    # chunk's), so the running summary covers all chunks completed so far.
    summaries = {}
    for sysname in sorted({r["system"] for r in judged}):
        recs = [r for r in judged if r["system"] == sysname]
        summaries[sysname] = judge_mod.summarize(recs)

    wall = round(time.time() - t_start, 1)
    meta = {
        "backend": os.environ["MEMOIR_LLM_BACKEND"],
        "model": args.gen_model,
        "judge_model": args.judge_model,
        "prompt_style": args.prompt_style,
        "n_tasks": len(tasks),
        "recall_limit": args.recall_limit,
        "wall_seconds": wall,
        "note_calls": len(records) * 2,  # rough: predict + judge per record (+ingest)
    }
    (out_dir / "summary.json").write_text(
        json.dumps(
            {"meta": meta, "summaries": summaries, "ingest": ingest_stats}, indent=2
        )
    )
    md = _markdown(summaries, ingest_stats, meta)
    (out_dir / "summary.md").write_text(md)
    print("\n" + md)
    print(
        f"\nWrote results to {out_dir}/ (summary.md, summary.json, predictions.json, judged.json)"
    )


def parse_args():
    p = argparse.ArgumentParser(description="memoir LoCoMo / LoCoMo-Plus benchmark")
    p.add_argument("--repo-dir", required=True, help="Local Locomo-Plus checkout")
    p.add_argument("--out", required=True, help="Output directory")
    p.add_argument(
        "--conversations",
        type=int,
        nargs="*",
        default=None,
        help="Factual conversation indices (default: all)",
    )
    p.add_argument(
        "--max-factual-per-category",
        type=int,
        default=None,
        help="Sample at most N factual queries per category per conversation",
    )
    p.add_argument(
        "--cognitive-limit",
        type=int,
        default=None,
        help="Use only N cognitive instances (after --cognitive-offset)",
    )
    p.add_argument(
        "--cognitive-offset",
        type=int,
        default=0,
        help="Skip the first N cognitive instances (for chunked runs)",
    )
    p.add_argument("--modes", nargs="+", default=["raw"], choices=["raw", "native"])
    p.add_argument(
        "--baseline", action="store_true", help="Also run full-context baseline"
    )
    p.add_argument("--no-factual", action="store_true")
    p.add_argument("--no-cognitive", action="store_true")
    p.add_argument("--recall-limit", type=int, default=8)
    p.add_argument(
        "--recall-mode",
        choices=["single", "tiered"],
        default="single",
        help="memoir search pipeline: single (flat, O(n)) or tiered "
        "(hierarchical L1/L2 drill-down; scalable, needs native taxonomy paths)",
    )
    p.add_argument("--concurrency", type=int, default=8)
    p.add_argument(
        "--gen-model", default="haiku", help="claude-cli model for memoir + generation"
    )
    p.add_argument(
        "--judge-model",
        default="claude-opus-4-8",
        help="claude-cli model for the judge (decoupled from the generator)",
    )
    p.add_argument(
        "--prompt-style",
        choices=["unified", "disclosed"],
        default="unified",
        help="unified = no task disclosure (paper sec 5.1/5.3); "
        "disclosed = official memory-aware instruction",
    )
    p.add_argument(
        "--native-merge-policy",
        default=None,
        choices=["append", "confidence_gated", "llm_merge", "replace"],
        help="override native-mode merge (default: memoir's per-type policy). "
        "'append' keeps colliding facts as coexisting facets (less lossy).",
    )
    p.add_argument(
        "--facet-cap",
        type=int,
        default=None,
        help="MEMOIR_FACET_MAX_ENTRIES — raise for append over long conversations",
    )
    p.add_argument(
        "--judge-batch",
        type=int,
        default=10,
        help="predictions per judge call (same category); 1 = per-item",
    )
    p.add_argument(
        "--resume",
        action="store_true",
        help="reuse predictions.json / judged.json in --out; only run what's missing",
    )
    return p.parse_args()


if __name__ == "__main__":
    asyncio.run(main_async(parse_args()))

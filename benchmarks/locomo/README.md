# LoCoMo / LoCoMo-Plus benchmark for memoir

Measures memoir's conversational memory against the
[LoCoMo-Plus](https://github.com/xjtuleeyf/Locomo-Plus) benchmark
(Li et al., 2026 — *Beyond-Factual Cognitive Memory Evaluation*).

memoir slots into the paper's **Memory Systems** family: instead of feeding the
full dialogue to the model, we **ingest the dialogue into a memoir store, recall
per query, and generate the answer from the retrieved context**. A **full-context
baseline** (no memoir) is the within-backbone comparison anchor. Answers are
scored with the paper's own constraint-consistency LLM-judge (correct=1,
partial=0.5, wrong=0), reused verbatim.

## What it covers

- **Factual LoCoMo** — five categories (single-hop, multi-hop, temporal,
  common-sense, adversarial) from `locomo10.json`.
- **Cognitive LoCoMo-Plus** — implicit cue->trigger instances from
  `locomo_plus.json`, stitched into long dialogues by the official
  `build_conv.build_context`.

## Setup

1. Clone the official repo (ships both datasets):

   ```bash
   git clone https://github.com/xjtuleeyf/Locomo-Plus.git /tmp/locomo-bench/Locomo-Plus
   ```

2. All LLM calls use memoir's **claude-cli backend** — no API key, rides your
   Claude Code auth. Make sure `claude` is on `PATH`.

## Run

Diagnostic subset (one factual conversation, sampled queries, a few cognitive
instances, both ingest modes, plus the baseline):

```bash
source venv/bin/activate
python benchmarks/locomo/run.py \
    --repo-dir /tmp/locomo-bench/Locomo-Plus \
    --conversations 0 --max-factual-per-category 3 \
    --cognitive-limit 8 --modes raw --baseline \
    --concurrency 10 --out /tmp/locomo-bench/runA
```

`make benchmark-locomo` runs this subset (set `REPO_DIR=...` / `OUT=...` to
override).

### Ingest modes

| mode     | how                                              | LLM at ingest | what it tests |
|----------|--------------------------------------------------|---------------|---------------|
| `raw`    | one unique path per utterance, `append` merge    | none          | memoir as a pure semantic KV+search store (loss-free) |
| `native` | `remember()` auto-classifies into the taxonomy   | 1 call/turn   | memoir as shipped — surfaces taxonomy collisions + confidence-gating |

`native` is slow (~2.5s/turn at concurrency 10) and costs one classification
call per utterance; keep conversation counts small. `raw` ingest is instant.

### Key flags

- `--conversations N [N ...]` — factual conversation indices (default: all 10).
- `--max-factual-per-category N` — sample at most N factual queries per category.
- `--cognitive-limit N` — first N cognitive instances.
- `--modes raw native` — which ingest modes to run.
- `--baseline` — also run the full-context (no-memoir) anchor.
- `--recall-limit K` — memories retrieved per query (default 8).
- `--concurrency N` — max concurrent claude-cli subprocesses.

## Output

Written to `--out`:
- `summary.md` — score-by-category table + ingest stats.
- `summary.json` — machine-readable summaries + ingest metrics.
- `predictions.json` — every prediction with retrieval/timing.
- `judged.json` — predictions + judge label/reason/score.

## Comparability caveat

Because we run on the claude-cli backend (Claude, no key), scores are comparable
to the **baseline we run here**, not directly to the paper's GPT-4o "Memory
Systems" rows. The paper reports judge scores are stable across judge backbones,
so the *relative* picture transfers.

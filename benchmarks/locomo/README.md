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
- `--cognitive-limit N` / `--cognitive-offset N` — take N cognitive instances after
  skipping N (use the pair to **chunk** the 401-instance set).
- `--modes raw native` — which ingest modes to run.
- `--native-merge-policy append` — stop native's lossy default merge so colliding
  facts coexist (fixes native temporal/recall loss). Pair with `--facet-cap 1000`
  so long conversations aren't truncated.
- `--baseline` — also run the full-context (no-memoir) anchor.
- `--recall-limit K` — memories retrieved per query (default 8).
- `--concurrency N` — max concurrent claude-cli subprocesses (20 is fine; I/O-bound).
- `--judge-model M` — judge LLM, decoupled from the generator (default
  `claude-opus-4-8`). Keeping judge ≠ generator avoids self-evaluation inflation.
- `--judge-batch N` — predictions per judge call (default 10; `1` = per-item,
  byte-identical to the official judge). Batching cuts the (pricey) judge calls ~Nx.
- `--prompt-style unified|disclosed` — `unified` (default) presents the query as a
  plain continuation with no task disclosure (paper sec 5.1/5.3); `disclosed` uses
  the official memory-aware instruction.
- `--resume` — reuse `predictions.json` / `judged.json` in `--out`; only run
  what's missing. Makes long runs interruption-safe and **chunkable**.

### Recommended config

Decoupled Opus judge + Haiku generator, unified input, native uses `append`:

```bash
python benchmarks/locomo/run.py --repo-dir /tmp/locomo-bench/Locomo-Plus \
    --modes raw native --native-merge-policy append --facet-cap 1000 \
    --baseline --judge-model claude-opus-4-8 --judge-batch 10 \
    --prompt-style unified --concurrency 20 --resume --out OUT_DIR
```

### Full run (chunked, ~4–4.5 h on claude-cli @ conc 20)

The full set is 1,986 factual QA + 401 cognitive instances. Run it in chunks into
**one** `--out` dir with `--resume`; each chunk merges into the cumulative
`summary.md`, so results accrue as chunks finish and a crash only loses the
current chunk. Native ingest (~1 classify/turn) is the slow pole, so native is
factual-only — **native-cognitive is infeasible (~days)** and intentionally skipped.

```bash
OUT=/tmp/locomo-bench/full
# Factual: one chunk per conversation (raw + native + baseline)
for c in 0 1 2 3 4 5 6 7 8 9; do
  python benchmarks/locomo/run.py --repo-dir /tmp/locomo-bench/Locomo-Plus \
    --conversations $c --no-cognitive \
    --modes raw native --native-merge-policy append --facet-cap 1000 \
    --baseline --judge-model claude-opus-4-8 --judge-batch 10 \
    --prompt-style unified --concurrency 20 --resume --out $OUT
done
# Cognitive: raw + baseline only, in chunks of 100
for off in 0 100 200 300; do
  python benchmarks/locomo/run.py --repo-dir /tmp/locomo-bench/Locomo-Plus \
    --no-factual --cognitive-offset $off --cognitive-limit 100 \
    --modes raw --baseline --judge-model claude-opus-4-8 --judge-batch 10 \
    --prompt-style unified --concurrency 20 --resume --out $OUT
done
```

For a cheaper but statistically solid signal, run all 401 cognitive + a balanced
factual sample (`--max-factual-per-category 8`) — roughly 1 h.

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

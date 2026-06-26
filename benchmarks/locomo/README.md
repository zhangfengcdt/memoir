# LoCoMo / LoCoMo-Plus benchmark for memoir

Measures memoir's conversational memory against the
[LoCoMo-Plus](https://github.com/xjtuleeyf/Locomo-Plus) benchmark
(Li et al., 2026 — *Beyond-Factual Cognitive Memory Evaluation*).

memoir slots into the paper's **Memory Systems** family: instead of feeding the
full dialogue to the model, we **ingest the dialogue into a memoir store, recall
per query, and generate the answer from the retrieved context**. A **full-context
baseline** (no memoir) is the comparison anchor. Answers are scored with the
paper's own constraint-consistency LLM-judge (correct=1, partial=0.5, wrong=0),
reused verbatim.

The two regimes use the representation suited to each (memory is not one-size):

- **Factual LoCoMo** (`run.py`) — five categories (single-hop, multi-hop,
  temporal, common-sense, adversarial). memoir uses **native** ingest: each
  utterance is classified into memoir's taxonomy (`append` merge so colliding
  facts coexist). System row: `memoir_native`.
- **Cognitive LoCoMo-Plus** (`cognitive.py`) — implicit cue→trigger instances.
  memoir uses **constraint-aware** ingest: a write-time pass indexes each
  utterance's latent state/goal/value/causal implication. System row:
  `memoir_hybrid` (constraint retrieval, generation grounded in the cue's source
  text). Uses git-like **branching** so each base conversation is ingested once
  and every instance is a cheap branch carrying only its cue.

## Models

All LLM calls go through litellm (no claude-cli):

- **Generation** (the answer) and **memoir-internal recall/extraction**:
  `gpt-4o-mini`.
- **Judge**: `gpt-4o` (paper-aligned).

Set `OPENAI_API_KEY` (e.g. in a local `.env.local` and `source` it). Note: recall
sends the whole store per query, so the recall model is the dominant token cost —
keep it cheap (`gpt-4o-mini`).

## Setup

```bash
git clone https://github.com/xjtuleeyf/Locomo-Plus.git /tmp/locomo-bench/Locomo-Plus
source venv/bin/activate
export OPENAI_API_KEY=...      # or: set -a && . .env.local && set +a
```

## Run

**Factual** (all 10 conversations, `memoir_native` + baseline):

```bash
python benchmarks/locomo/run.py --repo-dir /tmp/locomo-bench/Locomo-Plus \
    --no-cognitive --modes native --native-merge-policy append --facet-cap 1000 \
    --baseline --gen-model gpt-4o-mini --judge-model gpt-4o --judge-batch 10 \
    --prompt-style unified --concurrency 4 --resume --out OUT/factual
```

**Cognitive** (full 401 instances, `memoir_hybrid` + baseline):

```bash
python benchmarks/locomo/cognitive.py --repo-dir /tmp/locomo-bench/Locomo-Plus \
    --limit 401 --cog-mode hybrid --gen-model gpt-4o-mini --judge-model gpt-4o \
    --concurrency 2 --resume --out OUT/cognitive
```

Run the two **sequentially** — the `gpt-4o` judge shares a per-minute token limit,
so two judge streams at once throttle each other.

`make benchmark-locomo` runs a small factual subset (set `REPO_DIR=` / `OUT=`).

### Key flags

- `--conversations N [...]` — factual conversation indices (default: all 10).
- `--max-factual-per-category N` — sample at most N factual queries per category.
- `--cognitive-limit N` / `--cognitive-offset N` — chunk the 401 cognitive set.
- `--cog-mode constraint|hybrid` — cognitive ingest (hybrid grounds generation in
  the cue's source text).
- `--native-merge-policy append` + `--facet-cap 1000` — keep colliding native
  facts as coexisting facets (loss-free) over long conversations.
- `--gen-model` / `--judge-model` — litellm models (default gpt-4o-mini / gpt-4o).
- `--judge-batch N` — predictions per judge call (default 10; cuts judge calls).
- `--prompt-style unified|disclosed` — `unified` (default) = no task disclosure
  (paper sec 5.1/5.3).
- `--recall-mode single|tiered` — memoir search pipeline.
- `--concurrency N` — concurrent calls. Keep low (≈2–4) when judging with `gpt-4o`
  to respect its token-per-minute limit.
- `--resume` — reuse predictions/judgments already in `--out`; only run what's
  missing. Both runners flush incrementally, so runs are interruption-safe.

## Output

Per `--out`: `summary.md` / `summary.json` (factual) or `cog_summary.json`
(cognitive) — score-by-category tables; plus `predictions.json` / `judged.json`
(per-item predictions, retrieval/timing, judge label+reason+score).

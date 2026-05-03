---
description: "Recall memories from past sessions via memoir. Delegates to the memory-recall skill. Pass --include-metrics to include machine-generated turn statistics (excluded by default)."
argument-hint: "[--include-metrics] <query>"
---

Invoke the memory-recall skill to find memories relevant to: $ARGUMENTS

If `$ARGUMENTS` contains `--include-metrics`, the skill will include `metrics.*` keys (turn statistics, code-change summaries, etc.). Otherwise those keys are excluded silently — recall is for user-captured facts, not telemetry.

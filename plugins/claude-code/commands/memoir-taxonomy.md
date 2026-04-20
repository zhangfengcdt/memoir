---
description: "Show the memoir taxonomy — what categories are loaded and how memories are distributed across namespaces."
allowed-tools: Bash
---

Memoir classifies every memory into a hierarchical path (e.g. `preferences.coding.languages`). This command shows the taxonomy breakdown.

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; echo "=== Taxonomy summary ==="; memoir --json -s "$STORE" summarize taxonomy; echo; echo "=== Registered taxonomies ==="; memoir -s "$STORE" taxonomy list 2>/dev/null || true'`

Present the breakdown in a short table if non-trivial. Taxonomy is what makes memoir's recall O(log n) at a named path — unlike vector search, there are no embeddings to index.

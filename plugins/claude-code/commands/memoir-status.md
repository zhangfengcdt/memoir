---
description: "Show memoir store status — current branch, commit count, memory count, namespaces."
allowed-tools: Bash
---

Run memoir status against the per-project store:

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; memoir --json -s "$STORE" status 2>&1'`

Summarize the output for the user in one short line (branch, N memories, M commits, namespaces if any beyond taxonomy internals).

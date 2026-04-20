---
description: "Show the change history for a specific memory path — like git blame, but for a taxonomy path."
argument-hint: "<path> [-n <namespace>] [-l <limit>]"
allowed-tools: Bash
---

Who changed `<path>`, when, and in which commit?

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; memoir --json -s "$STORE" blame $ARGUMENTS' ARGUMENTS="$ARGUMENTS"`

Summarize the entries in chronological order (oldest first) so the user can see how the fact evolved. This is the kind of provenance question a vector-search system cannot answer at all.

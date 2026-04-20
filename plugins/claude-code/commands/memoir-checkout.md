---
description: "Switch the memoir active branch. Subsequent recalls and writes target the new branch."
argument-hint: "<branch-name> [--create]"
allowed-tools: Bash
---

Switch branches. Append `-b` (or `--create`) to create the branch if it doesn't exist.

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; memoir -s "$STORE" checkout $ARGUMENTS' ARGUMENTS="$ARGUMENTS"`

After checkout, the memory-recall skill and auto-capture write to the new branch. Confirm the user understands this switches Claude's memory context for the rest of the session.

---
description: "Create a branch rooted at a past commit and check it out. Lets you query memory as it was at that point in time."
argument-hint: "<commit-hash> [-b <branch-name>]"
allowed-tools: Bash
---

Travel to a past memory state. Memoir creates a new branch (named automatically if `-b` is omitted) and switches to it — the original branches are untouched.

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; memoir -s "$STORE" time-travel $ARGUMENTS' ARGUMENTS="$ARGUMENTS"`

After travelling, the memory-recall skill will return whatever was known at that commit. To return to the present, `/memoir-checkout main`.

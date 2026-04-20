---
description: "Verify a cryptographic proof previously generated with /memoir-proof."
argument-hint: "<path> [-n <namespace>] [-p <base64-proof> | -f <proof-file>] [--expected <json>]"
allowed-tools: Bash
---

Verify a memoir proof against the current store state.

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; memoir --json -s "$STORE" verify $ARGUMENTS' ARGUMENTS="$ARGUMENTS"`

Report `valid: true/false`. If `--expected` was provided, also state whether the current stored value matches. A failed verification means the path's value has changed since the proof was generated — useful for auditing whether a sensitive memory has been tampered with.

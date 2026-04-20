---
description: "Generate a SHA-256 cryptographic proof for a memoir path. Verifiable later with /memoir-verify."
argument-hint: "<path> [-n <namespace>] [-o <file>]"
allowed-tools: Bash
---

Produce a Merkle proof that a given taxonomy path holds its current value in the current commit.

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; memoir --json -s "$STORE" proof $ARGUMENTS' ARGUMENTS="$ARGUMENTS"`

If `-o <file>` was given, the base64 proof was saved to that file; otherwise it's in the JSON `proof_b64` field. Share the file or the string; recipients can verify integrity against the same store with `/memoir-verify`.

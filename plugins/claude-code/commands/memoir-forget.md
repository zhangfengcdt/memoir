---
description: "Delete a memory by key/path. Always uses --force (slash commands are non-interactive)."
argument-hint: "<key> [-n <namespace>]"
allowed-tools: Bash
---

Delete a memory permanently. The slash command always passes `--force` because Claude Code can't answer an interactive `[y/N]` prompt — this commits the deletion immediately. The deleted memory is recoverable via `/memoir-time-travel <prior-commit>` if needed.

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; memoir --json -s "$STORE" forget --force $ARGUMENTS' ARGUMENTS="$ARGUMENTS"`

Confirm what was deleted (key + commit hash). Remind the user that the entry is recoverable via time-travel if it was a mistake.

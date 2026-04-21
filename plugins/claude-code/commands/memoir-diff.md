---
description: "Compare memoir state between two commits. Pass --stat for a summary, full diff otherwise."
argument-hint: "[<commit1>] [<commit2>] [--stat]"
allowed-tools: Bash
---

Show what changed in the memoir store between two commits. Without arguments, memoir compares the most recent two commits.

```
/memoir-diff
/memoir-diff abc123f def456a
/memoir-diff abc123f def456a --stat
```

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; memoir -s "$STORE" diff $ARGUMENTS' ARGUMENTS="$ARGUMENTS"`

For a `--stat` invocation, show the summary as a brief table. For a full diff, summarize the meaningful additions/removals (taxonomy paths added, content updated) rather than dumping the raw output verbatim.

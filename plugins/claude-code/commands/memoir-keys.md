---
description: "List all keys (memories) in the memoir store. Optional glob pattern filters."
argument-hint: "[<glob-pattern>]"
allowed-tools: Bash
---

Browse the memoir store. Default lists everything; pass a glob like `preferences.*` or `*.coding.*` to filter.

```
/memoir-keys
/memoir-keys preferences.*
/memoir-keys *.coding.*
```

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; PATTERN="${ARGUMENTS:-*}"; memoir --json -s "$STORE" summarize --keys "$PATTERN"' ARGUMENTS="$ARGUMENTS"`

Filter out memoir's internal `taxonomy:v1:*` namespaces from your output unless the user specifically asked to see them — they're classifier bookkeeping, not user memories. Group the rest by namespace and list each `path` underneath.

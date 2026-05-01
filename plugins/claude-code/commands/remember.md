---
description: "Manually capture a memory now (independent of Stop-hook auto-capture). Pass -p <path> to skip classification."
argument-hint: "<fact> [-n <namespace>] [-p <path>]"
allowed-tools: Bash
---

Save a memory immediately, without waiting for the Stop hook to fire after the next turn. By default memoir's LLM classifier picks the taxonomy path; pass `-p preferences.coding.style` (or any explicit path) to skip classification — about 25× faster (~0.4s vs ~10s).

Multi-word content works with or without surrounding quotes — the wrapper rejoins bare words into a single argument:

```
/memoir:remember "I prefer vim" -p preferences.tools.editors
/memoir:remember Project uses Python 3.12 and ruff
```

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/remember-args.sh" $ARGUMENTS`

Show the resulting `key` (taxonomy path) and `commit_hash`. This is independent of the Stop hook — the auto-capture pipeline still fires at the end of the turn for any other durable facts mentioned.

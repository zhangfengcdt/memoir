---
description: "Create or list memoir memory branches. Branches isolate memory writes — useful for experiments you may want to discard or merge later."
argument-hint: "[branch-name]"
allowed-tools: Bash
---

With no argument, list branches; with one argument, create it.

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; if [ -z "$ARGUMENTS" ]; then memoir --json -s "$STORE" branch; else memoir -s "$STORE" branch "$ARGUMENTS"; fi' ARGUMENTS="$ARGUMENTS"`

Memoir branches isolate memory state — a fact written on `experiment` is not visible on `main` until merged. This is memoir's direct answer to "I want Claude to explore a hypothesis without polluting my long-term memory."

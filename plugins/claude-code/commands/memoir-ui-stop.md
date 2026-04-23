---
description: "Stop the memoir UI background server for the current project's store."
allowed-tools: Bash
---

Stop the memoir UI background server launched by the `memoir-ui` skill (or by a previous `/memoir-ui-stop` sibling). Idempotent — no-op if nothing is running.

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; bash "${CLAUDE_PLUGIN_ROOT}/scripts/memoir-ui-ctl.sh" stop "$STORE" 2>&1'`

Summarize the output in one short line (e.g. `stopped pid=12345`, `already gone`, or `no memoir-ui servers tracked`). If the user wants to stop every memoir-ui server across all projects, tell them to run:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/memoir-ui-ctl.sh" stop
```

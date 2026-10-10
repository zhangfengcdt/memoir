---
description: "Show what memoir just learned — live capture feed + taxonomy pane (Claude Code 2.1.287+; older versions get a text summary)."
allowed-tools: Bash
---

On Claude Code 2.1.287 or newer the memoir mod answers `/memoir:pane` itself and opens the pane, so this prompt never runs there. It runs only on older versions, which cannot draw a pane.

Run this Bash call and show its output to the user verbatim:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/pane-cmd.sh"
```

Then add one line: the live pane (and the built-in status line) needs Claude Code 2.1.287 or newer.

---
description: "[DISABLED pending upstream bugfix] Merge current memoir branch into main. Use would lose data on main."
allowed-tools: Bash
---

**⚠ Disabled** — `memoir merge` (the underlying prollytree primitive) has a bug that leaves the merge destination's tree empty with a `Root node not found in storage` warning. Running this would destroy whatever is on main. Tracked in `plugins/claude-code/TODO.md`.

Until the prollytree fix lands, this command is a no-op that prints a reminder.

!`bash -c '
echo "⚠ /memoir-sync is disabled — memoir merge is currently data-destructive."
echo "   See plugins/claude-code/TODO.md for tracking."
echo "   Feature branches keep their captures; they'"'"'re just not promotable to main right now."
'`

Do not attempt to bypass by invoking `memoir merge` directly — the same bug applies. Wait for the prollytree fix.

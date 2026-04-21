---
description: "[DISABLED pending upstream bugfix] Merge an arbitrary memoir branch into main. Use would lose data on main."
argument-hint: "<branch-name>"
allowed-tools: Bash
---

**⚠ Disabled** — same reason as `/memoir-sync`. `memoir merge` (the underlying prollytree primitive) is currently data-destructive: merging into a branch leaves that branch's tree empty with a `Root node not found in storage` warning. Tracked in `plugins/claude-code/TODO.md`.

Until the prollytree fix lands, this command is a no-op that prints a reminder.

!`bash -c '
echo "⚠ /memoir-sync-branch is disabled — memoir merge is currently data-destructive."
echo "   Target branch would be: ${ARGUMENTS:-<none>}"
echo "   See plugins/claude-code/TODO.md for tracking."
echo "   Your feature branches still have all their captures; they'"'"'re just not promotable to main right now."
' ARGUMENTS="$ARGUMENTS"`

Do not attempt to bypass by invoking `memoir merge` directly — the same bug applies. Wait for the prollytree fix.

---
description: "Merge the current memoir branch into main. Keeps the source branch so you can keep capturing on it."
allowed-tools: Bash
---

Promote the facts captured on the current memoir branch to main. The source branch is kept (delete manually via `/memoir-branch -d <name>` if you want cleanup). If you're already on main, this is a no-op.

!`bash -c '
STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"
CURRENT=$(memoir --json -s "$STORE" status | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or \"{}\").get(\"branch\",\"\"))")
if [ -z "$CURRENT" ] || [ "$CURRENT" = "main" ]; then
  echo "Already on main — nothing to sync."
  exit 0
fi
# Switch to main, merge the source, return to the feature branch, then record
# a sync marker so the unmerged-branch detector treats this branch as merged
# until further captures happen on it.
if memoir -s "$STORE" checkout main > /dev/null && \
   memoir -s "$STORE" merge "$CURRENT" && \
   memoir -s "$STORE" checkout "$CURRENT" > /dev/null; then
  # Branch names may contain `/` (e.g. feature/x), so mkdir -p the parent
  # directory of the marker file rather than just the top-level dir.
  mkdir -p "$(dirname "$STORE/.git/plugin-synced-branches/$CURRENT")"
  date +%s > "$STORE/.git/plugin-synced-branches/$CURRENT"
  echo "(synced memoir/$CURRENT into main; still on $CURRENT)"
fi
'`

Report the merge commit hash (if any) and whether there were conflicts. If `-S skip` was used as default and there were conflicts, some memories may have been dropped on main — remind the user they can re-run with `-S ours` or `-S theirs` explicitly via `memoir merge`.

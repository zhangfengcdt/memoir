---
description: "Merge a specific memoir branch into main without switching to it. Used to promote captures from branches you're no longer working on."
argument-hint: "<branch-name>"
allowed-tools: Bash
---

Merge a specified memoir branch into main while staying on your current branch. Useful when the SessionStart detector surfaces unmerged branches — you can promote each without switching away from your current work.

!`bash -c '
STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"
TARGET="$ARGUMENTS"
if [ -z "$TARGET" ]; then
  echo "Usage: memoir:memoir-sync-branch <branch-name>"
  exit 1
fi
if [ "$TARGET" = "main" ]; then
  echo "Refusing to merge main into main — pick a feature branch."
  exit 1
fi
CURRENT=$(memoir --json -s "$STORE" status | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or \"{}\").get(\"branch\",\"\"))")
# Checkout main, merge target, return to original branch, record sync marker.
if memoir -s "$STORE" checkout main > /dev/null && \
   memoir -s "$STORE" merge "$TARGET"; then
  if [ -n "$CURRENT" ] && [ "$CURRENT" != "main" ]; then
    memoir -s "$STORE" checkout "$CURRENT" > /dev/null
  fi
  mkdir -p "$(dirname "$STORE/.git/plugin-synced-branches/$TARGET")"
  date +%s > "$STORE/.git/plugin-synced-branches/$TARGET"
  echo "(synced memoir/$TARGET into main; back on ${CURRENT:-main})"
fi
' ARGUMENTS="$ARGUMENTS"`

Report the merge result. If the user has multiple unmerged branches (from the SessionStart detector), remind them they can repeat this command for each.

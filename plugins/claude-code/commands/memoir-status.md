---
description: "Show memoir store status — current branch, commit count, memory count, plus a hint if any branches need /memoir-sync."
allowed-tools: Bash
---

Run memoir status against the per-project store, and also count unmerged branches so you know if a sync is due.

!`bash -c '
STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"
echo "=== status ==="
memoir --json -s "$STORE" status 2>&1
echo
echo "=== unmerged-branch check ==="
THIRTY_DAYS_AGO=$(( $(date +%s) - 30*86400 ))
BRANCHES=$(memoir --json -s "$STORE" branch | python3 -c "
import json,sys
for b in json.loads(sys.stdin.read() or \"{}\").get(\"branches\", []):
    print(b)
")
COUNT=0
while IFS= read -r b; do
  [ -z "$b" ] || [ "$b" = "main" ] && continue
  if [ -f "$STORE/.git/plugin-ignored-branches" ] && grep -qxF "$b" "$STORE/.git/plugin-ignored-branches"; then
    continue
  fi
  AHEAD=$(git -C "$STORE" rev-list --count "main..$b" 2>/dev/null || echo 0)
  [ "$AHEAD" = "0" ] && continue
  LAST=$(git -C "$STORE" log -1 --format=%ct "$b" 2>/dev/null || echo 0)
  [ "$LAST" -lt "$THIRTY_DAYS_AGO" ] && continue
  MARKER_FILE="$STORE/.git/plugin-synced-branches/$b"
  if [ -f "$MARKER_FILE" ]; then
    MARKER_TS=$(cat "$MARKER_FILE" 2>/dev/null || echo 0)
    [ "$MARKER_TS" -ge "$LAST" ] && continue
  fi
  COUNT=$((COUNT + 1))
done <<< "$BRANCHES"
if [ "$COUNT" -gt 0 ]; then
  echo "$COUNT branch(es) ahead of main — run /memoir-unmerged to list. (Promotion is temporarily disabled; see TODO.md.)"
else
  echo "No branches need sync."
fi
'`

Summarize the output for the user: one short line for status (branch, N user memories, M commits, namespaces beyond taxonomy internals), plus the unmerged-branch hint on its own line if any exist.

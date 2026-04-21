---
description: "Show memoir branches ahead of main — the candidates for /memoir-sync-branch."
allowed-tools: Bash
---

List memoir branches that have captured memories not yet promoted to main. Same candidates the SessionStart hook surfaces to Claude in its context — this is the explicit pull-version you can run any time.

!`bash -c '
STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"
THIRTY_DAYS_AGO=$(( $(date +%s) - 30*86400 ))
CURRENT=$(memoir --json -s "$STORE" status | python3 -c "import json,sys;print(json.loads(sys.stdin.read() or \"{}\").get(\"branch\",\"\"))")
BRANCHES=$(memoir --json -s "$STORE" branch | python3 -c "
import json,sys
for b in json.loads(sys.stdin.read() or \"{}\").get(\"branches\", []):
    print(b)
")
FOUND=0
while IFS= read -r b; do
  [ -z "$b" ] && continue
  [ "$b" = "main" ] && continue
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
    if [ "$MARKER_TS" -ge "$LAST" ]; then
      continue
    fi
  fi
  STATUS=""
  [ "$b" = "$CURRENT" ] && STATUS=" (currently checked out)"
  echo "  memoir/$b: $AHEAD unmerged commits$STATUS"
  FOUND=$((FOUND + 1))
done <<< "$BRANCHES"
if [ "$FOUND" = "0" ]; then
  echo "All memoir branches are synced to main. Nothing to do."
else
  echo
  echo "Promote to main with: /memoir-sync-branch <branch-name>"
fi
'`

Report the list (or the "all clean" message). If branches are shown, remind the user they can run `/memoir-sync-branch <name>` for each, or `/memoir-sync` from the branch itself.

---
description: "Create or list memoir memory branches. Creating a branch whose name doesn't match the code branch opts out of auto-matching until you return."
argument-hint: "[branch-name]"
allowed-tools: Bash
---

With no argument, list branches; with one argument, create it. If the name doesn't match the current code git branch, this also sets a sticky marker so the plugin stops auto-matching memoir branch to code branch (the auto-match resumes when you check back out to a matching branch).

!`bash -c '
STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"
if [ -z "$ARGUMENTS" ]; then
  memoir --json -s "$STORE" branch
else
  memoir -s "$STORE" branch "$ARGUMENTS"
  # If the chosen name doesnt match the current code branch, set the sticky
  # marker so auto-match doesn't override the user's choice next session.
  CODE_BRANCH=$(git -C "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" branch --show-current 2>/dev/null || true)
  if [ -n "$CODE_BRANCH" ] && [ "$ARGUMENTS" != "$CODE_BRANCH" ]; then
    printf "%s\n" "$ARGUMENTS" > "$STORE/.git/plugin-sticky-branch"
    echo "(sticky opt-out set: auto-match disabled until you checkout a code-matching branch)"
  fi
fi
' ARGUMENTS="$ARGUMENTS"`

Memoir branches isolate memory state — a fact written on `experiment` is not visible on `main` until merged. Branch-matching with the code git branch is the plugin's default behavior; creating an explicitly-named branch (above) opts you out of that for the current sticky opt-out until you check back out.


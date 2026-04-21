---
description: "Switch the memoir active branch. Sets/clears the sticky opt-out based on whether the target matches the code branch."
argument-hint: "<branch-name> [-b]"
allowed-tools: Bash
---

Switch branches. Append `-b` (or `--create`) to create if missing. If the target matches the current code branch, the sticky opt-out marker is cleared (auto-match resumes). If it doesn't match, the marker is set so auto-match stays off next session.

!`bash -c '
STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"
memoir -s "$STORE" checkout $ARGUMENTS
# memoir checkout leaves the working tree dirty (updates .git/HEAD but not
# index + working tree). Reset so `git status` stays clean.
git -C "$STORE" reset --hard HEAD >/dev/null 2>&1 || true
# Parse the target branch name (first positional arg — skip -b/--create flags).
TARGET=""
for arg in $ARGUMENTS; do
  case "$arg" in
    -b|--create) ;;
    *) TARGET="$arg"; break ;;
  esac
done
CODE_BRANCH=$(git -C "$(git rev-parse --show-toplevel 2>/dev/null || pwd)" branch --show-current 2>/dev/null || true)
STICKY="$STORE/.git/plugin-sticky-branch"
if [ -n "$TARGET" ] && [ -n "$CODE_BRANCH" ]; then
  if [ "$TARGET" = "$CODE_BRANCH" ]; then
    rm -f "$STICKY" && echo "(sticky opt-out cleared: auto-match resumed)" || true
  else
    printf "%s\n" "$TARGET" > "$STICKY"
    echo "(sticky opt-out set: target $TARGET differs from code branch $CODE_BRANCH)"
  fi
fi
' ARGUMENTS="$ARGUMENTS"`

After checkout, the memory-recall skill and auto-capture target the new branch. Confirm the user understands this switches Claude's memory context for the rest of the session. Note the sticky-marker line — it tells the user whether future sessions will auto-match or stay on this branch.

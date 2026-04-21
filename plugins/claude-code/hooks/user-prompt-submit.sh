#!/usr/bin/env bash
# UserPromptSubmit hook: light hint reminding Claude the memory-recall skill
# is available, and surfacing the current memoir branch name.
# The actual retrieval is pull-based (memory-recall skill, context: fork).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

PROMPT=$(_json_val "$INPUT" "prompt" "")
if [ -z "$PROMPT" ] || [ "${#PROMPT}" -lt 10 ]; then
  echo '{}'
  exit 0
fi

if [ -z "$MEMOIR_CMD" ]; then
  echo '{}'
  exit 0
fi

# Re-run auto-match here (not just SessionStart). If the user switched code
# branches mid-session (e.g. `git checkout feature/b` in a terminal), the
# memoir branch would otherwise remain on the old match and subsequent Stop
# captures would write to the wrong branch. Calling auto_match on every
# prompt makes "memoir branch == code branch (unless sticky)" an invariant
# across the entire session, not just at start. Fast no-op when branches
# already agree; flips the memoir branch when they don't.
auto_match_memoir_branch || true

# Read state AFTER the potential auto-switch so the status hint reflects reality.
STATUS_JSON=$(memoir_json status || true)
BRANCH=$(_json_val "$STATUS_JSON" "branch" "main")
CODE_BRANCH=$(code_git_branch)

# Display: collapse to `<branch>` when code and memoir agree (the default
# after auto-match); show `<code>+<memory>*` when they differ, which only
# happens when the user has a sticky opt-out active.
if [ -n "$CODE_BRANCH" ] && [ "$CODE_BRANCH" = "$BRANCH" ]; then
  DISPLAY_BRANCH="${BRANCH}"
elif [ -n "$CODE_BRANCH" ]; then
  DISPLAY_BRANCH="${CODE_BRANCH}+${BRANCH}*"
else
  DISPLAY_BRANCH="${BRANCH}"
fi
msg="[memoir] ${DISPLAY_BRANCH}"
json_msg=$(_json_encode_str "$msg")
echo "{\"systemMessage\": $json_msg}"

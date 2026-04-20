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

# Surface both memory branch and code git branch so they're never confused.
# memoir's branch is its single clearest superpower over a flat vector store,
# and showing the code branch alongside makes it unambiguous which "branch" is which.
STATUS_JSON=$(memoir_json status || true)
BRANCH=$(_json_val "$STATUS_JSON" "branch" "main")
CODE_BRANCH=$(code_git_branch)

# Composite display `<code>+<memory>` — see session-start.sh for the reasoning.
if [ -n "$CODE_BRANCH" ]; then
  DISPLAY_BRANCH="${CODE_BRANCH}+${BRANCH}"
else
  DISPLAY_BRANCH="${BRANCH}"
fi
msg="[memoir] ${DISPLAY_BRANCH}"
json_msg=$(_json_encode_str "$msg")
echo "{\"systemMessage\": $json_msg}"

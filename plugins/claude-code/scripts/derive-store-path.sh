#!/usr/bin/env bash
# Derive a deterministic per-project memoir store path.
# Used by hooks (via common.sh) and the memory-recall skill.
#
# Usage: derive-store-path.sh [project_dir]
#        derive-store-path.sh --print-git-root
#   If no argument given, uses the git root (or pwd if no git).
#
# Output: $HOME/.memoir/<slug>
#   The slug mirrors Claude Code's own project naming convention under
#   ~/.claude/projects/: take the absolute path and replace '/' and '.'
#   with '-'.
#
#   /Users/feng/github/memoir         -> ~/.memoir/-Users-feng-github-memoir
#   /Users/feng/.claude-mem/sessions  -> ~/.memoir/-Users-feng--claude-mem-sessions
#
# Thin wrapper: the actual derivation (worktree-aware git-root resolution,
# slugging) now lives in memoir-ai core as `memoir store-path`, shared by
# every host plugin instead of each carrying its own copy. See
# src/memoir/cli/commands/store.py in the memoir-ai package.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=resolve-memoir-cli.sh
source "$SCRIPT_DIR/resolve-memoir-cli.sh"

if [ "${#MEMOIR_CMD_ARGV[@]}" -eq 0 ]; then
  echo "$MEMOIR_INSTALL_HINT" >&2
  exit 127
fi

"${MEMOIR_CMD_ARGV[@]}" store-path "$@"

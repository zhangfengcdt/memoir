#!/usr/bin/env bash
# Derive a deterministic per-project memoir store path.
# Used by hooks (via common.sh) and the memory-recall skill.
#
# Usage: derive-store-path.sh [project_dir]
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
# Design note: per-project store (not per-project namespace in a shared store)
# was chosen to keep memoir's git operations — branching, time-travel, merge
# — scoped to a single project. A shared store would entangle histories.

set -euo pipefail

# If no arg given, prefer the git root (matches common.sh behavior) so that
# slash commands and the memory-recall skill resolve to the same store
# regardless of which subdirectory pwd happens to be in.
#
# Non-git folder fallback uses absolute `pwd`. Renaming or moving the folder
# relocates the store. (Trade-off: store-identity is the absolute path. We
# considered a `.memoir/` marker file at the project root for stable identity
# across renames, but kept the path-keyed scheme for symmetry with the git
# case.)
if [ -n "${1:-}" ]; then
  PROJECT_DIR="$1"
else
  _GIT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
  if [ -n "$_GIT_ROOT" ]; then
    PROJECT_DIR="$_GIT_ROOT"
  else
    PROJECT_DIR="$(pwd)"
  fi
fi

# Resolve to absolute path.
if realpath -m "$PROJECT_DIR" &>/dev/null 2>&1; then
  PROJECT_DIR="$(realpath -m "$PROJECT_DIR")"
elif [ -d "$PROJECT_DIR" ]; then
  PROJECT_DIR="$(cd "$PROJECT_DIR" && pwd)"
else
  case "$PROJECT_DIR" in
    /*) ;;
    *)  PROJECT_DIR="$(pwd)/$PROJECT_DIR" ;;
  esac
fi

# Slug = absolute path with '/' and '.' replaced by '-'. Matches the
# layout Claude Code uses for its own project state under
# ~/.claude/projects/, so users can correlate across both systems by eye.
slug=$(printf '%s' "$PROJECT_DIR" | tr '/.' '--')

echo "$HOME/.memoir/${slug}"

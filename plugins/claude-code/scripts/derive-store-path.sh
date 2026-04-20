#!/usr/bin/env bash
# Derive a deterministic per-project memoir store path.
# Used by hooks (via common.sh) and the memory-recall skill.
#
# Usage: derive-store-path.sh [project_dir]
#   If no argument given, uses pwd.
#
# Output: $HOME/.memoir/<sanitized_basename>_<8char_sha256>
#   e.g. /home/user/my-app  ->  /home/user/.memoir/my_app_a1b2c3d4
#
# Design note: per-project store (not per-project namespace in a shared store)
# was chosen to keep memoir's git operations — branching, time-travel, merge
# — scoped to a single project. A shared store would entangle histories.

set -euo pipefail

# If no arg given, prefer the git root (matches common.sh behavior) so that
# slash commands and the memory-recall skill resolve to the same store
# regardless of which subdirectory pwd happens to be in.
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

sanitized=$(basename "$PROJECT_DIR" \
  | tr '[:upper:]' '[:lower:]' \
  | sed 's/[^a-z0-9]/_/g' \
  | sed 's/__*/_/g' \
  | sed 's/^_//;s/_$//' \
  | cut -c1-40)

if command -v sha256sum &>/dev/null; then
  hash=$(printf '%s' "$PROJECT_DIR" | sha256sum | cut -c1-8)
elif command -v shasum &>/dev/null; then
  hash=$(printf '%s' "$PROJECT_DIR" | shasum -a 256 | cut -c1-8)
else
  hash=$(python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:8])" "$PROJECT_DIR")
fi

echo "$HOME/.memoir/${sanitized}_${hash}"

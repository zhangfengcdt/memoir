#!/usr/bin/env bash
# Install Memoir OpenCode plugin from GitHub (sparse checkout, no full clone).
# Usage: curl -fsSL https://raw.githubusercontent.com/zhangfengcdt/memoir/main/plugins/opencode/install.sh | bash
set -euo pipefail

REPO="https://github.com/zhangfengcdt/memoir.git"
SUBDIR="plugins/opencode"
TARGET="${XDG_CONFIG_HOME:-$HOME/.config}/opencode/plugins/memoir"

# Pre-flight checks
for cmd in git node npm; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: $cmd is required but not installed." >&2
    exit 1
  fi
done

# Already installed?
if [ -d "$TARGET" ]; then
  echo "Memoir OpenCode plugin already installed at $TARGET" >&2
  echo "Remove it first: rm -rf '$TARGET'" >&2
  exit 1
fi

TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

echo "Downloading Memoir plugin..."
git clone --filter=blob:none --sparse --depth=1 "$REPO" "$TMPDIR" 2>/dev/null

(
  cd "$TMPDIR"
  git sparse-checkout set "$SUBDIR" 2>/dev/null
)

echo "Installing dependencies..."
npm ci --prefix "$TMPDIR/$SUBDIR" 2>/dev/null

echo "Building plugin..."
npm run build --prefix "$TMPDIR/$SUBDIR" 2>/dev/null

# Install to OpenCode's plugin directory
mkdir -p "$(dirname "$TARGET")"
mv "$TMPDIR/$SUBDIR" "$TARGET"

echo "Done. Restart OpenCode to load the plugin."

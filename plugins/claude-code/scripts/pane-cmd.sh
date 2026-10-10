#!/usr/bin/env bash
# Text fallback for /memoir:pane on Claude Code versions that cannot load mods
# (< 2.1.287). The mod in hooks/mod/ answers the command itself on newer
# versions, so this only runs where no pane can be drawn. Prints the store's
# status line and the most recent captures, metrics excluded. No memoir CLI,
# no LLM: git metadata only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STORE="${MEMOIR_STORE:-$(bash "$SCRIPT_DIR/derive-store-path.sh")}"

if [ ! -f "$STORE/.git/HEAD" ]; then
  echo "No memoir store for this folder."
  exit 0
fi

BRANCH=$(sed -n 's#^ref: refs/heads/##p' "$STORE/.git/HEAD" | head -n1)
COUNT=$(head -n1 "$STORE/.git/plugin-statusline-cache" 2>/dev/null | tr -dc '0-9' || true)
COMMITS=$(git -C "$STORE" rev-list --count HEAD 2>/dev/null || echo "?")

echo "memoir: ${BRANCH:-?} · ${COUNT:-?} memories · ${COMMITS} commits"
echo "Recent captures:"
git -C "$STORE" log --format='%h%x09%cr%x09%s' -n 40 2>/dev/null \
  | awk -F'\t' '$3 ~ /^Store / && $3 !~ /^Store metrics\./ {
      sub(/^Store /, "", $3); sub(/ in [^ ]*$/, "", $3);
      printf "  %-14s %s\n", $2, $3
    }' \
  | head -n 10

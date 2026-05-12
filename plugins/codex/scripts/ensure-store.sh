#!/usr/bin/env bash
# Idempotently create the memoir store at $1 with the builtin taxonomy.
#
# This is the single source of truth for store creation across the plugin —
# the SessionStart hook calls it, and command snippets (remember,
# status, ui) call it on every invocation so first-time users don't get
# trapped in the "CLI was missing at SessionStart, store never created,
# every helper now errors with 'Store not found'" failure mode.
#
# Usage:
#   bash ensure-store.sh <STORE_PATH>
#
# Exits:
#   0   — store exists (already, or just created). Prints "created" on
#         stdout iff this call is what materialized it, empty otherwise.
#         Callers gate one-time setup (custom-taxonomy load, store-mode
#         marker write) on that string.
#   1   — `memoir new` failed.
#   2   — missing argument.
#   127 — no memoir CLI available (PATH + uv chain both empty).
#
# Safety: only ever runs `memoir new` when <STORE>/.git/ does NOT exist.
# That guard prevents `StoreService.create_store()` from materializing a
# prolly-tree inside an unrelated git repo if MEMOIR_STORE is misconfigured
# (the documented hazard, see knowledge.technical.store).

set -e

STORE="${1:-}"
if [ -z "$STORE" ]; then
  echo "ensure-store.sh: missing store path argument" >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Standalone callers may run this from a minimal PATH (e.g. skill-driven
# helpers after SessionStart missed store creation). Mirror the same user bin
# bootstrap the other Codex helper entry points use before resolving the CLI.
for p in "$HOME/.local/bin" "$HOME/.cargo/bin" "$HOME/bin" "/usr/local/bin" "/opt/homebrew/bin"; do
  [[ -d "$p" ]] && [[ ":$PATH:" != *":$p:"* ]] && export PATH="$p:$PATH"
done

# shellcheck source=resolve-memoir-cli.sh
source "$SCRIPT_DIR/resolve-memoir-cli.sh"

if [ "${#MEMOIR_CMD_ARGV[@]}" -eq 0 ]; then
  echo "$MEMOIR_INSTALL_HINT" >&2
  exit 127
fi

# Existing store — nothing to do. Empty stdout signals "found existing".
if [ -d "$STORE/.git" ]; then
  exit 0
fi

mkdir -p "$(dirname "$STORE")"

# `memoir new --taxonomy-builtin` writes both the store git repo AND the
# builtin taxonomy. The taxonomy install runs against the store's git
# backend, which only works when the calling process's cwd is itself
# inside a git working tree. In a non-git project folder that's not
# guaranteed, so we cd into a throwaway git-init'd scratch dir first.
#
# Note: no `--no-connect` flag — it was deliberately removed when memoir
# eliminated the global ~/.config/memoir/config.json default (see
# src/memoir/cli/main.py:177). `memoir new` now always behaves as
# "no-connect" and the flag would error.
_scratch=$(mktemp -d -t memoir-scratch.XXXXXX 2>/dev/null || echo "")
if [ -n "$_scratch" ]; then
  git init -q "$_scratch" 2>/dev/null || true
  ( cd "$_scratch" \
    && "${MEMOIR_CMD_ARGV[@]}" new "$STORE" --taxonomy-builtin ) >/dev/null 2>&1
  rc=$?
  rm -rf "$_scratch"
  if [ "$rc" -ne 0 ]; then
    echo "ensure-store.sh: failed to create store at $STORE" >&2
    exit 1
  fi
else
  # mktemp failed — fall back to running from current cwd. May produce a
  # store without a fully loaded taxonomy in non-git folders, but the
  # store itself will be created so subsequent ops can recover.
  "${MEMOIR_CMD_ARGV[@]}" new "$STORE" --taxonomy-builtin >/dev/null 2>&1 || {
    echo "ensure-store.sh: failed to create store at $STORE" >&2
    exit 1
  }
fi

echo "created"

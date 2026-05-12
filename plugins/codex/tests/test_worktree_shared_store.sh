#!/usr/bin/env bash
# Smoke test for the worktree-aware path of the plugin.
#
# Verifies that derive-store-path.sh collapses all linked git worktrees of a
# repository onto the same memoir store (the main worktree's slug), instead
# of producing one store per worktree as it did before the fix.
#
# Usage: bash tests/test_worktree_shared_store.sh
# Requires: git on PATH. Does not require the memoir CLI — the test only
# exercises the shell script and git plumbing.

set -e

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$TEST_DIR/.." && pwd)"
DERIVE="$PLUGIN_ROOT/scripts/derive-store-path.sh"

if [ ! -x "$DERIVE" ] && [ ! -f "$DERIVE" ]; then
  echo "SKIP: $DERIVE not found"
  exit 0
fi

PROJ=$(mktemp -d -t memoir-wt-proj.XXXXXX)
WT=$(mktemp -d -t memoir-wt-link.XXXXXX); rm -rf "$WT"
BARE=$(mktemp -d -t memoir-wt-bare.XXXXXX); rm -rf "$BARE"

cleanup() { rm -rf "$PROJ" "$WT" "$BARE"; }
trap cleanup EXIT

PASS=0
FAIL=0
declare -a FAILURES=()

assert_eq() {
  local description="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    printf '  ✓ %s\n' "$description"
    PASS=$((PASS + 1))
  else
    printf '  ✗ %s\n    expected: %s\n    got:      %s\n' \
      "$description" "$expected" "$actual"
    FAIL=$((FAIL + 1))
    FAILURES+=("$description")
  fi
}

assert_neq() {
  local description="$1" not_expected="$2" actual="$3"
  if [ "$not_expected" != "$actual" ]; then
    printf '  ✓ %s\n' "$description"
    PASS=$((PASS + 1))
  else
    printf '  ✗ %s\n    must not equal: %s\n' "$description" "$not_expected"
    FAIL=$((FAIL + 1))
    FAILURES+=("$description")
  fi
}

assert_not_contains() {
  local description="$1" needle="$2" haystack="$3"
  if printf '%s' "$haystack" | grep -qF "$needle"; then
    printf '  ✗ %s\n    unexpected: %s\n' "$description" "$needle"
    FAIL=$((FAIL + 1))
    FAILURES+=("$description")
  else
    printf '  ✓ %s\n' "$description"
    PASS=$((PASS + 1))
  fi
}

# ---------------------------------------------------------------------------
# Setup: a real git repo plus a linked worktree.
# ---------------------------------------------------------------------------
(
  cd "$PROJ"
  git init -q
  git -c user.email=test@test -c user.name=test commit -q --allow-empty -m init
  git worktree add -q "$WT" -b worktree-test-branch >/dev/null
)

# ---------------------------------------------------------------------------
# Step 1: Main-checkout regression — derived store path matches the slug of
# the repo's `git rev-parse --show-toplevel`. Guards against the new logic
# accidentally changing behavior for non-worktree users.
# ---------------------------------------------------------------------------
echo "Step 1: Main checkout matches pre-fix behavior"
toplevel_main=$(cd "$PROJ" && git rev-parse --show-toplevel)
# realpath -m is GNU-only on Linux; on macOS we fall back via cd-and-pwd just
# like derive-store-path.sh's own resolver does.
if realpath -m "$toplevel_main" >/dev/null 2>&1; then
  toplevel_main_abs=$(realpath -m "$toplevel_main")
else
  toplevel_main_abs=$(cd "$toplevel_main" && pwd)
fi
expected_main_slug=$(printf '%s' "$toplevel_main_abs" | tr '/.' '--')
expected_main_store="$HOME/.memoir/${expected_main_slug}"
A=$(cd "$PROJ" && bash "$DERIVE")
assert_eq "[1.1] derive-store-path.sh from main checkout matches expected slug" \
  "$expected_main_store" "$A"

# ---------------------------------------------------------------------------
# Step 2: The actual fix — main checkout and linked worktree share one store.
# ---------------------------------------------------------------------------
echo
echo "Step 2: Linked worktree collapses onto main checkout's store"
B=$(cd "$WT" && bash "$DERIVE")
assert_eq "[2.1] worktree derives the same store path as the main checkout" "$A" "$B"

# ---------------------------------------------------------------------------
# Step 3: --print-git-root from main checkout returns the toplevel.
# ---------------------------------------------------------------------------
echo
echo "Step 3: --print-git-root from main checkout"
root_main=$(cd "$PROJ" && bash "$DERIVE" --print-git-root)
assert_eq "[3.1] --print-git-root in main checkout equals git toplevel" \
  "$toplevel_main" "$root_main"

# ---------------------------------------------------------------------------
# Step 4: --print-git-root from inside the linked worktree must point at the
# main checkout, NOT the worktree's own toplevel.
# ---------------------------------------------------------------------------
echo
echo "Step 4: --print-git-root from inside a linked worktree"
toplevel_wt=$(cd "$WT" && git rev-parse --show-toplevel)
root_wt=$(cd "$WT" && bash "$DERIVE" --print-git-root)
assert_eq "[4.1] --print-git-root in worktree returns main checkout's toplevel" \
  "$toplevel_main" "$root_wt"
assert_neq "[4.2] --print-git-root in worktree does NOT return its own toplevel" \
  "$toplevel_wt" "$root_wt"

# ---------------------------------------------------------------------------
# Step 5: Bare repo edge case — must not crash, must not leak `(bare)`.
# ---------------------------------------------------------------------------
echo
echo "Step 5: Bare repo edge case"
mkdir -p "$BARE"
( cd "$BARE" && git init --bare -q )
bare_out=$(cd "$BARE" && bash "$DERIVE" 2>&1) || {
  printf '  ✗ [5.1] derive-store-path.sh exited non-zero in bare repo\n    output: %s\n' "$bare_out"
  FAIL=$((FAIL + 1))
  FAILURES+=("[5.1]")
  bare_out=""
}
if [ -n "$bare_out" ]; then
  printf '  ✓ [5.1] derive-store-path.sh exits 0 in bare repo\n'
  PASS=$((PASS + 1))
fi
assert_not_contains "[5.2] bare-repo store path does not leak '(bare)'" "(bare)" "$bare_out"

echo
echo "----"
echo "PASS: $PASS"
echo "FAIL: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf '\nfailed checks:\n'
  for f in "${FAILURES[@]}"; do
    printf '  - %s\n' "$f"
  done
  exit 1
fi

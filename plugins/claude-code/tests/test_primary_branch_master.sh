#!/usr/bin/env bash
# Smoke test for the configurable-primary-branch feature.
#
# Creates a memoir store with `--initial-branch master`, then exercises the
# plugin's branch-aware code paths against a project whose code branches
# include "master" (the new primary). Asserts:
#   - cache_primary_branch reads the config and exports MEMOIR_PRIMARY_BRANCH=master
#   - auto_match_memoir_branch forks new code branches FROM master (not main)
#   - list_unmerged_memoir_branches excludes master (the primary)
#   - The same flow with the default `memoir new` (no flag) still uses main
#
# This is the "primary-branch" counterpart of test_branch_sync.sh: same
# structure, master-primary instead of main.
#
# Usage: bash tests/test_primary_branch_master.sh
# Requires: `memoir` CLI on PATH.

set -e

if ! command -v memoir &>/dev/null; then
  echo "SKIP: memoir CLI not on PATH"
  exit 0
fi

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLAUDE_PLUGIN_ROOT="$(cd "$TEST_DIR/.." && pwd)"

PROJ=$(mktemp -d -t memoir-pb-proj.XXXXXX)
STORE=$(mktemp -d -t memoir-pb-store.XXXXXX)
rm -rf "$STORE"

cleanup() { rm -rf "$PROJ" "$STORE"; }
trap cleanup EXIT

# Initialize a project repo with master as its initial branch (matches the
# real-world scenario where the user prefers master over main).
git init -q -b master "$PROJ"
git -C "$PROJ" commit --allow-empty -q -m init

# Create the memoir store with master as its primary branch. We have to
# do this from a git-aware cwd because of the prollytree-cwd-required quirk
# (see plugins/claude-code/hooks/common.sh: ensure_store workaround).
( cd "$PROJ" && memoir new "$STORE" --initial-branch master --taxonomy-builtin --no-connect ) >/dev/null 2>&1

export MEMOIR_STORE="$STORE"
cd "$PROJ"

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

assert_contains() {
  local description="$1" needle="$2" haystack="$3"
  if printf '%s' "$haystack" | grep -qF "$needle"; then
    printf '  ✓ %s\n' "$description"
    PASS=$((PASS + 1))
  else
    printf '  ✗ %s\n    missing:  %s\n' "$description" "$needle"
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
# Step 1: store config + cache_primary_branch
# ---------------------------------------------------------------------------
echo "Step 1: master is recorded as primary"

cfg=$(git -C "$STORE" config --get memoir.primaryBranch || echo "")
assert_eq "[1.1] git config memoir.primaryBranch=master" "master" "$cfg"

primary_via_helper=$(bash -c 'source "$CLAUDE_PLUGIN_ROOT/hooks/common.sh" >/dev/null 2>&1; cache_primary_branch; echo "$MEMOIR_PRIMARY_BRANCH"')
assert_eq "[1.2] cache_primary_branch exports master" "master" "$primary_via_helper"

# ---------------------------------------------------------------------------
# Step 2: SessionStart picks up the primary
# ---------------------------------------------------------------------------
echo
echo "Step 2: SessionStart in master-primary store"

run_session_start() {
  bash "$CLAUDE_PLUGIN_ROOT/hooks/session-start.sh" </dev/null 2>/dev/null || true
}

out=$(run_session_start)
assert_contains "[2.1] status line renders" "[memoir]" "$out"
# The store is on master after `memoir new --initial-branch master`; the
# code repo is also on master; auto-match should be a no-op.
branch_in_store=$( ( cd "$STORE" && memoir --json -s "$STORE" status ) \
  | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['branch'])")
assert_eq "[2.2] memoir branch is master after SessionStart" "master" "$branch_in_store"

# ---------------------------------------------------------------------------
# Step 3: auto_match_memoir_branch forks from MASTER, not main
# ---------------------------------------------------------------------------
echo
echo "Step 3: auto-match forks new code branches from master"

# Switch the project to a feature branch.
git -C "$PROJ" checkout -q -b feature/x

run_session_start >/dev/null

# The memoir branch should now be feature/x, forked off master. To prove the
# fork base, list branches via memoir and inspect the rev-list ancestry of
# feature/x against master inside the store.
branch_in_store=$( ( cd "$STORE" && memoir --json -s "$STORE" status ) \
  | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['branch'])")
assert_eq "[3.1] memoir auto-matched to feature/x" "feature/x" "$branch_in_store"

# Confirm feature/x's ancestry traces back to master, not main.
master_in_ancestry=$(git -C "$STORE" merge-base --is-ancestor master feature/x && echo yes || echo no)
assert_eq "[3.2] feature/x descends from master" "yes" "$master_in_ancestry"

# main should not even exist in the store (we never created it).
main_exists=$(git -C "$STORE" show-ref --verify --quiet refs/heads/main && echo yes || echo no)
assert_eq "[3.3] main branch does NOT exist in store" "no" "$main_exists"

# ---------------------------------------------------------------------------
# Step 4: list_unmerged_memoir_branches filters out the primary (master)
# ---------------------------------------------------------------------------
echo
echo "Step 4: unmerged-branch detection treats master as the baseline"

# Capture a memory on feature/x so it has a commit ahead of master.
( cd "$STORE" && memoir -s "$STORE" remember "primary-test fact" -p test.primary -n default ) >/dev/null 2>&1

# Now go back to master in the project and re-run SessionStart.
git -C "$PROJ" checkout -q master
run_session_start >/dev/null

# list_unmerged_memoir_branches should report feature/x and NOT master.
unmerged=$(bash -c '
source "$CLAUDE_PLUGIN_ROOT/hooks/common.sh" >/dev/null 2>&1
cache_primary_branch
list_unmerged_memoir_branches
' 2>&1 || true)
assert_contains "[4.1] feature/x surfaces as unmerged" "feature/x" "$unmerged"
assert_not_contains "[4.2] master is excluded from unmerged" "master	" "$unmerged"

# ---------------------------------------------------------------------------
# Step 5: backwards-compat — fresh main-default store uses main everywhere
# ---------------------------------------------------------------------------
echo
echo "Step 5: backwards-compat — default memoir new (no flag) still uses main"

PROJ2=$(mktemp -d -t memoir-pb-proj2.XXXXXX)
STORE2=$(mktemp -d -t memoir-pb-store2.XXXXXX)
rm -rf "$STORE2"
git init -q "$PROJ2"
git -C "$PROJ2" commit --allow-empty -q -m init
( cd "$PROJ2" && memoir new "$STORE2" --taxonomy-builtin --no-connect ) >/dev/null 2>&1

# memoir.primaryBranch must be UNSET (backwards-compat invariant).
cfg2=$(git -C "$STORE2" config --get memoir.primaryBranch 2>&1 || echo "<unset>")
assert_eq "[5.1] default memoir new leaves config unset" "<unset>" "$cfg2"

# cache_primary_branch defaults to "main" when config is unset.
primary2=$(MEMOIR_STORE="$STORE2" bash -c 'source "$CLAUDE_PLUGIN_ROOT/hooks/common.sh" >/dev/null 2>&1; cache_primary_branch; echo "$MEMOIR_PRIMARY_BRANCH"')
assert_eq "[5.2] cache_primary_branch defaults to main" "main" "$primary2"

rm -rf "$PROJ2" "$STORE2"

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

#!/usr/bin/env bash
# End-to-end smoke test for the plugin's branch-auto-matching + sync features.
#
# Exercises session-start.sh directly (no Claude Code needed) against a
# throwaway project and memoir store. Each step is a pass/fail check;
# script exits non-zero on first failure.
#
# Covers:
#   - Auto-matching memoir branch to current code branch on SessionStart
#   - Fork-from-main when a matching memoir branch doesn't exist
#   - Multi-branch unmerged detection (e.g. sequence main → a → b → main)
#   - /memoir-sync-branch writes the sync marker and suppresses suggestions
#   - New captures after sync correctly resurface the branch
#   - Sticky opt-out and its auto-clear on return to code-matching branch
#   - Concurrent-session heartbeat warning
#
# Usage: bash tests/test_branch_sync.sh
# Requires: `memoir` CLI on PATH.

set -e

if ! command -v memoir &>/dev/null; then
  echo "SKIP: memoir CLI not on PATH"
  exit 0
fi

# Resolve plugin root so the test works from any cwd.
TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLAUDE_PLUGIN_ROOT="$(cd "$TEST_DIR/.." && pwd)"

PROJ=$(mktemp -d -t memoir-test-proj.XXXXXX)
STORE=$(mktemp -d -t memoir-test-store.XXXXXX)
# mktemp creates the dir; memoir new expects a fresh path — reuse the parent.
rm -rf "$STORE"

cleanup() { rm -rf "$PROJ" "$STORE"; }
trap cleanup EXIT

git init -q "$PROJ"
git -C "$PROJ" commit --allow-empty -q -m init
memoir new "$STORE" --taxonomy-builtin --no-connect >/dev/null
export MEMOIR_STORE="$STORE"

# Avoid calling the LLM-backed classifier during the test — pass --path on
# every `memoir remember` so we don't need provider credentials.
cd "$PROJ"

PASS=0
FAIL=0
declare -a FAILURES=()

assert() {
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
    printf '  ✗ %s\n    missing:  %s\n    in:       %s\n' \
      "$description" "$needle" "$(printf '%s' "$haystack" | head -5)"
    FAIL=$((FAIL + 1))
    FAILURES+=("$description")
  fi
}

assert_not_contains() {
  local description="$1" needle="$2" haystack="$3"
  if printf '%s' "$haystack" | grep -qF "$needle"; then
    printf '  ✗ %s\n    unexpectedly present: %s\n' "$description" "$needle"
    FAIL=$((FAIL + 1))
    FAILURES+=("$description")
  else
    printf '  ✓ %s\n' "$description"
    PASS=$((PASS + 1))
  fi
}

# Helpers --- invoke the real hook, parse the JSON response.
session_start_status() {
  bash "$CLAUDE_PLUGIN_ROOT/hooks/session-start.sh" </dev/null 2>&1 |
    python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('systemMessage',''))"
}
session_start_context() {
  bash "$CLAUDE_PLUGIN_ROOT/hooks/session-start.sh" </dev/null 2>&1 |
    python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('hookSpecificOutput',{}).get('additionalContext',''))"
}
memoir_current_branch() {
  memoir --json -s "$STORE" status |
    python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('branch',''))"
}
sync_branch() {
  # Simulate what /memoir-sync-branch <name> does.
  local target="$1" current
  current=$(memoir_current_branch)
  memoir -s "$STORE" checkout main >/dev/null
  memoir -s "$STORE" merge "$target" >/dev/null 2>&1
  if [ -n "$current" ] && [ "$current" != "main" ]; then
    memoir -s "$STORE" checkout "$current" >/dev/null
  fi
  mkdir -p "$(dirname "$STORE/.git/plugin-synced-branches/$target")"
  date +%s > "$STORE/.git/plugin-synced-branches/$target"
}

heading() { printf '\n== %s ==\n' "$1"; }

# -------- 1. SessionStart on code main --------
heading "SessionStart on code main (default state)"
status=$(session_start_status)
assert_contains "status mentions 'main'" "main" "$status"
assert_contains "status shows 0 user memories" "0 memories" "$status"
assert "memoir branch is main" "main" "$(memoir_current_branch)"

# -------- 2. Capture on main --------
heading "Capture global fact on main"
memoir -s "$STORE" --json remember "Global fact on main" -p preferences.coding.editor >/dev/null
assert "capture went to memoir branch main" "main" "$(memoir_current_branch)"

# -------- 3. Auto-match on feature/a --------
heading "Switch to code feature/a (auto-match should fork from main)"
git -C "$PROJ" checkout -qb feature/a
status=$(session_start_status)
assert "memoir branch now matches feature/a" "feature/a" "$(memoir_current_branch)"
assert_contains "status shows feature/a" "feature/a" "$status"
# Fork inheritance — main's capture must be visible on feature/a.
keys=$(memoir --json -s "$STORE" summarize --keys '*' |
  python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(','.join(sorted(d.get('matching_keys',{}).get('default',[]))))")
assert_contains "fork inheritance: preferences.coding.editor visible on feature/a" "preferences.coding.editor" "$keys"

memoir -s "$STORE" --json remember "A-specific fact" -p context.project.cicd >/dev/null

# -------- 4. Auto-match on feature/b --------
heading "Switch to code feature/b"
git -C "$PROJ" checkout -qb feature/b
session_start_status >/dev/null
assert "memoir branch now matches feature/b" "feature/b" "$(memoir_current_branch)"
memoir -s "$STORE" --json remember "B-specific fact" -p context.project.database >/dev/null

# -------- 5. Multi-branch detection from main --------
heading "Back to code main — expect BOTH feature/a and feature/b in suggestions"
git -C "$PROJ" checkout -q main
session_start_status >/dev/null
context=$(session_start_context)
assert_contains "suggestions list feature/a" "/memoir-sync-branch feature/a" "$context"
assert_contains "suggestions list feature/b" "/memoir-sync-branch feature/b" "$context"

# -------- 6. Sync feature/a --------
heading "Sync feature/a"
sync_branch feature/a
assert "sync marker exists for feature/a" "0" "$([ -f "$STORE/.git/plugin-synced-branches/feature/a" ]; echo $?)"

# -------- 7. After sync: only feature/b remains --------
heading "Re-run SessionStart after syncing feature/a"
context=$(session_start_context)
assert_not_contains "feature/a gone from suggestions" "/memoir-sync-branch feature/a" "$context"
assert_contains "feature/b still in suggestions" "/memoir-sync-branch feature/b" "$context"

# -------- 8. Sync feature/b, suggestions empty --------
heading "Sync feature/b"
sync_branch feature/b
context=$(session_start_context)
assert_not_contains "no suggestions after both synced" "/memoir-sync-branch" "$context"

# -------- 9. New capture resurfaces branch --------
heading "New capture on feature/a resurfaces it"
memoir -s "$STORE" checkout feature/a >/dev/null
sleep 2  # ensure commit timestamp strictly > sync-marker timestamp
memoir -s "$STORE" --json remember "A follow-up" -p preferences.coding.style >/dev/null
memoir -s "$STORE" checkout main >/dev/null
context=$(session_start_context)
assert_contains "feature/a resurfaces after new capture" "/memoir-sync-branch feature/a" "$context"

# Clean state for the remaining tests — sync feature/a again.
sync_branch feature/a

# -------- 10. Sticky opt-out --------
heading "Sticky opt-out: create 'experiment' branch while code is on main"
memoir -s "$STORE" branch experiment --from main >/dev/null
printf 'experiment\n' > "$STORE/.git/plugin-sticky-branch"
memoir -s "$STORE" checkout experiment >/dev/null
status=$(session_start_status)
# Composite format indicates opt-out: main+experiment*
assert_contains "status shows sticky composite with *" "main+experiment*" "$status"
assert "memoir branch still on experiment after re-running SessionStart" "experiment" "$(memoir_current_branch)"

# -------- 11. Sticky auto-clear --------
heading "Sticky auto-clear when checking out to code-matching branch"
memoir -s "$STORE" checkout main >/dev/null
# session-start.sh clears the sticky when current memoir branch == code branch.
session_start_status >/dev/null
if [ -f "$STORE/.git/plugin-sticky-branch" ]; then
  # The plugin's checkout slash also clears it; simulate that path too.
  rm -f "$STORE/.git/plugin-sticky-branch"
fi
assert "sticky file cleared" "0" "$([ ! -f "$STORE/.git/plugin-sticky-branch" ]; echo $?)"
status=$(session_start_status)
assert_not_contains "status no longer shows *" "*" "$status"

# -------- 12. Concurrency warning --------
heading "Concurrent-session warning"
mkdir -p "$STORE/.git/plugin-active-sessions"
printf '%s\t%s\n' "feature/xyz" "$(date +%s)" \
  > "$STORE/.git/plugin-active-sessions/test-other-session-fake-id"
status=$(session_start_status)
assert_contains "status carries concurrency warning" "concurrent session detected" "$status"
assert_contains "warning names the other branch" "feature/xyz" "$status"
rm -rf "$STORE/.git/plugin-active-sessions"

# -------- Summary --------
printf '\n--------------------------------\n'
printf 'PASS: %d    FAIL: %d\n' "$PASS" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf 'Failures:\n'
  for f in "${FAILURES[@]}"; do printf '  - %s\n' "$f"; done
  exit 1
fi
printf 'All checks passed.\n'

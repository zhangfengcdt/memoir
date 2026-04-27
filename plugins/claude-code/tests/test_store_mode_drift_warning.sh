#!/usr/bin/env bash
# Smoke test for the store-mode drift warning (warning-only guardrail).
#
# Exercises session-start.sh against a project that flips between non-git and
# git states. Asserts the warning block surfaces on drift, stays silent on
# match, and that captures continue to work either way.
#
# Covers:
#   - non-git → git transition: warning fires, normal output still present
#   - git → non-git transition: warning fires (symmetric coverage)
#   - backfill case: store predates the marker → first observation backfills,
#     no warning
#   - suppression: after manual marker overwrite, warning stops firing
#
# Usage: bash tests/test_store_mode_drift_warning.sh
# Requires: `memoir` CLI on PATH.

set -e

if ! command -v memoir &>/dev/null; then
  echo "SKIP: memoir CLI not on PATH"
  exit 0
fi

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLAUDE_PLUGIN_ROOT="$(cd "$TEST_DIR/.." && pwd)"

PROJ=$(mktemp -d -t memoir-test-drift-proj.XXXXXX)
STORE=$(mktemp -d -t memoir-test-drift-store.XXXXXX)
rm -rf "$STORE"

cleanup() { rm -rf "$PROJ" "$STORE"; }
trap cleanup EXIT

memoir new "$STORE" --taxonomy-builtin --no-connect >/dev/null 2>&1
export MEMOIR_STORE="$STORE"

cd "$PROJ"

PASS=0
FAIL=0
declare -a FAILURES=()

assert_contains() {
  local description="$1" needle="$2" haystack="$3"
  if printf '%s' "$haystack" | grep -qF "$needle"; then
    printf '  ✓ %s\n' "$description"
    PASS=$((PASS + 1))
  else
    printf '  ✗ %s\n    missing:  %s\n    in:       %s\n' \
      "$description" "$needle" "$(printf '%s' "$haystack" | head -10)"
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

run_session_start() {
  bash "$CLAUDE_PLUGIN_ROOT/hooks/session-start.sh" </dev/null 2>/dev/null || true
}

marker_path="$STORE/.git/plugin-store-mode"

echo "Case 1: non-git → git transition"
# Fresh non-git folder. First run records the marker as non-git.
out=$(run_session_start)
assert_contains "[1.1] status line renders" "[memoir]" "$out"
assert_eq "[1.2] marker recorded as non-git" "non-git" "$(cat "$marker_path" 2>/dev/null || echo '')"
assert_not_contains "[1.3] no drift warning on first run" "store mode drift" "$out"

# Now git init → drift on next session-start.
git init -q "$PROJ"
git -C "$PROJ" commit --allow-empty -q -m init
out=$(run_session_start)
assert_contains "[1.4] drift warning fires after git init" "store mode drift" "$out"
assert_contains "[1.5] warning names recorded mode" "non-git\` mode" "$out"
assert_contains "[1.6] warning names current mode" "now \`git\`" "$out"
assert_contains "[1.7] status line still renders alongside warning" "[memoir]" "$out"

# Captures still work — write a memory and read it back.
memoir -s "$STORE" remember "drift test fact" -p test.drift -n default >/dev/null 2>&1
got=$(memoir --json -s "$STORE" get test.drift -n default 2>/dev/null | python3 -c "import json,sys; obj=json.loads(sys.stdin.read()); print(obj['items'][0]['value']['content'])")
assert_eq "[1.8] capture still works during drift" "drift test fact" "$got"

echo
echo "Case 2: suppression after marker overwrite"
echo git > "$marker_path"
out=$(run_session_start)
assert_not_contains "[2.1] no warning after marker matches current mode" "store mode drift" "$out"

echo
echo "Case 3: git → non-git transition (symmetric)"
rm -rf "$PROJ/.git"
out=$(run_session_start)
assert_contains "[3.1] drift warning fires after rm -rf .git" "store mode drift" "$out"
assert_contains "[3.2] warning names recorded git mode" "git\` mode" "$out"

echo
echo "Case 4: backfill on store with no marker"
# Reset: fresh store, fresh project, no marker.
cd /tmp
rm -rf "$STORE" "$PROJ"
mkdir -p "$PROJ"
memoir new "$STORE" --taxonomy-builtin --no-connect >/dev/null 2>&1
cd "$PROJ"
# Simulate an old store without the marker by deleting it after `memoir new`.
rm -f "$marker_path"
out=$(run_session_start)
assert_eq "[4.1] backfill writes current mode" "non-git" "$(cat "$marker_path" 2>/dev/null || echo '')"
assert_not_contains "[4.2] backfill emits no warning" "store mode drift" "$out"

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

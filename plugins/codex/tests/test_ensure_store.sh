#!/usr/bin/env bash
# Smoke test for scripts/ensure-store.sh — the command-snippet store-bootstrap
# helper. Covers the three branches a first-time user could hit:
#
#   1. memoir CLI unavailable        → exit 127, install hint on stderr.
#   2. store path already initialised → exit 0, empty stdout.
#   3. store path missing             → exit 0, "created" on stdout, store
#                                       directory now contains .git.

set -e

if ! command -v memoir &>/dev/null; then
  echo "SKIP: memoir CLI not on PATH"
  exit 0
fi

MEMOIR_BIN=$(command -v memoir)

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "$TEST_DIR/.." && pwd)"
HELPER="$PLUGIN_ROOT/scripts/ensure-store.sh"

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

# ---------------------------------------------------------------------------
# Case 1: missing CLI → exit 127 with install hint.
# ---------------------------------------------------------------------------
echo "Case 1: missing CLI"
TMP_STORE=$(mktemp -d -t memoir-ensure-test.XXXXXX)
rm -rf "$TMP_STORE"  # helper creates it
TMP_HOME=$(mktemp -d -t memoir-ensure-home.XXXXXX)

# Filter memoir / uv / uvx out of PATH so the resolver sees nothing.
NO_CLI_PATH=""
for p in $(echo "$PATH" | tr ':' '\n'); do
  [ -z "$p" ] && continue
  [ -x "$p/memoir" ] && continue
  [ -x "$p/uv" ] && continue
  [ -x "$p/uvx" ] && continue
  NO_CLI_PATH="${NO_CLI_PATH}${p}:"
done
NO_CLI_PATH="${NO_CLI_PATH%:}"

set +e
out=$(env -i PATH="$NO_CLI_PATH" HOME="$TMP_HOME" bash "$HELPER" "$TMP_STORE" 2>&1)
rc=$?
set -e
assert_eq "missing CLI exits 127" "127" "$rc"
case "$out" in
  *"memoir CLI not found"*) printf '  ✓ install hint surfaced\n'; PASS=$((PASS + 1)) ;;
  *)                         printf '  ✗ install hint missing\n    got: %s\n' "$out"; FAIL=$((FAIL + 1)); FAILURES+=("install hint") ;;
esac
[ ! -d "$TMP_STORE" ] && printf '  ✓ no store materialized when CLI missing\n' && PASS=$((PASS + 1)) \
  || { printf '  ✗ store unexpectedly created at %s\n' "$TMP_STORE"; FAIL=$((FAIL + 1)); FAILURES+=("no-create on missing CLI"); rm -rf "$TMP_STORE"; }
rm -rf "$TMP_HOME"

# ---------------------------------------------------------------------------
# Case 2: fresh store creation → exit 0, "created" on stdout, .git present.
# ---------------------------------------------------------------------------
echo "Case 2: fresh creation"
TMP_STORE_EXISTING=$(mktemp -d -t memoir-ensure-test.XXXXXX)
rm -rf "$TMP_STORE_EXISTING"

set +e
out=$(bash "$HELPER" "$TMP_STORE_EXISTING" 2>&1)
rc=$?
set -e

assert_eq "fresh creation exits 0" "0" "$rc"
assert_eq "fresh creation prints 'created'" "created" "$out"
[ -d "$TMP_STORE_EXISTING/.git" ] && printf '  ✓ store .git directory present\n' && PASS=$((PASS + 1)) \
  || { printf '  ✗ store .git directory missing at %s\n' "$TMP_STORE_EXISTING"; FAIL=$((FAIL + 1)); FAILURES+=("missing .git after create"); }

# ---------------------------------------------------------------------------
# Case 3: helper bootstraps a memoir binary staged only in ~/.local/bin.
# ---------------------------------------------------------------------------
echo "Case 3: bootstrap from ~/.local/bin when PATH is minimal"
TMP_HOME=$(mktemp -d -t memoir-ensure-home.XXXXXX)
TMP_STORE=$(mktemp -d -t memoir-ensure-test.XXXXXX)
rm -rf "$TMP_STORE"
mkdir -p "$TMP_HOME/.local/bin"
ln -s "$MEMOIR_BIN" "$TMP_HOME/.local/bin/memoir"

set +e
out=$(env -i PATH="/usr/bin:/bin" HOME="$TMP_HOME" bash "$HELPER" "$TMP_STORE" 2>&1)
rc=$?
set -e

assert_eq "minimal PATH + ~/.local/bin memoir exits 0" "0" "$rc"
assert_eq "minimal PATH + ~/.local/bin memoir prints 'created'" "created" "$out"
[ -d "$TMP_STORE/.git" ] && printf '  ✓ ~/.local/bin bootstrap created store\n' && PASS=$((PASS + 1)) \
  || { printf '  ✗ ~/.local/bin bootstrap did not create %s\n' "$TMP_STORE"; FAIL=$((FAIL + 1)); FAILURES+=("bootstrap from ~/.local/bin"); }

rm -rf "$TMP_HOME" "$TMP_STORE"

# ---------------------------------------------------------------------------
# Case 4: idempotent re-call → exit 0, empty stdout (no second creation).
# ---------------------------------------------------------------------------
echo "Case 4: idempotent re-call on existing store"
set +e
out=$(bash "$HELPER" "$TMP_STORE_EXISTING" 2>&1)
rc=$?
set -e

assert_eq "re-call exits 0" "0" "$rc"
assert_eq "re-call prints nothing (existing store)" "" "$out"

rm -rf "$TMP_STORE_EXISTING"

# ---------------------------------------------------------------------------
# Case 5: missing argument → exit 2.
# ---------------------------------------------------------------------------
echo "Case 5: missing argument"
set +e
bash "$HELPER" >/dev/null 2>&1
rc=$?
set -e
assert_eq "missing arg exits 2" "2" "$rc"

# ---------------------------------------------------------------------------
echo
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  printf '\nFailures:\n'
  for f in "${FAILURES[@]}"; do
    printf '  - %s\n' "$f"
  done
  exit 1
fi

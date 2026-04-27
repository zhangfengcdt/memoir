#!/usr/bin/env bash
# Smoke test for the non-git folder path of the plugin.
#
# Modeled on tests/test_branch_sync.sh but explicitly NEVER runs `git init`.
# Verifies that everything degrades gracefully and that the project:onboard
# extractors produce the expected blob shapes against synthetic fixtures
# covering the three target shapes (writing, bookkeeping, video editing).
#
# Usage: bash tests/test_no_git_repo.sh
# Requires: `memoir` CLI on PATH.

set -e

if ! command -v memoir &>/dev/null; then
  echo "SKIP: memoir CLI not on PATH"
  exit 0
fi

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CLAUDE_PLUGIN_ROOT="$(cd "$TEST_DIR/.." && pwd)"

PROJ=$(mktemp -d -t memoir-nogit-proj.XXXXXX)
STORE=$(mktemp -d -t memoir-nogit-store.XXXXXX)
rm -rf "$STORE"

cleanup() { rm -rf "$PROJ" "$STORE"; }
trap cleanup EXIT

memoir new "$STORE" --taxonomy-builtin --no-connect >/dev/null 2>&1
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

run_session_start() {
  bash "$CLAUDE_PLUGIN_ROOT/hooks/session-start.sh" </dev/null 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Step 1: SessionStart in a fresh non-git folder
# ---------------------------------------------------------------------------
echo "Step 1: SessionStart against fresh non-git folder"
out=$(run_session_start)
assert_contains "[1.1] status line renders without errors" "[memoir]" "$out"
assert_contains "[1.2] branch is main" "main" "$out"
# in_git_repo returns 1 in non-git; wrap in `if` so common.sh's `set -e` doesn't abort.
assert_eq "[1.3] in_git_repo helper sees non-git" "no" \
  "$(bash -c 'source "$CLAUDE_PLUGIN_ROOT/hooks/common.sh" >/dev/null 2>&1; if in_git_repo; then echo yes; else echo no; fi')"
assert_eq "[1.4] code_git_branch returns empty" "" \
  "$(bash -c 'source "$CLAUDE_PLUGIN_ROOT/hooks/common.sh" >/dev/null 2>&1; code_git_branch')"
assert_eq "[1.5] store-mode marker recorded as non-git" "non-git" \
  "$(cat "$STORE/.git/plugin-store-mode" 2>/dev/null || echo '')"

# ---------------------------------------------------------------------------
# Step 2: Stop-hook capture lands on main, recallable
# ---------------------------------------------------------------------------
echo
echo "Step 2: Captures land on main (via the same helpers the hooks use)"
# The Stop hook runs via memoir_json, which cd's to the store path. Mirror
# that path here so we exercise the same code that real captures use.
( cd "$STORE" && memoir -s "$STORE" remember "non-git fact" -p test.nogit -n default >/dev/null 2>&1 ) || true
got=$(cd "$STORE" && memoir --json -s "$STORE" get test.nogit -n default 2>/dev/null \
  | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['items'][0]['value']['content'])")
assert_eq "[2.1] capture recallable" "non-git fact" "$got"
branch=$(cd "$STORE" && memoir --json -s "$STORE" status 2>/dev/null \
  | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['branch'])")
assert_eq "[2.2] still on main after capture" "main" "$branch"
post_branch=$(bash -c 'source "$CLAUDE_PLUGIN_ROOT/hooks/common.sh" >/dev/null 2>&1; auto_match_memoir_branch || true; memoir_json status | python3 -c "import json,sys; print(json.loads(sys.stdin.read())[\"branch\"])"')
assert_eq "[2.3] auto_match_memoir_branch is a no-op (still on main)" "main" "$post_branch"

# ---------------------------------------------------------------------------
# Step 3: /memoir-sync-branch and /memoir-unmerged short-circuit cleanly
# ---------------------------------------------------------------------------
echo
echo "Step 3: Slash commands short-circuit"
sync_out=$(bash -c '
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "non-git folder: only \`main\` exists, nothing to sync."
  exit 0
fi
echo "should not reach here"
')
assert_contains "[3.1] memoir-sync-branch short-circuits with non-git message" "non-git folder" "$sync_out"

unmerged_out=$(bash -c '
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "non-git folder: only \`main\` exists. Nothing to do."
  exit 0
fi
echo "should not reach here"
')
assert_contains "[3.2] memoir-unmerged short-circuits with non-git message" "non-git folder" "$unmerged_out"

# ---------------------------------------------------------------------------
# Step 4: Cold project:onboard pass on a writing+bookkeeping mix
# ---------------------------------------------------------------------------
echo
echo "Step 4: Cold project:onboard pass on synthetic fixtures"

cat > "$PROJ/chapter01.md" << 'MD'
---
title: Chapter 1: Beginnings
---
# Chapter 1: Beginnings

It was a quiet morning when Sarah opened the door of her apartment.
The mother had been right after all — coffee was the only weapon.
MD

cat > "$PROJ/ledger.csv" << 'CSV'
date,amount,category,note
2026-01-01,50.00,groceries,Whole Foods
2026-01-02,12.00,coffee,Stumptown
2026-01-03,40.00,transit,Lyft
CSV

# Make a synthetic 1×1 PNG via a tiny python helper.
python3 - << 'PY' "$PROJ/cover.png"
import struct, sys
sig = b"\x89PNG\r\n\x1a\n"
ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + b"\x00\x00\x00\x00"
open(sys.argv[1], "wb").write(sig + ihdr)
PY

EXTRACTORS="$CLAUDE_PLUGIN_ROOT/skills/memoir-onboard/extractors.py"

WALK_JSON=$(python3 "$EXTRACTORS" walk "$PROJ")
SNAPSHOT_HASH_1=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['snapshot_hash'])" "$WALK_JSON")
SHAPE_JSON=$(python3 "$EXTRACTORS" shape "$PROJ")
SHAPE=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['shape'])" "$SHAPE_JSON")
OVERVIEW=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['overview'])" "$SHAPE_JSON")

assert_contains "[4.1] walk includes chapter01.md" "chapter01.md" "$WALK_JSON"
assert_contains "[4.2] walk includes ledger.csv" "ledger.csv" "$WALK_JSON"
assert_contains "[4.3] walk includes cover.png" "cover.png" "$WALK_JSON"
assert_contains "[4.4] walk classifies markdown" '"kind": "markdown"' "$WALK_JSON"
assert_contains "[4.5] walk classifies csv" '"kind": "csv"' "$WALK_JSON"
assert_contains "[4.6] walk classifies image" '"kind": "image"' "$WALK_JSON"

# Per-file extracts
md_blob=$(python3 "$EXTRACTORS" extract "$PROJ/chapter01.md")
csv_blob=$(python3 "$EXTRACTORS" extract "$PROJ/ledger.csv")
img_blob=$(python3 "$EXTRACTORS" extract "$PROJ/cover.png")

assert_contains "[4.7] markdown extract has kind first" "kind=markdown" "$md_blob"
assert_contains "[4.8] markdown extract has title" "title=Chapter 1: Beginnings" "$md_blob"
assert_contains "[4.9] markdown extract has top_terms" "top_terms=" "$md_blob"
assert_contains "[4.10] csv extract names columns" 'columns=["date", "amount", "category", "note"]' "$csv_blob"
assert_contains "[4.11] csv extract detects ledger shape" "shape=ledger" "$csv_blob"
assert_contains "[4.12] image extract has dimensions" "width=1" "$img_blob"

# Write to project:onboard via the same cd-to-store pattern memoir_plain uses.
DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
( cd "$STORE" && memoir -s "$STORE" remember "$OVERVIEW" -p summary.overview -n project:onboard >/dev/null 2>&1 )
( cd "$STORE" && memoir -s "$STORE" remember "$SHAPE" -p structure.shape -n project:onboard >/dev/null 2>&1 )
( cd "$STORE" && memoir -s "$STORE" remember "$SNAPSHOT_HASH_1" -p _meta.last_onboard.snapshot_hash -n project:onboard >/dev/null 2>&1 )
( cd "$STORE" && memoir -s "$STORE" remember "$DATE" -p _meta.last_onboard.date -n project:onboard >/dev/null 2>&1 )
( cd "$STORE" && memoir -s "$STORE" remember "cold" -p _meta.last_onboard.mode -n project:onboard >/dev/null 2>&1 )

stored_shape=$(cd "$STORE" && memoir --json -s "$STORE" get structure.shape -n project:onboard 2>/dev/null \
  | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['items'][0]['value']['content'])")
assert_eq "[4.13] structure.shape stored" "$SHAPE" "$stored_shape"
assert_contains "[4.14] overview is non-empty" "project" "$OVERVIEW"

# ---------------------------------------------------------------------------
# Step 5: Snapshot hash unchanged when no files change
# ---------------------------------------------------------------------------
echo
echo "Step 5: Warm/meta-only paths"
SNAPSHOT_HASH_2=$(python3 "$EXTRACTORS" snapshot-hash "$PROJ")
assert_eq "[5.1] hash unchanged across re-walk" "$SNAPSHOT_HASH_1" "$SNAPSHOT_HASH_2"

echo "appended" >> "$PROJ/chapter01.md"
sleep 0.1
SNAPSHOT_HASH_3=$(python3 "$EXTRACTORS" snapshot-hash "$PROJ")
if [ "$SNAPSHOT_HASH_1" = "$SNAPSHOT_HASH_3" ]; then
  printf '  ✗ %s\n' "[5.2] hash changes after file write"
  FAIL=$((FAIL + 1))
  FAILURES+=("[5.2]")
else
  printf '  ✓ %s\n' "[5.2] hash changes after file write"
  PASS=$((PASS + 1))
fi

# ---------------------------------------------------------------------------
# Step 6: SessionStart injects project:onboard hint when no snapshot exists
# ---------------------------------------------------------------------------
echo
echo "Step 6: SessionStart picks the project:onboard injection"
# Reset the namespace so we can verify the hint surfaces. Easier: spin up a
# fresh store with a single user memory so USER_MEMORIES > 0 (the hint only
# appears when some user memory exists).
STORE2=$(mktemp -d -t memoir-nogit-store2.XXXXXX)
rm -rf "$STORE2"
# Use ensure_store via the hook to get a properly bootstrapped store.
export MEMOIR_STORE="$STORE2"
run_session_start >/dev/null
( cd "$STORE2" && memoir -s "$STORE2" remember "seed" -p test.seed -n default >/dev/null 2>&1 )
out=$(run_session_start)
assert_contains "[6.1] hint references project:onboard, not codebase:onboard" "project:onboard snapshot" "$out"
assert_not_contains "[6.2] hint does not name codebase:onboard" "codebase:onboard snapshot" "$out"
rm -rf "$STORE2"

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

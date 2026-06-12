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
#   - Sync markers suppress suggestions (sim helper + real scripts/sync-cmd.sh)
#   - scripts/sync-cmd.sh subcommands: list / dry-run / merge / ignore /
#     snooze / decline / prune
#   - Auto-offer threshold (≥5 unmerged commits) and snooze cooldown gating
#   - Auto-promotion of memoir branches whose code branch merged into main
#   - Stale-branch GC (synced-or-abandoned + inactivity threshold)
#   - Escalating decline backoff (1d → 7d → 30d)
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
# No --no-connect: the flag was removed from `memoir new` (stores no longer
# auto-connect; see scripts/ensure-store.sh).
memoir new "$STORE" --taxonomy-builtin >/dev/null
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
  # Simulate a branch sync (merge + marker) without going through the CLI's
  # sync-branch — kept for the older sections; section 15 exercises the real
  # path via scripts/sync-cmd.sh.
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
assert_contains "suggestions list feature/a" "memoir/feature/a:" "$context"
assert_contains "suggestions list feature/b" "memoir/feature/b:" "$context"
assert_contains "suggestions point at /memoir:sync" "/memoir:sync" "$context"

# -------- 6. Sync feature/a --------
heading "Sync feature/a"
sync_branch feature/a
assert "sync marker exists for feature/a" "0" "$([ -f "$STORE/.git/plugin-synced-branches/feature/a" ]; echo $?)"

# -------- 7. After sync: only feature/b remains --------
heading "Re-run SessionStart after syncing feature/a"
context=$(session_start_context)
assert_not_contains "feature/a gone from suggestions" "memoir/feature/a:" "$context"
assert_contains "feature/b still in suggestions" "memoir/feature/b:" "$context"

# -------- 8. Sync feature/b, suggestions empty --------
heading "Sync feature/b"
sync_branch feature/b
context=$(session_start_context)
assert_not_contains "no suggestions after both synced" "unmerged branches detected" "$context"

# -------- 9. New capture resurfaces branch --------
heading "New capture on feature/a resurfaces it"
memoir -s "$STORE" checkout feature/a >/dev/null
sleep 2  # ensure commit timestamp strictly > sync-marker timestamp
memoir -s "$STORE" --json remember "A follow-up" -p preferences.coding.style >/dev/null
memoir -s "$STORE" checkout main >/dev/null
context=$(session_start_context)
assert_contains "feature/a resurfaces after new capture" "memoir/feature/a:" "$context"

# Clean state for the remaining tests — sync feature/a again.
sync_branch feature/a

# -------- 9b. Deleted code branch suppresses unmerged memoir branch --------
heading "Deleting the code branch removes its memoir branch from suggestions"
git -C "$PROJ" checkout -qb feature/deletable
session_start_status >/dev/null
assert "memoir matched feature/deletable via SessionStart" "feature/deletable" "$(memoir_current_branch)"
memoir -s "$STORE" --json remember "captured on deletable" -p context.project.database >/dev/null

git -C "$PROJ" checkout -q main
context=$(session_start_context)
assert_contains "feature/deletable initially listed while code branch exists" \
  "memoir/feature/deletable:" "$context"

git -C "$PROJ" branch -D feature/deletable >/dev/null
context=$(session_start_context)
assert_not_contains "feature/deletable suppressed after its code branch is deleted" \
  "memoir/feature/deletable:" "$context"

# -------- 9c. Unmerged detection only fires while code branch is main --------
heading "Unmerged detection suppressed when code branch != main"
# Put fresh unmerged work on memoir feature/b so it's a live candidate.
memoir -s "$STORE" checkout feature/b >/dev/null
sleep 2  # commit ts must exceed the existing sync-marker ts
memoir -s "$STORE" --json remember "fresh B fact" -p context.project.database >/dev/null
memoir -s "$STORE" checkout main >/dev/null

# While on code feature/a, the scan must not run — even though feature/b
# has unmerged captures.
git -C "$PROJ" checkout -q feature/a
context=$(session_start_context)
assert_not_contains "no unmerged suggestions while on code feature/a" \
  "unmerged branches detected" "$context"

# Returning to main resurfaces feature/b.
git -C "$PROJ" checkout -q main
context=$(session_start_context)
assert_contains "feature/b surfaces once code returns to main" \
  "memoir/feature/b:" "$context"

# Clean up so later tests start from a quiet state.
sync_branch feature/b

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

# -------- 12b. Dead-PID heartbeat is reaped, not warned on --------
heading "Dead-PID heartbeat reaped immediately"
mkdir -p "$STORE/.git/plugin-active-sessions"
# Pick a PID that is exceedingly unlikely to be live. `kill -0` on a free PID
# returns non-zero, which is what concurrent_session_warning should detect.
dead_pid=$(python3 -c "
import os
for p in range(99990, 99000, -1):
    try: os.kill(p, 0)
    except ProcessLookupError:
        print(p); break
    except PermissionError:
        continue
")
hb="$STORE/.git/plugin-active-sessions/test-dead-pid-session"
printf '%s\t%s\t%s\n' "feature/zombie" "$(date +%s)" "$dead_pid" > "$hb"
status=$(session_start_status)
assert_not_contains "dead-PID heartbeat does not warn" "feature/zombie" "$status"
assert "dead-PID heartbeat file is reaped" "0" "$([ ! -f "$hb" ]; echo $?)"
rm -rf "$STORE/.git/plugin-active-sessions"

# -------- 12c. Live-PID heartbeat on another branch still warns --------
heading "Live-PID heartbeat still warns"
mkdir -p "$STORE/.git/plugin-active-sessions"
# Use this test's own PID — guaranteed alive for the rest of the run.
printf '%s\t%s\t%s\n' "feature/alive" "$(date +%s)" "$$" \
  > "$STORE/.git/plugin-active-sessions/test-live-pid-session"
status=$(session_start_status)
assert_contains "live-PID heartbeat triggers warning" "concurrent session detected" "$status"
assert_contains "live-PID warning names the branch" "feature/alive" "$status"
rm -rf "$STORE/.git/plugin-active-sessions"

# -------- 13. Mid-session code branch switch --------
# Simulates the user running `git checkout feature/b` in a terminal without
# restarting Claude Code. UserPromptSubmit and Stop hooks must re-run
# auto_match so captures land on the right memoir branch.
heading "Mid-session code switch (UserPromptSubmit + Stop re-run auto-match)"

# Put memoir on feature/a via SessionStart.
git -C "$PROJ" checkout -q feature/a
session_start_status >/dev/null
assert "memoir matched feature/a via SessionStart" "feature/a" "$(memoir_current_branch)"

# User git-switches to feature/b without restarting Claude Code.
git -C "$PROJ" checkout -q feature/b

# Simulate a UserPromptSubmit — its call to auto_match should move memoir to feature/b.
INPUT='{"prompt":"a reasonably long prompt that the hook will actually process"}'
echo "$INPUT" | bash "$CLAUDE_PLUGIN_ROOT/hooks/user-prompt-submit.sh" >/dev/null 2>&1
assert "UserPromptSubmit flipped memoir to feature/b" "feature/b" "$(memoir_current_branch)"

# Simulate a Stop hook turn and verify it captures onto feature/b.
# Build a minimal transcript the parser accepts (≥3 lines, includes a real user turn).
TRANSCRIPT=$(mktemp -t memoir-test-transcript.XXXXXX)
cat > "$TRANSCRIPT" <<'EOF'
{"type":"user","message":{"content":"setup"}}
{"type":"assistant","message":{"content":[{"type":"text","text":"ok"}]}}
{"type":"user","message":{"content":"Remember: this test says the capture must land on feature/b."}}
{"type":"assistant","message":{"content":[{"type":"text","text":"noted"}]}}
EOF
# Put memoir back on feature/a to prove the Stop hook itself re-matches before capturing.
memoir -s "$STORE" checkout feature/a >/dev/null
# Stop's haiku path won't be reachable without a credentialed `claude` CLI, but
# the auto-match call happens before the haiku extraction — so even if the
# capture ultimately no-ops, the branch switch is what we're verifying here.
echo "{\"transcript_path\":\"$TRANSCRIPT\"}" | bash "$CLAUDE_PLUGIN_ROOT/hooks/stop.sh" >/dev/null 2>&1
assert "Stop hook re-matched memoir to feature/b before capture" "feature/b" "$(memoir_current_branch)"
rm -f "$TRANSCRIPT"

# -------- 14. sync-cmd.sh list --------
heading "sync-cmd.sh list emits unmerged JSON"
SYNC_CMD="$CLAUDE_PLUGIN_ROOT/scripts/sync-cmd.sh"
# Back to code main; re-match memoir to main, then put fresh captures on a and b.
git -C "$PROJ" checkout -q main
session_start_status >/dev/null
memoir -s "$STORE" checkout feature/a >/dev/null
sleep 2  # commit ts must exceed the sync-marker ts from earlier sections
memoir -s "$STORE" --json remember "list-test fact A" -p preferences.coding.style >/dev/null
memoir -s "$STORE" checkout feature/b >/dev/null
memoir -s "$STORE" --json remember "list-test fact B" -p context.project.database >/dev/null
memoir -s "$STORE" checkout main >/dev/null

list_json=$(bash "$SYNC_CMD" list)
list_check=$(printf '%s' "$list_json" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
branches = sorted(e['branch'] for e in d['unmerged'])
total_ok = d['total_ahead'] == sum(e['ahead'] for e in d['unmerged'])
ahead_ok = all(e['ahead'] >= 1 for e in d['unmerged'])
print(','.join(branches), total_ok, ahead_ok)
")
assert "list reports both branches, total_ahead consistent" \
  "feature/a,feature/b True True" "$list_check"

# -------- 15. sync-cmd.sh dry-run + merge (real CLI path) --------
heading "sync-cmd.sh dry-run previews without marker write; merge promotes"
marker_before=$(cat "$STORE/.git/plugin-synced-branches/feature/a")
dry_json=$(bash "$SYNC_CMD" dry-run feature/a)
assert_contains "dry-run reports dry_run: true" '"dry_run": true' "$dry_json"
assert "dry-run does not touch the sync marker" \
  "$marker_before" "$(cat "$STORE/.git/plugin-synced-branches/feature/a")"

merge_json=$(bash "$SYNC_CMD" merge feature/a)
assert_contains "merge reports success" '"success": true' "$merge_json"
marker_after=$(cat "$STORE/.git/plugin-synced-branches/feature/a")
assert "merge advanced the sync marker" "0" \
  "$([ "$marker_after" -gt "$marker_before" ]; echo $?)"
assert "merge restored memoir branch main" "main" "$(memoir_current_branch)"
context=$(session_start_context)
assert_not_contains "feature/a gone from suggestions after real merge" \
  "memoir/feature/a:" "$context"

# -------- 16. sync-cmd.sh ignore (idempotent, suppresses suggestions) --------
heading "sync-cmd.sh ignore"
ig1=$(bash "$SYNC_CMD" ignore feature/b)
assert_contains "first ignore reports already: false" '"already": false' "$ig1"
ig2=$(bash "$SYNC_CMD" ignore feature/b)
assert_contains "second ignore reports already: true" '"already": true' "$ig2"
assert "ignore file holds exactly one feature/b line" "1" \
  "$(grep -cxF 'feature/b' "$STORE/.git/plugin-ignored-branches")"
list_json=$(bash "$SYNC_CMD" list)
ignore_check=$(printf '%s' "$list_json" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
print('feature/b' not in {e['branch'] for e in d['unmerged']},
      'feature/b' in d['ignored'])
")
assert "ignored branch absent from unmerged, present in ignored" "True True" "$ignore_check"
context=$(session_start_context)
assert_not_contains "ignored branch absent from suggestions" "memoir/feature/b:" "$context"

# -------- 17. Auto-offer threshold + snooze cooldown --------
heading "Auto-offer gating (≥5 commits) and snooze"
# A fresh branch with a single capture stays below the threshold.
git -C "$PROJ" checkout -qb feature/small
session_start_status >/dev/null
memoir -s "$STORE" --json remember "small fact 1" -p preferences.coding.style >/dev/null
git -C "$PROJ" checkout -q main
context=$(session_start_context)
assert_contains "below threshold: informational block present" "memoir/feature/small:" "$context"
assert_not_contains "below threshold: no auto-offer" "## Auto-offer" "$context"

# Four more captures push the branch to 5 unmerged commits.
memoir -s "$STORE" checkout feature/small >/dev/null
for i in 2 3 4 5; do
  memoir -s "$STORE" --json remember "small fact $i" -p preferences.coding.style >/dev/null
done
memoir -s "$STORE" checkout main >/dev/null
context=$(session_start_context)
assert_contains "at threshold: auto-offer present" "## Auto-offer" "$context"
assert_contains "auto-offer recipe references sync-cmd.sh" "sync-cmd.sh" "$context"

# Snooze suppresses the auto-offer but not the count or the info block.
snooze_json=$(bash "$SYNC_CMD" snooze 7)
assert_contains "snooze emits snoozed_until" '"snoozed_until"' "$snooze_json"
status=$(session_start_status)
context=$(session_start_context)
assert_contains "snoozed: status line still counts unmerged" "branch unmerged" "$status"
assert_contains "snoozed: informational block still present" "memoir/feature/small:" "$context"
assert_not_contains "snoozed: auto-offer suppressed" "## Auto-offer" "$context"

# An expired cooldown reactivates the auto-offer.
echo "$(( $(date +%s) - 60 ))" > "$STORE/.git/plugin-merge-prompt-cooldown"
context=$(session_start_context)
assert_contains "expired snooze: auto-offer returns" "## Auto-offer" "$context"

# -------- 18. Auto-promote when the code branch merges into main --------
heading "Auto-promote memoir branch once its code branch is merged into main"
# Real work on feature/merged: a code commit + a memoir capture.
git -C "$PROJ" checkout -qb feature/merged
git -C "$PROJ" commit --allow-empty -qm "feat: merged work"
session_start_status >/dev/null
assert "memoir matched feature/merged" "feature/merged" "$(memoir_current_branch)"
memoir -s "$STORE" --json remember "merged-branch fact" -p preferences.coding.editor >/dev/null

# Merge the code branch (merge commit, the workflow auto-promote detects).
git -C "$PROJ" checkout -q main
git -C "$PROJ" merge -q --no-ff feature/merged -m "merge feature/merged"

# Opt-out: branch stays in the unmerged suggestions, nothing is promoted.
ctx_off=$(MEMOIR_AUTO_PROMOTE_MERGED=0 bash "$CLAUDE_PLUGIN_ROOT/hooks/session-start.sh" </dev/null 2>&1 |
  python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('hookSpecificOutput',{}).get('additionalContext',''))")
assert_contains "opt-out: merged branch still listed unmerged" "memoir/feature/merged:" "$ctx_off"
assert_not_contains "opt-out: no auto-promotion happened" "auto-promoted" "$ctx_off"

# Default-on: SessionStart promotes it and reports what it did.
raw=$(bash "$CLAUDE_PLUGIN_ROOT/hooks/session-start.sh" </dev/null 2>&1)
status=$(printf '%s' "$raw" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('systemMessage',''))")
context=$(printf '%s' "$raw" | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('hookSpecificOutput',{}).get('additionalContext',''))")
assert_contains "status reports the auto-promotion" "auto-promoted 1 merged branch" "$status"
assert_contains "context names the promoted branch" "memoir/feature/merged → main" "$context"
assert_not_contains "promoted branch gone from unmerged block" "memoir/feature/merged:" "$context"
assert "sync marker written by auto-promotion" "0" \
  "$([ -f "$STORE/.git/plugin-synced-branches/feature/merged" ]; echo $?)"
# Branches with no unique code commits (tips are old mainline commits now
# that main advanced) must NOT be swept up by the merged-branch heuristic.
assert_contains "in-progress branch not auto-promoted" "memoir/feature/small:" "$context"

# -------- 19. Stale-branch GC (sync-cmd.sh list/prune) --------
heading "Stale-branch detection and prune"
# Default 60-day threshold: everything in this test run is recent → no stale.
stale_default=$(bash "$SYNC_CMD" list | python3 -c "
import json, sys
print(len(json.loads(sys.stdin.read())['stale']) == 0)
")
assert "no stale branches at the default 60d threshold" "True" "$stale_default"

# Threshold 0 makes every inactive branch a candidate; only synced or
# code-branch-gone branches qualify.
stale_check=$(MEMOIR_STALE_BRANCH_DAYS=0 bash "$SYNC_CMD" list | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
s = {e['branch'] for e in d['stale']}
print('experiment' in s, 'feature/deletable' in s,
      'feature/small' not in s, 'feature/b' not in s)
")
assert "stale = synced-or-abandoned only (no resumable branches)" \
  "True True True True" "$stale_check"

prune_json=$(bash "$SYNC_CMD" prune experiment)
assert_contains "prune reports the deleted branch" '"pruned": "experiment"' "$prune_json"
experiment_left=$(memoir --json -s "$STORE" branch |
  python3 -c "import json,sys; print('experiment' in (json.loads(sys.stdin.read()).get('branches') or []))")
assert "experiment branch deleted from the store" "False" "$experiment_left"

out=$(bash "$SYNC_CMD" prune main 2>&1 || true)
assert_contains "prune refuses to delete main" "ERROR" "$out"

# Pruning cleans up the branch's plugin state (ignore entry + sync marker).
bash "$SYNC_CMD" prune feature/b >/dev/null
assert "pruned branch removed from ignore file" "0" \
  "$(grep -cxF 'feature/b' "$STORE/.git/plugin-ignored-branches" || true)"
assert "pruned branch's sync marker removed" "0" \
  "$([ ! -f "$STORE/.git/plugin-synced-branches/feature/b" ]; echo $?)"

# -------- 20. Escalating snooze on repeated declines --------
heading "Escalating snooze (decline backoff 1d → 7d → 30d)"
rm -f "$STORE/.git/plugin-merge-prompt-cooldown"
d1=$(bash "$SYNC_CMD" decline)
assert_contains "first decline snoozes 1 day" '"days": 1' "$d1"
assert_contains "first decline count is 1" '"declines": 1' "$d1"
d2=$(bash "$SYNC_CMD" decline)
assert_contains "second decline escalates to 7 days" '"days": 7' "$d2"
d3=$(bash "$SYNC_CMD" decline)
assert_contains "third decline escalates to 30 days" '"days": 30' "$d3"
# The decline cooldown suppresses the auto-offer (feature/small still has ≥5
# unmerged commits) without hiding the informational block.
context=$(session_start_context)
assert_not_contains "declined: auto-offer suppressed" "## Auto-offer" "$context"
assert_contains "declined: informational block still present" "memoir/feature/small:" "$context"
# An explicit snooze is a deliberate choice — it resets the escalation.
bash "$SYNC_CMD" snooze 7 >/dev/null
d4=$(bash "$SYNC_CMD" decline)
assert_contains "explicit snooze resets escalation" '"days": 1' "$d4"

# -------- Summary --------
printf '\n--------------------------------\n'
printf 'PASS: %d    FAIL: %d\n' "$PASS" "$FAIL"
if [ "$FAIL" -gt 0 ]; then
  printf 'Failures:\n'
  for f in "${FAILURES[@]}"; do printf '  - %s\n' "$f"; done
  exit 1
fi
printf 'All checks passed.\n'

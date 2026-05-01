#!/usr/bin/env bash
# Claude Code end-to-end smoke runner. Invoked by run.sh after env checks.
#
# Each case is a bash function. Cases run sequentially, in their own
# mktemp dirs, with a trap that cleans up on exit or failure.
#
# Pass/fail accounting mirrors scripts/pypi-smoke/smoke.sh: stdout shows
# per-case PASS/FAIL with timing; exit non-zero if anything failed.

set -uo pipefail

PLUGIN_DIR="${CC_SMOKE_PLUGIN_DIR:?missing}"
MODEL="${CC_SMOKE_MODEL:?missing}"

# ---------------------------------------------------------------------------
# Test runner — same shape as pypi-smoke for consistency.
# ---------------------------------------------------------------------------

pass_count=0
fail_count=0
results=()

run_case() {
  local name="$1"; shift
  local fn="$1"; shift
  local start end elapsed out rc

  start=$(date +%s)
  out=$("$fn" 2>&1); rc=$?
  end=$(date +%s)
  elapsed=$((end - start))

  if [ "$rc" -eq 0 ]; then
    printf "  [PASS] %-40s %ds\n" "$name" "$elapsed"
    results+=("PASS|${name}|${elapsed}|")
    pass_count=$((pass_count + 1))
  else
    printf "  [FAIL] %-40s %ds\n" "$name" "$elapsed"
    if [ -n "$out" ]; then
      printf "         %s\n" "${out//$'\n'/$'\n         '}"
    fi
    results+=("FAIL|${name}|${elapsed}|")
    fail_count=$((fail_count + 1))
  fi
}

# ---------------------------------------------------------------------------
# Helpers — shared by cases.
# ---------------------------------------------------------------------------

# claude_p — wrapper around `claude -p` that pins the model, points at our
# plugin checkout, isolates from the user's settings, and disables session
# persistence. Each invocation runs in its own mktemp dir so
# --dangerously-skip-permissions is safe (no access to anything important).
#
# Reads the prompt from $1; extra args (e.g. --output-format) follow.
claude_p() {
  local prompt="$1"; shift
  if [ "$#" -gt 0 ]; then
    printf '%s' "$prompt" | claude -p \
      --plugin-dir "$PLUGIN_DIR" \
      --setting-sources project,local \
      --no-session-persistence \
      --no-chrome \
      --dangerously-skip-permissions \
      --model "$MODEL" \
      "$@"
  else
    printf '%s' "$prompt" | claude -p \
      --plugin-dir "$PLUGIN_DIR" \
      --setting-sources project,local \
      --no-session-persistence \
      --no-chrome \
      --dangerously-skip-permissions \
      --model "$MODEL"
  fi
}

# claude_p_stream — same as claude_p but yields stream-json with hook events
# included, so callers can grep the events.
claude_p_stream() {
  local prompt="$1"; shift
  claude_p "$prompt" --output-format stream-json --include-hook-events --verbose
}

# new_proj — make a fresh git project (returns dir on stdout)
new_proj() {
  local d
  d=$(mktemp -d -t cc-smoke-proj.XXXXXX)
  (
    cd "$d"
    git init -q
    git -c user.email=cc-smoke@test -c user.name=cc-smoke commit -q --allow-empty -m init
  ) >/dev/null
  printf '%s' "$d"
}

# new_store — make a fresh memoir store (returns dir on stdout)
new_store() {
  local d
  d=$(mktemp -d -t cc-smoke-store.XXXXXX)
  rm -rf "$d"
  memoir new "$d" --no-connect >/dev/null
  printf '%s' "$d"
}

# memoir_user_count — count of user memories in default namespace.
memoir_user_count() {
  local store="$1"
  memoir --json -s "$store" status 2>/dev/null \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("user_memory_count", d.get("memory_count", 0)))' \
    2>/dev/null || echo 0
}

# ---------------------------------------------------------------------------
# Case 1: SessionStart hook fires and emits the [memoir] status line.
# ---------------------------------------------------------------------------
case_session_start_status() {
  local proj store stream
  proj=$(new_proj)
  store=$(new_store)
  trap 'rm -rf "$proj" "$store"' RETURN
  (
    cd "$proj"
    export MEMOIR_STORE="$store"
    stream=$(claude_p_stream "say hi" 2>&1)
    # Find a SessionStart hook_response event and extract its output field.
    msg=$(printf '%s\n' "$stream" \
      | jq -r 'select(.subtype=="hook_response" and .hook_event=="SessionStart") | .output' \
      2>/dev/null | head -1)
    if [ -z "$msg" ]; then
      echo "no SessionStart hook_response in stream-json output"
      printf '%s\n' "$stream" | head -20
      exit 1
    fi
    if ! printf '%s' "$msg" | grep -q '\[memoir\]'; then
      echo "SessionStart output did not contain [memoir]: $msg"
      exit 1
    fi
  )
}

# ---------------------------------------------------------------------------
# Case 2: /memoir:remember slash command captures a memory synchronously.
# Bypasses Stop-hook auto-capture (which gets cancelled in -p mode).
# ---------------------------------------------------------------------------
case_remember_slash_captures() {
  local proj store got
  proj=$(new_proj)
  store=$(new_store)
  trap 'rm -rf "$proj" "$store"' RETURN
  (
    cd "$proj"
    export MEMOIR_STORE="$store"
    claude_p '/memoir:remember I prefer hard tabs over spaces -p preferences.coding.style' \
      >/dev/null 2>&1 || true
    # Tight assertion: the explicit -p path must be honored. Doubles as a
    # regression test for the previously-fixed bug where Claude Code's $N
    # substitution inside slash-command bash blocks caused -p to be silently
    # dropped, leaving the memory at the classifier-fallback key.
    got=$(memoir --json -s "$store" get preferences.coding.style 2>/dev/null \
      | python3 -c 'import json,sys
try:
    d = json.load(sys.stdin)
    items = d.get("items") or []
    print(items[0]["value"]["content"] if items else "")
except Exception:
    print("")' 2>/dev/null)
    if ! printf '%s' "$got" | grep -qi 'tab'; then
      echo "/memoir:remember -p preferences.coding.style did not land at requested key"
      echo "  got content at preferences.coding.style: [$got]"
      memoir -s "$store" summarize --keys "*" 2>&1 | tail -10
      exit 1
    fi
  )
}

# ---------------------------------------------------------------------------
# Case 3: a recall-shaped question surfaces a previously seeded fact.
# Pre-seeded via `memoir remember` directly (no LLM/hook involvement) so the
# assertion only stresses the recall side.
# ---------------------------------------------------------------------------
case_recall_surfaces_prior_fact() {
  local proj store reply
  proj=$(new_proj)
  store=$(new_store)
  trap 'rm -rf "$proj" "$store"' RETURN
  (
    cd "$proj"
    export MEMOIR_STORE="$store"
    memoir -s "$store" remember "Python 3.12 with the Black formatter" \
      -p workflow.coding.language >/dev/null
    reply=$(claude_p "What version of Python do I use? Answer briefly using only what you remember about me." 2>&1) || true
    # Loose assertion — just look for the version string in the reply.
    if ! printf '%s' "$reply" | grep -q '3\.12'; then
      echo "reply did not surface seeded fact (expected '3.12'):"
      printf '%s\n' "$reply" | head -20
      exit 1
    fi
  )
}

# ---------------------------------------------------------------------------
# Case 4: worktree-shared store. Both the main checkout and a linked worktree
# must drive the SAME ~/.memoir/<slug>/ store when the plugin's hooks fire.
#
# Structural assertion (no LLM round-trip required): seed a memory at the
# slug directly, then run `claude -p "hi"` from the worktree and verify
# (a) no NEW slug directory was created under ~/.memoir/, and (b) the
# pre-existing slug still holds the seeded memory after the worktree session.
# ---------------------------------------------------------------------------
case_worktree_shared_store() {
  local proj wt slug before_slugs after_slugs new_slugs count
  proj=$(new_proj)
  wt=$(mktemp -d -t cc-smoke-wt.XXXXXX); rm -rf "$wt"
  (
    cd "$proj"
    git worktree add -q "$wt" -b cc-smoke-wt-branch >/dev/null
  )
  # Resolve the slug the plugin WILL derive — must run from inside the proj
  # so symlink resolution (e.g. /var → /private/var on macOS) matches the
  # plugin's runtime resolution.
  slug=$(cd "$proj" && bash "$PLUGIN_DIR/scripts/derive-store-path.sh")
  trap 'rm -rf "$proj" "$wt" "$slug"' RETURN

  # Pre-seed a memory at the slug so we can verify the worktree session
  # reads from the same place.
  rm -rf "$slug"
  memoir new "$slug" --no-connect >/dev/null
  memoir -s "$slug" remember "I prefer hard tabs over spaces" \
    -p preferences.coding.style >/dev/null

  # Snapshot ~/.memoir/ to detect any sibling slug creation.
  before_slugs=$(ls -1 "$HOME/.memoir/" 2>/dev/null | sort)

  # Run a benign turn from inside the worktree. Hooks fire, derive-store-path
  # resolves, the plugin reads the existing store. If the worktree-fix
  # regressed, this would create a NEW slug for the worktree's own path.
  (
    cd "$wt"
    unset MEMOIR_STORE
    claude_p "hi" >/dev/null 2>&1 || true
  )

  # Assertion 1: no NEW slug appeared under ~/.memoir/.
  after_slugs=$(ls -1 "$HOME/.memoir/" 2>/dev/null | sort)
  new_slugs=$(comm -13 <(printf '%s\n' "$before_slugs") <(printf '%s\n' "$after_slugs"))
  if [ -n "$new_slugs" ]; then
    echo "worktree session created NEW slug(s) under ~/.memoir/ — fix regressed:"
    printf '%s\n' "$new_slugs" | sed 's/^/  /'
    exit 1
  fi

  # Assertion 2: the seeded memory is still readable from the slug after
  # the worktree session. Stop hook cancellation (in -p) shouldn't have
  # corrupted the store.
  count=$(memoir_user_count "$slug")
  if [ "$count" -lt 1 ]; then
    echo "seeded memory disappeared after worktree session (count=$count)"
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Case 5: /memoir:status slash command renders status output for the model.
# ---------------------------------------------------------------------------
case_slash_command_status() {
  local proj store reply
  proj=$(new_proj)
  store=$(new_store)
  trap 'rm -rf "$proj" "$store"' RETURN
  (
    cd "$proj"
    export MEMOIR_STORE="$store"
    memoir -s "$store" remember "seed memory" -p test.seed >/dev/null
    reply=$(claude_p '/memoir:status' 2>&1) || true
    # Loose: status.md instructs the LLM to summarize as "branch, N memories,
    # M commits". Match any one of those deterministic labels.
    if ! printf '%s' "$reply" | grep -qiE 'memor(ies|y)|branch|commit'; then
      echo "/memoir:status reply did not mention status fields:"
      printf '%s\n' "$reply" | head -20
      exit 1
    fi
  )
}

# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

echo "== Test Results =="

run_case "cc-session-start-status"        case_session_start_status
run_case "cc-remember-slash-captures"     case_remember_slash_captures
run_case "cc-recall-surfaces-prior-fact"  case_recall_surfaces_prior_fact
run_case "cc-worktree-shared-store"       case_worktree_shared_store
run_case "cc-slash-command-status"        case_slash_command_status

total=$((pass_count + fail_count))
echo
echo "== Summary =="
echo "  ${pass_count}/${total} passed"

if (( fail_count > 0 )); then
  echo "  Failed:"
  for r in "${results[@]}"; do
    IFS='|' read -r status name elapsed reason <<<"$r"
    [[ "$status" == "FAIL" ]] && echo "    - ${name} (${elapsed}s)"
  done
  exit 1
fi

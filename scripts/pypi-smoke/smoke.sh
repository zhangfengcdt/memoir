#!/usr/bin/env bash
# In-container smoke test for memoir-ai installed from PyPI.
#
# Runs a set of small, named test cases against the published wheel and
# reports per-case pass/fail with timing. Two outputs:
#   - human-readable (stdout): always
#   - markdown summary ($MEMOIR_SMOKE_SUMMARY_FILE): when that env var is set,
#     used by the CI workflow to populate GITHUB_STEP_SUMMARY.
#
# Env:
#   MEMOIR_VERSION           required — the version under test (asserted)
#   MEMOIR_SMOKE_HEADLESS=1  exit after the assertions instead of holding
#                            the UI open for a human eyeballer
#   MEMOIR_SMOKE_SUMMARY_FILE absolute path to write a markdown summary to
set -uo pipefail

: "${MEMOIR_VERSION:?MEMOIR_VERSION must be set (Docker ARG/ENV)}"
SUMMARY_FILE="${MEMOIR_SMOKE_SUMMARY_FILE:-}"
HEADLESS="${MEMOIR_SMOKE_HEADLESS:-0}"

# ---------------------------------------------------------------------------
# Environment block
# ---------------------------------------------------------------------------

env_kv() { printf "  %-18s %s\n" "$1" "$2"; }

env_memoir=$(memoir --version 2>&1 || echo "missing")
env_python=$(python3 --version 2>&1 | sed 's/^Python //')
env_os=$(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || uname -sr)
env_arch=$(uname -m)
env_git=$(git --version 2>&1 | sed 's/^git version //')
env_pip_pkg=$(pip show memoir-ai 2>/dev/null | awk -F': ' '/^Version:/{print $2}')
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  env_llm="yes (model: ${MEMOIR_LLM_MODEL:-claude-haiku-4-5})"
else
  env_llm="no — LLM cases will be skipped"
fi

echo "== Environment =="
env_kv "memoir-ai"     "${env_pip_pkg:-not installed} (cli: ${env_memoir})"
env_kv "Python"        "$env_python"
env_kv "OS"            "$env_os"
env_kv "Architecture"  "$env_arch"
env_kv "git"           "$env_git"
env_kv "Install source" "PyPI (memoir-ai==${MEMOIR_VERSION})"
env_kv "LLM key"       "$env_llm"
echo

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

declare -i pass_count=0 fail_count=0 skip_count=0
declare -a results=()        # "PASS|name|elapsed|" or "FAIL|name|elapsed|reason" or "SKIP|name|0.00|reason"

run_case() {
  local name="$1"; shift
  local fn="$1"; shift
  local start="${EPOCHREALTIME}"
  local out rc elapsed

  out=$("$fn" 2>&1); rc=$?
  elapsed=$(awk -v a="$start" -v b="${EPOCHREALTIME}" 'BEGIN{printf "%.2f", b-a}')

  if (( rc == 0 )); then
    printf "  [PASS] %-40s %ss\n" "$name" "$elapsed"
    results+=("PASS|${name}|${elapsed}|")
    pass_count+=1
  else
    printf "  [FAIL] %-40s %ss\n" "$name" "$elapsed"
    if [[ -n "$out" ]]; then
      printf "         %s\n" "${out//$'\n'/$'\n         '}"
    fi
    # Pipe-escape the reason for the markdown table.
    local reason="${out//$'\n'/ }"
    reason="${reason//|/ }"
    results+=("FAIL|${name}|${elapsed}|${reason}")
    fail_count+=1
  fi
}

skip_case() {
  local name="$1"; shift
  local reason="$1"; shift
  printf "  [SKIP] %-40s %s\n" "$name" "$reason"
  results+=("SKIP|${name}|0.00|${reason}")
  skip_count+=1
}

# ---------------------------------------------------------------------------
# Test cases — each prints diagnostic detail to stdout/err on failure and
# returns 0 on pass / non-zero on fail. No `set -e` inside cases; the runner
# captures rc explicitly.
# ---------------------------------------------------------------------------

STORE=/tmp/store

case_cli_on_path()       { command -v memoir >/dev/null || { echo "memoir not on PATH"; return 1; }; }

case_cli_version_matches() {
  local out; out=$(memoir --version 2>&1)
  [[ "$out" == "memoir, version ${MEMOIR_VERSION}" ]] || {
    echo "expected 'memoir, version ${MEMOIR_VERSION}'; got '$out'"
    return 1
  }
}

case_cli_new_creates_git_repo() {
  rm -rf "$STORE"
  memoir new "$STORE" >/dev/null || { echo "memoir new failed"; return 1; }
  [[ -d "$STORE/.git" ]] || { echo ".git not created at $STORE"; return 1; }
}

case_cli_connect_persists() {
  memoir connect "$STORE" >/dev/null || { echo "connect failed"; return 1; }
  # status without -s / MEMOIR_STORE should still find the connected store
  unset MEMOIR_STORE
  memoir status >/dev/null || { echo "status after connect failed"; return 1; }
}

case_cli_status_json_is_valid() {
  local out; out=$(memoir --json status 2>&1) || { echo "status --json failed: $out"; return 1; }
  echo "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert isinstance(d, dict), d' \
    || { echo "not valid JSON object: $out"; return 1; }
}

case_cli_remember_three_keys() {
  memoir remember "feng prefers tabs" -p preferences.coding.style >/dev/null || return 1
  memoir remember "uses python 3.11"  -p workflow.coding.language >/dev/null || return 1
  memoir remember "lives in Torrance" -p user.location.city       >/dev/null || return 1
}

case_cli_get_each() {
  memoir get preferences.coding.style 2>&1 | grep -q "tabs"     || { echo "key1 missing"; return 1; }
  memoir get workflow.coding.language 2>&1 | grep -q "3.11"     || { echo "key2 missing"; return 1; }
  memoir get user.location.city       2>&1 | grep -q "Torrance" || { echo "key3 missing"; return 1; }
}

case_cli_forget_removes_key() {
  memoir forget user.location.city --force >/dev/null 2>&1 || { echo "forget failed"; return 1; }
  if memoir get user.location.city >/dev/null 2>&1; then
    echo "key still retrievable after forget"; return 1
  fi
}

case_cli_get_missing_exits_nonzero() {
  if memoir get this.key.does.not.exist >/dev/null 2>&1; then
    echo "expected non-zero exit for missing key"; return 1
  fi
}

case_cli_branch_create_and_list() {
  memoir branch feature-test >/dev/null 2>&1 || { echo "branch create failed"; return 1; }
  memoir branch 2>&1 | grep -q "feature-test" || { echo "feature-test not in branch list"; return 1; }
}

case_cli_checkout_and_write() {
  memoir checkout feature-test >/dev/null 2>&1 || { echo "checkout failed"; return 1; }
  memoir remember "only on feature branch" -p preferences.coding.feature-only >/dev/null || return 1
  memoir get preferences.coding.feature-only 2>&1 | grep -q "feature branch" || {
    echo "key on feature branch not retrievable"; return 1
  }
}

case_cli_branch_isolation() {
  memoir checkout main >/dev/null 2>&1 || { echo "checkout main failed"; return 1; }
  if memoir get preferences.coding.feature-only >/dev/null 2>&1; then
    echo "feature-only key leaked to main"; return 1
  fi
}

# --- LLM-backed CLI cases (gated on ANTHROPIC_API_KEY) ---

# `remember` without -p triggers the IntelligentClassifier (LLM call).
# We don't assert *which* path Haiku picks (it's non-deterministic), only
# that the round-trip succeeds and produces a syntactically valid dotted key.
# stderr is captured separately so memoir's warnings/log lines don't poison
# the JSON parse on stdout.
case_cli_remember_no_path() {
  local out err=/tmp/memoir-llm-remember.err
  out=$(memoir --json remember --model claude-haiku-4-5 \
        "I prefer dark mode for IDEs and 2-space indents" 2>"$err") \
    || { echo "remember (no -p) exited non-zero. stderr:"; cat "$err"; echo "stdout: $out"; return 1; }
  echo "$out" | python3 -c '
import json, re, sys
d = json.load(sys.stdin)
assert d.get("success") is True, f"success not true: {d}"
key = d.get("key") or ""
assert re.match(r"^[a-z][a-z0-9._-]+$", key), f"key not a dotted path: {key!r}"
' || { echo "JSON shape unexpected. stdout: $out"; echo "stderr:"; cat "$err"; return 1; }
}

# `recall` calls the IntelligentSearchEngine (LLM call). We rely on the prior
# `cli-remember-three-keys` case having stored "feng prefers tabs" at
# preferences.coding.style; recall("tabs") should surface either that path
# or a memory whose content mentions "tabs" — tolerating ranking variance.
case_cli_recall_finds_stored() {
  local out err=/tmp/memoir-llm-recall.err
  out=$(memoir --json recall --model claude-haiku-4-5 "tabs" 2>"$err") \
    || { echo "recall exited non-zero. stderr:"; cat "$err"; echo "stdout: $out"; return 1; }
  echo "$out" | python3 -c '
import json, sys
d = json.load(sys.stdin)
assert d.get("success") is True, f"success not true: {d}"
mems = d.get("memories", [])
assert mems, f"empty memories: {d}"
def matches(m):
    return (m.get("path") == "preferences.coding.style"
            or "tabs" in str(m.get("content","")).lower())
assert any(matches(m) for m in mems), f"no memory matched: {mems}"
' || { echo "JSON shape or content unexpected. stdout: $out"; echo "stderr:"; cat "$err"; return 1; }
}

# --- UI ---

start_ui() {
  memoir ui "$STORE" --no-browser --port 9090 --idle-timeout 0 >/tmp/ui.log 2>&1 &
  UI_PID=$!
  for _ in $(seq 1 20); do
    curl -fsS http://127.0.0.1:9090/ >/dev/null 2>&1 && return 0
    sleep 0.5
  done
  echo "UI did not bind on :9090 within 10s; log:"; cat /tmp/ui.log
  return 1
}

case_ui_server_binds()   { curl -fsS http://127.0.0.1:9090/ >/dev/null; }

case_ui_html_react_root() {
  local out; out=$(curl -fsS http://127.0.0.1:9090/) || return 1
  echo "$out" | grep -q '<div id="root"' || { echo "no React root in served HTML"; return 1; }
}

case_ui_api_branches() {
  local out; out=$(curl -fsS "http://127.0.0.1:9090/api/branches?path=${STORE}") || return 1
  echo "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d, "empty"' \
    || { echo "non-empty JSON expected, got: $out"; return 1; }
}

case_ui_api_current_branch() {
  curl -fsS "http://127.0.0.1:9090/api/current-branch?path=${STORE}" >/dev/null
}

case_ui_api_statistics() {
  local out; out=$(curl -fsS "http://127.0.0.1:9090/api/statistics?path=${STORE}") || return 1
  echo "$out" | python3 -c 'import json,sys; json.load(sys.stdin)' \
    || { echo "statistics not JSON: $out"; return 1; }
}

case_ui_api_commits() {
  local out; out=$(curl -fsS "http://127.0.0.1:9090/api/commits?path=${STORE}") || return 1
  echo "$out" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d, "empty"' \
    || { echo "commits empty/invalid: $out"; return 1; }
}

# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

echo "== Test Results =="

run_case "cli-on-path"                  case_cli_on_path
run_case "cli-version-matches"          case_cli_version_matches
run_case "cli-new-creates-git-repo"     case_cli_new_creates_git_repo
run_case "cli-connect-persists"         case_cli_connect_persists
run_case "cli-status-json-is-valid"     case_cli_status_json_is_valid
run_case "cli-remember-three-keys"      case_cli_remember_three_keys
run_case "cli-get-each"                 case_cli_get_each
run_case "cli-forget-removes-key"       case_cli_forget_removes_key
run_case "cli-get-missing-exits-nonzero" case_cli_get_missing_exits_nonzero
run_case "cli-branch-create-and-list"   case_cli_branch_create_and_list
run_case "cli-checkout-and-write"       case_cli_checkout_and_write
run_case "cli-branch-isolation"         case_cli_branch_isolation

# LLM-backed cases — gated on ANTHROPIC_API_KEY presence so a forked PR run
# (or a local run without a key configured) doesn't fail the suite.
if [[ -n "${ANTHROPIC_API_KEY:-}" ]]; then
  run_case "cli-remember-no-path-uses-llm" case_cli_remember_no_path
  run_case "cli-recall-finds-stored-key"   case_cli_recall_finds_stored
else
  skip_case "cli-remember-no-path-uses-llm" "ANTHROPIC_API_KEY not set"
  skip_case "cli-recall-finds-stored-key"   "ANTHROPIC_API_KEY not set"
fi

# UI tests share one server; bring it up once.
echo
ui_screenshots=()  # list of "name|absolute_path" — embedded into summary.md if produced
if start_ui; then
  run_case "ui-server-binds"        case_ui_server_binds
  run_case "ui-html-react-root"     case_ui_html_react_root
  run_case "ui-api-branches"        case_ui_api_branches
  run_case "ui-api-current-branch"  case_ui_api_current_branch
  run_case "ui-api-statistics"      case_ui_api_statistics
  run_case "ui-api-commits"         case_ui_api_commits

  # Headless screenshots — best-effort, do not fail the run if chromium hiccups.
  # Saved into the same dir as the markdown summary (bind-mounted from the
  # host in CI), so the workflow can pick them up as artifacts too.
  if [[ -n "$SUMMARY_FILE" ]] && command -v chromium >/dev/null 2>&1; then
    shot_dir="$(dirname "$SUMMARY_FILE")"
    capture_screenshot() {
      local name="$1" url="$2" path="${shot_dir}/${1}.png"
      chromium --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
        --window-size=1280,900 --virtual-time-budget=8000 \
        --screenshot="$path" "$url" >/dev/null 2>&1 || true
      if [[ -s "$path" ]]; then
        ui_screenshots+=("${name}|${path}")
        echo "  [shot] ${name} → $(stat -c%s "$path" 2>/dev/null || echo ?) bytes"
      else
        echo "  [shot] ${name} → SKIPPED (chromium produced no image)"
      fi
    }
    echo
    echo "== UI Screenshots =="
    capture_screenshot "ui-landing"  "http://127.0.0.1:9090/?store=${STORE}&readonly=0&usellm=0"
    capture_screenshot "ui-welcome"  "http://127.0.0.1:9090/"
  fi
else
  results+=("FAIL|ui-server-startup|0.00|UI failed to bind; remaining UI tests skipped")
  fail_count+=1
fi

total=$((pass_count + fail_count + skip_count))
ran=$((pass_count + fail_count))

# ---------------------------------------------------------------------------
# Summary (stdout)
# ---------------------------------------------------------------------------

echo
echo "== Summary =="
if (( skip_count > 0 )); then
  echo "  ${pass_count}/${ran} passed, ${skip_count} skipped"
else
  echo "  ${pass_count}/${total} passed"
fi
if (( fail_count > 0 )); then
  echo "  Failed:"
  for r in "${results[@]}"; do
    IFS='|' read -r status name elapsed reason <<<"$r"
    [[ "$status" == "FAIL" ]] && echo "    - ${name} (${elapsed}s) — ${reason}"
  done
fi

# ---------------------------------------------------------------------------
# Markdown summary (for GITHUB_STEP_SUMMARY)
# ---------------------------------------------------------------------------

if [[ -n "$SUMMARY_FILE" ]]; then
  status_emoji="✅"
  (( fail_count > 0 )) && status_emoji="❌"
  {
    echo "## ${status_emoji} PyPI Smoke Test — memoir-ai ${MEMOIR_VERSION}"
    echo
    if (( skip_count > 0 )); then
      echo "**${pass_count}/${ran} passed, ${skip_count} skipped**"
    else
      echo "**${pass_count}/${total} passed**"
    fi
    echo
    echo "### Environment"
    echo
    echo "| Field | Value |"
    echo "|---|---|"
    echo "| memoir-ai | ${MEMOIR_VERSION} (from PyPI) |"
    echo "| Python | ${env_python} |"
    echo "| OS | ${env_os} |"
    echo "| Architecture | ${env_arch} |"
    echo "| git | ${env_git} |"
    echo "| LLM key | ${env_llm} |"
    echo
    echo "### Results"
    echo
    echo "| | Case | Time | Note |"
    echo "|---|---|---|---|"
    for r in "${results[@]}"; do
      IFS='|' read -r status name elapsed reason <<<"$r"
      case "$status" in
        PASS) echo "| ✅ | \`${name}\` | ${elapsed}s | |" ;;
        FAIL) echo "| ❌ | \`${name}\` | ${elapsed}s | ${reason} |" ;;
        SKIP) echo "| ⏭️ | \`${name}\` | — | ${reason} |" ;;
      esac
    done
    if (( fail_count > 0 )); then
      echo
      echo "### Failures"
      echo
      for r in "${results[@]}"; do
        IFS='|' read -r status name elapsed reason <<<"$r"
        if [[ "$status" == "FAIL" ]]; then
          echo "- **\`${name}\`** — ${reason}"
        fi
      done
    fi
    if (( ${#ui_screenshots[@]} > 0 )); then
      echo
      echo "### UI Screenshots"
      echo
      echo "Captured by headless Chromium against the running UI server:"
      echo
      for s in "${ui_screenshots[@]}"; do
        IFS='|' read -r shot_name shot_path <<<"$s"
        size=$(stat -c%s "$shot_path" 2>/dev/null || echo "?")
        echo "- **\`${shot_name}\`** ($(numfmt --to=iec --suffix=B "$size" 2>/dev/null || echo "${size}B"))"
      done
      echo
      echo "_Download the raw PNGs from the workflow's **Artifacts** section (linked below)._"
    fi
  } > "$SUMMARY_FILE"
fi

# ---------------------------------------------------------------------------
# Exit / hand-off
# ---------------------------------------------------------------------------

if (( fail_count > 0 )); then
  kill "${UI_PID:-}" 2>/dev/null || true
  exit 1
fi

if [[ "$HEADLESS" == "1" ]]; then
  kill "${UI_PID:-}" 2>/dev/null || true
  echo
  echo "OK: all checks passed for memoir-ai ${MEMOIR_VERSION} (headless)."
  exit 0
fi

cat <<EOF

==============================================================
OK: ${pass_count}/${total} automated checks passed.

UI is live at:  http://localhost:9090/?store=${STORE}&readonly=0&usellm=0

Open the URL in your host browser and confirm:
  1. Page loads (no white screen, no "failed to fetch").
  2. Timeline view renders.
  3. You can click a branch and open a key detail panel.
  4. Browser DevTools Console shows no red errors.

Press Ctrl-C in this terminal when done.
==============================================================
EOF

trap 'kill "${UI_PID:-}" 2>/dev/null || true' EXIT
wait "${UI_PID:-}"

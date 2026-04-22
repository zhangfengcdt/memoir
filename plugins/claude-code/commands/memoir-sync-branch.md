---
description: "Merge a specific memoir branch into main without switching to it. Used to promote captures from branches you're no longer working on."
argument-hint: "<branch-name>"
allowed-tools: Bash
---

Merge a specified memoir branch into main while staying on your current branch. Useful when the SessionStart detector surfaces unmerged branches — you can promote each without switching away from your current work.

!`bash -c '
STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"
TARGET="$ARGUMENTS"
if [ -z "$TARGET" ]; then
  echo "Usage: memoir:memoir-sync-branch <branch-name>"
  exit 1
fi
if [ "$TARGET" = "main" ]; then
  echo "Refusing to merge main into main — pick a feature branch."
  exit 1
fi
CURRENT=$(memoir --json -s "$STORE" status | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or \"{}\").get(\"branch\",\"\"))")
# Capture the code-side SHA before the merge so we can detect whether the
# merge window covered meaningful code changes (triggers the onboard hint).
CODE_SHA_BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "")
# Checkout main, merge target, return to original branch, record sync marker.
if memoir -s "$STORE" checkout main > /dev/null && \
   memoir -s "$STORE" merge "$TARGET"; then
  # Deterministic bump of _meta.last_onboard.* on main so the onboard snapshot
  # metadata stays truthful even if the user never reruns /memoir-onboard.
  # The narrative keys (structure.*, goal.*, …) are intentionally NOT rewritten
  # here — that needs an LLM pass, which stays user-triggered.
  CODE_SHA_AFTER=$(git rev-parse HEAD 2>/dev/null || echo "")
  MEMOIR_SHA=$(memoir --json -s "$STORE" status | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or \"{}\").get(\"commit_hash\",\"\"))" 2>/dev/null || echo "")
  if [ -n "$CODE_SHA_AFTER" ]; then
    DATE_ISO=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    memoir -s "$STORE" remember "$CODE_SHA_AFTER" -p _meta.last_onboard.commit -n codebase:onboard >/dev/null 2>&1 || true
    memoir -s "$STORE" remember "$DATE_ISO"       -p _meta.last_onboard.date   -n codebase:onboard >/dev/null 2>&1 || true
    if [ -n "$MEMOIR_SHA" ]; then
      memoir -s "$STORE" remember "$MEMOIR_SHA" -p _meta.last_onboard.memoir_commit -n codebase:onboard >/dev/null 2>&1 || true
    fi
  fi
  if [ -n "$CURRENT" ] && [ "$CURRENT" != "main" ]; then
    memoir -s "$STORE" checkout "$CURRENT" > /dev/null
  fi
  mkdir -p "$(dirname "$STORE/.git/plugin-synced-branches/$TARGET")"
  date +%s > "$STORE/.git/plugin-synced-branches/$TARGET"
  echo "(synced memoir/$TARGET into main; back on ${CURRENT:-main})"
  # Onboard-refresh suggestion: emit only when the code diff across the sync
  # window touched something substantive (src/, plugins/, pyproject, Makefile,
  # Dockerfile, workflows). No-op when the merge was purely memoir memories
  # with no code change, so we do not nag on pure-memory promotions.
  if [ -n "$CODE_SHA_BEFORE" ] && [ -n "$CODE_SHA_AFTER" ] && [ "$CODE_SHA_BEFORE" != "$CODE_SHA_AFTER" ]; then
    if git diff --name-only "$CODE_SHA_BEFORE" "$CODE_SHA_AFTER" 2>/dev/null \
         | grep -qE "^(src/|plugins/|pyproject\.toml|Makefile|docker|\.github/workflows/)"; then
      echo "💡 code changed in this window — run /memoir-onboard to refresh the codebase:onboard snapshot"
    fi
  fi
fi
' ARGUMENTS="$ARGUMENTS"`

Report the merge result. Relay the `/memoir-onboard` refresh suggestion verbatim if it appears — it means the merge pulled in code changes that likely shifted the codebase overview. If the user has multiple unmerged branches (from the SessionStart detector), remind them they can repeat this command for each.

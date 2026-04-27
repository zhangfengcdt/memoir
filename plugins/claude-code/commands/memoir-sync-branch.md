---
description: "Promote a memoir branch's default-namespace memories into main without switching to it. Add/update only — never deletes, never touches other namespaces."
argument-hint: "<branch-name> [--yes]"
allowed-tools: Bash
---

Safely promote a memoir branch into main as an additive merge. Only the
`default` namespace is touched, only inserts/updates are applied, and system
namespaces (e.g. `codebase:onboard`) plus any keys absent from the source
branch are left intact. Useful when the SessionStart detector surfaces
unmerged branches.

This command runs in **two phases**:

  1. Without `--yes` (default), it prints a dry-run preview of what *would*
     change. Show the preview to the user and confirm before applying.
  2. With `--yes`, it actually writes the changes.

!`bash -c '
STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"

# Non-git folders are locked to main — there are no code branches to follow,
# so there is nothing to promote. Short-circuit cleanly.
if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "non-git folder: only \`main\` exists, nothing to sync."
  exit 0
fi

ARGS=$ARGUMENTS
TARGET=""
APPLY=0
for tok in $ARGS; do
  case "$tok" in
    --yes|-y) APPLY=1 ;;
    -*) ;;  # ignore unknown flags for forward-compat
    *) [ -z "$TARGET" ] && TARGET="$tok" ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "Usage: memoir:memoir-sync-branch <branch-name> [--yes]"
  exit 1
fi
if [ "$TARGET" = "main" ]; then
  echo "Refusing to merge main into main — pick a feature branch."
  exit 1
fi

if [ "$APPLY" = "0" ]; then
  echo "(preview — no changes written; re-run with --yes to apply)"
  memoir -s "$STORE" sync-branch "$TARGET" --into main --dry-run
  exit $?
fi

# Capture the code-side SHA before the merge so we can detect whether the
# merge window covered meaningful code changes (triggers the onboard hint).
CODE_SHA_BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "")

if memoir -s "$STORE" sync-branch "$TARGET" --into main --yes; then
  # Deterministic bump of _meta.last_onboard.* on main so the onboard snapshot
  # metadata stays truthful even if the user never reruns /memoir-onboard.
  # The narrative keys (structure.*, goal.*, …) are intentionally NOT rewritten
  # here — that needs an LLM pass, which stays user-triggered. These writes go
  # to codebase:onboard *after* the safe promotion has finished, so they are
  # additive and never overlap with the default namespace.
  CODE_SHA_AFTER=$(git rev-parse HEAD 2>/dev/null || echo "")
  CURRENT=$(memoir --json -s "$STORE" status | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or \"{}\").get(\"branch\",\"\"))")
  if [ "$CURRENT" != "main" ]; then
    memoir -s "$STORE" checkout main > /dev/null 2>&1 || true
  fi
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
    memoir -s "$STORE" checkout "$CURRENT" > /dev/null 2>&1 || true
  fi
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

If the bash output is a **preview** (says "no changes written"), summarise
what would change and ask the user to confirm. Once they confirm, re-run
this command with `--yes` appended (e.g. `/memoir:memoir-sync-branch
<branch-name> --yes`).

If the bash output is the **applied** result, report the merge result and
relay the `/memoir-onboard` refresh suggestion verbatim if it appears — it
means the merge pulled in code changes that likely shifted the codebase
overview. If the user has multiple unmerged branches (from the SessionStart
detector), remind them they can repeat this command for each.

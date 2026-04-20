---
description: "Merge a memoir branch into the current one. Use --into <target> to merge into a non-current branch, and -S {ours|theirs|skip} to choose a conflict strategy."
argument-hint: "<source-branch> [--into <target>] [-S ours|theirs|skip]"
allowed-tools: Bash
---

Merge memoir branches. Default conflict strategy is `skip` — conflicting paths are left on the target branch.

!`bash -c 'STORE="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"; memoir -s "$STORE" merge $ARGUMENTS' ARGUMENTS="$ARGUMENTS"`

If there were conflicts, report them clearly — the user may want to re-run with a different `-S` strategy or hand-edit specific paths via `memoir forget` + `memoir remember`.

---
description: "Review and promote unmerged memoir branches into main (interactive)."
argument-hint: "[branch ...]"
allowed-tools: Bash, AskUserQuestion
---

Guide the user through promoting unmerged memoir branches into `main`. Current state (JSON from the backing script — `unmerged` is sorted most-recent-first):

!`bash "${CLAUDE_PLUGIN_ROOT}/scripts/sync-cmd.sh" list 2>&1`

Arguments passed by the user (may be empty): `$ARGUMENTS`

## Step 0 — Triage the state above

- If the script output starts with `ERROR:` (or is not JSON): reply `[mode=error]` plus the error/install hint on the next line. Stop.
- If `$ARGUMENTS` is non-empty: treat each whitespace-separated token as a branch name. Validate each against the `unmerged` list — warn about and skip unknown names. Jump straight to **Step 3** with the valid ones (no questions). Power-user fast path.
- If `unmerged` is empty: reply `[mode=clean]` — "All memoir branches are merged into main." Add, when applicable: "N branch(es) are on your ignore list (delete a line in `<store>/.git/plugin-ignored-branches` to unignore)" and, if `snoozed_until` is a future epoch, when the session-start auto-offer resumes. Note that the currently-checked-out memoir branch is never listed. Stop.
- If `concurrent_warning` is non-empty: print it as a one-line caution before any question (merging briefly moves the store's HEAD, which can collide with another live session).

## Step 1 — Ask what to do (AskUserQuestion, single-select, header "Memoir sync")

Render the branch table in the question text, one line per branch: `memoir/<branch> — <ahead> commits, last capture <age_days>d ago` (if more than 6 branches, show the top 6 and "… (N more)").

**Multiple branches** — options exactly:

1. `Merge all (Recommended)` — promote every listed branch into main → Step 3 with all branches.
2. `Choose branches` → Step 2.
3. `Ignore or snooze` → Step 4.
4. `Not now` — reply `[mode=cancelled]`, mention `/memoir:sync` works any time, change nothing. Stop.

**Exactly one branch** — skip Step 2; options instead:

1. `Merge <branch> (Recommended)` → Step 3.
2. `Ignore this branch permanently` → run `ignore <branch>` (see Step 4 mechanics), reply `[mode=ignored]`.
3. `Snooze reminders for a week` → run `snooze 7`, reply `[mode=snoozed]`.
4. `Not now` → `[mode=cancelled]`.

## Step 2 — Pick branches (AskUserQuestion, multiSelect, header "Pick branches")

- ≤4 branches: one option per branch, label = branch name, description = `<ahead> commits · last capture <age_days>d ago`.
- >4 branches: options are the **top 4 by `last_commit_ts`** (the list is already sorted). In the question text, list the remaining branch names and say: *"To include a branch not shown, pick Other and type its name (comma-separated for several)."* Validate Other-typed names against `unmerged`; warn about and skip unknown ones.

## Step 3 — Preview, then apply (per selected branch, in order)

For each branch run two Bash calls:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/sync-cmd.sh" dry-run "<branch>"
bash "${CLAUDE_PLUGIN_ROOT}/scripts/sync-cmd.sh" merge "<branch>"
```

- After `dry-run`, print a one-line preview from its JSON: `<branch>: +N new keys, M updated (<up to 5 key names>, …)`.
- If the dry-run shows **0 added and 0 updated keys** (branch is ahead only by non-default-namespace commits), still run `merge` — success writes the sync marker, which is what stops the branch from resurfacing every session. Report it as: `<branch>: no key changes — sync marker updated, branch will stop appearing`.
- After `merge`, report `✓ merged → main (commit <first 8 chars of commit_hash>)`.
- On failure (non-zero exit or `"success": false`): print the JSON `error`/`message`, **continue with the remaining branches**, and never ignore/snooze a failed branch.

Final reply: first line `[mode=synced]` (all succeeded) or `[mode=partial]` (some failed) or `[mode=error]` (all failed), then the per-branch result lines, then `N branches promoted to main, M failed.`

## Step 4 — Ignore or snooze (AskUserQuestion, single-select, header "Quiet options")

1. `Ignore branches permanently` — exactly one branch: run `ignore` directly. Several: ask one more multiSelect picker (same top-4 + Other pattern as Step 2), then per pick:
   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/scripts/sync-cmd.sh" ignore "<branch>"
   ```
   Reply `[mode=ignored]` listing the branches and the unignore path (`<store>/.git/plugin-ignored-branches`).
2. `Snooze auto-offers for a week` → `bash "${CLAUDE_PLUGIN_ROOT}/scripts/sync-cmd.sh" snooze 7` → `[mode=snoozed]`.
3. `Snooze for a month` → `… snooze 30` → `[mode=snoozed]`. Note to the user: the detector only surfaces branches active in the last 30 days, so a month-long snooze effectively silences the current set unless new captures land on them.
4. `Back` → re-ask Step 1.

When replying `[mode=snoozed]`, clarify that snooze only suppresses the proactive session-start offer — the status-line count keeps showing, and `/memoir:sync` keeps working.

## Rules

- At most 2 AskUserQuestion calls on the happy path (Stage 1 + optional picker). No extra confirmation between preview and apply — the promote is additive-only (never deletes keys), lands as one revertable commit on the store, and restores the prior branch.
- Never invoke `memoir` directly — always go through `sync-cmd.sh` (it owns CLI resolution, store path, and `cd`-into-store).
- Never hand-edit `plugin-ignored-branches` or `plugin-merge-prompt-cooldown` — only via the `ignore` / `snooze` subcommands.
- First line of every final reply is the mode marker: `[mode=synced|partial|clean|ignored|snoozed|cancelled|error]`.

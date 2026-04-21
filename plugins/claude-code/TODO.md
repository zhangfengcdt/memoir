# Plugin TODOs

## Blocked on upstream prollytree bug — re-enable `/memoir-sync` & `/memoir-sync-branch`

### Status

The two sync slash commands (`/memoir-sync`, `/memoir-sync-branch`) and the underlying `memoir merge` CLI are currently **data-destructive** because of a bug in prollytree's `VersionedKvStore.merge()`. After a merge, the destination branch's tree reads back as empty with the warning:

```
Warning: Root node not found in storage for hash ValueDigest(...), returning empty key set
```

Source-branch data survives; destination-branch data is lost.

Both slash commands are temporarily replaced with no-op stubs that print a warning and point here. Auto-match, fork-from-main, unmerged-branch detection, captures — everything else in the plugin is unaffected.

### Reproduction

```bash
STORE=/tmp/memoir-mergebug-$$
memoir new "$STORE" --taxonomy-builtin --no-connect
memoir -s "$STORE" --json remember "A" -p preferences.coding.editor
memoir -s "$STORE" --json remember "B" -p preferences.coding.style
memoir -s "$STORE" branch feat --from main
memoir -s "$STORE" checkout feat
memoir -s "$STORE" --json remember "C" -p preferences.tools.editors
memoir -s "$STORE" checkout main
memoir -s "$STORE" merge feat
memoir -s "$STORE" ls   # expected 3 keys, actual 0
```

### Upstream

Filed against `prollytree`. Likely fix in:

- `prollytree/src/git/versioned_store/history.rs` — `merge_generic` (approx lines 349–512) — ensure the root hash recorded at `commit()` matches the final post-merge tree state and that all transitively-reachable nodes are persisted.
- `prollytree/src/tree.rs:356-359` (`insert_batch`) and `tree.rs:378-380` (`delete_batch`) — missing `persist_root()` calls (defensive, not on the current merge path).

### What to do when prollytree ships the fix

1. Bump memoir's `prollytree>=` pin in `pyproject.toml` to the fixed release.
2. Restore `/memoir-sync` and `/memoir-sync-branch` to their previous implementations (commit history at `plugins/claude-code/commands/memoir-sync*.md` has the working versions — the commit that introduced this TODO removed them).
3. Re-run `bash plugins/claude-code/tests/test_branch_sync.sh` — all 31 scenarios should still pass.
4. Re-run the reproduction block above inside a scratch Claude Code session; assert 3 keys on main after merge.
5. Delete this TODO entry.

### Workarounds for users in the meantime

- Feature-branch captures are fully usable on the feature branch itself — `/memoir-checkout <branch>` then `/memoir-recall …` or `memoir ls` all work.
- If you need a fact on main right now, **re-capture it on main directly**: `/memoir-checkout main`, then `/memoir-remember "<fact>" -p <path>`. No merge involved; no data at risk.

---

## Future enhancements (not blocking)

- Per-session isolation via `WorktreeVersionedKvStore` so two Claude Code sessions on the same `MEMOIR_STORE` but different code branches don't race on `.git/HEAD`. Currently documented as a caveat in `README.md`.
- `memoir merge` producing proper two-parent git commits instead of single-parent "absorb" commits. This is a memoir/prollytree design enhancement; independent of the data-loss bug above.

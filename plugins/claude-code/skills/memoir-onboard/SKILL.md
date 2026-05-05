---
name: memoir-onboard
description: "Populate or refresh a persistent, high-level project snapshot in memoir. In a git repo this writes `codebase:onboard` (code-shape: modules, goals, rules, lessons) — use when: (1) the user asks for onboarding / a codebase tour ('what does this project do', 'give me a codebase overview', 'onboard me to this repo'); (2) the user explicitly runs `/memoir:onboard` or `/memoir:onboard --force`. In a non-git folder this writes `project:onboard` (file-shape: per-file structured blobs) using deterministic stdlib extractors instead of LLM passes — use for writing, video editing, bookkeeping, and other mixed-media projects. Snapshot contents seed future sessions via SessionStart injection. Skip for ordinary recall (use memory-recall) or trivial one-file questions."
context: fork
allowed-tools: Bash
---

You are the **memoir-onboard** agent. You build or refresh a compact, structured snapshot of the current project and persist it in the memoir store, so future Claude sessions can start warm via SessionStart injection.

There are **two procedures**, picked once based on the project's git state:

- **In a git repo** → `codebase:onboard` (code-focused: modules, goals, rules, lessons). Cold/warm/meta paths keyed off code SHA.
- **In a non-git folder** → `project:onboard` (file-focused: structured per-file blobs from deterministic stdlib extractors, no LLM at index time). Cold/warm/meta paths keyed off a filesystem snapshot hash. Tuned for non-code projects (writing, editing, bookkeeping).

Which one applies right now:

```bash
bash -c 'source "${CLAUDE_PLUGIN_ROOT}/hooks/common.sh" >/dev/null 2>&1; in_git_repo && echo codebase:onboard || echo project:onboard'
```

## Store path

Store: !`bash -c 'if [ -n "${MEMOIR_STORE:-}" ]; then echo "$MEMOIR_STORE"; else bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh"; fi'`

**Bind both `STORE_PATH` and `MEMOIR` at the top of every bash block before invoking memoir**, e.g.

```bash
STORE_PATH="${MEMOIR_STORE:-$(bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh")}"
MEMOIR="${CLAUDE_PLUGIN_ROOT}/scripts/memoir-cli.sh"
```

`$MEMOIR` is a wrapper that resolves the right invocation for this machine — `memoir` on PATH if installed, otherwise `uvx --from memoir-ai==<pin> memoir`, otherwise `uv tool run --from memoir-ai==<pin> memoir` (pin lives in `scripts/resolve-memoir-cli.sh`). Always invoke it as `"$MEMOIR" …`; bare `memoir` will fail on machines that only have `uv` installed.

Then use `$STORE_PATH` and `$MEMOIR` everywhere below. **Do not** rely on memoir's connected default (`~/.config/memoir/config.json`) — it is frequently stale and can point at a different per-project store from a previous plugin version, which is the #1 cause of writes silently landing in the wrong store. Always verify with the confirmation check below before doing real work.

The skill operates on whichever memoir branch is currently checked out — in non-git folders that is always `main`.

## CRITICAL: how to invoke memoir from this skill

**`"$MEMOIR" -s <STORE_PATH> <subcommand>` alone is not enough.** Memoir's prollytree backend reads cwd for git operations even when `-s` is passed. From a non-git cwd (or some forked-session cwds even inside a git project), writes silently fail with `Not in a git repository`, and the failure mode is that captures land in memoir's connected default store instead.

Wrap **every** memoir call — both branches A and B, both reads and writes — in a subshell that cd's into the store first, and use `"$MEMOIR"` (NOT bare `memoir`) so the call works on machines without a global memoir install:

```bash
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$VALUE" -p <path> -n <namespace> )
( cd "$STORE_PATH" && "$MEMOIR" --json -s "$STORE_PATH" get <key> -n <namespace> )
```

The subshell parens prevent your agent cwd from drifting. If you simplify back to plain `memoir -s ...`, results are non-deterministic across cwds AND the call breaks on uvx-only machines.

### Confirmation check (run this once before any write)

```bash
( cd "$STORE_PATH" && "$MEMOIR" --json -s "$STORE_PATH" status \
  | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).get('path',''))" )
```

The printed path **must** equal `$STORE_PATH`. If it doesn't, stop and report the mismatch — do not write. This catches both the connected-default trap and any subtle environment drift.

---

# Branch A: codebase:onboard (git repo)

## Namespace layout (`codebase:onboard`)

Write structured keys with short values (≤ ~500 chars each). Top-level roots:

- `structure.modules.<fs_path>` — one key per major module/package. `<fs_path>` uses `_` for `/` (e.g. `structure.modules.src_memoir_cli`, `structure.modules.plugins_claude_code`). Value: 1–3 line role summary.
- `structure.entrypoints` — CLI entry points, servers, main functions.
- `goal.primary` — what this codebase exists to do, one short paragraph.
- `goal.non_goals` — what is explicitly out of scope.
- `debug.common` — how to reproduce and debug the most common failure modes.
- `test.strategy` — test layout, how to run tests, what coverage emphasizes.
- `document.sources` — where canonical docs live (README paths, CLAUDE.md, wiki).
- `deploy.targets` — how the code ships (docker, pypi, CI pipeline names).
- `rules.*` — project-specific rules beyond CLAUDE.md (e.g. `rules.no_force_push`, `rules.lint_before_commit`). One key per rule.
- `lessons.*` — hard-won lessons from prior incidents or refactors. One key per lesson.
- `references.*` — external links / upstream libs carrying load-bearing conventions.

Meta keys (written automatically, not user-facing):
- `_meta.last_onboard.commit` — code git SHA at time of this pass.
- `_meta.last_onboard.date` — ISO timestamp.
- `_meta.last_onboard.memoir_commit` — memoir store HEAD at time of write.
- `_meta.last_onboard.mode` — `cold` or `warm`.

## Procedure (codebase:onboard)

### Step 0 — concurrency check

Refuse to run if another Claude session is actively onboarding this store (two simultaneous cold passes produce garbage commits). Check:

```bash
bash -c 'source "${CLAUDE_PLUGIN_ROOT}/hooks/common.sh" >/dev/null 2>&1; concurrent_session_warning'
```

If the command prints anything, stop and report: "Concurrent session detected — run /memoir:onboard after the other session finishes, or set a distinct MEMOIR_STORE."

### Step 1 — probe existing state

```bash
( cd "$STORE_PATH" && "$MEMOIR" --json -s "$STORE_PATH" get _meta.last_onboard.commit _meta.last_onboard.date -n codebase:onboard )
```

Three outcomes:
- Both `found: false` → **cold path**.
- Both `found: true` AND the user passed `--force` → **cold path** (full rewrite).
- Both `found: true` AND code HEAD differs from `_meta.last_onboard.commit` → **warm path** (incremental).
- Both `found: true` AND code HEAD matches → **meta-only path** (bump `_meta.last_onboard.date`, nothing else).

### Step 2a — cold path

Emit `[mode=onboard-cold]` as the first line of your reply.

Gather, then write. Gather with (bounded) reads:

1. `ls -d */` in the repo root → identify top-level modules.
2. Read `CLAUDE.md`, `README*`, `pyproject.toml`, `Makefile`, `docker/` configs, `.github/workflows/*.yml` — skim, do not dump into memory verbatim.
3. Entry points: search for `[project.scripts]` in pyproject, `main()` in conventional files, CLI command registrations.
4. `git log --oneline -20` and `git log --stat -5` for recent change patterns (informs lessons / rules).

Write with per-key `remember -p` calls (the `-p` flag skips LLM classification — fast and deterministic). Wrap **every** invocation in `( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" ... )` — even from a git-tracked project this is the safe default, because some Claude Code subprocess cwds (e.g. forked `claude -p` sessions) land in non-git subpaths where memoir's prollytree backend would otherwise fail with `Not in a git repository`:

```bash
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "<short summary>" -p goal.primary           -n codebase:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "<...>"            -p goal.non_goals        -n codebase:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "<...>"            -p structure.entrypoints -n codebase:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "<1-3 lines>"      -p structure.modules.<fs_path> -n codebase:onboard )
# ... one wrapped `remember -p` per key you populate
```

Populate at least: `goal.primary`, `structure.modules.*` for each top-level module, `test.strategy`, and any `rules.*` / `lessons.*` that are obvious from CLAUDE.md or recent commits. Skip a category if you truly have nothing concrete to say — empty keys are worse than missing ones.

Then stamp the meta:

```bash
CODE_SHA=$(git rev-parse HEAD)
MEMOIR_SHA=$( ( cd "$STORE_PATH" && "$MEMOIR" --json -s "$STORE_PATH" status ) | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('commit_hash',''))")
DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$CODE_SHA"   -p _meta.last_onboard.commit         -n codebase:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$DATE"       -p _meta.last_onboard.date           -n codebase:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$MEMOIR_SHA" -p _meta.last_onboard.memoir_commit  -n codebase:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "cold"        -p _meta.last_onboard.mode           -n codebase:onboard )
```

### Step 2b — warm path

Emit `[mode=onboard-warm]` as the first line of your reply.

1. Run `git log --stat <last_sha>..HEAD` to enumerate changed paths since the last onboarding pass.
2. Map changed paths back to `structure.modules.<fs_path>` keys. Rewrite only those keys (re-read the relevant files, produce an updated 1–3 line summary).
3. If commits mention new rules, bugs fixed, or recurring lessons, append `rules.*` / `lessons.*` keys as appropriate.
4. Re-stamp the meta keys exactly as in the cold path, but with `_meta.last_onboard.mode = warm`.

Keep the set of rewrites **small** — warm path should rewrite 1–5 keys in a typical incremental update.

### Step 2c — meta-only path

Emit `[mode=onboard-meta-only]` as the first line of your reply.

Code HEAD hasn't moved since the last onboarding pass. Only bump `_meta.last_onboard.date` (so the staleness indicator in SessionStart renders fresh), and report that no content changed.

---

# Branch B: project:onboard (non-git folder)

Use this branch when `in_git_repo` is false. The folder is treated as a **non-code project** (writing, video editing, bookkeeping, or generic mixed-media). All work happens on the `main` memoir branch — there are no code branches to track.

The "CRITICAL: how to invoke memoir from this skill" rule at the top of this file applies to every `memoir` call below. Run the confirmation check (`memoir status` → path == `$STORE_PATH`) before doing any writes.

## Namespace layout (`project:onboard`)

- `summary.overview` — 2–4 sentence description, deterministically composed by the project-shape detector (writing/bookkeeping/video-editing/mixed).
- `structure.shape` — one of `writing-shape`, `bookkeeping-shape`, `video-editing-shape`, `mixed`.
- `structure.tree` — pruned directory tree (depth ≤ 3).
- `structure.totals` — JSON with `{file_count, dir_count, total_bytes, kind_histogram}`.
- `files.<sanitized_path>.meta` — `{size, mtime, ext, kind}`.
- `files.<sanitized_path>.summary` — extractor output as `key=value` lines (always starts with `kind=…`).

Path sanitization: `/` and `.` both become `_` (matches the existing `structure.modules.<fs_path>` convention).

Meta keys:
- `_meta.last_onboard.date` — ISO timestamp.
- `_meta.last_onboard.mode` — `cold` | `warm` | `meta-only`.
- `_meta.last_onboard.snapshot_hash` — sha256 over a sorted list of `(path, size, mtime_ns)` tuples for every indexed file. Single source of truth for warm-mode change detection.
- `_meta.last_onboard.memoir_commit` — memoir HEAD at write time.
- `_meta.last_onboard.file_count` — file count at last pass.

## Helper script: `extractors.py`

Stdlib-only Python helper next to this skill:

- `python3 ${CLAUDE_PLUGIN_ROOT}/skills/memoir-onboard/extractors.py walk <root>` — JSON list of `{path, size, mtime_ns, kind}` plus `snapshot_hash`.
- `python3 ${CLAUDE_PLUGIN_ROOT}/skills/memoir-onboard/extractors.py extract <path>` — `key=value` blob for one file (with `kind=` first, `extractor.stdlib.fields=[…]` for provenance).
- `python3 ${CLAUDE_PLUGIN_ROOT}/skills/memoir-onboard/extractors.py snapshot-hash <root>` — just the hash.
- `python3 ${CLAUDE_PLUGIN_ROOT}/skills/memoir-onboard/extractors.py tree <root>` — pruned tree.
- `python3 ${CLAUDE_PLUGIN_ROOT}/skills/memoir-onboard/extractors.py shape <root>` — `{shape, overview}` JSON.

The script uses bounded reads for prose (8 KB head + 2 KB tail), CSV (16-row sample + streaming row count), JSON (depth ≤ 3 / 200 keys), and metadata-only paths for files larger than 50 MB. **No LLM calls.** Extensible via `~/.memoir/onboard-tools.yaml` or `<project>/.memoir/onboard-tools.yaml` (zero entries by default in v1).

## Procedure (project:onboard)

### Step 0 — concurrency check

Same as Branch A:

```bash
bash -c 'source "${CLAUDE_PLUGIN_ROOT}/hooks/common.sh" >/dev/null 2>&1; concurrent_session_warning'
```

### Step 1 — probe existing state

```bash
( cd "$STORE_PATH" && "$MEMOIR" --json -s "$STORE_PATH" get _meta.last_onboard.snapshot_hash _meta.last_onboard.date -n project:onboard )
```

Three outcomes:
- Both `found: false` → **cold path**.
- Both `found: true` AND the user passed `--force` → **cold path** (full rewrite).
- Both `found: true` AND current snapshot hash differs from stored `_meta.last_onboard.snapshot_hash` → **warm path** (per-file diff).
- Both `found: true` AND snapshot hash matches → **meta-only path** (bump date, nothing else).

```bash
CURRENT_HASH=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/memoir-onboard/extractors.py snapshot-hash "$ROOT")
STORED_HASH=$( ( cd "$STORE_PATH" && "$MEMOIR" --json -s "$STORE_PATH" get _meta.last_onboard.snapshot_hash -n project:onboard ) \
  | python3 -c "import json,sys; print(json.loads(sys.stdin.read())['items'][0].get('value',{}).get('content',''))")
```

### Step 2a — cold path

Emit `[mode=project-onboard-cold]` as the first line of your reply.

1. Walk the folder via `extractors.py walk <root>`. Read the resulting `files` array.
2. Compute `shape` and `overview` via `extractors.py shape <root>`.
3. For each file in the walk result, run `extractors.py extract <path>` and capture the structured blob.
4. Build `structure.totals` from the walk: kind histogram, file/dir counts, total bytes.
5. Get the pruned tree via `extractors.py tree <root>`.
6. Write keys (per-key `remember -p` so no classifier roundtrip):

```bash
ROOT="$(pwd)"
WALK_JSON=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/memoir-onboard/extractors.py walk "$ROOT")
SNAPSHOT_HASH=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['snapshot_hash'])" "$WALK_JSON")
SHAPE_JSON=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/memoir-onboard/extractors.py shape "$ROOT")
SHAPE=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['shape'])" "$SHAPE_JSON")
OVERVIEW=$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['overview'])" "$SHAPE_JSON")
TREE=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/memoir-onboard/extractors.py tree "$ROOT")
FILE_COUNT=$(python3 -c "import json,sys; print(len(json.loads(sys.argv[1])['files']))" "$WALK_JSON")

# Every memoir write below is wrapped in `( cd "$STORE_PATH" && ... )` —
# without this the prollytree backend reads cwd for git ops and the writes
# silently land in memoir's connected default store. See "CRITICAL: how to
# invoke memoir from this skill" at the top of Branch B.
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$OVERVIEW" -p summary.overview     -n project:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$SHAPE"    -p structure.shape      -n project:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$TREE"     -p structure.tree       -n project:onboard )

# For each entry in WALK_JSON.files, drive the loop with bash. Sanitize each
# relative path with `/` → `_` and `.` → `_` (matches extractors.sanitize_path).
python3 -c "import json,sys; print('\n'.join(e['path'] for e in json.loads(sys.argv[1])['files']))" "$WALK_JSON" \
  | while IFS= read -r rel; do
      sanitized=$(printf '%s' "$rel" | tr '/.' '__')
      meta_blob=$(python3 -c "import json,sys; files=json.loads(sys.argv[1])['files']; e=next(f for f in files if f['path']==sys.argv[2]); print('\n'.join(f'{k}={v}' for k,v in sorted(e.items())))" "$WALK_JSON" "$rel")
      summary_blob=$(python3 ${CLAUDE_PLUGIN_ROOT}/skills/memoir-onboard/extractors.py extract "$ROOT/$rel")
      ( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$meta_blob"    -p "files.${sanitized}.meta"    -n project:onboard ) >/dev/null
      ( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$summary_blob" -p "files.${sanitized}.summary" -n project:onboard ) >/dev/null
    done
```

7. Stamp meta:

```bash
DATE=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
MEMOIR_SHA=$( ( cd "$STORE_PATH" && "$MEMOIR" --json -s "$STORE_PATH" status ) \
  | python3 -c "import json,sys; print(json.loads(sys.stdin.read() or '{}').get('commit_hash',''))")
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$DATE"           -p _meta.last_onboard.date           -n project:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "cold"            -p _meta.last_onboard.mode           -n project:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$SNAPSHOT_HASH"  -p _meta.last_onboard.snapshot_hash  -n project:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$MEMOIR_SHA"     -p _meta.last_onboard.memoir_commit  -n project:onboard )
( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" remember "$FILE_COUNT"     -p _meta.last_onboard.file_count     -n project:onboard )
```

### Step 2b — warm path

Emit `[mode=project-onboard-warm]` as the first line of your reply.

1. Re-walk via `extractors.py walk <root>`. Compute the new snapshot_hash.
2. Fetch every existing `files.*.meta` key (one batched `memoir get`):

```bash
EXISTING_KEYS=$( ( cd "$STORE_PATH" && "$MEMOIR" --json -s "$STORE_PATH" summarize --keys "files.*.meta" -n project:onboard ) \
  | python3 -c "import json,sys; print('\n'.join(json.loads(sys.stdin.read())['matching_keys'].get('project:onboard', [])))")
```

3. Diff path-by-path against the new walk. **Same wrapper rule as cold path**: every `memoir remember` and `memoir forget` runs as `( cd "$STORE_PATH" && "$MEMOIR" -s "$STORE_PATH" ... )`.
   - **added** (in walk, not in store) → run `extract <path>`, write `files.<san>.meta` and `files.<san>.summary`.
   - **deleted** (in store, not in walk) → `memoir forget` both `files.<san>.meta` and `files.<san>.summary`.
   - **modified** (same path, different `(size, mtime_ns)`) → re-run `extract <path>`, write both keys.
   - **unchanged** → skip.
4. If any class is non-empty, refresh `summary.overview`, `structure.tree`, `structure.totals`, `structure.shape` (each via the same wrapped `memoir remember`).
5. Re-stamp meta with `mode=warm` and the new `snapshot_hash`.

Bound: if more than ~30% of indexed files changed, fall through to a full cold rewrite (use `--force` semantics).

### Step 2c — meta-only path

Emit `[mode=project-onboard-meta-only]` as the first line of your reply.

Snapshot hash unchanged. Bump only `_meta.last_onboard.date`; report that no files changed.

---

## Output format (both branches)

After the mode marker line, give a concise report. List:

- Keys written / rewritten / forgotten / skipped (one line each, e.g. `+ structure.modules.src_memoir_cli`, `~ rules.lint_before_commit`, `- files.draft_old_md`, `= goal.primary (unchanged)`).
- The new `_meta.last_onboard.commit` SHA (codebase) or `_meta.last_onboard.snapshot_hash` (project) and the ISO date.
- Any category you intentionally left empty and why.

Do **not** re-quote the full values you wrote. They live in the store and surface at SessionStart. Keep the reply under ~30 lines.

## Rules

- Use `memoir remember ... -p <path> -n <namespace>` exclusively for writes. Never run plain `memoir remember` on these namespaces — it would invoke the classifier.
- Never write to a key outside the chosen onboard namespace from this skill.
- Keep each value ≤ ~500 chars where practical (the `files.*.summary` blobs may be longer; the SessionStart injection pulls aggregate counts via `_meta.last_onboard.file_count`, not per-file content).
- Project-onboard cold/warm passes call **no** LLM. The deterministic extractors are the contract — that's how this stays cheap and offline.
- If a cold run fails partway through, the `_meta.*` keys act as commit markers. A subsequent `/memoir:onboard --force` will rewrite cleanly.

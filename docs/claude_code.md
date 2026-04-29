# Claude Code Plugin

Memoir ships a first-class plugin for [Claude Code](https://docs.claude.com/en/docs/claude-code/overview). Drop it in and memoir becomes native to your coding sessions: context injected on session start, durable facts auto-captured at turn end, and a full suite of slash commands for everything in between.

The plugin lives in the repo at `plugins/claude-code/`.

## Install

Inside a Claude Code session, run:

```
/plugin marketplace add zhangfengcdt/memoir
/plugin install memoir@memoir
```

The first command registers the memoir GitHub repo as a plugin marketplace; the second installs the `memoir` plugin from that marketplace. Hooks take effect on the next session start.

Each project gets its own memoir store under `~/.memoir/memoir_<hash>/`, derived from your cwd. Override by exporting `MEMOIR_STORE=/path/to/store`.

## What ships

| Component | Count | Role |
|---|---|---|
| Slash commands | 9 | Manual memory ops, admin, UI launch |
| Skills | 2 | Auto-invoked: recall + codebase onboarding |
| Lifecycle hooks | 4 | Context injection + auto-capture |
| Helper scripts | 3 | Store path, UI control, status line |

## Slash commands

| Command | Purpose |
|---|---|
| `/memoir:onboard [--force]` | Populate or refresh the `codebase:onboard` snapshot. |
| `/memoir:remember <fact>` | Capture a memory. `-p <path>` skips classification. |
| `/memoir:recall <query>` | Recall from prior sessions (delegates to the `memory-recall` skill). |
| `/memoir:status` | Branch, commit count, memory count, namespaces. |
| `/memoir:ui` | Launch or re-open the web UI (readonly, LLM off by default). |

Admin operations (`forget`, `taxonomy`, `unmerged`, `sync-branch`) are available via the `memoir` CLI directly — they were dropped from the slash-command surface to keep the in-session UX focused on the five everyday actions.

## Skills

| Skill | Namespace | Role |
|---|---|---|
| `memory-recall` | `default` | User-captured facts. Picks taxonomy paths with `summarize`, batches `get`, never invokes nested LLMs. Runs in a forked context. Configured **default on** with aggressive triggering so remembered preferences are never silently skipped. |
| `memoir-onboard` | `codebase:onboard` | Maintains a high-level repo snapshot that seeds future sessions via SessionStart injection. |

The split is deliberate: **recall owns user-captured facts; onboard owns codebase structure.**

### Read/write asymmetry

By design:

- **Reads are auto-triggered via skills.** The agent pulls context when it thinks it might need to, without the user asking.
- **Writes are an explicit slash command.** `/memoir:remember` stays as a command — not a skill — because the `Stop` hook already handles auto-capture; this command is the manual escape hatch. Deletion (`memoir forget`) lives on the CLI rather than as a slash command, kept explicit for safety.

## Lifecycle hooks

Configured in `plugins/claude-code/hooks/hooks.json`:

| Event | Script | Timeout | Async | Purpose |
|---|---|---|---|---|
| `SessionStart` | `session-start.sh` | 15s | — | Inject store status, branch/commit state, onboard snapshot, and "memory available" hints. |
| `UserPromptSubmit` | `user-prompt-submit.sh` | 10s | — | Surface matching memory hints for the current prompt. |
| `Stop` | `stop.sh` | 180s | yes | Parse the transcript and auto-capture durable facts into the taxonomy. |
| `SessionEnd` | `session-end.sh` | 5s | yes | Cleanup. |

Shared helpers: `hooks/common.sh`, `hooks/parse-transcript.sh`.

## Helper scripts

| Script | Role |
|---|---|
| `derive-store-path.sh` | Maps the current cwd to `~/.memoir/memoir_<hash>`. Respects `$MEMOIR_STORE`. |
| `memoir-ui-ctl.sh` | `start` / `stop` / `status` for the web UI, with pidfile bookkeeping so repeated `/memoir:ui` calls reuse the same server. |
| `statusline.sh` | Renders memoir state into Claude Code's status line, e.g. `memoir: feature/foo · 14 memories`. |

## Lifecycle

A session flows through four hook events. Steps 2–4 loop once per user prompt; step 5 runs once at the end.

```mermaid
sequenceDiagram
    actor You
    participant Claude as Claude Code
    participant Plugin as memoir plugin hooks
    participant Store as memoir store

    rect rgb(30, 50, 70)
    Note over Claude,Store: 1. SessionStart — session-start.sh (sync, 15s)
    Plugin->>Store: read status, branch/commit, codebase:onboard
    Store-->>Claude: inject snapshot + "memory available" hints
    end

    rect rgb(30, 55, 45)
    Note over You,Store: 2–4. Per user prompt (loops)
    You->>Claude: prompt
    Plugin->>Store: 2. UserPromptSubmit — match paths (sync, 10s)
    Store-->>Claude: "[memoir] memory available" hints
    Claude->>Store: 3. memory-recall skill (forked, on-demand)
    Store-->>Claude: summarize → pick prefixes → get → facts
    Claude-->>You: response
    Plugin->>Store: 4. Stop — classify + auto-capture (async, 180s)
    end

    rect rgb(60, 45, 30)
    Note over Claude,Store: 5. SessionEnd — session-end.sh (async, 5s)
    Plugin->>Store: cleanup
    end
```

Two properties to notice:

- **Reads happen eagerly, writes happen lazily.** Every prompt passes through `UserPromptSubmit` (step 2) and potentially fires `memory-recall` (step 3) — the agent pulls context without the user asking. Auto-capture is deferred to `Stop` (step 4), which is async so it never blocks the turn.
- **Namespaces split along read/write paths.** `memory-recall` works against `default` (user-captured facts, written by the `Stop` hook or `/memoir:remember`). `memoir-onboard` works against `codebase:onboard` (repo snapshot, written by `/memoir:onboard`, replayed by the `SessionStart` hook). Two namespaces, two lifecycles, no overlap.

The admin surface — `/memoir:ui`, `/memoir:status` (slash commands), plus `memoir taxonomy`, `memoir unmerged`, and `memoir sync-branch` (CLI) — sits outside this lifecycle: it's explicit user invocation, not hook-driven.

## Session context injection

`SessionStart` writes a single JSON object to stdout that Claude Code reads as the session preamble: `{"systemMessage": ..., "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": ...}}`. The `additionalContext` block is assembled in order from up to four parts, each conditional on having something to say. Every part comes from raw `memoir get`/`summarize` calls — no LLM is invoked at session start.

| Block | Source | Always on? |
|---|---|---|
| Store summary | `memoir status` + `memoir summarize taxonomy` | Yes — branch, user-memory count, namespace counts. |
| Default-namespace keys | `memoir summarize --keys "*" -n default` | Yes (when default has keys). Capped at 200, grouped by L1 prefix. |
| Unmerged-branch detector | `git for-each-ref` on `refs/heads/memoir/*` | Only when the **code branch is `main`**. Mid-flight on a feature branch, other branches' unmerged work is noise. |
| Codebase snapshot | `memoir summarize --keys "*" -n codebase:onboard` + batched `get` | Default on (`MEMOIR_ONBOARD_INJECT=1`). See [Codebase snapshot](#codebase-snapshot-codebaseonboard) below. |

The status line itself follows the same conditional shape: `[memoir] <branch> · <N> memories [· capture disabled] [· N branches unmerged] [· concurrent session warning]`.

Shape of the default-keys block:

```text
# default namespace keys
(12 keys, grouped by L1 prefix)

knowledge (7):
  - knowledge.technical.branching
  - knowledge.technical.merge
  ...
preferences (1):
  - preferences.communication.tone
metrics (1):
  - metrics.turn.main
```

This is just the index — agents `memoir get <key>` the ones they care about, paying for content only on demand.

## Codebase snapshot (`codebase:onboard`)

A persistent, high-level repo overview written by `/memoir:onboard` and replayed by `SessionStart` so fresh sessions start warm with a structured map of the codebase.

**Layout.** Keys live in the `codebase:onboard` namespace, grouped by L1 root:

| Root | What it captures |
|---|---|
| `goal.primary` / `goal.non_goals` | What the project is and isn't. |
| `structure.entrypoints` | CLIs, servers, main functions. |
| `structure.modules.<fs_path>` | One key per major module (`src_memoir_cli`, `plugins_claude_code`, …). 1–3 line role summary. |
| `test.strategy` | Test layout + how to run. |
| `debug.common` | How to reproduce common failure modes. |
| `deploy.targets` | How the code ships (CI workflows, packaging). |
| `document.sources` | Where canonical docs live. |
| `rules.*` | Project rules beyond CLAUDE.md, one key per rule. |
| `lessons.*` | Hard-won facts from prior incidents, one key per lesson. |
| `references.*` | External links / upstream conventions. |
| `_meta.last_onboard.{commit,date,memoir_commit,mode}` | Staleness anchors. |

Each value is ≤ ~500 chars; the SessionStart compact view takes the first sentence and caps a root's joined children at 140 chars.

**Refresh paths.** `/memoir:onboard` probes `_meta.last_onboard.commit` and picks one of three:

- **cold** — no prior snapshot. Full scan: `ls -d */`, skim `CLAUDE.md` / `README*` / `pyproject.toml` / `Makefile` / `.github/workflows/*.yml`, `git log --oneline -20`. Write every `goal.*` / `structure.modules.*` / `rules.*` / `lessons.*` / `references.*` key with `memoir remember -p <path> -n codebase:onboard` (the `-p` flag bypasses the LLM classifier — fast and deterministic).
- **warm** — code HEAD has moved. `git log --stat <last_sha>..HEAD` enumerates changed paths; only the affected `structure.modules.*` keys and any new lessons are rewritten. Typically 1–5 keys per pass.
- **meta-only** — code HEAD unchanged. Bumps `_meta.last_onboard.date` so the staleness indicator renders fresh; no narrative keys touched.

`--force` always uses the cold path.

**Branch behavior.** The snapshot lives in the `codebase:onboard` namespace, **not `default`** — `BranchService.promote_branch` only carries the default namespace, so `codebase:onboard` stays per-branch. This is intentional: a feature branch can carry its own structural notes without leaking them to `main` until the user explicitly chooses to.

**Staleness.** `SessionStart` flags the snapshot `stale="true"` when `_meta.last_onboard.date` is more than 30 days old, and appends a `(snapshot is stale — run /memoir:onboard to refresh)` hint. `memoir sync-branch` calls `update_onboard_meta_after_sync` on the merged branch so the meta keys stay truthful even when the user hasn't re-run `/memoir:onboard`.

## Non-git folders (`project:onboard`)

The plugin treats non-git folders as a first-class case rather than a degraded git mode. This is the home for running Claude Code over **non-code projects** — writing (drafts, manuscripts, research notes), video editing (clips, transcripts, project files), bookkeeping (statements, receipts, spreadsheets), and similar mixed-media folders.

**Contract.**

| Surface | Git folder | Non-git folder |
|---|---|---|
| Branches | Auto-tracks code branch | Locked to `main` |
| Status line | `[memoir] <branch> · N memories` | `[memoir] main · N memories` |
| Stop auto-capture | Captures to current memoir branch | Captures to `main` |
| `memoir sync-branch`, `memoir unmerged` (CLI) | Operate normally | Short-circuit with "non-git folder: only `main` exists" |
| `/memoir:onboard` | `codebase:onboard` cold/warm based on **code SHA** | `project:onboard` cold/warm based on **filesystem snapshot hash** |
| `SessionStart` injection | Renders `codebase:onboard` block | Renders `project:onboard` block |
| Stats / `memoir log`, `graph`, `tree` | Identical | Identical |

**`project:onboard` namespace layout.**

| Key | Contents |
|---|---|
| `summary.overview` | 2–4 sentences auto-composed by a deterministic shape detector (writing / bookkeeping / video-editing / mixed). |
| `structure.shape` | One of `writing-shape`, `bookkeeping-shape`, `video-editing-shape`, `mixed`. |
| `structure.tree` | Pruned directory tree (depth ≤ 3). |
| `structure.totals` | JSON: `{file_count, dir_count, total_bytes, kind_histogram}`. |
| `files.<sanitized_path>.meta` | `{size, mtime, ext, kind}` per file (`/` and `.` → `_` for the path segment). |
| `files.<sanitized_path>.summary` | Structured `key=value` blob from a per-kind extractor. Always begins with `kind=…`. |
| `_meta.last_onboard.{date,mode,snapshot_hash,memoir_commit,file_count}` | Refresh anchors. |

**Deterministic extractors — no LLM at index time.** The skill runs `plugins/claude-code/skills/memoir-onboard/extractors.py` (stdlib-only Python) once per file. One function per `kind`, all bounded:

- prose / markdown — frontmatter `title:` → first H1 → first non-empty line; first 50 / last 20 words; word count; top non-stopword terms.
- csv / tsv — sniffed delimiter, columns, 16-row sample, streamed row count, numeric columns. Adds `shape=ledger` when columns include date+amount+category-like patterns.
- office-zip (`.docx`, `.pptx`, `.xlsx`, `.epub`) — stdlib `zipfile` + `xml.etree` reads `docProps/core.xml`, sheet names, slide count, paragraph count, EPUB manifest.
- pdf — metadata-only at v1 (file size, magic bytes, version). Real text extraction is a tool entry.
- video-project (`.fcpxml`, `.kdenlive`, `.prproj`, `.aep`) — XML parse for project name, clip count, duration; binary `.aep` is metadata-only.
- json / yaml — top-level keys, max depth, item count.
- srt / vtt — first cue, last cue, cue count, total duration.
- image / audio / video — extension-derived `kind` plus stdlib-cheap header parses (PNG dimensions from IHDR, WAV duration, etc.). Anything that needs a real codec stays metadata-only.

Files larger than 50 MB get metadata-only treatment regardless of kind, so raw video and audio never enter the snapshot.

**Cold / warm / meta-only paths.** Same shape as `codebase:onboard`, but keyed off a **filesystem snapshot hash** (sha256 over sorted `(path, size, mtime_ns)` tuples) instead of a code SHA:

- **cold** — no prior snapshot. Walk → run every extractor → write `files.*` keys, `summary.overview`, `structure.tree`, `structure.totals`, `structure.shape` → stamp `_meta.*`.
- **warm** — snapshot hash differs. Diff path-by-path: added → run extractor + write; deleted → `memoir forget`; modified → re-run extractor + write; unchanged → skip. Refresh aggregate keys and re-stamp meta. Falls through to a full cold rewrite when more than ~30% of files changed.
- **meta-only** — snapshot hash unchanged. Bump `_meta.last_onboard.date` only.

**Pluggable tool registry.** v1 ships with **zero tool entries** — every cold and warm pass is free, offline, and stdlib-only. To add an external tool (e.g. Whisper for audio transcription, ExifTool for images, a vision LLM for image captioning), drop a YAML or JSON config:

```yaml
# ~/.memoir/onboard-tools.yaml          (user-global)
# <project>/.memoir/onboard-tools.yaml  (project-local; merged after global)
audio:
  - name: whisper
    command: "whisper {path} --output-format json"
    timeout_s: 60
image:
  - name: claude-vision
    command: "vision-caption.sh {path}"
    timeout_s: 30
```

Per `kind`, the stdlib extractor always runs first; configured tools then run and merge their JSON output under `extractor.<tool_name>.<field>` keys, so the consumer LLM can tell deterministic fields apart from tool-derived ones via the `extractor.stdlib.fields=[…]` provenance line. Results are cached at `<store>/.git/plugin-extractor-cache/<sha256-of-file-content>.<tool>.json` so warm-mode reuses tool output when file content is unchanged. Failures are silent — tool errors and timeouts are logged to `/tmp/memoir-hook.log`; the blob is emitted with stdlib fields only.

**Excludes.** Default exclusion globs cover OS / editor cruft (`.DS_Store`, `~$*`), code build artifacts (`node_modules`, `__pycache__`, `dist`, `.venv`), and video / audio editor caches (`Adobe Premiere Pro Auto-Save/`, `*.fcpcache/`, `Render Files/`). Add project-local entries via `.memoir/onboard-excludes.txt` (gitignore syntax, one glob per line).

**Store-mode drift guardrail (warning-only).** A folder that flips between non-git and git states (running `git init` on an existing project, or `rm -rf .git`-ing a tracked folder) keeps the same store path — they share `~/.memoir/<slug>`. The plugin records the mode at first store creation in `<store>/.git/plugin-store-mode`. Subsequent SessionStarts compare the marker to the current state; on mismatch, it surfaces a one-block warning alongside the normal status line:

```
[memoir] note: store mode drift
  This store was created in `non-git` mode; the project directory is now `git`.
  Captures continue, but branch auto-matching and the SessionStart onboard
  injection now use the new mode — earlier non-git-mode data may be on a
  different memoir branch (run `memoir branch list` to inspect).
  To suppress: `memoir checkout main` and update the marker with
  `echo git > <store>/.git/plugin-store-mode`.
```

Captures keep working through the warning — it's informational, not enforced. The marker is auto-backfilled the first time an old (pre-guardrail) store is observed, so no warning fires for stores that pre-date this feature.

## Per-branch turn metrics (`metrics.turn.<branch>`)

The `Stop` hook accumulates per-turn statistics into one key per branch in the `default` namespace, alongside auto-captured memories.

**Key shape:** `metrics.turn.<branch>` — for example `metrics.turn.main`, `metrics.turn.feature/x`. Branch names with `/` are kept literal (memoir's `remember -p` accepts arbitrary path strings).

**Value shape:**

```json
{
  "schema_version": 1,
  "tokens": null,
  "llms": null,
  "turns_count": 42,
  "total_output_chars": 198432,
  "total_tool_input_chars": 24561,
  "total_tool_result_chars": 884201,
  "total_tool_calls": 187,
  "total_tool_errors": 6,
  "total_repeated_tool_calls": 12,
  "total_latency_ms": 1845300,
  "latency_samples": 31
}
```

Each turn the hook reads the existing accumulator, folds in deltas computed by `collect-metrics.sh`, and writes it back via `merge-metrics.py`. `tokens` and `llms` are reserved `null` until Claude Code exposes per-turn usage to hooks; today the proxies are char-count and tool-count fields. `latency_samples` only ticks for turns whose transcript line carries a user-message timestamp.

**Toggles & failure mode.** `MEMOIR_NO_METRICS=1` disables the metrics path independently of `MEMOIR_NO_CAPTURE` — either can fail without affecting the other. The whole block is wrapped in `2>/dev/null || true`, matching the rest of the Stop hook's fail-silent design.

**Branch identity & merge.** Source-branch identity lives in the key fragment, not the value — so `BranchService.promote_branch` (default-namespace only) carries `metrics.turn.feature/x` to `main` automatically when the user runs `memoir sync-branch feature/x`. After promotion, `main` retains its own `metrics.turn.main` untouched; `metrics.turn.feature/x` rides along, preserving the per-source-branch view.

**UI surface.** The `/memoir:ui` Statistics modal grows two conditional tabs after Overview:

- **Codebase** — renders `codebase:onboard` keys grouped by L1 prefix, first sentence per child, with a header showing `last_onboard <commit> · <date> · <mode>`. Same compact rendering shape as the SessionStart inject.
- **Metrics** — table view with rows = branches and columns = accumulator fields (`Turns`, `Calls`, `Errors`, `Avg latency (ms)`, `Output chars`, …). Three bar charts below show avg-latency / output-chars / tool-result-chars distributions across branches.

Both tabs only appear when their data exists. Both fetch via raw `GET /api/onboard` and `GET /api/metrics` — no LLM.

## Environment variables

All optional. Set in your shell or per-project `.envrc`.

| Variable | Default | Effect |
|---|---|---|
| `MEMOIR_STORE` | `~/.memoir/memoir_<hash>` | Override the per-project store path. |
| `MEMOIR_NO_CAPTURE` | unset | `1` disables `Stop`-hook auto-capture (haiku classification + memory writes). Metrics still record. |
| `MEMOIR_NO_METRICS` | unset | `1` disables the per-branch turn-metrics accumulator. Auto-capture still runs. |
| `MEMOIR_ONBOARD_INJECT` | `1` | `0` suppresses the `codebase:onboard` block in `SessionStart`'s `additionalContext`. |
| `MEMOIR_LLM_MODEL` | `haiku` | Model used for the `Stop` hook's fact extractor. Override only if you've validated alignment with the prompt-test harness. |
| `MEMOIR_MAX_RESULT_CHARS` | `1000` | Per-tool-result truncation in `parse-transcript.sh`. |

## Manifest

`plugins/claude-code/.claude-plugin/plugin.json`:

```json
{
  "name": "memoir",
  "version": "0.1.0",
  "description": "Git-versioned, taxonomy-structured memory for Claude Code — recall by path, branch to isolate, time-travel to audit."
}
```

## See also

- [CLI](cli.md) — the underlying `memoir` commands the plugin wraps.
- [API](api/memoir.md) — the Python library for programmatic use.
- [Architecture](architecture.md) — how memoir is structured under the hood.

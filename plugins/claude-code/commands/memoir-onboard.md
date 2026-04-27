---
description: "Indexes this folder and saves a persistent overview that future sessions pick up automatically. In a git repo this writes `codebase:onboard` (code-shape map). In a non-git folder this writes `project:onboard` (file-shape index built by deterministic extractors — no LLM at index time)."
argument-hint: "[--force]"
allowed-tools: Bash
---

Run the `memoir-onboard` skill. The skill picks the right procedure for the current folder:

- **git repo** → `codebase:onboard` (modules, goals, rules, lessons). Cold path on a fresh clone, warm path after meaningful diffs, meta-only when code HEAD hasn't moved.
- **non-git folder** → `project:onboard` (per-file structured blobs from deterministic stdlib extractors, plus a project-shape summary). Tuned for writing, video editing, bookkeeping, and other mixed-media projects. Cold/warm/meta paths keyed off a filesystem snapshot hash.

Pass `--force` to rewrite even when nothing has changed since the last onboarding pass.

Arguments: $ARGUMENTS

Invoke the `memoir-onboard` skill now, forwarding any arguments above.

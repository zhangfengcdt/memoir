---
description: "Populate or refresh the codebase:onboard snapshot — a persistent, high-level overview of this repo that future sessions pick up automatically via SessionStart injection."
argument-hint: "[--force]"
allowed-tools: Bash
---

Run the `memoir-onboard` skill to build (cold path) or refresh (warm path) the high-level codebase snapshot stored under the `codebase:onboard` namespace. Pass `--force` to rewrite even if the code SHA hasn't moved since the last onboarding pass.

Use this on a fresh clone, after a large refactor, or whenever SessionStart tags the existing snapshot as `stale`. The skill figures out whether to do a cold full-scan or a warm incremental pass based on `_meta.last_onboard.commit` vs. current HEAD.

Arguments: $ARGUMENTS

Invoke the `memoir-onboard` skill now, forwarding any arguments above.

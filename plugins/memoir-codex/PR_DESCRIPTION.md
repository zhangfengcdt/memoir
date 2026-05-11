## Summary
- Adds the Memoir Codex plugin as the first multi-host plugin port for #85.
- Packages Memoir as a Codex plugin with lifecycle hooks, recall/onboarding skills, local marketplace metadata, and Codex-specific transcript parsing.
- Documents install, configuration, limitations, and real Codex smoke-test evidence.

## What changed
- Added `plugins/memoir-codex/` with `.codex-plugin/plugin.json`, `skills/`, `hooks/hooks.json`, hook scripts, helper scripts, tests, and fixtures.
- Added `.agents/plugins/marketplace.json` for local Codex plugin discovery.
- Ported SessionStart, UserPromptSubmit, and Stop behavior from the Claude Code plugin where Codex supports equivalent lifecycle hooks.
- Added Codex-specific transcript parsing for messages, tool calls, apply_patch, shell calls, and tool outputs.
- Preserved the read/write asymmetry: recall is skill-driven, onboarding is an explicit project-indexing skill, manual remember/forget stay CLI-only, and Stop handles best-effort auto-capture.
- Started the Codex plugin's independent release line at `0.1.0`.
- Added a `scripts/install-codex-hooks.sh` bridge for the current Codex plugin-hook gap tracked upstream in openai/codex#16430, where marketplace plugins install skills but do not yet activate bundled lifecycle hooks.
- Aligned Codex install docs with `/plugins` repo-marketplace distribution from `zhangfengcdt/memoir`, including the local-checkout path for PR testing and the uv-based CLI fallback.
- Documented that pre-merge marketplace testing must use the PR branch or local checkout so Codex does not fall back to the existing Claude Code marketplace on upstream main.
- Updated docs, release notes, and version consistency checks for the new Codex plugin surface.

## Limitations
- Codex plugin slash commands, deprecated custom prompt surfaces, Claude Code statusline behavior, and SessionEnd cleanup are not included in v1.
- Codex does not activate marketplace plugin hooks automatically yet (openai/codex#16430); run `scripts/install-codex-hooks.sh` after plugin install to bridge the bundled `SessionStart`, `UserPromptSubmit`, and `Stop` hooks into `~/.codex/hooks.json`.
- Stop-hook LLM extraction uses `codex exec`; if Codex auth or the executable is unavailable, capture fails open and the user turn is not blocked.

## Validation
- `.venv/bin/pytest plugins/memoir-codex/tests -v` - 43 passed.
- `.venv/bin/python plugins/memoir-codex/tests/prompt-harness/runner.py gate --hook user-prompt-submit` - 13/13 passed.
- `PATH="$PWD/.venv/bin:$PATH" ... for t in plugins/memoir-codex/tests/*.sh; do bash "$t"; done` - shell hook suite passed.
- `uv run --extra dev make test` - 350 passed, 9 skipped.
- `uv run --extra dev make lint` - passed.
- `plugins/memoir-codex/tests/prompt-harness/runner.py run --prompt stop_capture --model gpt-5.4` - one full run passed 16/16; after prompt/timeout hardening, targeted `gpt-5.4` reruns of the strengthened positive cases and highest-risk negative cases passed.
- Real Codex smoke with `gpt-5.4` in `/tmp/memoir-codex-smoke` wrote `default:preferences.coding.testing` and SessionStart reported `[memoir] main · 1 memories`; sanitized evidence exported to `/tmp/memoir-codex-smoke-evidence.md`, then the disposable project and store were removed.

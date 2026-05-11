## Summary
- Adds the Memoir Codex plugin as the first multi-host plugin port for #85.
- Packages Memoir as a Codex plugin with lifecycle hooks, recall/onboarding skills, local marketplace metadata, and Codex-specific transcript parsing.
- Documents install, configuration, limitations, and real Codex smoke-test evidence.

## Install / try it
- In Codex, open `/plugins`, add marketplace `scdozier/memoir` with ref `codex/issue-85-codex-extension`, then install `memoir-codex`.
- CLI equivalent for PR testing: `codex plugin marketplace add scdozier/memoir --ref codex/issue-85-codex-extension`.
- After install, run the hook bridge until openai/codex#16430 is resolved:
  `PLUGIN_ROOT=$(find "${CODEX_HOME:-$HOME/.codex}/plugins/cache" -path '*/memoir-codex/*/.codex-plugin/plugin.json' -print -quit | sed 's#/.codex-plugin/plugin.json$##') && bash "$PLUGIN_ROOT/scripts/install-codex-hooks.sh"`
- Restart Codex, open `/hooks` if prompted, and press `t` to trust the Memoir hooks.
- Try: `remember that this project prefers pytest`, `show Memoir status`, `open the Memoir UI`, or ask a question that should use `memory-recall`.

## Screenshot
<!-- Add screenshot here before opening/marking the upstream PR ready. Suggested: Codex plugin detail page showing Memoir skills/hooks, or a session showing Memoir hooks + a remembered fact. -->

## What changed
- Added `plugins/memoir-codex/` with `.codex-plugin/plugin.json`, `skills/`, `hooks/hooks.json`, hook scripts, helper scripts, tests, and fixtures.
- Added `.agents/plugins/marketplace.json` for local Codex plugin discovery.
- Ported SessionStart, UserPromptSubmit, and Stop behavior from the Claude Code plugin where Codex supports equivalent lifecycle hooks.
- Migrated Claude Code slash-command behavior into Codex skills: `memoir-remember`, `memoir-status`, and `memoir-ui`, alongside the existing `memory-recall` and `memoir-onboard` skills.
- Added Codex-specific transcript parsing for messages, tool calls, apply_patch, shell calls, and tool outputs.
- Preserved the read/write asymmetry: recall is skill-driven, onboarding is explicit, manual remember is an explicit Codex skill, deletion stays CLI-only, and Stop handles best-effort auto-capture.
- Matched Claude Code plugin CLI resolution semantics: `memoir` on PATH first, then pinned `uvx` / `uv tool run` fallbacks, with Codex-specific LLM extraction through `codex exec` that inherits the active Codex model and falls back to `gpt-5.4`.
- Started the Codex plugin's independent release line at `0.1.0`.
- Added a `scripts/install-codex-hooks.sh` bridge for the current Codex plugin-hook gap tracked upstream in openai/codex#16430, where marketplace plugins install skills but do not yet activate bundled lifecycle hooks.
- Aligned Codex install docs with `/plugins` repo-marketplace distribution from `zhangfengcdt/memoir`, including the local-checkout path for PR testing and the uv-based CLI fallback.
- Documented that pre-merge marketplace testing must use the PR branch or local checkout so Codex does not fall back to the existing Claude Code marketplace on upstream main.
- Updated docs, release notes, and version consistency checks for the new Codex plugin surface.

## Limitations
- Codex plugin slash commands, deprecated custom prompt surfaces, Claude Code statusline behavior, and SessionEnd cleanup are not included in v1.
- Codex does not activate marketplace plugin hooks automatically yet (openai/codex#16430); run `scripts/install-codex-hooks.sh` after plugin install to bridge the bundled `SessionStart`, `UserPromptSubmit`, and `Stop` hooks into `~/.codex/hooks.json`.
- After installing the hook bridge, Codex may warn that 3 hooks need review; open `/hooks`, review each Memoir hook, and press `t` to trust it before expecting hooks to run.
- Stop-hook LLM extraction uses `codex exec`; if Codex auth or the executable is unavailable, capture fails open and the user turn is not blocked.
- Stop capture only runs after a completed Codex turn; interrupted turns may not produce auto-captured memories.

## Validation
- `.venv/bin/pytest plugins/memoir-codex/tests -v` - 45 passed.
- `.venv/bin/python plugins/memoir-codex/tests/prompt-harness/runner.py gate --hook user-prompt-submit` - 13/13 passed.
- `PATH="$PWD/.venv/bin:$PATH" ... for t in plugins/memoir-codex/tests/*.sh; do bash "$t"; done` - shell hook suite passed.
- `uv run --extra dev make test` - 350 passed, 9 skipped.
- `uv run --extra dev make lint` - passed.
- `plugins/memoir-codex/tests/prompt-harness/runner.py run --prompt stop_capture --model gpt-5.4` - one full run passed 16/16; after prompt/timeout hardening, targeted `gpt-5.4` reruns of the strengthened positive cases and highest-risk negative cases passed.
- Real Codex smoke with `gpt-5.4` in `/tmp/memoir-codex-smoke` wrote `default:preferences.coding.testing` and SessionStart reported `[memoir] main · 1 memories`; sanitized evidence exported to `/tmp/memoir-codex-smoke-evidence.md`, then the disposable project and store were removed.

# Prompt Test Harness

The harness exercises the same prompt templates and gate logic that the Codex plugin uses in production.

## Modes

- **Gate mode**: deterministic shell-hook tests. No LLM, no network.
- **LLM mode**: `run`, `case`, and `adhoc` call `codex exec` against prompt templates in `hooks/prompts/*.tmpl`.

## Requirements

- Python 3.10+ with PyYAML.
- `codex` on `PATH` and already authenticated for LLM mode.
- The repo venv is recommended: `source venv/bin/activate`.

## Commands

```bash
# Deterministic recall-gate suite.
plugins/memoir-codex/tests/prompt-harness/runner.py gate --hook user-prompt-submit

# Full Stop-hook prompt suite. Use gpt-5.4 for PR validation.
plugins/memoir-codex/tests/prompt-harness/runner.py run --prompt stop_capture --model gpt-5.4

# One case.
plugins/memoir-codex/tests/prompt-harness/runner.py case stop_capture/capture-going-forward-rule.yaml --model gpt-5.4

# Diagnostic replay from a pasted turn.
plugins/memoir-codex/tests/prompt-harness/runner.py adhoc --prompt stop_capture --input /tmp/turn.txt --model gpt-5.4

# Assemble prompts without an LLM call.
plugins/memoir-codex/tests/prompt-harness/runner.py adhoc --prompt stop_capture --input /tmp/turn.txt --model gpt-5.4 --dry-run
```

Every run writes artifacts under `/tmp/memoir-prompt-tests/<UTC-timestamp>/`, including `summary.md`, `summary.json`, per-case `system.txt`, `input.txt`, `output.txt`, and a replayable `command.sh`.

## Gate Cases

Gate cases live under `cases/gate/<hook>/*.yaml`. A case invokes `hooks/<hook>.sh` with synthetic Codex hook JSON on stdin and asserts on the parsed JSON output. `USER_MEMORIES` in a case is materialized into the same `.git/plugin-memory-count-cache` file that the live hook reads.

## LLM Cases

LLM cases live under `cases/<prompt>/*.yaml`. `prompt` must match a template at `hooks/prompts/<prompt>.tmpl`. The harness renders the taxonomy block from `--store`, `MEMOIR_STORE`, or a temp store under `/tmp/memoir-prompt-tests/_store/`, then calls `codex exec --disable hooks --sandbox read-only --skip-git-repo-check`.

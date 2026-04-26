# Prompt test harness

Runs the Claude Code plugin's LLM prompts against canned test cases (or an ad-hoc input) and saves every conversation to a temp folder so you can inspect what the model actually did.

Loads the **same** prompt templates the plugin uses in production (`hooks/prompts/*.tmpl`) — no duplicated copies that could drift. Calls the LLM via `claude -p`, which uses your Claude Code OAuth login (no API key needed).

## Requirements

- `claude` CLI on `$PATH` (Claude Code) — already logged in (`claude /login`).
- Python 3.10+ with **PyYAML** (`python3 -m pip install pyyaml`). If you have the memoir repo's venv set up (`make install-dev`), it's already there — invoke as `<venv>/bin/python3 runner.py …`.

## Quickstart

```bash
# From the plugin root. Use the venv if you have one — it has PyYAML.
cd plugins/claude-code/tests/prompt-harness

# Run all cases for the Stop-hook auto-capture prompt.
./runner.py run --prompt stop_capture --model haiku

# Run one case.
./runner.py case stop_capture/capture-going-forward-rule.yaml --model haiku

# Diagnostic: paste a transcript that "should have captured but didn't"
# into a file and replay it through the real production prompt.
echo "=== Transcript of a conversation between a human and Claude Code ===
[Human]
From now on, deploy on Tuesdays only.
[Claude Code]
Got it." > /tmp/my-failed-turn.txt

./runner.py adhoc --prompt stop_capture --input /tmp/my-failed-turn.txt --model haiku

# Dry-run (no LLM call, just assemble the prompt and record artifacts).
./runner.py adhoc --prompt stop_capture --input /tmp/my-failed-turn.txt --model haiku --dry-run
```

`--model` is **mandatory** for every command — pick `haiku`, `sonnet`, `opus`, or any model name `claude -p --model` accepts. Production uses `haiku`; cases should pass against haiku.

## Inspecting a run

Every invocation creates `/tmp/memoir-prompt-tests/<UTC-timestamp>/` with:

```
summary.md             ← human-readable per-case pass/fail
summary.json           ← machine-readable
<prompt>/<case>/
  system.txt           ← assembled system prompt (template + taxonomy block)
  input.txt            ← stdin fed to claude -p
  output.txt           ← raw model response
  command.sh           ← replayable invocation — run this to re-run the same call
  result.json          ← per-assertion pass/fail
```

If a case fails, the path to its `output.txt` is the answer to *"what did the model actually emit?"* — open it.

## Authoring a case

Add a YAML file under `cases/<prompt>/<name>.yaml`:

```yaml
description: "Short description shown in the summary"
prompt: stop_capture       # must match a file in plugins/claude-code/hooks/prompts/<name>.tmpl
input: |
  === Transcript of a conversation between a human and Claude Code ===
  [Human]
  ...
  [Claude Code]
  ...
expect:
  - kind: min_lines
    value: 1
  - kind: regex_each_line
    value: "^[a-z][a-z0-9_]*(\\.[a-z0-9_]+){1,3}\\t.+$"
  - kind: any_path_prefix
    value: ["preferences.coding"]
```

### Assertion kinds

| Kind | Meaning |
|---|---|
| `empty` | Output must be empty / whitespace-only |
| `not_empty` | Output must contain at least one non-whitespace char |
| `min_lines` | Output has ≥ `value` non-empty lines |
| `max_lines` | Output has ≤ `value` non-empty lines |
| `exact_lines` | Output has exactly `value` non-empty lines |
| `regex_each_line` | Every non-empty line matches `value` (regex) |
| `any_line_matches` | At least one line matches `value` (regex) |
| `no_line_contains` | No line contains substring `value` |
| `any_path_prefix` | At least one line's path field starts with one of the prefixes in `value` (list of dotted prefixes; line is split on first `\t`) |
| `no_path_prefix` | Inverse of `any_path_prefix` |

## How taxonomy block injection works

The Stop-hook prompt has a `${TAXONOMY_BLOCK}` placeholder that production fills in at SessionStart from `memoir taxonomy prompt-snippet`. The harness does the same — but uses an isolated temp store by default so test runs are reproducible and never touch the user's real `~/.memoir/`.

Resolution order (first match wins):

1. **`--store /path/to/memoir/store`** — explicit override. Use this when diagnosing a failure tied to a real store's loaded taxonomies.
2. **`$MEMOIR_STORE`** env var — same as #1, just env-driven.
3. **Default**: `/tmp/memoir-prompt-tests/_store/` — bootstrapped on first use via `memoir new --taxonomy-builtin --no-connect`. Idempotent across runs. The taxonomy block then comes from `memoir -s <temp-store> taxonomy prompt-snippet`. This is the **builtin taxonomy** memoir ships — the same shape every fresh memoir install starts with.

The hardcoded category sheet (the same fallback `stop.sh` uses when no store has been initialised) only fires if `memoir` itself is not on `PATH`.

`summary.json[i].notes` records which source was used per case (e.g. `"taxonomy: memoir-cli: /tmp/memoir-prompt-tests/_store"`); `<run>/<prompt>/<case>/system.txt` shows the exact assembled prompt.

## Costs

Each case costs LLM tokens. The harness is **opt-in** — never run automatically by hooks or CI. Run it manually when you change a prompt or want to diagnose a failure.

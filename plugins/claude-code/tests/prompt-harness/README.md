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

Each `run` / `case` / `adhoc` invocation costs LLM tokens. The harness is **opt-in** — never run automatically by hooks or CI. Run it manually when you change a prompt or want to diagnose a failure. (`gate` mode is free — see below.)

---

## Gate mode (deterministic, no LLM)

The plugin's shell hooks make decisions before any LLM call — e.g. `user-prompt-submit.sh` decides whether to inject a "recall before acting" hint into the next turn's context. Gate cases pin those decisions with deterministic regression tests:

```bash
# Run all gate cases (sub-second per case; safe to run on every commit).
./runner.py gate --hook user-prompt-submit

# Run a single gate case via the existing case command — kind is auto-detected.
./runner.py case gate/user-prompt-submit/verb-add-fires.yaml
```

A gate case invokes the named hook script (`hooks/<name>.sh`) with synthetic JSON stdin (`{"prompt": "..."}`), captures its stdout, parses the JSON, and asserts on the parsed result. No `claude -p`, no network. Each case runs against a fresh per-case temp store under `/tmp/memoir-prompt-tests/_gate-store/` so there's no leakage between cases.

### Gate case schema

```yaml
kind: gate
hook: user-prompt-submit          # → hooks/user-prompt-submit.sh
description: "Verb 'add' in a 40+ char prompt fires the recall block"
env:                              # exported before running the hook
  USER_MEMORIES: "5"              # written into the statusline-cache file
  MEMOIR_CMD: "memoir"
prompt: "Please add a Stripe webhook handler to the billing service."
expect:
  - kind: parsed_ok
  - kind: recall_block_emitted
  - kind: system_message_contains
    value: "memory available"
  - kind: exit_code_is
    value: 0
```

`USER_MEMORIES` is special-cased: it isn't an env var the hook reads — it's the count from `<store>/.git/plugin-statusline-cache`. The harness writes it there on your behalf so the hook's real read path exercises.

### Gate assertion kinds

| Kind | Meaning |
|---|---|
| `parsed_ok` | Hook stdout was a valid JSON object |
| `recall_block_emitted` | `hookSpecificOutput.additionalContext` contained the production "memoir — recall before acting" header |
| `recall_block_absent` | The recall block was NOT emitted |
| `additional_context_contains` | Substring check on `additionalContext` (case sensitive). `value: str` |
| `system_message_contains` | Substring check on `systemMessage`. `value: str` |
| `exit_code_is` | Hook exit code matches. `value: int` |

### Adding a new hook to gate-test

1. Drop cases under `cases/gate/<hook-name>/*.yaml` (any depth — discovery is recursive).
2. Use `kind: gate` and `hook: <name>` (must match `hooks/<name>.sh`).
3. Run `./runner.py gate --hook <name>` to execute just that hook's cases.

---

## Recall A/B mode (LLM, run on demand)

Measures whether the recall-trigger hook is earning its tokens by running the same labeled prompts through three system-prompt configurations:

| Arm | System prompt | Hook block prepended | What it tests |
|---|---|---|---|
| `with_hook` | skill description | ✅ yes (production) | Today's recall rate |
| `prose_only` | skill description | ❌ no | Can the model decide on its own? |
| `bare` | (no skill description) | ❌ no | Sanity baseline |

```bash
./runner.py recall-ab --model haiku
```

Output: `<run>/recall_ab/summary.md` with a per-arm precision/recall/F1 table; per-arm raw stream-json under `<run>/recall_ab/<case>/<arm>/events.jsonl`.

### Recall A/B case schema

```yaml
prompt: "Refactor the auth middleware to share state with the rate limiter."
should_fire: true
```

`should_fire` is the human ground truth — used to compute aggregate precision/recall/F1, NOT a per-case assertion. Cases live flat under `cases/recall_ab/*.yaml`.

**Cost:** ~3 arms × 1–2s × N cases. Three sample cases ship; expand to ~30 for a representative corpus before drawing conclusions.

**Caveat:** the `claude -p --output-format stream-json` event parser in `recall_ab.py` is best-effort. Run one case manually first and inspect `events.jsonl` + `tool_calls.json` to confirm the parser caught the Skill tool call as expected before trusting aggregate numbers.

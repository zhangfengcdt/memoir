---
name: memoir-remember
description: "Explicitly save a user-requested memory to Memoir now. Use when the user says remember, save, store, capture, or record a durable preference, decision, rule, fact, or note. Pick a taxonomy path with Codex when none is provided, always write with `memoir remember -p`, and never use legacy unpathed `memoir remember`."
---

Use this skill only for explicit manual capture. Do not use it for incidental facts; the Stop hook handles best-effort auto-capture at turn end.

## Parse The Request

Extract:

- Memory content: the fact/rule/preference/decision to save. Remove leading phrases like "remember that" unless they are part of the fact.
- `-p <path>` / `--path <path>`: optional target taxonomy path. May appear more than once.
- `-n <namespace>` / `--namespace <namespace>`: optional namespace. Default is `default`.
- `--replace`: optional overwrite flag.

If the user supplied one or more paths, use them exactly unless they are malformed. If no path was supplied, choose a concise semantic path yourself, using 2-4 lowercase dot segments such as `preferences.coding.style`, `workflow.coding.testing`, or `context.project.standards`.

Do not run `memoir remember` without `-p`. The unpathed CLI path invokes Memoir's package-level LLM classifier and may require non-Codex API credentials. This skill is the Codex-native classifier: pick the path, then write with `-p`.

Ask one short clarification only if the memory content is empty, the user is clearly asking to save a secret/API key, or the target path is too ambiguous to choose safely.

## Resolve Plugin And Store

Use this preamble in the Bash call:

```bash
PLUGIN_ROOT="${PLUGIN_ROOT:-}"
if [ -z "$PLUGIN_ROOT" ]; then
  PLUGIN_ROOT=$(find "${CODEX_HOME:-$HOME/.codex}/plugins" -path '*/.codex-plugin/plugin.json' -print 2>/dev/null \
    | while IFS= read -r manifest; do
        python3 - "$manifest" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text())
except Exception:
    raise SystemExit(0)
if data.get("name") == "memoir":
    print(path.parent.parent)
PY
      done | head -n 1)
fi
MEMOIR="$PLUGIN_ROOT/scripts/memoir-cli.sh"
if [ -z "$PLUGIN_ROOT" ] || [ ! -x "$MEMOIR" ] || [ ! -x "$PLUGIN_ROOT/scripts/derive-store-path.sh" ]; then
  echo "Memoir Codex plugin not found" >&2
  exit 127
fi
STORE="${MEMOIR_STORE:-$(bash "$PLUGIN_ROOT/scripts/derive-store-path.sh")}"
bash "$PLUGIN_ROOT/scripts/ensure-store.sh" "$STORE" >/dev/null
```

If `$PLUGIN_ROOT` is empty or `$MEMOIR` is not executable, stop and tell the user the Memoir Codex plugin is not installed or cannot be found.

## Optional Taxonomy Hint

When no path was supplied and you are unsure which path to choose, make one quick read-only call before writing:

```bash
( cd "$STORE" && "$MEMOIR" -s "$STORE" taxonomy prompt-snippet )
```

Use the snippet to choose the path, then continue with the write. If the snippet fails, choose a reasonable path from the memory content.

## Write

Use a single-quoted heredoc for content so shell metacharacters are preserved. Put `-p`, `-n`, and `--replace` after the content argument.

```bash
CONTENT=$(cat <<'MEMOIR_REMEMBER_EOF'
<paste memory content verbatim>
MEMOIR_REMEMBER_EOF
)
( cd "$STORE" && "$MEMOIR" --json -s "$STORE" remember "$CONTENT" -p "<path>" )
```

Rules:

- If the content contains a line that is exactly `MEMOIR_REMEMBER_EOF`, use a different delimiter.
- For multiple paths, repeat `-p "<path>"` in the same command.
- If `-n <namespace>` was supplied, append `-n "<namespace>"`.
- If `--replace` was supplied, append `--replace`.
- Never save obvious secrets, tokens, private keys, or credentials. Ask for confirmation with a safer redacted form instead.

## Reply

Parse the JSON response and report one short line with the saved key or keys and commit hash. If the CLI fails, report the stderr briefly and include the store path.

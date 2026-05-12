---
name: memoir-status
description: "Show Memoir status for the current Codex project: store path, branch, commit count, memory count, and namespaces. Use when the user asks for Memoir status, whether Memoir is working, what store or branch is active, or why memories are not appearing."
---

Use this skill for Memoir diagnostics and status checks.

Run:

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
if [ -z "$PLUGIN_ROOT" ] || [ ! -x "$PLUGIN_ROOT/scripts/status-cmd.sh" ]; then
  echo "Memoir Codex plugin not found" >&2
  exit 127
fi
bash "$PLUGIN_ROOT/scripts/status-cmd.sh"
```

Summarize the JSON in one short paragraph: store path, current branch, memory count, commit count, and namespaces. If the user is debugging missing memories, also explain that the Codex plugin uses a derived store under `~/.memoir/<slug>` unless `MEMOIR_STORE` is set, so bare `memoir status` from the project directory may inspect a different store.

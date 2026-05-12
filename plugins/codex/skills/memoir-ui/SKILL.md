---
name: memoir-ui
description: "Launch or reopen the Memoir web UI for the current Codex project store. Use when the user asks to open, browse, inspect, visualize, or view Memoir memories in the UI. Starts the safe readonly, no-LLM UI through the plugin helper and reports the URL, PID, and store."
---

Launch or reopen the Memoir UI through the plugin helper. Do not call `memoir ui` directly.

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
if [ -z "$PLUGIN_ROOT" ] || [ ! -x "$PLUGIN_ROOT/scripts/memoir-ui-ctl.sh" ]; then
  echo "Memoir Codex plugin not found" >&2
  exit 127
fi
STORE="${MEMOIR_STORE:-$(bash "$PLUGIN_ROOT/scripts/derive-store-path.sh")}"
bash "$PLUGIN_ROOT/scripts/memoir-ui-ctl.sh" start "$STORE"
```

The helper prints JSON with `url`, `pid`, `store`, and `reused`.

Reply in 4-6 short lines:

```text
[mode=ui-launched|ui-reopened]
Memoir UI: <url>
Store: <store>
Mode: readonly, LLM off
PID: <pid>
```

Use `[mode=ui-reopened]` when `reused` is true; otherwise use `[mode=ui-launched]`.

If the helper exits non-zero, show the failure briefly. Do not run `open`, `xdg-open`, or `start`; the helper already opens the browser tab.

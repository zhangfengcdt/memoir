---
description: "Launch (or re-open) the memoir web UI for the current project's store."
allowed-tools: Bash
---

Launch (or re-open) the memoir web UI for the current project's store as a detached background server.

## Step 1 — Derive the store path

Run this Bash call to resolve the store path (respects `$MEMOIR_STORE`, otherwise falls back to the per-project derivation):

```bash
if [ -n "${MEMOIR_STORE:-}" ]; then echo "$MEMOIR_STORE"; else bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh"; fi
```

Capture stdout as `<STORE_PATH>`. The launch helper in Step 2 will auto-bootstrap the store if it doesn't exist yet (idempotent — same logic SessionStart uses), so you don't need to pre-check.

## Step 2 — Launch (or re-open) the UI

One Bash call does the whole job — the helper handles reuse, launch, and the browser open:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/memoir-ui-ctl.sh" start "<STORE_PATH>"
```

The helper prints a single-line JSON document on stdout:

```json
{"pid": 12345, "port": 62891, "url": "http://localhost:62891/?store=…&readonly=1&usellm=0", "store": "/abs/path", "started": "...", "log": "/tmp/...", "reused": false}
```

- `reused: true` — an existing server for this store was already running; the helper just re-opened the browser tab.
- `reused: false` — the helper launched a fresh detached server; the CLI opens the browser automatically.

Pipe the output through `python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["url"]); print(d["pid"]); print("reused" if d.get("reused") else "launched")'` to extract the fields you need.

## Output format

**First line of your reply MUST be the mode marker**, one of:

- `[mode=ui-reopened]` — helper reported `reused: true`.
- `[mode=ui-launched]` — helper reported `reused: false`.

Then 4–6 short lines for the user:

```
[mode=ui-launched]
Memoir UI available at <URL>
Store: <STORE>
Mode: readonly · LLM off (relaunch from a terminal with `memoir ui <STORE> --no-readonly --usellm` for write/search access)
PID: <PID>
Stop anytime with `kill <PID>`.
```

If the helper exits non-zero, print its stderr back to the user under a one-line header like `UI failed to start:` — don't swallow it.

## Rules

- Do NOT pass `--no-browser` — the CLI's built-in `webbrowser.open()` is what we want.
- Do NOT run `open <url>` (or `xdg-open`, `start`, etc.) after the helper — the helper already opens the browser exactly once. A second open creates a duplicate tab. This is true for both `reused: true` (helper re-opens) and `reused: false` (CLI auto-opens on bind).
- Do NOT pass `--no-readonly` or `--usellm` — chat-triggered launches stay in the safe default (readonly, no-LLM). The reply tells the user exactly how to relaunch with those flags from a terminal if they want more.
- Do NOT block the turn waiting on the server. The helper returns within ~3 seconds whether it launched or reused.
- Do NOT invoke `memoir ui` directly. Always go through the helper so the pidfile bookkeeping stays consistent.
- This command is for **visual browsing only**. If the user is asking a factual question about their memories ("what did I decide about X"), defer to `/memoir:recall`.

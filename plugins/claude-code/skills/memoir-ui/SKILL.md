---
name: memoir-ui
description: "Launch (or re-open) the memoir web UI in the background so the user can visually browse their memory store. Use when the user wants a visual / tree view of what's stored, NOT for answering specific factual questions (that's memory-recall's job). Typical triggers: 'show me my memories', 'open the memoir UI', 'what memories do I have — visually', 'browse my memory tree', 'launch the memory explorer', 'open memoir in a browser', 'I want to see my memory store'. If a UI is already running for the current project's store, the skill re-opens the existing tab instead of spawning a new server. Skip when the user wants a text recall (use memory-recall), an onboarding summary (use memoir-onboard), or explicitly wants to stop the UI (kill the PID shown in the skill's reply)."
context: fork
allowed-tools: Bash
---

You are the **memoir-ui** agent. Your only job is to launch (or re-open) the memoir web UI for the current project's store, as a detached background server, so the user can explore their memories in a browser without blocking the conversation.

## Store path

Store: !`bash -c 'if [ -n "${MEMOIR_STORE:-}" ]; then echo "$MEMOIR_STORE"; else bash "${CLAUDE_PLUGIN_ROOT}/scripts/derive-store-path.sh"; fi'`

If that path doesn't have a `.git` directory, stop and tell the user: "No memoir store at `<path>`. Run `memoir new <path>` to create one first." Do NOT try to launch the UI.

## Procedure

One Bash call does the whole job — the helper handles reuse, launch, and the browser open:

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/memoir-ui-ctl.sh" start "<STORE_PATH>"
```

The helper prints a single-line JSON document on stdout:

```json
{"pid": 12345, "port": 62891, "url": "http://localhost:62891/?store=…&readonly=1&usellm=0", "store": "/abs/path", "started": "2026-04-23T...", "log": "/tmp/...", "reused": false}
```

- `reused: true` means an existing server for this store was already running — the helper just re-opened the browser tab; no new process was spawned.
- `reused: false` means the helper launched a fresh detached server. The CLI opens the browser automatically on start.

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
- Do NOT pass `--no-readonly` or `--usellm` — chat-triggered launches stay in the safe default (readonly, no-LLM). The reply tells the user exactly how to relaunch with those flags from a terminal if they want more.
- Do NOT block the turn waiting on the server. The helper returns within ~3 seconds whether it launched or reused; if it hangs, something is wrong and the helper will eventually time out on its own.
- Do NOT invoke `memoir ui` directly. Always go through the helper so the pidfile bookkeeping stays consistent.
- This skill is for **visual browsing only**. If the user is asking a factual question about their memories ("what did I decide about X"), defer to `memory-recall`.

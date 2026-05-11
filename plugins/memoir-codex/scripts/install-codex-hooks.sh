#!/usr/bin/env bash
# Install or remove Memoir Codex lifecycle hooks in the user Codex hooks file.
#
# Codex v0.130.0 installs plugin skills from marketplace plugins, but does not
# yet activate plugin-bundled hooks from hooks/hooks.json. This script writes
# equivalent user-level hooks that point at this installed plugin root.

set -euo pipefail

MODE="${1:-install}"
case "$MODE" in
  install|--install) MODE="install" ;;
  uninstall|--uninstall|remove|--remove) MODE="uninstall" ;;
  *)
    echo "usage: $0 [install|uninstall]" >&2
    exit 2
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="${PLUGIN_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
HOOKS_FILE="${CODEX_HOOKS_FILE:-$CODEX_HOME/hooks.json}"

mkdir -p "$(dirname "$HOOKS_FILE")"

python3 - "$MODE" "$PLUGIN_ROOT" "$HOOKS_FILE" <<'PY'
import json
import shlex
import sys
import time
from pathlib import Path

mode = sys.argv[1]
plugin_root = Path(sys.argv[2]).resolve()
hooks_file = Path(sys.argv[3]).expanduser()

marker = "memoir-codex managed hook"
events = {
    "SessionStart": {
        "script": "session-start.sh",
        "timeout": 15,
        "statusMessage": "Loading Memoir context",
    },
    "UserPromptSubmit": {
        "script": "user-prompt-submit.sh",
        "timeout": 10,
        "statusMessage": "Checking Memoir recall",
    },
    "Stop": {
        "script": "stop.sh",
        "timeout": 180,
        "statusMessage": "Capturing Memoir facts",
    },
}


def load_config() -> dict:
    if not hooks_file.exists():
        return {"hooks": {}}
    try:
        data = json.loads(hooks_file.read_text())
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{hooks_file}: invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{hooks_file}: expected JSON object")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise SystemExit(f"{hooks_file}: hooks must be an object")
    return data


def is_memoir_handler(handler: object) -> bool:
    if not isinstance(handler, dict):
        return False
    command = str(handler.get("command", ""))
    status = str(handler.get("statusMessage", ""))
    return (
        marker in command
        or "/memoir-codex/" in command
        or command.endswith("/hooks/session-start.sh")
        or command.endswith("/hooks/user-prompt-submit.sh")
        or command.endswith("/hooks/stop.sh")
        or status in {v["statusMessage"] for v in events.values()}
    )


def strip_existing(data: dict) -> None:
    hooks = data.setdefault("hooks", {})
    for event in list(events):
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                kept_groups.append(group)
                continue
            kept_handlers = [h for h in handlers if not is_memoir_handler(h)]
            if kept_handlers:
                new_group = dict(group)
                new_group["hooks"] = kept_handlers
                kept_groups.append(new_group)
        if kept_groups:
            hooks[event] = kept_groups
        else:
            hooks.pop(event, None)


def install(data: dict) -> None:
    hooks = data.setdefault("hooks", {})
    quoted_root = shlex.quote(str(plugin_root))
    for event, spec in events.items():
        script = plugin_root / "hooks" / spec["script"]
        command = (
            f"PLUGIN_ROOT={quoted_root} "
            f"bash {shlex.quote(str(script))} "
            f"# {marker}: {event}"
        )
        hooks.setdefault(event, []).append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": command,
                        "timeout": spec["timeout"],
                        "statusMessage": spec["statusMessage"],
                    }
                ]
            }
        )


data = load_config()
strip_existing(data)
if mode == "install":
    install(data)

if hooks_file.exists():
    backup = hooks_file.with_name(f"{hooks_file.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    backup.write_text(hooks_file.read_text())

hooks_file.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")
print(f"{mode}ed Memoir Codex hooks in {hooks_file}")
PY

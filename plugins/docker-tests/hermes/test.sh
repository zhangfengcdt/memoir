#!/usr/bin/env bash
# In-container smoke test for the memoir Hermes plugin. Run inside the image
# built from this directory's Dockerfile (HERMES_HOME=/data). Pass
# ANTHROPIC_API_KEY for the real auto-capture step (it's the only step that
# calls an LLM; everything else is offline).
set +e

echo "===== 1. versions ====="
hermes --version 2>&1 | head -1
memoir --version 2>&1 | head -1

echo
echo "===== 2. hermes memory status (provider installed/available/active) ====="
hermes memory status 2>&1 | grep -iE "provider|plugin|status|available|active|memoir" | head -12

echo
echo "===== 3. provider load + /memoir slash command (Hermes loaders) ====="
python3 - <<'PY'
from hermes_cli.plugins import discover_plugins, get_plugin_commands, get_plugin_command_handler
discover_plugins(force=True)
print("slash /memoir registered:", "memoir" in get_plugin_commands())
from plugins.memory import load_memory_provider
p = load_memory_provider("memoir")
print("provider loads:", bool(p) and p.name == "memoir", "| available:", p.is_available() if p else None)
print("tools:", [s["name"] for s in p.get_tool_schemas()] if p else None)
p.initialize("docker-sess", hermes_home="/data", agent_context="primary")  # ensures the store
print("store at:", p._store_path)
h = get_plugin_command_handler("memoir")
print("/memoir status →\n" + (h("status") if h else "NO HANDLER"))
PY

echo
echo "===== 4. real auto-capture (needs ANTHROPIC_API_KEY) ====="
printf '[Human]\nFrom now on call me Captain, and my dog Rex sees the vet every March.\n[Assistant]\nUnderstood, Captain.\n' \
  | memoir -s /data/memoir-store capture --profile assistant 2>&1 | tail -22

echo
echo "===== 5. store contents after capture ====="
memoir --json -s /data/memoir-store summarize --depth 3 -n default 2>/dev/null \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print('default keys:', sorted((d.get('prefix_counts') or {}).get('default',{})))"

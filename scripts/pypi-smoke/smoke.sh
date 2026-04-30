#!/usr/bin/env bash
# In-container smoke test for memoir-ai installed from PyPI.
# Asserts CLI works offline, then starts the UI and asserts the
# server + bundled React app + key API endpoints respond.
set -euo pipefail

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok: $*"; }

: "${MEMOIR_VERSION:?MEMOIR_VERSION must be set (set as Docker ARG/ENV)}"

echo "== memoir-ai $MEMOIR_VERSION =="
which memoir || fail "memoir not on PATH"

# --- CLI smoke (offline, no API key) ---
echo "[CLI]"
memoir --version | grep -qE "^memoir, version ${MEMOIR_VERSION}$" \
  || fail "version mismatch: $(memoir --version)"
ok "memoir --version → $MEMOIR_VERSION"

memoir new /tmp/store
ok "memoir new"

memoir connect /tmp/store
ok "memoir connect"

memoir remember "test fact" -p preferences.coding.style
ok "memoir remember (with -p path)"

got=$(memoir get preferences.coding.style)
echo "$got" | grep -q "test fact" \
  || fail "memoir get did not return stored content; got: $got"
ok "memoir get → returned stored content"

memoir branch | grep -q "main" || fail "no main branch"
ok "memoir branch → main present"

memoir status >/dev/null
ok "memoir status"

# --- UI smoke ---
echo "[UI]"
memoir ui /tmp/store --no-browser --port 9090 --idle-timeout 0 &
UI_PID=$!
trap 'kill $UI_PID 2>/dev/null || true' EXIT

# Wait up to ~10s for the server to bind.
for i in $(seq 1 20); do
  curl -fsS http://127.0.0.1:9090/ >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fsS http://127.0.0.1:9090/ >/dev/null 2>&1 \
  || fail "UI did not come up on :9090"
ok "UI server bound on :9090"

curl -fsS -o /tmp/index.html http://127.0.0.1:9090/
grep -q '<div id="root"' /tmp/index.html \
  || fail "served HTML missing React root <div id=\"root\">"
ok "/  → served HTML with React root"

curl -fsS "http://127.0.0.1:9090/api/branches?path=/tmp/store" \
  | python -c "import json,sys; d=json.load(sys.stdin); assert d, 'empty branches response'" \
  || fail "/api/branches did not return non-empty JSON"
ok "/api/branches → JSON"

curl -fsS "http://127.0.0.1:9090/api/current-branch?path=/tmp/store" >/dev/null \
  || fail "/api/current-branch failed"
ok "/api/current-branch → 200"

if [[ "${MEMOIR_SMOKE_HEADLESS:-0}" == "1" ]]; then
  echo
  echo "OK: automated checks passed for memoir-ai $MEMOIR_VERSION (headless)."
  exit 0
fi

cat <<EOF

==============================================================
OK: automated checks passed for memoir-ai $MEMOIR_VERSION.

UI is live at:  http://localhost:9090
                http://localhost:9090/?path=/tmp/store&readonly=0&usellm=0

Open the URL in your host browser and confirm:
  1. Page loads (no white screen, no "failed to fetch").
  2. Timeline view renders.
  3. You can click a branch and open a key detail panel.
  4. Browser DevTools Console shows no red errors.

Press Ctrl-C in this terminal when done.
==============================================================
EOF

wait $UI_PID

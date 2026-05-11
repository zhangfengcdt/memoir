#!/usr/bin/env bash
# memoir-ui-ctl.sh — start/status/stop the memoir UI background server.
#
# Usage:
#   memoir-ui-ctl.sh start <STORE_PATH>     # reuse if running, else launch
#   memoir-ui-ctl.sh status [<STORE_PATH>]  # one store or all
#   memoir-ui-ctl.sh stop   [<STORE_PATH>]  # one store or all
#
# `start` prints a single-line JSON document describing the live server
# (pid, port, url, store, started, reused). `status` and `stop` print
# human-readable text.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for p in "$HOME/.local/bin" "$HOME/.cargo/bin" "$HOME/bin" "/usr/local/bin"; do
    [[ -d "$p" ]] && [[ ":$PATH:" != *":$p:"* ]] && export PATH="$p:$PATH"
done

# shellcheck source=resolve-memoir-cli.sh
source "$SCRIPT_DIR/resolve-memoir-cli.sh"

PIDFILE_DIR="${HOME}/.memoir/ui-servers"
mkdir -p "$PIDFILE_DIR"

pidfile_for() {
    # Filename = first 8 hex chars of sha256(absolute store path).
    local store="$1"
    local hash
    hash=$(printf '%s' "$store" | python3 -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.read().encode()).hexdigest()[:8])')
    printf '%s/%s.json\n' "$PIDFILE_DIR" "$hash"
}

json_get() {
    # json_get <file> <key>  -> prints value or empty
    python3 -c '
import json, sys
try:
    with open(sys.argv[1]) as f:
        d = json.load(f)
    v = d.get(sys.argv[2], "")
    print(v if v is not None else "")
except Exception:
    pass
' "$1" "$2"
}

server_alive() {
    # server_alive <pid> <url>  -> exit 0 if process is running AND the
    # URL answers. Both checks catch distinct failure modes (crashed
    # process vs. OS-level port reuse).
    local pid="$1" url="$2"
    [ -n "$pid" ] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    curl -sf -o /dev/null --max-time 2 "$url" || return 1
    return 0
}

open_in_browser() {
    # python3 -m webbrowser works on macOS, Linux, and WSL without deps.
    local url="$1"
    python3 -m webbrowser -t "$url" >/dev/null 2>&1 || true
}

cmd_start() {
    local store="${1:-}"
    if [ -z "$store" ]; then
        echo "usage: memoir-ui-ctl.sh start <STORE_PATH>" >&2
        return 2
    fi
    if [ "${#MEMOIR_CMD_ARGV[@]}" -eq 0 ]; then
        echo "$MEMOIR_INSTALL_HINT" >&2
        return 127
    fi
    # First-time-user safety net: bootstrap the store if SessionStart didn't
    # (e.g. memoir was installed mid-session). ensure-store.sh is idempotent.
    if [ ! -d "$store/.git" ]; then
        bash "$SCRIPT_DIR/ensure-store.sh" "$store" >/dev/null || {
            echo "failed to bootstrap memoir store at $store" >&2
            return 3
        }
    fi
    # Resolve to absolute path so two invocations with different relative
    # forms still hash to the same pidfile.
    store=$(cd "$store" && pwd -P)

    local pidfile; pidfile=$(pidfile_for "$store")

    # --- reuse path ---
    if [ -f "$pidfile" ]; then
        local pid url
        pid=$(json_get "$pidfile" pid)
        url=$(json_get "$pidfile" url)
        if server_alive "$pid" "$url"; then
            open_in_browser "$url"
            # Emit the existing pidfile contents with reused=true merged in.
            python3 -c '
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
d["reused"] = True
print(json.dumps(d))
' "$pidfile"
            return 0
        fi
        # Stale pidfile — scrub and fall through to launch.
        rm -f "$pidfile"
    fi

    # --- launch path ---
    local log
    log=$(mktemp -t memoir-ui.XXXXXX.log)
    # Subshell + nohup + stdio redirection fully detaches the server
    # from this script's process group; it survives when the skill's
    # Bash tool call returns.
    ( nohup "${MEMOIR_CMD_ARGV[@]}" ui "$store" </dev/null >"$log" 2>&1 & echo $! ) > "$log.pid"
    local pid; pid=$(cat "$log.pid")
    rm -f "$log.pid"

    # Poll for the "Opening ... at http://localhost:<port>/?store=..."
    # line (CLI prints this inside the on_ready callback after bind
    # succeeds). Ceiling at ~3s.
    local url="" deadline=$((SECONDS + 3))
    while [ "$SECONDS" -lt "$deadline" ]; do
        url=$(grep -oE 'http://localhost:[0-9]+/\?store=[^ ]+' "$log" 2>/dev/null | head -1 || true)
        [ -n "$url" ] && break
        # Bail early if the process has already died.
        if ! kill -0 "$pid" 2>/dev/null; then
            break
        fi
        sleep 0.2
    done

    if [ -z "$url" ] || ! kill -0 "$pid" 2>/dev/null; then
        echo "memoir ui failed to start. Log tail:" >&2
        tail -40 "$log" >&2 || true
        rm -f "$log"
        return 4
    fi

    # Derive port from the URL for convenience.
    local port; port=$(printf '%s' "$url" | sed -E 's|.*localhost:([0-9]+)/.*|\1|')
    local started; started=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    python3 - "$pidfile" "$pid" "$port" "$url" "$store" "$started" "$log" <<'PY'
import json, sys
pidfile, pid, port, url, store, started, log = sys.argv[1:]
with open(pidfile, 'w') as f:
    json.dump({
        "pid": int(pid),
        "port": int(port),
        "url": url,
        "store": store,
        "started": started,
        "log": log,
    }, f)
print(json.dumps({
    "pid": int(pid),
    "port": int(port),
    "url": url,
    "store": store,
    "started": started,
    "log": log,
    "reused": False,
}))
PY
}

cmd_status() {
    local store="${1:-}"
    if [ -n "$store" ]; then
        store=$(cd "$store" && pwd -P 2>/dev/null || echo "$store")
        local pidfile; pidfile=$(pidfile_for "$store")
        if [ ! -f "$pidfile" ]; then
            echo "not running: $store"
            return 0
        fi
        local pid url; pid=$(json_get "$pidfile" pid); url=$(json_get "$pidfile" url)
        if server_alive "$pid" "$url"; then
            echo "running: pid=$pid url=$url store=$store"
        else
            echo "stale  : pid=$pid url=$url store=$store (cleanup with stop)"
        fi
        return 0
    fi
    # list all
    shopt -s nullglob
    local any=0
    for pidfile in "$PIDFILE_DIR"/*.json; do
        any=1
        local pid url s; pid=$(json_get "$pidfile" pid); url=$(json_get "$pidfile" url); s=$(json_get "$pidfile" store)
        if server_alive "$pid" "$url"; then
            echo "running: pid=$pid url=$url store=$s"
        else
            echo "stale  : pid=$pid url=$url store=$s"
        fi
    done
    [ "$any" -eq 0 ] && echo "no memoir-ui servers tracked"
}

stop_one() {
    local pidfile="$1"
    [ -f "$pidfile" ] || return 0
    local pid; pid=$(json_get "$pidfile" pid)
    local url; url=$(json_get "$pidfile" url)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        # Give it a moment, then SIGKILL if still around.
        for _ in 1 2 3 4 5; do
            kill -0 "$pid" 2>/dev/null || break
            sleep 0.2
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
        fi
        echo "stopped pid=$pid url=$url"
    else
        echo "already gone: pid=$pid url=$url"
    fi
    rm -f "$pidfile"
}

cmd_stop() {
    local store="${1:-}"
    if [ -n "$store" ]; then
        store=$(cd "$store" && pwd -P 2>/dev/null || echo "$store")
        stop_one "$(pidfile_for "$store")"
        return 0
    fi
    shopt -s nullglob
    local any=0
    for pidfile in "$PIDFILE_DIR"/*.json; do
        any=1
        stop_one "$pidfile"
    done
    [ "$any" -eq 0 ] && echo "no memoir-ui servers tracked"
}

sub="${1:-}"
shift || true
case "$sub" in
    start)  cmd_start  "$@" ;;
    status) cmd_status "$@" ;;
    stop)   cmd_stop   "$@" ;;
    *)
        cat >&2 <<EOF
usage: memoir-ui-ctl.sh <start|status|stop> [<STORE_PATH>]
  start  <STORE_PATH>     launch the UI (or reopen if already running)
  status [<STORE_PATH>]   show one store's server, or all
  stop   [<STORE_PATH>]   stop one store's server, or all
EOF
        exit 2
        ;;
esac

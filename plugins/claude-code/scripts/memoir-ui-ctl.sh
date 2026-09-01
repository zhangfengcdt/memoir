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
#
# Thin wrapper: the pidfile bookkeeping and daemon lifecycle (launch,
# liveness polling, graceful-then-forced stop) now live in memoir-ai core
# as `memoir ui-start` / `ui-status` / `ui-stop`, shared by every host
# plugin instead of each carrying its own copy. See
# src/memoir/ui/daemon.py in the memoir-ai package.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=resolve-memoir-cli.sh
source "$SCRIPT_DIR/resolve-memoir-cli.sh"

if [ "${#MEMOIR_CMD_ARGV[@]}" -eq 0 ]; then
  echo "$MEMOIR_INSTALL_HINT" >&2
  exit 127
fi

cmd_start() {
  local store="${1:-}"
  if [ -z "$store" ]; then
    echo "usage: memoir-ui-ctl.sh start <STORE_PATH>" >&2
    return 2
  fi
  # Re-serialize as a single compact line regardless of how the CLI
  # formatted it — this is the documented contract callers (commands/ui.md)
  # parse with `json.load`.
  "${MEMOIR_CMD_ARGV[@]}" --json ui-start "$store" \
    | python3 -c 'import json, sys; print(json.dumps(json.load(sys.stdin)))'
}

sub="${1:-}"
shift || true
case "$sub" in
  start)
    cmd_start "$@"
    ;;
  status)
    "${MEMOIR_CMD_ARGV[@]}" ui-status "$@"
    ;;
  stop)
    "${MEMOIR_CMD_ARGV[@]}" ui-stop "$@"
    ;;
  *)
    echo "usage: memoir-ui-ctl.sh {start|status|stop} [STORE_PATH]" >&2
    exit 2
    ;;
esac

#!/usr/bin/env bash
# SessionEnd hook: clear this session's heartbeat file so future sessions'
# concurrent-session detector doesn't spuriously warn on our stale state.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

remove_session_heartbeat 2>/dev/null || true
exit 0

#!/usr/bin/env bash
# SessionEnd hook: restore memoir to the branch matching the current code
# branch (unless sticky opt-out is active).
#
# Rationale: if the session ended with memoir on a non-matching branch — e.g.
# the user invoked `memoir checkout` directly from a terminal, or a mid-session
# hook left state inconsistent — aligning on exit means any subsequent
# terminal use of `memoir` or the next Claude Code session starts from a
# clean, predictable place. auto_match_memoir_branch honors the sticky
# marker, so experiment branches the user explicitly chose are preserved.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Re-align memoir branch to the code branch if drifted. No-op when they
# already match or when sticky is active.
auto_match_memoir_branch 2>/dev/null || true

exit 0

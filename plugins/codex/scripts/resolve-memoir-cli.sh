#!/usr/bin/env bash
# Resolve how the plugin should invoke the memoir CLI on this machine.
#
# This file is meant to be SOURCED, not executed. It exports two variables:
#
#   MEMOIR_CMD       — human-readable form, e.g. "memoir" or
#                      "uvx --from memoir-ai==<pin> memoir". Empty if no
#                      working invocation exists. Hooks use
#                      `[ -z "$MEMOIR_CMD" ]` as the "is the CLI available?"
#                      check.
#
#   MEMOIR_CMD_ARGV  — bash array suitable for direct invocation, i.e.
#                      "${MEMOIR_CMD_ARGV[@]}" --json -s "$STORE" status
#                      Multi-token forms (uvx, uv tool run) need the array
#                      because they expand to several argv entries.
#
# Preference order:
#   1. `memoir` on PATH — explicit install (pip / pipx / uv tool install).
#      Fastest cold start, no warmup. The plugin trusts whatever version
#      the user installed; we do not pin this branch.
#   2. `uvx --from memoir-ai==<pin> memoir` — uv installed, no global
#      memoir. Ephemeral, no Python env pollution, ~1s warmup on first use
#      then cached. Pinned (see MEMOIR_AI_PIN below).
#   3. `uv tool run --from memoir-ai==<pin> memoir` — uv installed but uvx
#      shim missing (older uv layouts). Same pin as branch 2.
#   4. Empty — caller must surface an install hint.
#
# Hooks add common user bin paths to PATH before sourcing this; standalone
# scripts and skills should do the same if they want to find a
# user-local pip install.

# Pin the published memoir-ai version that the uvx / uv-tool-run fallbacks
# resolve to. The Codex plugin and the memoir-ai PyPI package version
# independently (see scripts/check_version_consistency.py — they form two
# separate version groups). This pin is the plugin's downstream constraint
# against the published package; bump it deliberately after verifying the
# new release works with the current plugin.
MEMOIR_AI_PIN="0.2.0"

if command -v memoir &>/dev/null; then
  MEMOIR_CMD="memoir"
  MEMOIR_CMD_ARGV=(memoir)
elif command -v uvx &>/dev/null; then
  MEMOIR_CMD="uvx --from memoir-ai==${MEMOIR_AI_PIN} memoir"
  MEMOIR_CMD_ARGV=(uvx --from "memoir-ai==${MEMOIR_AI_PIN}" memoir)
elif command -v uv &>/dev/null; then
  MEMOIR_CMD="uv tool run --from memoir-ai==${MEMOIR_AI_PIN} memoir"
  MEMOIR_CMD_ARGV=(uv tool run --from "memoir-ai==${MEMOIR_AI_PIN}" memoir)
else
  MEMOIR_CMD=""
  MEMOIR_CMD_ARGV=()
fi

# Canonical install hint — matches session-start.sh wording so the user
# sees the same message regardless of which entry point hit the missing-CLI
# state. Caller decides when (and via which channel) to print it.
MEMOIR_INSTALL_HINT="memoir CLI not found. Install one of: \`pip install memoir-ai\`, \`pipx install memoir-ai\`, \`uv tool install memoir-ai\`, or install \`uv\` for transparent uvx fallback."

#!/usr/bin/env bash
# Resolver should see user-installed tools even when the host provides a
# minimal PATH that omits the user's shell profile.

set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESOLVER="$(cd "$TEST_DIR/../scripts" && pwd)/resolve-memoir-cli.sh"
TMP_HOME="$(mktemp -d -t memoir-resolve-test.XXXXXX)"
trap 'rm -rf "$TMP_HOME"' EXIT

mkdir -p "$TMP_HOME/.local/bin"
printf '#!/usr/bin/env sh\nexit 0\n' > "$TMP_HOME/.local/bin/uv"
chmod +x "$TMP_HOME/.local/bin/uv"

env -i PATH=/usr/bin:/bin HOME="$TMP_HOME" RESOLVER="$RESOLVER" /bin/bash -c '
  set -euo pipefail
  source "$RESOLVER"
  [[ "${MEMOIR_CMD_ARGV[0]}" == "uv" ]]
  [[ "${MEMOIR_CMD_ARGV[1]}" == "tool" ]]
  [[ "${MEMOIR_CMD_ARGV[2]}" == "run" ]]
  [[ "${MEMOIR_CMD_ARGV[3]}" == "--from" ]]
  [[ "${MEMOIR_CMD_ARGV[4]}" == "memoir-ai==${MEMOIR_AI_PIN}" ]]
  [[ "${MEMOIR_CMD_ARGV[5]}" == "memoir" ]]
'

echo "PASS: resolver finds uv in a user bin directory outside the original PATH"

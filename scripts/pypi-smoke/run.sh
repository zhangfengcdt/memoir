#!/usr/bin/env bash
# Host entry point: build the smoke-test image and run it with the UI
# port forwarded to the host so you can open it in your browser.
#
# Usage:
#   scripts/pypi-smoke/run.sh <pypi-version>
# Example:
#   scripts/pypi-smoke/run.sh 0.1.4
set -euo pipefail

VERSION="${1:?usage: $(basename "$0") <pypi-version>   (e.g. 0.1.4)}"

# Always run from the directory this script lives in so the build context
# is correct regardless of where the caller invoked it from.
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker build \
  --build-arg "MEMOIR_VERSION=${VERSION}" \
  -t "memoir-pypi-smoke:${VERSION}" \
  "${HERE}"

# Forward ANTHROPIC_API_KEY from the host environment into the container so
# LLM-backed cases can run. If unset, the container picks up an empty string
# and the smoke script gracefully skips those cases.
docker run --rm -it -p 9090:9090 \
  -e "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}" \
  "memoir-pypi-smoke:${VERSION}"

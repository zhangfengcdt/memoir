# Smoke-test the memoir Hermes plugin in a clean container.
#
# Builds a slim image with Hermes + the memoir CLI, installs the plugin via the
# `owner/repo/subdir` path, and activates it. Run `test.sh` inside to verify
# install → provider load → tools → /memoir slash command → real auto-capture.
#
#   docker build -t hermes-memoir-test plugins/docker-tests/hermes
#   docker run --rm -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
#       -v "$PWD/plugins/docker-tests/hermes/test.sh:/test.sh:ro" \
#       hermes-memoir-test bash /test.sh
#
# Notes:
# - Hermes is installed from `main`: the subdir-aware `hermes plugins install
#   owner/repo/subdir` postdates the 0.16.0 release. Pin HERMES_REF to a tag
#   once a release includes it.
# - memoir-ai is the published CLI (>= 0.2.3 ships `capture`). The plugin shells
#   out to it; PATH `memoir` wins, else a pinned uvx fallback.
FROM python:3.12-slim

ARG HERMES_REF=main
ARG MEMOIR_AI_VERSION=0.2.3
ARG MEMOIR_REPO=zhangfengcdt/memoir
ARG MEMOIR_PLUGIN=zhangfengcdt/memoir/plugins/hermes

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "hermes-agent @ git+https://github.com/NousResearch/hermes-agent@${HERMES_REF}"
RUN pip install --no-cache-dir "memoir-ai==${MEMOIR_AI_VERSION}"

ENV HERMES_HOME=/data
RUN mkdir -p /data

# Install via the owner/repo/subdir shorthand, then activate as the memory
# provider and enable the in-session /memoir command.
RUN hermes plugins install ${MEMOIR_PLUGIN} --no-enable \
    && printf 'memory:\n  provider: memoir\nplugins:\n  enabled:\n    - memoir\n' > /data/config.yaml

CMD ["bash"]

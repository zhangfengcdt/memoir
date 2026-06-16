# Smoke-test the memoir Codex plugin in a clean container.
#
# Installs the Codex CLI + the memoir CLI + the plugin (from a repo checkout),
# then `test.sh` verifies the plugin's memoir wiring headlessly: CLI
# resolution, store creation, and capture. The plugin is bash hooks + skills
# that shell out to `memoir`; a live hook-driven Codex session additionally
# needs Codex auth (out of scope for an unattended smoke test).
#
#   docker build -t memoir-codex-test plugins/docker-tests/codex
#   docker run --rm -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
#       -v "$PWD/plugins/docker-tests/codex/test.sh:/test.sh:ro" \
#       memoir-codex-test bash /test.sh
FROM node:22-bookworm-slim

ARG MEMOIR_AI_VERSION=0.2.3
ARG MEMOIR_REF=main

RUN apt-get update && apt-get install -y --no-install-recommends \
        git python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# memoir CLI (what the plugin's hooks/scripts shell out to).
RUN pip install --no-cache-dir --break-system-packages "memoir-ai==${MEMOIR_AI_VERSION}"
# Codex CLI (the host agent).
RUN npm install -g @openai/codex

# Plugin source (hooks/skills/scripts) from the repo.
RUN git clone --depth 1 --branch "${MEMOIR_REF}" https://github.com/zhangfengcdt/memoir /opt/memoir
ENV MEMOIR_PLUGIN_ROOT=/opt/memoir/plugins/codex

CMD ["bash"]

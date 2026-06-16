# Smoke-test the memoir Claude Code plugin in a clean container.
#
# Installs the Claude Code CLI + the memoir CLI + the plugin (from a repo
# checkout), then `test.sh` verifies the plugin's memoir wiring headlessly:
# CLI resolution, store creation, and capture. The plugin is bash hooks +
# skills that shell out to `memoir`, so the smoke test exercises that path;
# a live hook-driven session additionally needs Claude Code auth (out of
# scope for an unattended smoke test).
#
#   docker build -t memoir-claude-code-test plugins/docker-tests/claude-code
#   docker run --rm -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
#       -v "$PWD/plugins/docker-tests/claude-code/test.sh:/test.sh:ro" \
#       memoir-claude-code-test bash /test.sh
FROM node:22-bookworm-slim

ARG MEMOIR_AI_VERSION=0.2.3
ARG MEMOIR_REF=main

RUN apt-get update && apt-get install -y --no-install-recommends \
        git python3 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# memoir CLI (what the plugin's hooks/scripts shell out to).
RUN pip install --no-cache-dir --break-system-packages "memoir-ai==${MEMOIR_AI_VERSION}"
# Claude Code CLI (the host agent).
RUN npm install -g @anthropic-ai/claude-code

# Plugin source (hooks/skills/scripts) from the repo.
RUN git clone --depth 1 --branch "${MEMOIR_REF}" https://github.com/zhangfengcdt/memoir /opt/memoir
ENV CLAUDE_PLUGIN_ROOT=/opt/memoir/plugins/claude-code

CMD ["bash"]

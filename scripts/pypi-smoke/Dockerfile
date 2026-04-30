FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    chromium fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

ARG MEMOIR_VERSION
ENV MEMOIR_VERSION=${MEMOIR_VERSION}

# Install with the [litellm] extra so LLM-backed CLI commands (recall,
# remember without -p) can actually run. Without this extra, memoir's LLM
# code path raises ImportError at runtime — which IS the documented behavior,
# but a meaningful end-to-end smoke needs LLM features wired up.
RUN pip install --no-cache-dir "memoir-ai[litellm]==${MEMOIR_VERSION}"

# Sane defaults for git inside the container (memoir stores are git repos)
RUN git config --global user.email "smoke@memoir.test" \
    && git config --global user.name "memoir smoke"

COPY smoke.sh /smoke.sh
RUN chmod +x /smoke.sh

EXPOSE 9090
CMD ["/smoke.sh"]

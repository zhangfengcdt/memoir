FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates \
    chromium fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

ARG MEMOIR_VERSION
ENV MEMOIR_VERSION=${MEMOIR_VERSION}

# [litellm] is a no-op extra in v0.1.7+ (litellm is a default dep) but
# required for v0.1.5 / v0.1.6 to enable the LLM code path. Keeping it on
# the install line lets the same harness smoke any of those versions.
RUN pip install --no-cache-dir "memoir-ai[litellm]==${MEMOIR_VERSION}"

# Sane defaults for git inside the container (memoir stores are git repos)
RUN git config --global user.email "smoke@memoir.test" \
    && git config --global user.name "memoir smoke"

COPY smoke.sh /smoke.sh
RUN chmod +x /smoke.sh

EXPOSE 9090
CMD ["/smoke.sh"]

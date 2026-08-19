FROM docker:27-cli AS docker-cli

FROM nousresearch/hermes-agent:main

# Copy Docker CLI from official image (docker.io apt package is unreliable on
# this base image). The host Docker engine is accessed via the bind-mounted
# /var/run/docker.sock — no daemon runs inside the container.
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
RUN ln -sf /usr/local/bin/docker /usr/bin/docker

ENV PATH="/opt/data/bin:/workspace/scripts:/opt/hermes/.venv/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin"

RUN apt-get update && apt-get install -y \
    python3 \
    python3-venv \
    bash \
    file \
    grep \
    git \
    vim \
    docker.io \
    ripgrep \
    findutils \
    coreutils \
    net-tools \
    curl \
    procps \
    iproute2 \
    strace \
    tini \
    nodejs && rm -rf /var/lib/apt/lists/*

# Smoke-test: confirm docker CLI is reachable
RUN docker --version

# Stdio-based MCP terminal server for Hermes's built-in Terminal tool.
# Hermes spawns this via MCP_TERMINAL_CMD and sends JSON-RPC over stdin/stdout.
COPY mcp-terminal-stdio.js /opt/hermes/mcp-terminal-stdio.js
COPY skills/investment-analyst/SKILL.md /usr/local/share/hermes-seed-skills/investment-analyst/SKILL.md
COPY skills/investment-broker/SKILL.md /usr/local/share/hermes-seed-skills/investment-broker/SKILL.md
COPY skills/investment-analysis-cycle/SKILL.md /usr/local/share/hermes-seed-skills/investment-analysis-cycle/SKILL.md
COPY docker-entrypoint.sh /usr/local/bin/hermes-entrypoint.sh
RUN chmod +x /usr/local/bin/hermes-entrypoint.sh

# napraw venv pip (to jest KLUCZ)
RUN /opt/hermes/.venv/bin/python -m ensurepip --upgrade || true
RUN /opt/hermes/.venv/bin/python -m pip install --upgrade pip setuptools wheel

# teraz zależności
COPY requirements.txt .
RUN /opt/hermes/.venv/bin/python -m pip install --no-cache-dir \
    --default-timeout=200 \
    --retries 10 \
    -r requirements.txt

ENTRYPOINT ["/usr/local/bin/hermes-entrypoint.sh"]

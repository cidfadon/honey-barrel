FROM docker:27-cli AS docker-cli

FROM python:3.11-slim

# Copy Docker CLI only (no full docker daemon needed — we talk to host socket)
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /app

# Minimal system deps: only gcc (for any C extensions) + curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --default-timeout=200 \
    --retries 10 \
    -r requirements.txt

# Copy application code
COPY . .

# Create data directories
RUN mkdir -p /data/cache /data/models

EXPOSE 8001

CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8001"]

# ClawLite - Lightweight Agentic AI Container
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ripgrep \
    procps \
    cron \
    libmagic1 \
    gosu \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (add to crontab group for cron access)
RUN groupadd -r clawlite && useradd -r -g clawlite -G crontab -d /app -s /sbin/nologin clawlite

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and templates
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY templates/ ./templates/

# Copy example config (actual config.yaml should be mounted)
COPY config-example.yaml ./config-example.yaml

# Copy scripts directory (includes reminder daemon)
COPY scripts/ ./scripts/

# Copy entrypoint and CLI scripts to PATH
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && chmod +x /app/scripts/*.sh /app/scripts/*.py 2>/dev/null || true \
    && ln -sf /app/scripts/clawlite-send /usr/local/bin/ \
    && ln -sf /app/scripts/clawlite-prompt /usr/local/bin/

# Create data directories
RUN mkdir -p /data/whatsapp && chown -R clawlite:clawlite /data

# Set ownership
RUN chown -R clawlite:clawlite /app

# NOTE: Not switching to non-root here - entrypoint handles it
# This allows starting cron daemon before dropping privileges

# Volumes
VOLUME ["/workspace", "/data/whatsapp"]

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Use entrypoint for auto-bootstrap
ENTRYPOINT ["docker-entrypoint.sh"]

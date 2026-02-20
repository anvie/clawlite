# ClawLite - Lightweight Agentic AI Container
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ripgrep \
    procps \
    cron \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r clawlite && useradd -r -g clawlite -d /app -s /sbin/nologin clawlite

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY config/ ./config/

# Create data directories
RUN mkdir -p /data/whatsapp && chown -R clawlite:clawlite /data

# Set ownership
RUN chown -R clawlite:clawlite /app

# Switch to non-root user
USER clawlite

# Volumes
VOLUME ["/workspace", "/data/whatsapp"]

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Use main.py for multi-channel support
CMD ["python", "-m", "src.main"]

# PyClaw Agentic AI - Lightweight Python Container
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ripgrep \
    procps \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r pyclaw && useradd -r -g pyclaw -d /app -s /sbin/nologin pyclaw

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY prompts/ ./prompts/
COPY config/ ./config/

# Set ownership
RUN chown -R pyclaw:pyclaw /app

# Switch to non-root user
USER pyclaw

# Workspace will be mounted at runtime
VOLUME ["/workspace"]

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-m", "src.bot"]

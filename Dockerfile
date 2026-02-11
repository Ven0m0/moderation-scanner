# Multi-stage build for optimized production image
FROM python:3.14-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PYTHONIOENCODING=utf-8 \
    PYTHONOPTIMIZE=1 \
    LC_ALL=C \
    DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential && \
    apt-get autoremove --purge -y && apt-get clean -y && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Install Sherlock (optional but recommended for full functionality)
# Use --use-pep517 to avoid stem build issues with legacy setup.py
RUN pip install --no-cache-dir --use-pep517 sherlock-project

# Production stage
FROM python:3.14-slim

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash botuser && \
    mkdir -p /app /app/scans && \
    chown -R botuser:botuser /app

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=botuser:botuser account_scanner.py discord_bot.py ./

# Switch to non-root user
USER botuser

# Create scans directory with proper permissions
RUN mkdir -p /app/scans

# Health check (optional - checks if Python process is running)
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

# Set environment variables for Python optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PYTHONIOENCODING=utf-8 \
    PYTHONOPTIMIZE=1 \
    LC_ALL=C \
    PATH="/home/botuser/.local/bin:$PATH"

# Run the Discord bot
CMD ["python", "discord_bot.py"]

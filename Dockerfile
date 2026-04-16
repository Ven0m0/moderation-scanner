ARG PYTHON_VERSION=3.14

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=1 \
    PYTHONHASHSEED=0 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LC_ALL=C.UTF-8 \
    DEBIAN_FRONTEND=noninteractive \
    DEBCONF_NOWARNINGS=yes

# Install build dependencies
RUN apt-get update -qq && apt-get install -yqq --no-install-recommends \
    build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy only the files needed to build the package
COPY pyproject.toml README.md ./
COPY src ./src

# Build wheels once so the runtime image can install without compilers
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip wheel --no-cache-dir --wheel-dir /tmp/wheels . sherlock-project

# Production stage
FROM python:${PYTHON_VERSION}-slim

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash botuser && \
    mkdir -p /app /app/scans && \
    chown -R botuser:botuser /app

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=1 \
    PYTHONHASHSEED=0 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LC_ALL=C.UTF-8

COPY --from=builder /tmp/wheels /tmp/wheels

RUN python3 -m pip install --no-cache-dir /tmp/wheels/* && \
    rm -rf /tmp/wheels

USER botuser

# Run the Discord bot
CMD ["scanner-bot"]

FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Install Sherlock
RUN pip install sherlock-project

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install application
RUN pip install --no-cache-dir -e .

# Create scans directory
RUN mkdir -p /app/scans

# Run as non-root user
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app
USER botuser

# Run bot
CMD ["python", "-m", "discord_bot"]

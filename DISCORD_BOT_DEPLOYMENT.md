# Discord Bot Deployment Guide

Complete guide for deploying the Account Scanner Discord bot to production.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [Installation](#installation)
- [Deployment Options](#deployment-options)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Security Best Practices](#security-best-practices)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required
- Python 3.11 or 3.12
- Discord Bot Token (from Discord Developer Portal)
- Sherlock OSINT tool (optional, for OSINT scanning)

### Optional
- Perspective API Key (for Reddit toxicity scanning)
- Reddit API Credentials (for Reddit scanning)

## Configuration

### Environment Variables

Create a `.env` file or set environment variables:

```bash
# Required
DISCORD_BOT_TOKEN=your_discord_bot_token_here

# Optional - Reddit Toxicity Scanning
PERSPECTIVE_API_KEY=your_perspective_api_key
REDDIT_CLIENT_ID=your_reddit_client_id
REDDIT_CLIENT_SECRET=your_reddit_client_secret
REDDIT_USER_AGENT=account-scanner-bot/1.2.3

# Optional - Admin Controls
ADMIN_USER_IDS=123456789,987654321  # Comma-separated Discord user IDs
LOG_CHANNEL_ID=123456789012345678   # Discord channel ID for logging
```

### Getting API Credentials

#### Discord Bot Token

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application"
3. Go to "Bot" section
4. Click "Add Bot"
5. Under "Token", click "Copy" to get your bot token
6. Enable required Privileged Gateway Intents:
   - ✅ Message Content Intent

#### Perspective API Key

1. Go to [Perspective API](https://perspectiveapi.com/)
2. Request API access
3. Create a project in Google Cloud Console
4. Enable Perspective Comment Analyzer API
5. Create credentials (API key)

#### Reddit API Credentials

1. Go to [Reddit Apps](https://www.reddit.com/prefs/apps)
2. Click "create another app..."
3. Select "script" type
4. Note your `client_id` (under app name) and `client_secret`

#### Sherlock Installation

```bash
# Using pip
pip install sherlock-project

# Using pipx (recommended)
pipx install sherlock-project

# Verify installation
sherlock --version
```

## Installation

### Method 1: From Source

```bash
# Clone repository
git clone https://github.com/Ven0m0/moderation-scanner.git
cd moderation-scanner

# Install dependencies
pip install -e .

# Or with development dependencies
pip install -e ".[dev]"

# Install Sherlock separately
pipx install sherlock-project
```

### Method 2: Using pip

```bash
# Once published to PyPI
pip install account-scanner

# Install Sherlock separately
pipx install sherlock-project
```

## Deployment Options

### Option 1: Systemd Service (Linux)

Create `/etc/systemd/system/discord-scanner-bot.service`:

```ini
[Unit]
Description=Account Scanner Discord Bot
After=network.target

[Service]
Type=simple
User=botuser
WorkingDirectory=/opt/discord-scanner-bot
Environment="PATH=/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/opt/discord-scanner-bot/.env
ExecStart=/usr/bin/python3 -m discord_bot
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/discord-scanner-bot/scans

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable discord-scanner-bot
sudo systemctl start discord-scanner-bot
sudo systemctl status discord-scanner-bot
```

### Option 2: Docker

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

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
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app
USER botuser

# Run bot
CMD ["python", "-m", "discord_bot"]
```

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  discord-bot:
    build: .
    restart: unless-stopped
    environment:
      - DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}
      - PERSPECTIVE_API_KEY=${PERSPECTIVE_API_KEY}
      - REDDIT_CLIENT_ID=${REDDIT_CLIENT_ID}
      - REDDIT_CLIENT_SECRET=${REDDIT_CLIENT_SECRET}
      - REDDIT_USER_AGENT=${REDDIT_USER_AGENT}
      - ADMIN_USER_IDS=${ADMIN_USER_IDS}
    volumes:
      - ./scans:/app/scans
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

Deploy:

```bash
docker-compose up -d
docker-compose logs -f
```

### Option 3: Kubernetes

Create `k8s-deployment.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: discord-bot-secrets
type: Opaque
stringData:
  discord-token: "your_token_here"
  perspective-key: "your_key_here"
  reddit-client-id: "your_id_here"
  reddit-client-secret: "your_secret_here"

---
apiVersion: v1
kind: ConfigMap
metadata:
  name: discord-bot-config
data:
  REDDIT_USER_AGENT: "account-scanner-bot/1.2.3"
  ADMIN_USER_IDS: "123456789"

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: discord-scanner-bot
spec:
  replicas: 1
  selector:
    matchLabels:
      app: discord-scanner-bot
  template:
    metadata:
      labels:
        app: discord-scanner-bot
    spec:
      containers:
      - name: bot
        image: your-registry/discord-scanner-bot:latest
        env:
        - name: DISCORD_BOT_TOKEN
          valueFrom:
            secretKeyRef:
              name: discord-bot-secrets
              key: discord-token
        - name: PERSPECTIVE_API_KEY
          valueFrom:
            secretKeyRef:
              name: discord-bot-secrets
              key: perspective-key
        - name: REDDIT_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: discord-bot-secrets
              key: reddit-client-id
        - name: REDDIT_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: discord-bot-secrets
              key: reddit-client-secret
        envFrom:
        - configMapRef:
            name: discord-bot-config
        volumeMounts:
        - name: scans
          mountPath: /app/scans
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
      volumes:
      - name: scans
        persistentVolumeClaim:
          claimName: scanner-scans-pvc

---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: scanner-scans-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1Gi
```

Deploy:

```bash
kubectl apply -f k8s-deployment.yaml
kubectl logs -f deployment/discord-scanner-bot
```

### Option 4: Simple Screen Session

For development/testing:

```bash
# Start in screen session
screen -S discord-bot
cd /path/to/moderation-scanner
source .env  # Load environment variables
python -m discord_bot

# Detach: Ctrl+A, then D
# Reattach: screen -r discord-bot
```

## Monitoring & Maintenance

### Logging

Bot logs include:
- Startup configuration
- Command usage (who scanned what)
- Errors and warnings
- Scan results

View logs:

```bash
# Systemd
sudo journalctl -u discord-scanner-bot -f

# Docker
docker-compose logs -f

# Kubernetes
kubectl logs -f deployment/discord-scanner-bot
```

### Health Checks

Use the `!health` command in Discord to check:
- Bot latency
- Service availability (Sherlock, Perspective API, Reddit API)
- Connected guilds and users

### Log Rotation

For systemd, logs are automatically rotated by journald.

For Docker, configure in `docker-compose.yml` (already included above).

For file-based logging, use logrotate:

```bash
# /etc/logrotate.d/discord-bot
/var/log/discord-bot/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0644 botuser botuser
    sharedscripts
    postrotate
        systemctl reload discord-scanner-bot
    endscript
}
```

### Backup Scan Data

```bash
# Backup scans directory
tar -czf scans-backup-$(date +%Y%m%d).tar.gz scans/

# Automated daily backup (cron)
0 2 * * * cd /opt/discord-scanner-bot && tar -czf /backups/scans-$(date +\%Y\%m\%d).tar.gz scans/ && find /backups -name "scans-*.tar.gz" -mtime +30 -delete
```

## Security Best Practices

### 1. Secure Secrets Management

**Never commit secrets to git:**

```bash
# Add to .gitignore
echo ".env" >> .gitignore
echo "*.pem" >> .gitignore
echo "secrets/" >> .gitignore
```

**Use secret management tools:**

- **Docker Secrets** (Swarm mode)
- **Kubernetes Secrets** (with encryption at rest)
- **HashiCorp Vault**
- **AWS Secrets Manager**
- **Azure Key Vault**

### 2. Principle of Least Privilege

Bot Discord permissions (minimal required):
- Send Messages
- Embed Links
- Read Message History
- Add Reactions

Bot should NOT have:
- Administrator
- Manage Server
- Manage Roles (unless absolutely necessary)

### 3. Rate Limiting

Bot includes built-in rate limiting:
- 1 scan per 30 seconds per user
- Configurable in code if needed

### 4. Admin Controls

Configure `ADMIN_USER_IDS` for sensitive commands:
- `!shutdown` - Only admins can shutdown bot

### 5. Network Security

For production deployments:
- Use firewalls to restrict inbound connections
- Enable TLS for all API communications (automatic with httpx)
- Consider running in isolated network namespace

### 6. Regular Updates

```bash
# Update dependencies
pip install --upgrade pip setuptools
pip install -e ".[dev]" --upgrade

# Check for vulnerabilities
pip-audit

# Update Sherlock
pipx upgrade sherlock-project
```

### 7. Monitoring & Alerting

Set up alerts for:
- Bot disconnections
- High error rates
- Failed API authentications
- Disk space (scan data accumulation)

## Troubleshooting

### Bot won't start

**Error: `DISCORD_BOT_TOKEN is required`**
- Solution: Set the `DISCORD_BOT_TOKEN` environment variable

**Error: `Invalid Discord token`**
- Solution: Verify token in Discord Developer Portal
- Regenerate token if compromised

### Commands not working

**Error: `Missing permissions`**
- Solution: Ensure bot has required Discord permissions
- Check user has "Moderate Members" permission for `!scan`

**Error: `Command not found`**
- Solution: Verify message content intent is enabled in Discord Developer Portal

### Scanning issues

**Error: `Sherlock not available`**
- Solution: Install Sherlock with `pipx install sherlock-project`
- Verify with `sherlock --version`

**Error: `Reddit scanning not configured`**
- Solution: Set all Reddit environment variables:
  - `PERSPECTIVE_API_KEY`
  - `REDDIT_CLIENT_ID`
  - `REDDIT_CLIENT_SECRET`

**Error: `Scan timeout`**
- Solution: Scan taking too long (>5 minutes)
- Try single mode: `!scan username sherlock` or `!scan username reddit`
- Check network connectivity

### Performance issues

**High memory usage:**
- Check scan data accumulation in `./scans/`
- Implement cleanup of old scans
- Consider increasing container/VM memory

**High latency:**
- Check `!health` for bot latency
- Verify network connectivity
- Consider deploying closer to Discord servers (EU/US)

### Logs and debugging

Enable verbose logging:

```python
# Modify discord_bot.py temporarily
logging.basicConfig(level=logging.DEBUG)  # Instead of INFO
```

Check specific component logs:

```bash
# Filter for errors only
journalctl -u discord-scanner-bot | grep ERROR

# Check last 100 lines
journalctl -u discord-scanner-bot -n 100
```

## Production Checklist

Before deploying to production:

- [ ] All environment variables configured
- [ ] Secrets stored securely (not in code/git)
- [ ] Bot permissions minimized in Discord
- [ ] Admin user IDs configured
- [ ] Sherlock installed and tested
- [ ] API credentials validated (Perspective, Reddit)
- [ ] Logging configured and tested
- [ ] Monitoring/alerting set up
- [ ] Backup strategy implemented
- [ ] Documentation reviewed
- [ ] Test in staging environment first
- [ ] Rollback plan prepared
- [ ] Rate limits tested
- [ ] Error handling tested
- [ ] Health check command tested

## Updates and Maintenance

### Updating the Bot

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install -e . --upgrade

# Restart service
sudo systemctl restart discord-scanner-bot

# Or for Docker
docker-compose pull
docker-compose up -d
```

### Monitoring Dependency Vulnerabilities

```bash
# Run security audit
pip-audit

# Check for outdated packages
pip list --outdated
```

### Scheduled Maintenance

Recommended maintenance schedule:
- **Weekly**: Review logs for errors
- **Monthly**: Update dependencies, run security audit
- **Quarterly**: Review and rotate API keys
- **Annually**: Full security review

## Support and Resources

- **GitHub Issues**: https://github.com/Ven0m0/moderation-scanner/issues
- **Documentation**: See README.md and DEPENDENCY_AUDIT_REPORT.md
- **Discord.py Docs**: https://discordpy.readthedocs.io/
- **Sherlock Project**: https://github.com/sherlock-project/sherlock

## License

MIT License - See LICENSE file for details

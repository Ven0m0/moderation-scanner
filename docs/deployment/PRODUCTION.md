# Production Readiness Guide

This guide covers production best practices, optimizations, and security considerations for running the Account Scanner Bot.

## Table of Contents

- [Pre-Deployment Checklist](#pre-deployment-checklist)
- [Security Best Practices](#security-best-practices)
- [Performance Optimization](#performance-optimization)
- [Monitoring & Alerts](#monitoring--alerts)
- [Backup & Recovery](#backup--recovery)
- [Rate Limiting & API Quotas](#rate-limiting--api-quotas)
- [Error Handling](#error-handling)

## Pre-Deployment Checklist

### ✅ Required Configuration

- [ ] Discord bot token set in secrets
- [ ] Reddit API credentials configured
- [ ] Perspective API key configured
- [ ] Admin user IDs set (for `!shutdown` command)
- [ ] Bot permissions configured in Discord Developer Portal
- [ ] Tested all commands in development environment

### ✅ Discord Bot Permissions

Your bot needs these Discord permissions:
- **Read Messages/View Channels**
- **Send Messages**
- **Embed Links**
- **Attach Files** (if exporting scan results)
- **Moderate Members** (required to use `!scan` command)

**OAuth2 URL Generator:**
```
https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_ID&permissions=1099511627776&scope=bot
```

### ✅ Optional but Recommended

- [ ] Set up logging channel (`LOG_CHANNEL_ID`)
- [ ] Configure persistent volume for scan data
- [ ] Set up monitoring/alerting
- [ ] Document admin procedures
- [ ] Test rate limiting behavior

## Security Best Practices

### 1. Secrets Management

**DO:**
- ✅ Use Fly.io secrets (`fly secrets set`)
- ✅ Rotate API keys regularly
- ✅ Use environment variables, never hardcode
- ✅ Keep `.env` files in `.gitignore`

**DON'T:**
- ❌ Commit secrets to git
- ❌ Share tokens publicly
- ❌ Use the same token across environments

### 2. Bot Token Security

```bash
# Rotate your token if compromised:
# 1. Go to Discord Developer Portal
# 2. Regenerate bot token
# 3. Update Fly.io secret
fly secrets set DISCORD_BOT_TOKEN="new_token"
```

### 3. Permission Restrictions

The bot uses `@commands.has_permissions(moderate_members=True)` for the `!scan` command. This ensures only trusted users can scan accounts.

**Review your Discord server roles:**
- Ensure only moderators have "Moderate Members" permission
- Consider creating a dedicated "Scanner" role

### 4. Admin Command Protection

The `!shutdown` command is restricted to user IDs in `ADMIN_USER_IDS`:

```bash
# Set your Discord user ID (right-click your name → Copy ID)
fly secrets set ADMIN_USER_IDS="123456789012345678"
```

### 5. Rate Limiting

Current settings in `cogs/moderation.py`:
```python
@commands.cooldown(1, 30, commands.BucketType.user)  # 1 scan per 30s per user
```

**Considerations:**
- Prevents spam and API abuse
- Protects against rate limit violations
- Adjust if needed for your use case

## Performance Optimization

### 1. Memory Usage

**Current Configuration:**
- Docker image: ~200-300MB
- Runtime memory: ~100-150MB (idle)
- Peak memory: ~200MB (during scans)

**Fly.io free tier (256MB) is sufficient** for most use cases.

**Monitor memory usage:**
```bash
fly ssh console
# Inside VM:
ps aux | grep python
free -h
```

### 2. Scan Timeout Configuration

In `cogs/moderation.py`:
```python
SCAN_TIMEOUT: Final = 300  # 5 minutes
```

**Adjust based on your needs:**
- Sherlock scans: ~30-60 seconds
- Reddit scans: ~30-120 seconds (depends on comment count)
- Both: up to 5 minutes

### 3. Concurrent Scans

The bot handles one scan per user per 30 seconds. Multiple users can scan simultaneously.

**For high-traffic servers**, consider:
- Increasing VM resources
- Implementing a queue system
- Adjusting cooldowns

### 4. Database/Storage Optimization

**Current behavior:**
- Scan results saved to `./scans/` directory
- Files persist until VM restarts (ephemeral storage)

**For persistent storage:**
```bash
# Create volume
fly volumes create scan_data --size 1

# Update fly.toml (already included, just uncomment)
[mounts]
  source = "scan_data"
  destination = "/app/scans"

# Redeploy
fly deploy
```

**Clean up old scans:**
```bash
# Add cron job or scheduled cleanup
# Example: Delete scans older than 7 days
find /app/scans -name "*.csv" -mtime +7 -delete
find /app/scans -name "*.json" -mtime +7 -delete
```

## Monitoring & Alerts

### 1. Log Monitoring

**Essential logs to watch:**
```bash
# Follow logs in real-time
fly logs -f

# Filter for errors
fly logs | grep ERROR

# Filter for specific user scans
fly logs | grep "Scan requested"
```

### 2. Discord Logging Channel

Set up a logging channel to receive bot events:

```bash
# 1. Create a private channel in your Discord server
# 2. Get the channel ID (right-click → Copy ID)
# 3. Set as secret
fly secrets set LOG_CHANNEL_ID="123456789012345678"
```

**Note:** You'll need to implement logging in `discord_bot.py` to send events to this channel.

### 3. Uptime Monitoring

Use external monitoring services:
- **UptimeRobot**: https://uptimerobot.com/ (free)
- **Pingdom**: https://www.pingdom.com/
- **StatusCake**: https://www.statuscake.com/

**What to monitor:**
- Bot online status (check `!health` command response)
- Response latency
- API availability (Reddit, Perspective)

### 4. Error Tracking

The bot logs errors to stdout. Consider integrating:
- **Sentry**: https://sentry.io/ (error tracking)
- **DataDog**: https://www.datadoghq.com/ (APM)
- **Fly.io Metrics**: Built-in dashboard

## Backup & Recovery

### 1. Code Backup

```bash
# Your code should be in git
git push origin main

# Tag releases
git tag -a v1.2.3 -m "Production release"
git push --tags
```

### 2. Configuration Backup

**Document your secrets:**
```bash
# Export secret names (not values!)
fly secrets list > secrets-list.txt

# Keep a template
cp .env.example .env.backup
```

### 3. Scan Data Backup

If using persistent storage:

```bash
# Create volume snapshot (future Fly.io feature)
# For now, manually backup:
fly ssh console
tar -czf scans-backup.tar.gz /app/scans
# Copy to local machine or S3
```

### 4. Disaster Recovery

**If your app is destroyed:**

```bash
# 1. Recreate app
fly apps create your-app-name

# 2. Restore secrets
fly secrets set DISCORD_BOT_TOKEN="..." [...]

# 3. Redeploy
fly deploy

# 4. Restore scan data (if needed)
fly ssh console
# Upload and extract scans-backup.tar.gz
```

## Rate Limiting & API Quotas

### API Limits to Monitor

**1. Discord API:**
- Global rate limit: 50 requests/second
- Per-route limits vary
- Bot should handle rate limits automatically

**2. Reddit API:**
- 60 requests/minute (default in account_scanner.py:116)
- OAuth: 600 requests/10 minutes

**3. Perspective API:**
- Free tier: 1 QPS (query per second)
- Paid tier: Higher limits

### Handling Rate Limits

The scanner has built-in rate limiting:
```python
# In account_scanner.py
--rate-per-min 60  # Configurable
```

**If you hit limits frequently:**
- Reduce `--comments` and `--posts` defaults
- Implement request queuing
- Upgrade API tier (Perspective)
- Add retry logic with exponential backoff

## Error Handling

### Current Error Handling

The bot handles:
- Missing permissions
- Missing arguments
- Cooldown violations
- Command errors

### Common Errors & Solutions

**1. "Reddit scanning not configured"**
```bash
# Ensure all Reddit secrets are set
fly secrets set REDDIT_CLIENT_ID="..." \
  REDDIT_CLIENT_SECRET="..." \
  REDDIT_USER_AGENT="..."
```

**2. "Sherlock not available"**
- Sherlock is installed in Dockerfile
- If missing, rebuild: `fly deploy`

**3. "Scan timed out"**
- Increase `SCAN_TIMEOUT` in `cogs/moderation.py`
- Use specific scan modes (`!scan username reddit`)

**4. Out of Memory**
```bash
# Increase VM memory
fly scale memory 512
```

**5. Bot offline/not responding**
```bash
# Check status
fly status

# Check logs
fly logs

# Restart if needed
fly apps restart
```

### Graceful Shutdown

The bot handles `SIGINT` gracefully (fly.toml:5):
```toml
kill_signal = "SIGINT"
kill_timeout = "30s"
```

**This ensures:**
- Ongoing scans can complete (up to 30s)
- Discord connection closes properly
- No data corruption

## Production Monitoring Checklist

- [ ] Bot is online and responding to `!health`
- [ ] All required APIs are accessible
- [ ] Memory usage is stable (<200MB)
- [ ] No error spikes in logs
- [ ] Cooldowns are working as expected
- [ ] Admin commands are restricted properly
- [ ] Scan results are being saved
- [ ] Discord latency is acceptable (<500ms)

## Performance Benchmarks

**Expected performance on Fly.io free tier:**
- Bot startup: ~10-15 seconds
- `!health` response: <1 second
- Sherlock scan: ~30-60 seconds (300+ platforms)
- Reddit scan (50 comments): ~30-90 seconds
- Combined scan: ~60-120 seconds
- Memory usage: ~100-200MB
- Discord latency: 50-200ms

**If performance degrades:**
1. Check `fly logs` for errors
2. Monitor memory: `fly ssh console` → `free -h`
3. Check API rate limits
4. Consider scaling up: `fly scale memory 512`

## Security Incident Response

**If your token is compromised:**

1. **Immediately** regenerate token in Discord Developer Portal
2. Update Fly.io secret: `fly secrets set DISCORD_BOT_TOKEN="new_token"`
3. Review bot audit log in Discord
4. Check for unauthorized commands in `fly logs`
5. Notify your server administrators

**If suspicious activity detected:**

1. Check logs: `fly logs --recent`
2. Review scan requests
3. Verify admin user IDs
4. Check for unusual resource usage
5. Consider temporarily stopping: `fly apps stop`

---

**Questions or issues?** Check the repository documentation or open an issue.

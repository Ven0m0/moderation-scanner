# Deploying Account Scanner Bot to Fly.io

Complete guide for deploying the Discord Account Scanner Bot to Fly.io with production-ready configuration.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Initial Setup](#initial-setup)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Monitoring & Logs](#monitoring--logs)
- [Updating the Bot](#updating-the-bot)
- [Scaling & Optimization](#scaling--optimization)
- [Troubleshooting](#troubleshooting)
- [Cost Information](#cost-information)

## Prerequisites

### 1. Install Fly.io CLI

**macOS/Linux:**
```bash
curl -L https://fly.io/install.sh | sh
```

**Windows (PowerShell):**
```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

### 2. Create Fly.io Account

```bash
fly auth signup
# or login if you already have an account
fly auth login
```

### 3. Get Required API Keys

You'll need:
- **Discord Bot Token**: https://discord.com/developers/applications
- **Reddit API Credentials**: https://www.reddit.com/prefs/apps
- **Google Perspective API Key**: https://perspectiveapi.com/

## Initial Setup

### 1. Configure Your App Name

Edit `fly.toml` and change the app name to something unique:

```toml
app = "your-unique-bot-name"  # Change this!
```

### 2. Choose Your Region

Available regions (use closest to your users):
- `iad` - Ashburn, Virginia (US East)
- `lax` - Los Angeles, California (US West)
- `ord` - Chicago, Illinois (US Central)
- `lhr` - London, UK
- `fra` - Frankfurt, Germany
- `syd` - Sydney, Australia
- `sin` - Singapore

Update `primary_region` in `fly.toml`:

```toml
primary_region = "iad"  # Change to your preferred region
```

### 3. Create the App

```bash
fly apps create your-unique-bot-name
```

Or let Fly.io generate a name:

```bash
fly apps create
```

## Configuration

### Set Environment Variables (Secrets)

Fly.io uses secrets for sensitive data. Set all required environment variables:

```bash
# Required: Discord Bot Token
fly secrets set DISCORD_BOT_TOKEN="your_discord_token_here"

# Required: Reddit API (for Reddit scanning)
fly secrets set REDDIT_CLIENT_ID="your_client_id"
fly secrets set REDDIT_CLIENT_SECRET="your_client_secret"
fly secrets set REDDIT_USER_AGENT="account-scanner-bot/1.2.3"

# Required: Perspective API (for toxicity analysis)
fly secrets set PERSPECTIVE_API_KEY="your_perspective_key"

# Optional: Admin users (comma-separated Discord user IDs)
fly secrets set ADMIN_USER_IDS="123456789012345678,987654321098765432"

# Optional: Logging channel
fly secrets set LOG_CHANNEL_ID="123456789012345678"
```

**Tip:** Set all secrets in one command to avoid multiple restarts:

```bash
fly secrets set \
  DISCORD_BOT_TOKEN="your_token" \
  REDDIT_CLIENT_ID="your_id" \
  REDDIT_CLIENT_SECRET="your_secret" \
  REDDIT_USER_AGENT="account-scanner-bot/1.2.3" \
  PERSPECTIVE_API_KEY="your_key"
```

### Verify Secrets

```bash
fly secrets list
```

## Deployment

### 1. Deploy the Bot

```bash
fly deploy
```

This will:
- Build the Docker image
- Push it to Fly.io's registry
- Create and start your VM
- Run the bot

### 2. Verify Deployment

Check app status:

```bash
fly status
```

Check if the bot is running:

```bash
fly logs
```

You should see:
```
[INFO] Starting Discord bot...
[INFO] Bot ready: YourBotName (ID: ...)
[INFO] Connected to X guilds
```

### 3. Test the Bot

In Discord, try:
- `!help` - Show bot commands
- `!health` - Check bot status
- `!scan username` - Test scanning functionality

## Monitoring & Logs

### View Live Logs

```bash
fly logs
```

### View Recent Logs

```bash
fly logs --recent
```

### Follow Logs in Real-time

```bash
fly logs -f
```

### SSH into Your VM (for debugging)

```bash
fly ssh console
```

### Check Resource Usage

```bash
fly status
fly vm status
```

### Monitor with Dashboard

Visit https://fly.io/dashboard and select your app for metrics.

## Updating the Bot

### Deploy Code Changes

```bash
# 1. Make your code changes
# 2. Commit to git (optional but recommended)
git add .
git commit -m "Update bot features"

# 3. Deploy updated version
fly deploy
```

### Update Environment Variables

```bash
fly secrets set VARIABLE_NAME="new_value"
```

### Restart the Bot

```bash
fly apps restart your-app-name
```

## Scaling & Optimization

### Current Configuration

The `fly.toml` is configured with:
- **CPU**: 1 shared CPU
- **Memory**: 512MB RAM (increased from 256MB to prevent crashes)
- **Regions**: 1 instance
- **Restart Policy**: On failure, max 5 retries

### Scale Up (if needed)

**Increase memory:**
```bash
fly scale memory 512  # or 1024, 2048, etc.
```

**Add more CPUs:**
```bash
fly scale vm shared-cpu-2x  # 2 CPUs
```

**Add more regions (for redundancy):**
```bash
fly regions add lax ord  # Add Los Angeles and Chicago
fly scale count 3         # Run 3 instances total
```

**Note:** Scaling beyond free tier will incur costs.

### Check Current Scale

```bash
fly scale show
```

## Troubleshooting

### Bot Crashes with "DISCORD_BOT_TOKEN is required"

**Cause**: Missing Discord bot token environment variable.

**Solution**:
```bash
fly secrets set DISCORD_BOT_TOKEN="your_discord_token_here" -a moderation-scanner
```

### Bot Crashes with "Missing required Discord intents"

**Cause**: MESSAGE CONTENT intent not enabled in Discord Developer Portal.

**Solution**:
1. Go to https://discord.com/developers/applications
2. Select your application
3. Go to **Bot** section
4. Scroll to **Privileged Gateway Intents**
5. Enable **MESSAGE CONTENT INTENT** ✅
6. Save changes
7. Restart bot: `fly apps restart -a moderation-scanner`

### Slash Commands Don't Appear

**Causes and Solutions**:

1. **Commands not synced**: Wait 5-10 minutes for Discord to propagate slash commands globally
2. **Bot missing scopes**: Re-invite bot with `applications.commands` scope
3. **Sync failed**: Check logs for errors: `fly logs -a moderation-scanner`

### Prefix Commands (!scan) Don't Work

**Cause**: MESSAGE CONTENT intent not enabled (see above).

**Additional checks**:
1. Ensure bot has "Read Messages" permission in the channel
2. Check logs for command errors: `fly logs -a moderation-scanner`
3. Try `/help` slash command instead

### Bot Not Connecting to Discord

1. Check logs: `fly logs -a moderation-scanner`
2. Verify token: `fly secrets list -a moderation-scanner`
3. Ensure token is valid in Discord Developer Portal
4. Restart: `fly apps restart -a moderation-scanner`

### Out of Memory Errors

The bot is now configured with 512MB RAM by default. If you still see OOM errors:

```bash
# Increase memory to 1GB
fly scale memory 1024 -a moderation-scanner
```

Check current memory usage:
```bash
fly vm status -a moderation-scanner
```

### Bot Keeps Crashing

```bash
# Check logs for errors
fly logs --recent

# SSH into VM for debugging
fly ssh console

# Check running processes
ps aux
```

### Deployment Fails

```bash
# Check Dockerfile syntax
docker build -t test .

# Verify fly.toml configuration
fly config validate

# Deploy with verbose output
fly deploy --verbose
```

### Reset Everything

```bash
# Destroy and recreate app
fly apps destroy your-app-name
fly apps create your-app-name
# Re-set secrets and redeploy
```

## Cost Information

### Free Tier Limits (as of 2024)

Fly.io free tier includes:
- **3 shared-cpu-1x VMs** (256MB RAM each)
- **160GB outbound data transfer**
- **3GB persistent storage**

**For this bot on free tier:**
- ✅ 1 instance in 1 region = **FREE**
- ✅ 256MB RAM for Discord bot = **FREE**
- ✅ Typical Discord bot traffic = **FREE**

### Paid Usage

You'll be charged if you exceed:
- More than 3 VMs
- More than 256MB RAM per VM
- More than 160GB outbound transfer/month

**Example costs:**
- 512MB RAM: ~$0.0000008/second (~$2/month)
- Additional instances: ~$0.0000008/second each

**Check your usage:**
```bash
fly dashboard
```

Or visit: https://fly.io/dashboard/personal/billing

### Cost Optimization Tips

1. **Use 1 instance** - Discord bots don't need multiple instances
2. **Use 256MB RAM** - Usually sufficient for Discord bots
3. **Monitor logs** - `fly logs` to check memory usage
4. **Use persistent volumes only if needed** - Scan results can be ephemeral

## Advanced Configuration

### Enable Persistent Storage (Optional)

If you want scan results to persist between deployments:

```bash
# Create a volume
fly volumes create scan_data --size 1

# Uncomment the [mounts] section in fly.toml
# Then redeploy
fly deploy
```

### Auto-start/Stop

Fly.io VMs run continuously by default. To reduce costs:

```bash
# Manually stop when not needed
fly apps stop

# Start when needed
fly apps start
```

### Health Checks (Optional)

To add HTTP health checks, modify `discord_bot.py` to add a simple HTTP server:

```python
# Add this to discord_bot.py for health checks
from aiohttp import web

async def health_check(request):
    return web.Response(text="OK")

app = web.Application()
app.router.add_get('/health', health_check)
```

Then uncomment the `[[services]]` section in `fly.toml`.

## Support

- **Fly.io Documentation**: https://fly.io/docs/
- **Fly.io Community**: https://community.fly.io/
- **Bot Issues**: Check the repository issues

## Quick Reference Commands

```bash
# Deploy
fly deploy

# Logs
fly logs -f

# Status
fly status

# SSH
fly ssh console

# Restart
fly apps restart

# Scale
fly scale show
fly scale memory 512

# Secrets
fly secrets list
fly secrets set KEY="value"

# Stop/Start
fly apps stop
fly apps start

# Destroy
fly apps destroy your-app-name
```

---

**Ready to deploy?** Run `fly deploy` and your bot will be live in minutes! 🚀

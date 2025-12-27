# 🚀 Quick Start: Deploy to Fly.io in 5 Minutes

Get your Discord Account Scanner Bot running on Fly.io in just a few commands.

## Prerequisites

You'll need:
1. A Discord bot token ([Get one here](https://discord.com/developers/applications))
2. Reddit API credentials ([Create app here](https://www.reddit.com/prefs/apps))
3. Perspective API key ([Get key here](https://perspectiveapi.com/))

## 5-Minute Deployment

### Step 1: Install Fly.io CLI

**macOS/Linux:**
```bash
curl -L https://fly.io/install.sh | sh
```

**Windows:**
```powershell
iwr https://fly.io/install.ps1 -useb | iex
```

### Step 2: Login to Fly.io

```bash
fly auth login
```

### Step 3: Configure Your Bot

Edit `fly.toml` and change the app name:
```toml
app = "my-discord-scanner-bot"  # Pick a unique name
```

### Step 4: Create the App

```bash
fly apps create my-discord-scanner-bot
```

### Step 5: Set Your Secrets

```bash
fly secrets set \
  DISCORD_BOT_TOKEN="paste_your_discord_token_here" \
  REDDIT_CLIENT_ID="paste_your_reddit_client_id" \
  REDDIT_CLIENT_SECRET="paste_your_reddit_secret" \
  REDDIT_USER_AGENT="account-scanner-bot/1.2.3" \
  PERSPECTIVE_API_KEY="paste_your_perspective_key"
```

### Step 6: Deploy!

```bash
fly deploy
```

That's it! Your bot is now live. 🎉

### Step 7: Test Your Bot

In Discord, try:
```
!help
!health
!scan reddit_username
```

## What's Next?

- **Monitor logs**: `fly logs -f`
- **Check status**: `fly status`
- **Read full deployment guide**: See [DEPLOYMENT.md](DEPLOYMENT.md)
- **Production tips**: See [PRODUCTION.md](PRODUCTION.md)

## Troubleshooting

**Bot not online?**
```bash
fly logs
```

**Need to update secrets?**
```bash
fly secrets set DISCORD_BOT_TOKEN="new_token"
```

**Want to restart?**
```bash
fly apps restart
```

## Free Tier Info

Your bot runs **FREE** on Fly.io as long as:
- You use 1 instance
- Memory is 256MB or less
- You stay under 160GB bandwidth/month

Perfect for small to medium Discord servers!

## Need Help?

- **Full documentation**: [DEPLOYMENT.md](DEPLOYMENT.md)
- **Fly.io docs**: https://fly.io/docs/
- **Bot repository**: Check the issues page

---

**Ready to deploy?** Just run `fly deploy` and you're live! 🚀

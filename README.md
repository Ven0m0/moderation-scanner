# Account Scanner

Multi-source account scanner combining Reddit toxicity analysis via Perspective API with Sherlock OSINT username enumeration.

## Features

- **Reddit Analysis**: Scan user comments/posts for toxic content using Google Perspective API
- **OSINT Discovery**: Enumerate username across 300+ platforms via Sherlock
- **Discord Bot**: Ready-to-deploy moderation bot with slash commands
- **Async Performance**: HTTP/2 support with configurable rate limiting
- **Flexible Output**: CSV for Reddit results, JSON for Sherlock findings
- **Production Ready**: Docker support with Fly.io deployment configuration

## Requirements

- Python 3.11+
- [Sherlock](https://github.com/sherlock-project/sherlock) (optional, for OSINT)

## Installation

See [INSTALL.md](INSTALL.md) for comprehensive installation guide.

**Quick Install:**

```bash
# Pip (development)
pip install -e .

# Arch Linux (system-wide)
make pkg-install

# From AUR
yay -S account-scanner
```

**Dependencies:**
- Python 3.11+
- [Sherlock](https://github.com/sherlock-project/sherlock) (optional, for OSINT)

**Full setup:**
```bash
# Clone repository
git clone <repo-url>
cd account-scanner

# Install with dev dependencies
pip install -e ".[dev]"

# Install Sherlock (optional)
pip install sherlock-project
```

## Configuration

Create credentials file at `~/.config/account_scanner/credentials`:

```bash
# Reddit API (https://www.reddit.com/prefs/apps)
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"
export REDDIT_USER_AGENT="account-scanner/1.2.0 (by u/your_username)"

# Google Perspective API (https://perspectiveapi.com/)
export PERSPECTIVE_API_KEY="your_api_key"
```

## Usage

### Via Wrapper Script

```bash
# Both scans
./scan.sh target_username

# Reddit only
./scan.sh target_username --mode reddit

# Sherlock only
./scan.sh target_username --mode sherlock

# Custom thresholds
./scan.sh target_username --toxicity-threshold 0.8 --comments 100

# Verbose mode
./scan.sh target_username --verbose
```

### Direct Python

```bash
python3 account_scanner.py target_username \
  --perspective-api-key "$PERSPECTIVE_API_KEY" \
  --client-id "$REDDIT_CLIENT_ID" \
  --client-secret "$REDDIT_CLIENT_SECRET" \
  --mode both
```

## Options

```
positional arguments:
  username              Username to scan

optional arguments:
  --mode {sherlock,reddit,both}
                        Scan mode (default: both)
  --perspective-api-key API_KEY
                        Perspective API key
  --client-id ID        Reddit client ID
  --client-secret SECRET
                        Reddit client secret
  --user-agent UA       Reddit user agent
  --comments N          Max comments to fetch (default: 50)
  --posts N             Max posts to fetch (default: 20)
  --toxicity-threshold T
                        Toxicity threshold 0-1 (default: 0.7)
  --rate-per-min N      API rate limit (default: 60)
  --sherlock-timeout N  Sherlock timeout seconds (default: 60)
  --output-reddit FILE  Reddit output (default: reddit_flagged.csv)
  --output-sherlock FILE
                        Sherlock output (default: sherlock_results.json)
  --verbose             Verbose output
```

## Output

### Reddit (CSV)

```csv
timestamp,type,subreddit,content,TOXICITY,INSULT,PROFANITY,SEXUALLY_EXPLICIT
2024-01-15 10:30:45,comment,politics,This is...,0.89,0.76,0.45,0.12
```

### Sherlock (JSON)

```json
[
  {
    "platform": "GitHub",
    "url": "https://github.com/username",
    "status": "Claimed",
    "response_time": 0.234
  }
]
```

## Discord Bot

The project includes a production-ready Discord bot for server moderation.

### Features

- `!scan <username> [mode]` - Scan accounts across platforms
- `!health` - Check bot and API status
- `!help` - Display help information
- Permission-based access control
- Rate limiting and cooldowns
- Rich embed responses

### Local Testing

```bash
# Set environment variables
export DISCORD_BOT_TOKEN="your_token"
export REDDIT_CLIENT_ID="your_id"
export REDDIT_CLIENT_SECRET="your_secret"
export PERSPECTIVE_API_KEY="your_key"

# Run the bot
python discord_bot.py
```

### Cloud Deployment

**Quick Deploy to Fly.io (FREE):**

See [QUICKSTART.md](QUICKSTART.md) for 5-minute deployment guide.

**Full Documentation:**
- [DEPLOYMENT.md](DEPLOYMENT.md) - Complete Fly.io deployment guide
- [PRODUCTION.md](PRODUCTION.md) - Production best practices and optimization
- [.env.example](.env.example) - Environment variable template

**Other Hosting Options:**
- Fly.io (recommended, free tier available)
- Railway ($5/month after trial)
- Render.com (free tier with limitations)
- Oracle Cloud (free tier, requires VPS setup)

## Architecture

### Project Structure

```
moderation-scanner/
├── account_scanner.py    # Core scanner library (Reddit + Sherlock)
├── discord_bot.py        # Discord bot integration
├── scan.sh               # Wrapper script for CLI usage
├── test-scanner.py       # Test suite
├── fly.toml              # Fly.io deployment config
├── Dockerfile            # Container image
├── INSTALL.md            # Installation guide
├── DEPLOYMENT.md         # Cloud deployment guide
├── PRODUCTION.md         # Production best practices
├── QUICKSTART.md         # 5-minute quick start
└── CONTRIBUTING.md       # Development guide
```

### Component Overview

**account_scanner.py** - Core scanning engine
- `ScanConfig`: Configuration dataclass for scan parameters
- `RateLimiter`: Token bucket rate limiter for API throttling
- `SherlockScanner`: Wrapper for Sherlock OSINT tool
- `RedditScanner`: Reddit API + Perspective API toxicity analysis
- `ScannerAPI`: High-level library interface for programmatic use

**discord_bot.py** - Discord integration
- `BotConfig`: Environment-based configuration management
- Commands: `!scan`, `!health`, `!help`, `!shutdown`
- Permission-based access control and rate limiting
- Rich embed formatting for results

### Data Flow

1. **Input**: Username + scan mode (sherlock/reddit/both)
2. **Reddit Path**:
   - Fetch comments/posts via AsyncPRAW
   - Analyze toxicity via Perspective API (HTTP/2, rate-limited)
   - Filter by threshold, save flagged items to CSV
3. **Sherlock Path**:
   - Execute Sherlock subprocess
   - Parse stdout for claimed accounts
   - Return structured JSON
4. **Output**: Structured results dict or file output

### Technology Stack

- **Python 3.11+** with type hints and dataclasses
- **AsyncIO**: uvloop for high-performance event loop
- **HTTP**: httpx with HTTP/2 support
- **APIs**: AsyncPRAW (Reddit), Google Perspective API
- **OSINT**: Sherlock command-line tool integration
- **Discord**: discord.py with commands extension
- **Data**: CSV (Reddit), JSON (Sherlock)

## API Reference

### Library Usage

```python
from account_scanner import ScannerAPI, ScanConfig

# Configure scan
config = ScanConfig(
    username="target_user",
    mode="both",                    # "sherlock", "reddit", or "both"
    api_key="perspective_key",      # Google Perspective API
    client_id="reddit_client_id",
    client_secret="reddit_secret",
    comments=100,                   # Max comments to fetch
    posts=50,                       # Max posts to fetch
    threshold=0.7,                  # Toxicity threshold (0-1)
    rate_per_min=60.0,             # API rate limit
    sherlock_timeout=60,           # Sherlock timeout (seconds)
    verbose=False
)

# Run scan (async)
results = await ScannerAPI.scan_user("target_user", config)

# Access results
if results["reddit"]:
    for item in results["reddit"]:
        print(f"Toxic content: {item['content'][:100]}")
        print(f"Toxicity: {item['TOXICITY']:.2f}")

if results["sherlock"]:
    for account in results["sherlock"]:
        print(f"{account['platform']}: {account['url']}")

if results["errors"]:
    print(f"Errors: {results['errors']}")
```

### Discord Bot Usage

```python
# In your Discord bot
import os
import discord
from account_scanner import ScannerAPI, ScanConfig

@bot.command()
async def scan(ctx, username: str):
    config = ScanConfig(
        username=username,
        mode="both",
        api_key=os.getenv("PERSPECTIVE_API_KEY"),
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET")
    )

    results = await ScannerAPI.scan_user(username, config)

    # Display results in embed
    embed = discord.Embed(title=f"Scan: {username}")
    if results.get("reddit"):
        embed.add_field(
            name="Reddit",
            value=f"{len(results['reddit'])} toxic items found"
        )
    await ctx.send(embed=embed)
```

## Development

### Setup Development Environment

```bash
# Clone repository
git clone <repo-url>
cd moderation-scanner

# Install with development dependencies
pip install -e ".[dev]"

# Install Sherlock (optional, for OSINT scanning)
pip install sherlock-project

# Set up pre-commit hooks (recommended)
pre-commit install
```

### Code Quality

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type checking
mypy account_scanner.py discord_bot.py

# Run tests
pytest

# Run tests with coverage
pytest --cov=account_scanner --cov-report=html
```

### Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines, coding standards,
and how to submit pull requests.

## Toxicity Attributes

- **TOXICITY**: Overall rudeness/disrespect
- **INSULT**: Personal attacks
- **PROFANITY**: Swear words
- **SEXUALLY_EXPLICIT**: Sexual content

Scores range 0-1 (higher = more toxic).

## License

MIT

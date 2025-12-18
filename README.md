# Account Scanner

Multi-source account scanner combining Reddit toxicity analysis via Perspective API with Sherlock OSINT username enumeration.

## Features

- **Reddit Analysis**: Scan user comments/posts for toxic content using Google Perspective API
- **OSINT Discovery**: Enumerate username across 300+ platforms via Sherlock
- **Async Performance**: HTTP/2 support with configurable rate limiting
- **Flexible Output**: CSV for Reddit results, JSON for Sherlock findings

## Requirements

- Python 3.11+
- [Sherlock](https://github.com/sherlock-project/sherlock) (optional, for OSINT)

## Installation

```bash
# Clone or download
git clone <repo-url>
cd account-scanner

# Install dependencies
pip install -e .

# Dev dependencies
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

## Development

```bash
# Format
ruff format .

# Lint
ruff check .

# Type check
mypy account_scanner.py

# Run tests
pytest
```

## Toxicity Attributes

- **TOXICITY**: Overall rudeness/disrespect
- **INSULT**: Personal attacks
- **PROFANITY**: Swear words
- **SEXUALLY_EXPLICIT**: Sexual content

Scores range 0-1 (higher = more toxic).

## License

MIT

# Account Scanner

Multi-source account intelligence: Reddit toxicity analysis + Sherlock OSINT platform discovery.
Optimized for performance using `orjson` (fast JSON) and `uvloop` (fast async loop).

## Features

- **Sherlock Mode**: Discover username presence across 400+ platforms
- **Reddit Mode**: Scan user content for toxicity via Google Perspective API
- **Both Mode**: Run both scanners concurrently
- **High Performance**: Uses `uvloop` and `orjson` for minimal overhead

## Installation

### Python Dependencies

```bash
# Using pip
pip install .

# For development
pip install ".[dev]"
```

### Sherlock (Optional)

Sherlock is an optional OSINT tool for username discovery across platforms. Install it separately:

```bash
# Using pipx (recommended - isolated installation)
pipx install sherlock-project

# Using pip (user installation)
pip install --user sherlock-project

# Arch Linux / CachyOS
paru -S sherlock-git
```

**Note:** Sherlock is not a Python library dependency - it's invoked as a CLI tool. The scanner will automatically detect if Sherlock is available.

### Usage

```bash
# Sherlock Only
./account_scanner.py username --mode sherlock

# Reddit Only
./account_scanner.py username \
  --mode reddit \
  --perspective-api-key YOUR_KEY \
  --client-id YOUR_ID \
  --client-secret YOUR_SECRET \
  --user-agent "Bot/1.0"

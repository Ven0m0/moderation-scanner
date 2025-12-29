#!/usr/bin/env python3
"""Multi-source account scanner: Reddit toxicity analysis + Sherlock OSINT.

This module provides comprehensive account scanning across multiple platforms:

1. **Reddit Toxicity Analysis**: Fetches a user's Reddit comments and posts,
   analyzes them using Google's Perspective API to detect toxic content
   (toxicity, insults, profanity, sexually explicit language), and generates
   a CSV report of flagged items.

2. **Sherlock OSINT**: Uses the Sherlock tool to enumerate usernames across
   300+ social media platforms and websites, returning claimed accounts.

The module can be used as a command-line tool or imported as a library for
integration into other applications (Discord bots, web APIs, etc.).

## Command-Line Usage

    python account_scanner.py username --mode both \\
      --perspective-api-key KEY \\
      --client-id ID \\
      --client-secret SECRET

## Library Usage

    from account_scanner import ScannerAPI, ScanConfig

    config = ScanConfig(
        username="johndoe",
        mode="both",
        api_key="perspective_key",
        client_id="reddit_id",
        client_secret="reddit_secret"
    )
    results = await ScannerAPI.scan_user("johndoe", config)

## API Requirements

- **Reddit API**: Register app at https://www.reddit.com/prefs/apps
- **Perspective API**: Get key at https://perspectiveapi.com/
- **Sherlock**: Install via `pip install sherlock-project`

## Architecture

- Uses uvloop for improved async performance
- HTTP/2 support for Perspective API requests
- Token bucket rate limiting to respect API quotas
- AsyncPRAW for Reddit API access
- Subprocess execution for Sherlock integration
"""
import argparse
import asyncio
import csv
import io
import logging
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import aiofiles
import httpx
import orjson
import uvloop
from asyncpraw import Reddit
from asyncprawcore import AsyncPrawcoreException

# Constants
PERSPECTIVE_URL: Final = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
DEFAULT_TIMEOUT: Final = 10
SHERLOCK_BUFFER: Final = 30
ATTRIBUTES: Final = ["TOXICITY", "INSULT", "PROFANITY", "SEXUALLY_EXPLICIT"]
HTTP2_LIMITS: Final = httpx.Limits(max_keepalive_connections=5, max_connections=10)

# Logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


@dataclass
class ScanConfig:
  """Configuration for account scanning operations.

  This dataclass holds all configuration parameters for Reddit toxicity analysis
  and Sherlock OSINT scanning. It provides sensible defaults while allowing
  full customization of API credentials, rate limits, and output paths.

  Attributes:
    username: Target username to scan across platforms.
    mode: Scan mode - 'reddit', 'sherlock', or 'both'. Default: 'both'.

    Reddit configuration:
    api_key: Google Perspective API key for toxicity analysis.
    client_id: Reddit API client ID from https://www.reddit.com/prefs/apps.
    client_secret: Reddit API client secret.
    user_agent: Reddit API user agent string. Auto-generated if not provided.
    comments: Maximum number of comments to fetch per user. Default: 50.
    posts: Maximum number of posts to fetch per user. Default: 20.
    threshold: Toxicity threshold (0-1). Content >= threshold is flagged. Default: 0.7.
    rate_per_min: API requests per minute rate limit. Default: 60.0.

    Sherlock configuration:
    sherlock_timeout: Timeout in seconds for Sherlock subprocess. Default: 60.

    Output configuration:
    output_reddit: Path for Reddit CSV results. Default: 'reddit_flagged.csv'.
    output_sherlock: Path for Sherlock JSON results. Default: 'sherlock_results.json'.
    verbose: Enable verbose logging output. Default: False.

  Example:
    >>> config = ScanConfig(
    ...     username="johndoe",
    ...     mode="both",
    ...     api_key="your_key_here",
    ...     client_id="your_client_id"
    ... )
  """
  username: str
  mode: str = "both"
  # Reddit
  api_key: str | None = None
  client_id: str | None = None
  client_secret: str | None = None
  user_agent: str | None = None
  comments:  int = 50
  posts: int = 20
  threshold: float = 0.7
  rate_per_min: float = 60.0
  # Sherlock
  sherlock_timeout: int = 60
  # Output
  output_reddit: Path = field(default_factory=lambda: Path("reddit_flagged.csv"))
  output_sherlock: Path = field(default_factory=lambda: Path("sherlock_results.json"))
  verbose: bool = False

  def __post_init__(self) -> None:
    self.output_reddit = Path(self.output_reddit)
    self.output_sherlock = Path(self.output_sherlock)
    if not self.user_agent:
      self.user_agent = f"account-scanner/1.2. 3 (by u/{self.username})"


class RateLimiter:
  """Token bucket rate limiter for API request throttling.

  Implements a simple token bucket algorithm to ensure API requests
  don't exceed the specified rate limit. Each call to wait() blocks
  until enough time has elapsed to respect the rate limit.

  Attributes:
    delay: Minimum seconds between consecutive requests.
    last_call: Timestamp (monotonic) of the last request.

  Example:
    >>> limiter = RateLimiter(rate_per_min=60.0)  # Max 60 requests/minute
    >>> async def make_request():
    ...     await limiter.wait()  # Blocks if too soon
    ...     # Make API request here
  """

  def __init__(self, rate_per_min: float) -> None:
    """Initialize rate limiter.

    Args:
      rate_per_min: Maximum requests per minute allowed.
    """
    self.delay = 60.0 / rate_per_min
    self.last_call = 0.0

  async def wait(self) -> None:
    """Wait if necessary to respect rate limit.

    Calculates time since last call and sleeps if insufficient time
    has elapsed. Updates last_call timestamp after sleeping.
    """
    now = time.monotonic()
    elapsed = now - self.last_call
    if elapsed < self.delay:
      await asyncio.sleep(self.delay - elapsed)
    self.last_call = time.monotonic()


class SherlockScanner:
  """Handles Sherlock OSINT username enumeration across platforms.

  This class wraps the Sherlock command-line tool to search for usernames
  across 300+ social media platforms and websites. It parses Sherlock's
  stdout output and returns structured results.

  The scanner requires the 'sherlock' command to be available in the system PATH.
  Install via: pip install sherlock-project
  """

  @staticmethod
  def available() -> bool:
    """Check if Sherlock is installed and available.

    Returns:
      True if 'sherlock' command is found in PATH, False otherwise.
    """
    return shutil.which("sherlock") is not None

  @staticmethod
  def _parse_stdout(text: str) -> list[dict[str, Any]]:
    """Parse Sherlock stdout output into structured data.

    Sherlock outputs results in the format:
      [+] Platform: https://example.com/username

    This parser extracts platform names and URLs, filtering out duplicates
    and invalid entries.

    Args:
      text: Raw stdout from Sherlock command.

    Returns:
      List of dicts with keys: platform, url, status, response_time.
      Only includes claimed/found accounts.
    """
    seen:  set[tuple[str, str]] = set()
    results:  list[dict[str, Any]] = []
    for line in text.splitlines():
      line = line.strip()
      if "://" not in line or ":  " not in line:
        continue
      if "]:  " in line:
        _, line = line.split("]: ", 1)
      parts = line.split(": ", 1)
      if len(parts) != 2:
        continue
      platform, url = parts
      url = url.strip()
      platform = platform.strip(" +[]")
      if not url. startswith("http"):
        continue
      key = (platform. lower(), url)
      if key in seen:
        continue
      seen.add(key)
      results.append({
        "platform": platform,
        "url": url,
        "status": "Claimed",
        "response_time": None,
      })
    return results

  @staticmethod
  def _is_claimed(status: str) -> bool:
    """Check if account status indicates a claimed/found account.

    Args:
      status: Status string from Sherlock output.

    Returns:
      True if account is claimed, False if not found/available/invalid.
    """
    s = status.lower()
    invalid = ("not", "available", "invalid", "unchecked", "unknown")
    return not any(x in s or s.startswith(x) for x in invalid)

  async def scan(self, username: str, timeout: int, verbose: bool, output_dir: Path | None = None) -> list[dict[str, Any]]:
    """Run Sherlock OSINT scan for the given username.

    Executes the Sherlock command-line tool as a subprocess and parses
    its output to find claimed accounts across platforms.

    Args:
      username: Username to search for across platforms.
      timeout: Maximum seconds to wait for Sherlock to complete.
      verbose: If True, log detailed stdout/stderr from Sherlock.
      output_dir: Optional directory to save Sherlock's txt output.
                  If None, uses current directory.

    Returns:
      List of found accounts, each as a dict with:
        - platform: Platform name (e.g., "GitHub", "Twitter")
        - url: Full URL to the user's profile
        - status: "Claimed" if found
        - response_time: None (not parsed from stdout)

      Returns empty list if Sherlock fails or finds no accounts.

    Raises:
      No exceptions are raised; errors are logged and empty list returned.
    """
    log.info("🔎 Sherlock:  Scanning '%s'.. .", username)
    cmd = [
      "sherlock", username,
      "--timeout", str(timeout),
      "--no-color",
      "--print-found",
    ]
    # Specify output location if provided (prevents files in inaccessible directories)
    if output_dir:
      output_file = output_dir / f"{username}.txt"
      cmd.extend(["--output", str(output_file)])
    try:
      proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
      )
      try:
        stdout, stderr = await asyncio.wait_for(
          proc.communicate(),
          timeout=timeout + SHERLOCK_BUFFER,
        )
      except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        log.warning("🔎 Sherlock: timed out after %ds", timeout)
        stdout, stderr = b"", b""
      if verbose:
        if stdout:
          log.debug("Sherlock stdout:\n%s", stdout.decode(errors="ignore"))
        if stderr:
          log.debug("Sherlock stderr:\n%s", stderr.decode(errors="ignore"))
      # Parse stdout
      results:  list[dict[str, Any]] = []
      if stdout:
        results = self._parse_stdout(stdout.decode(errors="ignore"))
      if results:
        log.info("🔎 Sherlock: collected %d claimed accounts", len(results))
      else:
        if stderr and not verbose:
          log.error(stderr.decode(errors="ignore"))
        log.info("🔎 Sherlock: no claimed accounts found")
      return results
    except Exception as e:
      msg = f"Sherlock error: {e}"
      (log.debug if verbose else log.error)(msg)
      if not verbose:
        log.info("🔎 Sherlock: failed; rerun with --verbose for details")
      return []


class RedditScanner:
  """Handles Reddit content fetching and toxicity analysis.

  This class fetches a user's recent Reddit comments and posts, then
  analyzes them using Google's Perspective API to detect toxic content.
  Results are filtered by toxicity threshold and saved to CSV.

  The scanner uses AsyncPRAW for Reddit API access and httpx with HTTP/2
  for Perspective API requests. Rate limiting ensures API quotas are respected.

  Attributes:
    config: ScanConfig instance with API credentials and settings.
    limiter: RateLimiter for Perspective API request throttling.
  """

  def __init__(self, config: ScanConfig) -> None:
    """Initialize Reddit scanner with configuration.

    Args:
      config: ScanConfig with Reddit/Perspective API credentials.
    """
    self.config = config
    self.limiter = RateLimiter(config.rate_per_min)

  async def _check_toxicity(
    self,
    client: httpx.AsyncClient,
    text: str,
    key: str,
  ) -> dict[str, float]:
    """Analyze text toxicity using Google Perspective API.

    Sends text to Perspective API and requests toxicity attribute scores.
    Respects rate limits via the rate limiter.

    Args:
      client: httpx AsyncClient instance for HTTP requests.
      text: Text content to analyze (comment or post body).
      key: Google Perspective API key.

    Returns:
      Dict mapping attribute names to scores (0-1):
        - TOXICITY: Overall rudeness/disrespect
        - INSULT: Personal attacks
        - PROFANITY: Swear words
        - SEXUALLY_EXPLICIT: Sexual content

      Returns empty dict if text is empty or API request fails.
    """
    if not text.strip():
      return {}
    await self.limiter.wait()
    payload = {
      "comment":  {"text": text},
      "languages": ["en"],
      "requestedAttributes": {a: {} for a in ATTRIBUTES},
    }
    try:
      resp = await client.post(
        PERSPECTIVE_URL,
        params={"key": key},
        content=orjson.dumps(payload),
        timeout=DEFAULT_TIMEOUT,
      )
      if resp.status_code == 200:
        data = orjson.loads(resp.content)
        return {
          k: v["summaryScore"]["value"]
          for k, v in data. get("attributeScores", {}).items()
        }
    except Exception: 
      pass
    return {}

  async def _fetch_items(self) -> list[tuple[str, str, str, float]] | None:
    """Fetch Reddit comments and posts for the configured user.

    Uses AsyncPRAW to fetch recent comments and posts from the target
    Reddit user. Combines both into a single list for analysis.

    Returns:
      List of tuples, each containing:
        - type: "comment" or "post"
        - subreddit: Subreddit display name
        - content: Comment body or post title+selftext
        - timestamp: UTC timestamp (seconds since epoch)

      Returns None if user doesn't exist, API fails, or no content found.
    """
    cfg = self.config
    log.info("🤖 Reddit: Fetching content for u/%s.. .", cfg.username)
    reddit:  Reddit | None = None
    try: 
      reddit = Reddit(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        user_agent=cfg.user_agent,
        requestor_kwargs={"timeout": DEFAULT_TIMEOUT},
      )
      user = await reddit.redditor(cfg.username)
      items:  list[tuple[str, str, str, float]] = []
      async for c in user.comments.new(limit=cfg.comments):
        items.append(("comment", c.subreddit. display_name, c.body, c.created_utc))
      async for s in user.submissions.new(limit=cfg.posts):
        items.append((
          "post",
          s. subreddit.display_name,
          f"{s.title}\n{s.selftext}",
          s.created_utc,
        ))
      return items if items else None
    except AsyncPrawcoreException as e: 
      log.error("Reddit API Error: %s", e)
    except Exception as e:
      log.error("Reddit fetch error: %s", e)
    finally:
      if reddit:
        await reddit.close()
    return None

  async def scan(self) -> list[dict[str, Any]] | None:
    """Scan Reddit user's content for toxic language.

    High-level workflow:
      1. Fetch user's recent comments and posts
      2. Analyze each item using Perspective API
      3. Filter items exceeding toxicity threshold
      4. Save flagged items to CSV file

    Returns:
      List of flagged items as dicts with keys:
        - timestamp: Human-readable datetime
        - type: "comment" or "post"
        - subreddit: Subreddit name
        - content: Text content (truncated to 500 chars)
        - TOXICITY, INSULT, PROFANITY, SEXUALLY_EXPLICIT: Scores (0-1)

      Returns None if no items fetched or empty list if no toxic content found.

    Side Effects:
      Writes CSV file to self.config.output_reddit if toxic content found.
    """
    items = await self._fetch_items()
    if not items:
      log.info("🤖 Reddit: No items to analyze")
      return None
    log.info("🤖 Reddit:  Analyzing %d items...", len(items))
    headers = {"Content-Type": "application/json"}
    async with httpx.AsyncClient(
      http2=True,
      limits=HTTP2_LIMITS,
      headers=headers,
    ) as client:
      results = await asyncio.gather(*[
        self._check_toxicity(client, text, self.config.api_key or "")
        for _, _, text, _ in items
      ])
    # Filter flagged content
    flagged:  list[dict[str, Any]] = []
    for (kind, sub, text, ts), scores in zip(items, results):
      if any(s >= self.config.threshold for s in scores. values()):
        flagged.append({
          "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
          "type": kind,
          "subreddit": str(sub),
          "content": text[: 500],
          **scores,
        })
    if flagged:
      # Write CSV
      buffer = io.StringIO()
      writer = csv.DictWriter(
        buffer,
        fieldnames=["timestamp", "type", "subreddit", "content"] + ATTRIBUTES,
      )
      writer.writeheader()
      writer.writerows(flagged)
      async with aiofiles.open(self.config.output_reddit, "w", encoding="utf-8") as f:
        await f. write(buffer.getvalue())
      log.info(
        "🤖 Reddit:  Saved %d flagged items → %s",
        len(flagged),
        self.config. output_reddit,
      )
    else:
      log.info("🤖 Reddit: No toxic content found")
    return flagged


class ScannerAPI:
  """Library interface for programmatic access to scanner functionality.

  This class provides a high-level async API for integrating account scanning
  into other applications (Discord bots, web APIs, etc.). It returns structured
  data instead of writing files, making it suitable for programmatic use.

  All methods are static and can be called without instantiation.
  """

  @staticmethod
  async def scan_user(
    username: str,
    config: ScanConfig,
  ) -> dict[str, Any]:
    """Run account scan and return structured results.

    Executes Sherlock and/or Reddit scans based on config.mode and
    returns all results in a structured format. This is the recommended
    entry point for programmatic access to the scanner.

    Args:
      username: Username to scan across platforms.
      config: ScanConfig with API credentials and scan settings.

    Returns:
      Dict with structure:
        {
          "username": str,           # Username that was scanned
          "sherlock": list[dict] | None,  # Sherlock OSINT results
          "reddit": list[dict] | None,    # Reddit toxicity results
          "errors": list[str]        # Any errors encountered
        }

      Sherlock results: List of dicts with platform, url, status, response_time.
      Reddit results: List of flagged items with toxicity scores.

      None values indicate scan wasn't run or found no results.
      Errors list includes configuration issues and scan failures.

    Example:
      >>> config = ScanConfig(
      ...     username="johndoe",
      ...     mode="both",
      ...     api_key="key",
      ...     client_id="id",
      ...     client_secret="secret"
      ... )
      >>> results = await ScannerAPI.scan_user("johndoe", config)
      >>> if results["reddit"]:
      ...     print(f"Found {len(results['reddit'])} toxic items")
    """
    results:  dict[str, Any] = {
      "username": username,
      "sherlock": None,
      "reddit": None,
      "errors": [],
    }
    tasks:  list[tuple[str, Any]] = []
    if config.mode in ("sherlock", "both"):
      if SherlockScanner.available():
        scanner = SherlockScanner()
        output_dir = config.output_sherlock.parent if config.output_sherlock else None
        tasks.append(("sherlock", scanner.scan(username, config.sherlock_timeout, config.verbose, output_dir)))
      else:
        results["errors"].append("Sherlock not installed")
    if config.mode in ("reddit", "both"):
      if all((config.api_key, config. client_id, config.client_secret)):
        reddit = RedditScanner(config)
        tasks.append(("reddit", reddit.scan()))
      elif config.mode == "reddit":
        results["errors"].append("Reddit mode requires API credentials")
    if not tasks:
      results["errors"]. append("No valid scan modes configured")
      return results
    completed = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
    for (scan_type, _), result in zip(tasks, completed):
      if isinstance(result, Exception):
        results["errors"].append(f"{scan_type} failed: {result}")
      else:
        results[scan_type] = result
    return results


async def main_async() -> None:
  """Main async entry point for command-line usage.

  Parses command-line arguments, validates configuration, executes
  requested scans (Sherlock and/or Reddit), and saves results to files.

  Exits with code 1 if required credentials are missing or no valid
  scan modes are configured.
  """
  parser = argparse.ArgumentParser(
    description="Multi-source account scanner",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter,
  )
  parser.add_argument("username", help="Username to scan")
  parser.add_argument(
    "--mode",
    choices=["sherlock", "reddit", "both"],
    default="both",
    help="Scan mode",
  )
  parser.add_argument("--perspective-api-key", dest="api_key", help="Perspective API key")
  parser.add_argument("--client-id", help="Reddit client ID")
  parser.add_argument("--client-secret", help="Reddit client secret")
  parser.add_argument("--user-agent", help="Reddit user agent")
  parser.add_argument("--comments", type=int, default=50, help="Max comments to fetch")
  parser.add_argument("--posts", type=int, default=20, help="Max posts to fetch")
  parser.add_argument(
    "--toxicity-threshold",
    dest="threshold",
    type=float,
    default=0.7,
    help="Toxicity threshold (0-1)",
  )
  parser.add_argument("--rate-per-min", type=float, default=60.0, help="API rate limit")
  parser.add_argument("--sherlock-timeout", type=int, default=60, help="Sherlock timeout (s)")
  parser.add_argument("--output-reddit", default="reddit_flagged.csv", help="Reddit output file")
  parser.add_argument("--output-sherlock", default="sherlock_results. json", help="Sherlock output file")
  parser.add_argument("--verbose", action="store_true", help="Verbose output")
  args = parser.parse_args()
  if args.verbose:
    logging.getLogger().setLevel(logging.DEBUG)
  config = ScanConfig(**vars(args))
  # Validate requirements
  tasks:  list[Any] = []
  if config. mode in ("sherlock", "both"):
    if SherlockScanner.available():
      scanner = SherlockScanner()
      output_dir = config.output_sherlock.parent if config.output_sherlock else None
      tasks.append(scanner.scan(config.username, config.sherlock_timeout, config.verbose, output_dir))
    else:
      log.warning("Sherlock not installed, skipping")
  if config.mode in ("reddit", "both"):
    if all((config.api_key, config.client_id, config. client_secret)):
      reddit = RedditScanner(config)
      tasks.append(reddit.scan())
    elif config.mode == "reddit":
      sys.exit("Error: Reddit mode requires --perspective-api-key, --client-id, --client-secret")
  if not tasks:
    sys.exit("Error: No valid scan modes configured")
  # Execute scans
  results = await asyncio.gather(*tasks, return_exceptions=True)
  # Save Sherlock results
  for result in results:
    if isinstance(result, list) and result and "platform" in result[0]:
      json_content = orjson.dumps(result, option=orjson.OPT_INDENT_2)
      async with aiofiles.open(config.output_sherlock, "wb") as f:
        await f.write(json_content)
      log.info(
        "🔎 Sherlock: Found %d accounts → %s",
        len(result),
        config.output_sherlock,
      )


def main() -> None:
  """Main entry point for CLI execution.

  Installs uvloop for better async performance and runs the async
  main function. Handles KeyboardInterrupt gracefully.
  """
  uvloop.install()
  try:
    asyncio.run(main_async())
  except KeyboardInterrupt:
    log. info("\nInterrupted by user")
    sys.exit(130)


if __name__ == "__main__":
  main()

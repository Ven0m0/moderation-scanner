#!/usr/bin/env python3
"""Multi-source account scanner: Reddit toxicity + Sherlock OSINT."""
import argparse
import asyncio
import csv
import io
import logging
import shutil
import sys
import tempfile
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
  """Configuration for account scanning."""
  username: str
  mode: str = "both"
  # Reddit
  api_key: str | None = None
  client_id: str | None = None
  client_secret: str | None = None
  user_agent: str | None = None
  comments: int = 50
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
      self.user_agent = f"account-scanner/1.2.0 (by u/{self.username})"


class RateLimiter:
  """Token bucket rate limiter."""
  def __init__(self, rate_per_min: float) -> None:
    self.delay = 60.0 / rate_per_min
    self.last_call = 0.0

  async def wait(self) -> None:
    now = time.monotonic()
    elapsed = now - self.last_call
    if elapsed < self.delay:
      await asyncio.sleep(self.delay - elapsed)
    self.last_call = time.monotonic()


class SherlockScanner:
  """Handles Sherlock OSINT scanning."""

  @staticmethod
  def available() -> bool:
    return shutil.which("sherlock") is not None

  @staticmethod
  def _parse_stdout(text: str) -> list[dict[str, Any]]:
    """Parse Sherlock stdout as fallback."""
    seen: set[tuple[str, str]] = set()
    results: list[dict[str, Any]] = []
    for line in text.splitlines():
      line = line.strip()
      if "://" not in line or ": " not in line:
        continue
      if "]: " in line:
        _, line = line.split("]: ", 1)
      parts = line.split(": ", 1)
      if len(parts) != 2:
        continue
      platform, url = parts
      url = url.strip()
      platform = platform.strip(" +[]")
      if not url.startswith("http"):
        continue
      key = (platform.lower(), url)
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
    """Check if account status indicates claimed."""
    s = status.lower()
    invalid = ("not", "available", "invalid", "unchecked", "unknown")
    return not any(x in s or s.startswith(x) for x in invalid)

  async def scan(self, username: str, timeout: int, verbose: bool) -> list[dict[str, Any]]:
    """Run Sherlock scan for username."""
    log.info("🔎 Sherlock: Scanning '%s'...", username)
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"sherlock_{username}_"))
    json_file = tmp_dir / f"{username}.json"
    cmd = [
      "sherlock", username,
      "--json", json_file.name,
      "--timeout", str(timeout),
      "--print-found",
      "--no-color",
    ]
    try:
      proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=tmp_dir,
      )
      try:
        await asyncio.wait_for(proc.wait(), timeout=timeout + SHERLOCK_BUFFER)
      except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        log.warning("🔎 Sherlock: timed out after %ds", timeout)

      stdout = await proc.stdout.read() if proc.stdout else b""
      stderr = await proc.stderr.read() if proc.stderr else b""

      if verbose:
        if stdout:
          log.debug("Sherlock stdout:\n%s", stdout.decode(errors="ignore"))
        if stderr:
          log.debug("Sherlock stderr:\n%s", stderr.decode(errors="ignore"))

      # Try JSON first
      results: list[dict[str, Any]] = []
      if json_file.exists():
        async with aiofiles.open(json_file, "rb") as f:
          content = await f.read()
        if content.strip():
          data = orjson.loads(content)
          results = [
            {
              "platform": k,
              "url": d.get("url_user"),
              "status": d.get("status"),
              "response_time": d.get("response_time_s"),
            }
            for k, d in data.items()
            if self._is_claimed(str(d.get("status", "")))
          ]

      # Fallback to stdout parsing
      if not results and stdout:
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
    finally:
      shutil.rmtree(tmp_dir, ignore_errors=True)


class RedditScanner:
  """Handles Reddit toxicity analysis."""

  def __init__(self, config: ScanConfig) -> None:
    self.config = config
    self.limiter = RateLimiter(config.rate_per_min)

  async def _check_toxicity(
    self,
    client: httpx.AsyncClient,
    text: str,
    key: str,
  ) -> dict[str, float]:
    """Analyze text toxicity via Perspective API."""
    if not text.strip():
      return {}

    await self.limiter.wait()
    payload = {
      "comment": {"text": text},
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
          for k, v in data.get("attributeScores", {}).items()
        }
    except Exception:
      pass
    return {}

  async def _fetch_items(self) -> list[tuple[str, str, str, float]] | None:
    """Fetch Reddit comments and posts."""
    cfg = self.config
    log.info("🤖 Reddit: Fetching content for u/%s...", cfg.username)

    reddit: Reddit | None = None
    try:
      reddit = Reddit(
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        user_agent=cfg.user_agent,
        requestor_kwargs={"timeout": DEFAULT_TIMEOUT},
      )
      user = await reddit.redditor(cfg.username)
      items: list[tuple[str, str, str, float]] = []

      async for c in user.comments.new(limit=cfg.comments):
        items.append(("comment", c.subreddit.display_name, c.body, c.created_utc))

      async for s in user.submissions.new(limit=cfg.posts):
        items.append((
          "post",
          s.subreddit.display_name,
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
    """Scan Reddit content for toxicity."""
    items = await self._fetch_items()
    if not items:
      log.info("🤖 Reddit: No items to analyze")
      return None

    log.info("🤖 Reddit: Analyzing %d items...", len(items))
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
    flagged: list[dict[str, Any]] = []
    for (kind, sub, text, ts), scores in zip(items, results):
      if any(s >= self.config.threshold for s in scores.values()):
        flagged.append({
          "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
          "type": kind,
          "subreddit": str(sub),
          "content": text[:500],
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
        await f.write(buffer.getvalue())

      log.info(
        "🤖 Reddit: Saved %d flagged items → %s",
        len(flagged),
        self.config.output_reddit,
      )
    else:
      log.info("🤖 Reddit: No toxic content found")

    return flagged


async def main_async() -> None:
  """Main async entry point."""
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
  parser.add_argument("--output-sherlock", default="sherlock_results.json", help="Sherlock output file")
  parser.add_argument("--verbose", action="store_true", help="Verbose output")

  args = parser.parse_args()
  if args.verbose:
    logging.getLogger().setLevel(logging.DEBUG)

  config = ScanConfig(**vars(args))

  # Validate requirements
  tasks: list[Any] = []
  if config.mode in ("sherlock", "both"):
    if SherlockScanner.available():
      scanner = SherlockScanner()
      tasks.append(scanner.scan(config.username, config.sherlock_timeout, config.verbose))
    else:
      log.warning("Sherlock not installed, skipping")

  if config.mode in ("reddit", "both"):
    if all((config.api_key, config.client_id, config.client_secret)):
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
  """Main entry point."""
  uvloop.install()
  try:
    asyncio.run(main_async())
  except KeyboardInterrupt:
    log.info("\nInterrupted by user")
    sys.exit(130)


if __name__ == "__main__":
  main()

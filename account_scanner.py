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
"""

import argparse
import asyncio
import csv
import io
import logging
import re
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
from asyncpraw.models import Redditor
from asyncprawcore import AsyncPrawcoreException

# Constants
PERSPECTIVE_URL: Final = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
DEFAULT_TIMEOUT: Final = 10
SHERLOCK_BUFFER: Final = 30
ATTRIBUTES: Final = ["TOXICITY", "INSULT", "PROFANITY", "SEXUALLY_EXPLICIT"]
HTTP2_LIMITS: Final = httpx.Limits(max_keepalive_connections=5, max_connections=10)
HTTP_OK: Final = 200
# Concurrency limit for API calls to prevent overwhelming the event loop
MAX_CONCURRENT_API_CALLS: Final = 5

# Logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# Shared HTTP client for connection reuse (performance optimization)
_http_client: httpx.AsyncClient | None = None
_http_client_lock = asyncio.Lock()

# TTL-based cache for scan results (performance optimization)
_scan_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_cache_lock = asyncio.Lock()
CACHE_TTL: Final = 900  # 15 minutes
CACHE_MAX_SIZE: Final = 100


async def get_http_client() -> httpx.AsyncClient:
    """Get or create shared HTTP client for connection reuse."""
    global _http_client
    async with _http_client_lock:
        if _http_client is None or _http_client.is_closed:
            _http_client = httpx.AsyncClient(
                http2=True,
                limits=HTTP2_LIMITS,
                headers={"Content-Type": "application/json"},
                timeout=DEFAULT_TIMEOUT,
            )
    return _http_client


async def close_http_client() -> None:
    """Close the shared HTTP client."""
    global _http_client
    async with _http_client_lock:
        if _http_client is not None and not _http_client.is_closed:
            await _http_client.aclose()
            _http_client = None


async def get_cached_result(cache_key: str) -> dict[str, Any] | None:
    """Get cached scan result if not expired."""
    async with _cache_lock:
        if cache_key in _scan_cache:
            timestamp, result = _scan_cache[cache_key]
            if time.monotonic() - timestamp < CACHE_TTL:
                log.info("📦 Cache hit for '%s'", cache_key)
                return result
            else:
                # Expired, remove it
                del _scan_cache[cache_key]
    return None


async def set_cached_result(cache_key: str, result: dict[str, Any]) -> None:
    """Cache scan result with TTL."""
    async with _cache_lock:
        # Simple LRU: if cache is full, remove oldest entry
        if len(_scan_cache) >= CACHE_MAX_SIZE:
            oldest_key = min(_scan_cache.keys(), key=lambda k: _scan_cache[k][0])
            del _scan_cache[oldest_key]
        _scan_cache[cache_key] = (time.monotonic(), result)
        log.info("📦 Cached result for '%s'", cache_key)


class RateLimiter:
    """Token bucket rate limiter for API request throttling.

    Implements a simple token bucket algorithm to ensure API requests
    don't exceed the specified rate limit. Each call to wait() blocks
    until enough time has elapsed to respect the rate limit.

    Attributes:
      delay: Minimum seconds between consecutive requests.
      last_call: Timestamp (monotonic) of the last request.
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


@dataclass
class ScanConfig:
    """Configuration for account scanning operations.

    Attributes:
      username: Target username to scan across platforms.
      mode: Scan mode - 'reddit', 'sherlock', or 'both'. Default: 'both'.
      limiter: Optional shared RateLimiter instance.

      Reddit configuration:
      api_key: Google Perspective API key for toxicity analysis.
      client_id: Reddit API client ID.
      client_secret: Reddit API client secret.
      user_agent: Reddit API user agent string.
      comments: Maximum number of comments to fetch per user. Default: 50.
      posts: Maximum number of posts to fetch per user. Default: 20.
      threshold: Toxicity threshold (0-1). Default: 0.7.
      rate_per_min: API requests per minute rate limit. Default: 60.0.

      Sherlock configuration:
      sherlock_timeout: Timeout in seconds for Sherlock subprocess. Default: 60.

      Output configuration:
      output_reddit: Path for Reddit CSV results.
      output_sherlock: Path for Sherlock JSON results.
      verbose: Enable verbose logging output.
    """

    username: str
    mode: str = "both"
    limiter: RateLimiter | None = None
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
    sherlock_timeout: int = 120  # Increased from 60s to handle slow network/server
    # Output
    output_reddit: Path = field(default_factory=lambda: Path("reddit_flagged.csv"))
    output_sherlock: Path = field(default_factory=lambda: Path("sherlock_results.json"))
    verbose: bool = False

    def __post_init__(self) -> None:
        # FIX 4: Sanitize username to prevent path traversal if used in filenames
        # Allows alphanumeric, underscores, and hyphens only.
        self.username = re.sub(r"[^\w\-]", "_", self.username)

        self.output_reddit = Path(self.output_reddit)
        self.output_sherlock = Path(self.output_sherlock)

        if not self.user_agent:
            self.user_agent = f"account-scanner/1.2.3 (by u/{self.username})"


class SherlockScanner:
    """Handles Sherlock OSINT username enumeration across platforms."""

    @staticmethod
    def available() -> bool:
        """Check if Sherlock is installed and available."""
        return shutil.which("sherlock") is not None

    @staticmethod
    def _parse_stdout(text: str) -> list[dict[str, Any]]:
        """Parse Sherlock stdout output into structured data."""
        seen: set[tuple[str, str]] = set()
        results: list[dict[str, Any]] = []
        for raw_line in text.splitlines():
            stripped_line = raw_line.strip()
            # FIX 1: Relaxed parsing to accept single space ": "
            if "://" not in stripped_line or ": " not in stripped_line:
                continue
            # Remove timestamp prefix if present
            if "]:  " in stripped_line:
                _, stripped_line = stripped_line.split("]: ", 1)
            parts = stripped_line.split(": ", 1)
            if len(parts) < 2:
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
            results.append(
                {
                    "platform": platform,
                    "url": url,
                    "status": "Claimed",
                    "response_time": None,
                }
            )
        return results

    async def scan(
        self,
        username: str,
        timeout_seconds: int,
        verbose: bool,
        output_dir: Path | None = None,
    ) -> list[dict[str, Any]]:
        """Run Sherlock OSINT scan for the given username."""
        log.info("🔎 Sherlock:  Scanning '%s'.. .", username)

        # FIX 5: Added "--" to prevent argument injection
        cmd = [
            "sherlock",
            "--",
            username,
            "--timeout",
            str(timeout_seconds),
            "--no-color",
            "--print-found",
        ]

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
                    timeout=timeout_seconds + SHERLOCK_BUFFER,
                )
            except TimeoutError:
                proc.kill()
                await proc.wait()
                log.warning("🔎 Sherlock: timed out after %ds", timeout_seconds)
                stdout, stderr = b"", b""

            stderr_text = stderr.decode(errors="ignore").strip() if stderr else ""
            if stderr_text:
                log.warning("🔎 Sherlock stderr:\n%s", stderr_text)

            if verbose and stdout:
                log.info("🔎 Sherlock stdout:\n%s", stdout.decode(errors="ignore"))

            results: list[dict[str, Any]] = []
            if stdout:
                results = self._parse_stdout(stdout.decode(errors="ignore"))

            if proc.returncode and proc.returncode != 0:
                log.error("🔎 Sherlock: process exited with code %d", proc.returncode)

            if results:
                log.info("🔎 Sherlock: collected %d claimed accounts", len(results))
            else:
                log.info("🔎 Sherlock: no claimed accounts found")
            return results
        except OSError:
            log.exception("🔎 Sherlock OS error")
            return []
        except asyncio.CancelledError:
            log.warning("🔎 Sherlock: scan cancelled")
            raise
        except (ValueError, RuntimeError):
            log.exception("🔎 Sherlock error")
            return []


class RedditScanner:
    """Handles Reddit content fetching and toxicity analysis."""

    def __init__(self, config: ScanConfig) -> None:
        """Initialize Reddit scanner with configuration.

        Args:
          config: ScanConfig with Reddit/Perspective API credentials.
        """
        self.config = config
        # FIX 2: Reuse shared limiter if provided, else create new
        if config.limiter:
            self.limiter = config.limiter
        else:
            self.limiter = RateLimiter(config.rate_per_min)

    async def _check_toxicity(
        self,
        client: httpx.AsyncClient,
        text: str,
        key: str,
    ) -> dict[str, float]:
        """Analyze text toxicity using Google Perspective API."""
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
            if resp.status_code == HTTP_OK:
                data = orjson.loads(resp.content)
                return {
                    k: v["summaryScore"]["value"]
                    for k, v in data.get("attributeScores", {}).items()
                }
        except httpx.HTTPError as exc:
            log.warning("Perspective API HTTP error; returning empty scores: %s", exc)
        except (orjson.JSONDecodeError, KeyError, TypeError) as exc:
            log.warning(
                "Perspective API response parsing failed; returning empty scores: %s",
                exc,
            )
        return {}

    async def _fetch_comments(self, user: Redditor) -> list[tuple[str, str, str, float]]:
        """Fetch Reddit comments for a user."""
        items: list[tuple[str, str, str, float]] = []
        async for c in user.comments.new(limit=self.config.comments):
            items.append(("comment", c.subreddit.display_name, c.body, c.created_utc))
        return items

    async def _fetch_posts(self, user: Redditor) -> list[tuple[str, str, str, float]]:
        """Fetch Reddit posts for a user."""
        items: list[tuple[str, str, str, float]] = []
        async for s in user.submissions.new(limit=self.config.posts):
            items.append(
                (
                    "post",
                    s.subreddit.display_name,
                    f"{s.title}\n{s.selftext}",
                    s.created_utc,
                )
            )
        return items

    async def _fetch_items(self) -> list[tuple[str, str, str, float]] | None:
        """Fetch Reddit comments and posts for the configured user (concurrently)."""
        cfg = self.config
        log.info("🤖 Reddit: Fetching content for u/%s.. .", cfg.username)
        reddit: Reddit | None = None
        try:
            reddit = Reddit(
                client_id=cfg.client_id,
                client_secret=cfg.client_secret,
                user_agent=cfg.user_agent,
                requestor_kwargs={"timeout": DEFAULT_TIMEOUT},
            )
            user = await reddit.redditor(cfg.username)

            # Fetch comments and posts concurrently for better performance
            comments, posts = await asyncio.gather(
                self._fetch_comments(user),
                self._fetch_posts(user),
                return_exceptions=False,
            )

            items = comments + posts
            return items if items else None
        except AsyncPrawcoreException:
            log.exception("Reddit API Error")
        except (OSError, ValueError, RuntimeError):
            log.exception("Reddit fetch error")
        finally:
            if reddit:
                await reddit.close()
        return None

    async def scan(self) -> list[dict[str, Any]] | None:
        """Scan Reddit user's content for toxic language."""
        items = await self._fetch_items()
        if not items:
            log.info("🤖 Reddit: No items to analyze")
            return None
        log.info("🤖 Reddit:  Analyzing %d items...", len(items))
        # Use shared HTTP client for connection reuse
        client = await get_http_client()

        # Use semaphore to limit concurrent API calls and prevent blocking heartbeat
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_API_CALLS)

        async def throttled_check(text: str) -> dict[str, float]:
            async with semaphore:
                result = await self._check_toxicity(client, text, self.config.api_key or "")
                # Yield to event loop to prevent blocking Discord heartbeat
                await asyncio.sleep(0)
                return result

        results = await asyncio.gather(*[throttled_check(text) for _, _, text, _ in items])
        # Filter flagged content
        flagged: list[dict[str, Any]] = []
        for (kind, sub, text, ts), scores in zip(items, results, strict=True):
            if any(s >= self.config.threshold for s in scores.values()):
                flagged.append(
                    {
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)),
                        "type": kind,
                        "subreddit": str(sub),
                        "content": text[:500],
                        **scores,
                    }
                )
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
                "🤖 Reddit:  Saved %d flagged items → %s",
                len(flagged),
                self.config.output_reddit,
            )
        else:
            log.info("🤖 Reddit: No toxic content found")
        return flagged


class ScannerAPI:
    """Library interface for programmatic access to scanner functionality."""

    @staticmethod
    async def scan_user(
        username: str,
        config: ScanConfig,
    ) -> dict[str, Any]:
        """Run account scan and return structured results."""
        # Create cache key based on username and mode
        cache_key = f"{config.username}:{config.mode}"

        # Check cache first
        cached_result = await get_cached_result(cache_key)
        if cached_result is not None:
            return cached_result

        results: dict[str, Any] = {
            "username": config.username,  # Use sanitized username from config
            "sherlock": None,
            "reddit": None,
            "errors": [],
        }
        tasks: list[tuple[str, Any]] = []
        if config.mode in ("sherlock", "both"):
            if SherlockScanner.available():
                scanner = SherlockScanner()
                output_dir = config.output_sherlock.parent if config.output_sherlock else None
                tasks.append(
                    (
                        "sherlock",
                        scanner.scan(
                            config.username,
                            config.sherlock_timeout,
                            config.verbose,
                            output_dir,
                        ),
                    )
                )
            else:
                results["errors"].append("Sherlock not installed")
        if config.mode in ("reddit", "both"):
            if all((config.api_key, config.client_id, config.client_secret)):
                reddit = RedditScanner(config)
                tasks.append(("reddit", reddit.scan()))
            elif config.mode == "reddit":
                results["errors"].append("Reddit mode requires API credentials")
        if not tasks:
            results["errors"].append("No valid scan modes configured")
            return results
        completed = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        for (scan_type, _), result in zip(tasks, completed, strict=True):
            if isinstance(result, Exception):
                results["errors"].append(f"{scan_type} failed: {result}")
            else:
                results[scan_type] = result

        # Cache the results before returning
        await set_cached_result(cache_key, results)

        return results


async def main_async() -> None:
    """Main async entry point for command-line usage."""
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
    parser.add_argument("--sherlock-timeout", type=int, default=120, help="Sherlock timeout (s)")
    parser.add_argument("--output-reddit", default="reddit_flagged.csv", help="Reddit output file")
    parser.add_argument(
        "--output-sherlock",
        default="sherlock_results.json",
        help="Sherlock output file",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    config = ScanConfig(**vars(args))

    # Execute scan using ScannerAPI for consistency
    results = await ScannerAPI.scan_user(config.username, config)

    # Handle results output manually for CLI (file writing is partly done in API)
    # But Sherlock JSON writing was done in main previously.
    # Note: Reddit CSV writing is handled inside RedditScanner.scan()

    if results["sherlock"]:
        result = results["sherlock"]
        json_content = orjson.dumps(result, option=orjson.OPT_INDENT_2)
        async with aiofiles.open(config.output_sherlock, "wb") as f:
            await f.write(json_content)
        log.info(
            "🔎 Sherlock: Found %d accounts → %s",
            len(result),
            config.output_sherlock,
        )

    if results["errors"]:
        for err in results["errors"]:
            log.error("Error: %s", err)


def main() -> None:
    """Main entry point for CLI execution."""
    uvloop.install()
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        log.info("\nInterrupted by user")
        sys.exit(130)
    finally:
        # Clean up shared HTTP client
        try:
            asyncio.run(close_http_client())
        except RuntimeError:
            pass  # Event loop already closed


if __name__ == "__main__":
    main()

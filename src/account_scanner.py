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
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, Literal, TypedDict

import aiofiles
import httpx
import orjson
import uvloop

# --- PEP 695 type aliases ---
type ScanMode = Literal["sherlock", "reddit", "both"]
# Plain dict alias: Perspective API returns dynamic keys — TypedDict adds no value here.
type ToxicityScores = dict[str, float]

# --- TypedDicts for structured data at module boundaries ---


class SherlockResult(TypedDict):
    """Single Sherlock OSINT result entry."""

    platform: str
    url: str
    status: str
    response_time: float | None


class _RedditFlaggedBase(TypedDict):
    timestamp: str
    type: str
    subreddit: str
    content: str


class RedditFlaggedItem(_RedditFlaggedBase, total=False):
    """Reddit flagged item with optional per-attribute toxicity scores."""

    TOXICITY: float
    INSULT: float
    PROFANITY: float
    SEXUALLY_EXPLICIT: float


class ScanResult(TypedDict):
    """Structured result returned by ScannerAPI.scan_user."""

    username: str
    sherlock: list[SherlockResult] | None
    reddit: list[RedditFlaggedItem] | None
    errors: list[str]


# --- Thread-safe lock for Sherlock availability cache (sync API) ---
_sherlock_available_thread_lock = threading.Lock()

# --- Constants ---
PERSPECTIVE_URL: Final = "https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze"
DEFAULT_TIMEOUT: Final = 10
SHERLOCK_BUFFER: Final = 30
SHERLOCK_PARTIAL_READ_TIMEOUT: Final = 2.0
SHERLOCK_PARTIAL_READ_EXCEPTIONS: Final = (OSError, RuntimeError, ValueError, TimeoutError)
ATTRIBUTES: Final = ("TOXICITY", "INSULT", "PROFANITY", "SEXUALLY_EXPLICIT")
HTTP2_LIMITS: Final = httpx.Limits(max_keepalive_connections=5, max_connections=10)
HTTP_OK: Final = 200
MAX_CONCURRENT_API_CALLS: Final = 5
CACHE_TTL: Final = 900  # 15 minutes
CACHE_MAX_SIZE: Final = 100

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# --- Module-level singletons (performance: connection & cache reuse) ---
_http_client: httpx.AsyncClient | None = None
_http_client_lock = asyncio.Lock()

_sherlock_available: bool | None = None
_sherlock_lock = asyncio.Lock()

_scan_cache: OrderedDict[str, tuple[float, ScanResult]] = OrderedDict()
_cache_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    """Get or create the shared HTTP/2 client."""
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
    """Close the shared HTTP client and release resources."""
    global _http_client
    async with _http_client_lock:
        if _http_client is not None and not _http_client.is_closed:
            await _http_client.aclose()
            _http_client = None


async def get_cached_result(cache_key: str) -> ScanResult | None:
    """Return a cached ScanResult if still within TTL, otherwise None."""
    async with _cache_lock:
        if cache_key in _scan_cache:
            timestamp, result = _scan_cache[cache_key]
            if time.monotonic() - timestamp < CACHE_TTL:
                log.info("📦 Cache hit for '%s'", cache_key)
                _scan_cache.move_to_end(cache_key)
                return result
            del _scan_cache[cache_key]
    return None


async def set_cached_result(cache_key: str, result: ScanResult) -> None:
    """Store a ScanResult in the TTL LRU cache, evicting the oldest if at capacity."""
    async with _cache_lock:
        if cache_key in _scan_cache:
            del _scan_cache[cache_key]
        elif len(_scan_cache) >= CACHE_MAX_SIZE:
            _scan_cache.popitem(last=False)
        _scan_cache[cache_key] = (time.monotonic(), result)
        log.info("📦 Cached result for '%s'", cache_key)


@dataclass(slots=True)
class RateLimiter:
    """Token bucket rate limiter for API request throttling.

    Attributes:
      rate_per_min: Maximum requests per minute allowed.
      delay: Minimum seconds between consecutive requests (derived).
      last_call: Monotonic timestamp of the most recent request.
    """

    rate_per_min: float
    delay: float = field(init=False)
    last_call: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self.delay = 60.0 / self.rate_per_min

    async def wait(self) -> None:
        """Sleep only as long as necessary to honour the configured rate."""
        now = time.monotonic()
        elapsed = now - self.last_call
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
        self.last_call = time.monotonic()


@dataclass(slots=True)
class ScanConfig:
    """Configuration for account scanning operations.

    Attributes:
      username: Target username (sanitised on construction).
      mode: Scan mode — 'reddit', 'sherlock', or 'both'.
      limiter: Optional shared RateLimiter instance.

      Reddit configuration:
        api_key, client_id, client_secret, user_agent,
        comments, posts, threshold, rate_per_min.

      Sherlock configuration:
        sherlock_timeout — subprocess timeout in seconds.

      Output configuration:
        output_reddit, output_sherlock, verbose.
    """

    username: str
    mode: ScanMode = "both"
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
    sherlock_timeout: int = 120
    # Output
    output_reddit: Path = field(default_factory=lambda: Path("reddit_flagged.csv"))
    output_sherlock: Path = field(default_factory=lambda: Path("sherlock_results.json"))
    verbose: bool = False

    def __post_init__(self) -> None:
        # Sanitise username to prevent path traversal (alphanumeric, _ and - only).
        self.username = re.sub(r"[^\w\-]", "_", self.username)
        if not self.user_agent:
            self.user_agent = f"account-scanner/1.2.3 (by u/{self.username})"


class SherlockScanner:
    """Handles Sherlock OSINT username enumeration across platforms."""

    @staticmethod
    async def available() -> bool:
        """Check whether Sherlock is installed (result is cached)."""
        global _sherlock_available
        if (cached := _sherlock_available) is not None:
            return cached
        async with _sherlock_lock:
            if (cached := _sherlock_available) is not None:
                return cached
            path = await asyncio.to_thread(shutil.which, "sherlock")
            _sherlock_available = path is not None
            return _sherlock_available

    @staticmethod
    def available_sync() -> bool:
        """Synchronous availability check, safe outside an event loop.

        Uses a dedicated threading.Lock so it never touches asyncio primitives,
        avoiding event-loop binding issues.
        """
        global _sherlock_available
        with _sherlock_available_thread_lock:
            if _sherlock_available is not None:
                return _sherlock_available
            result = shutil.which("sherlock") is not None
            _sherlock_available = result
            return result

    @staticmethod
    def _extract_accounts(text: str) -> Iterator[tuple[str, str]]:
        """Yield (platform, url) pairs from Sherlock stdout text."""
        for raw_line in text.splitlines():
            stripped = raw_line.strip()
            if "://" not in stripped or ": " not in stripped:
                continue
            if "]:  " in stripped:
                _, stripped = stripped.split("]: ", 1)
            parts = stripped.split(": ", 1)
            if len(parts) < 2:
                continue
            platform, url = parts
            url = url.strip()
            platform = platform.strip(" +[]")
            if not url.startswith("http"):
                continue
            yield platform, url

    @staticmethod
    def _parse_stdout(text: str) -> list[SherlockResult]:
        """Parse Sherlock stdout into a list of SherlockResult entries."""
        seen: set[tuple[str, str]] = set()
        results: list[SherlockResult] = []
        for platform, url in SherlockScanner._extract_accounts(text):
            key = (platform.lower(), url)
            if key in seen:
                continue
            seen.add(key)
            results.append(
                SherlockResult(platform=platform, url=url, status="Claimed", response_time=None)
            )
        return results

    async def scan(
        self,
        username: str,
        timeout_seconds: int,
        verbose: bool,
        output_dir: Path | None = None,
    ) -> list[SherlockResult]:
        """Run Sherlock for *username* and return parsed results."""
        log.info("🔎 Sherlock:  Scanning '%s'...", username)
        cmd = [
            "sherlock",
            "--timeout",
            str(timeout_seconds),
            "--no-color",
            "--print-found",
        ]
        if output_dir:
            cmd.extend(["--output", str(output_dir / f"{username}.txt")])
        cmd.extend(["--", username])

        async def _read_stream(stream: asyncio.StreamReader | None) -> bytes:
            return (await stream.read()) if stream is not None else b""

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # Start background readers immediately.  They are NOT cancelled on timeout,
            # so every byte Sherlock emits is preserved.  After proc.kill(), the OS
            # closes the write end of both pipes → EOF → the readers complete naturally
            # with all accumulated data.
            stdout_task: asyncio.Task[bytes] = asyncio.create_task(_read_stream(proc.stdout))
            stderr_task: asyncio.Task[bytes] = asyncio.create_task(_read_stream(proc.stderr))

            timed_out = False
            try:
                await asyncio.wait_for(proc.wait(), timeout=timeout_seconds + SHERLOCK_BUFFER)
                stdout = await stdout_task
                stderr = await stderr_task
            except TimeoutError:
                timed_out = True
                if proc.returncode is None:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        log.debug(
                            "🔎 Sherlock: process exited before kill during timeout recovery",
                            exc_info=True,
                        )
                await proc.wait()
                # Readers get EOF from the killed process and complete with partial data.
                try:
                    stdout = await asyncio.wait_for(
                        stdout_task, timeout=SHERLOCK_PARTIAL_READ_TIMEOUT
                    )
                except SHERLOCK_PARTIAL_READ_EXCEPTIONS as exc:
                    stdout_task.cancel()
                    try:
                        await stdout_task
                    except asyncio.CancelledError:
                        pass
                    stdout = b""
                    log.debug(
                        "🔎 Sherlock: failed to recover partial stdout: %s",
                        type(exc).__name__,
                        exc_info=True,
                    )
                try:
                    stderr = await asyncio.wait_for(
                        stderr_task, timeout=SHERLOCK_PARTIAL_READ_TIMEOUT
                    )
                except SHERLOCK_PARTIAL_READ_EXCEPTIONS as exc:
                    stderr_task.cancel()
                    try:
                        await stderr_task
                    except asyncio.CancelledError:
                        pass
                    stderr = b""
                    log.debug(
                        "🔎 Sherlock: failed to recover partial stderr: %s",
                        type(exc).__name__,
                        exc_info=True,
                    )
                log.warning(
                    "🔎 Sherlock: timed out after %ds; using partial results",
                    timeout_seconds,
                )

            if stderr_text := stderr.decode(errors="ignore").strip():
                log.warning("🔎 Sherlock stderr:\n%s", stderr_text)
            if verbose and stdout:
                log.info("🔎 Sherlock stdout:\n%s", stdout.decode(errors="ignore"))

            results = self._parse_stdout(stdout.decode(errors="ignore")) if stdout else []

            if not timed_out and proc.returncode is not None and proc.returncode != 0:
                log.error("🔎 Sherlock: process exited with code %d", proc.returncode)
            log.info(
                "🔎 Sherlock: %s",
                f"collected {len(results)} claimed accounts"
                if results
                else "no claimed accounts found",
            )
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
        self.config = config
        self.limiter: RateLimiter = config.limiter or RateLimiter(config.rate_per_min)

    async def _check_toxicity(
        self,
        client: httpx.AsyncClient,
        text: str,
        key: str,
    ) -> ToxicityScores:
        """Analyse *text* with the Perspective API and return attribute scores."""
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
            log.warning("Perspective API parse error; returning empty scores: %s", exc)
        return {}

    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        cfg = self.config
        if not cfg.client_id or not cfg.client_secret:
            raise ValueError("Reddit API credentials are required")
        response = await client.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(cfg.client_id, cfg.client_secret),
            data={"grant_type": "client_credentials"},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        token = data.get("access_token")
        if not (isinstance(token, str) and token):
            raise ValueError("Reddit access token missing from API response")
        return token

    async def _fetch_listing(
        self,
        client: httpx.AsyncClient,
        path: str,
        limit: int,
    ) -> list[tuple[str, str, str, float]]:
        response = await client.get(
            f"https://oauth.reddit.com/user/{self.config.username}/{path}",
            params={"sort": "new", "limit": limit, "raw_json": 1},
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        children = payload.get("data", {}).get("children", [])
        if not isinstance(children, list):
            raise ValueError("Reddit listing response missing children")
        items: list[tuple[str, str, str, float]] = []
        for child in children:
            if not isinstance(child, dict):
                continue
            data = child.get("data", {})
            if not isinstance(data, dict):
                continue
            subreddit = data.get("subreddit")
            created_utc = data.get("created_utc")
            if not isinstance(subreddit, str) or not isinstance(created_utc, (int, float)):
                continue
            if path == "comments":
                body = data.get("body")
                if isinstance(body, str):
                    items.append(("comment", subreddit, body, float(created_utc)))
            else:
                title = data.get("title")
                selftext = data.get("selftext")
                if isinstance(title, str) and isinstance(selftext, str):
                    if not title and not selftext:
                        continue
                    has_title = bool(title)
                    has_selftext = bool(selftext)
                    content = (
                        f"{title}\n{selftext}" if has_title and has_selftext else title or selftext
                    )
                    items.append(("post", subreddit, content, float(created_utc)))
        return items

    async def _fetch_comments(self, client: httpx.AsyncClient) -> list[tuple[str, str, str, float]]:
        return await self._fetch_listing(client, "comments", self.config.comments)

    async def _fetch_posts(self, client: httpx.AsyncClient) -> list[tuple[str, str, str, float]]:
        return await self._fetch_listing(client, "submitted", self.config.posts)

    async def _fetch_items(self) -> list[tuple[str, str, str, float]] | None:
        """Fetch Reddit comments and posts concurrently via TaskGroup."""
        cfg = self.config
        log.info("🤖 Reddit: Fetching content for u/%s...", cfg.username)
        items: list[tuple[str, str, str, float]] | None = None
        if not cfg.user_agent:
            log.error("Reddit fetch error: missing Reddit user agent")
            return None
        try:
            async with httpx.AsyncClient(headers={"User-Agent": cfg.user_agent}) as client:
                token = await self._get_access_token(client)
                client.headers["Authorization"] = f"Bearer {token}"
                async with asyncio.TaskGroup() as tg:
                    comments_t = tg.create_task(self._fetch_comments(client))
                    posts_t = tg.create_task(self._fetch_posts(client))
                merged = comments_t.result() + posts_t.result()
                items = merged if merged else None
        except* httpx.HTTPStatusError as status_group:
            for status_error in status_group.exceptions:
                log.error("Reddit API Error: %s", status_error)
        except* httpx.HTTPError as http_group:
            for http_error in http_group.exceptions:
                log.error("Reddit HTTP error: %s", http_error)
        except* (OSError, ValueError, RuntimeError) as fetch_group:
            for fetch_error in fetch_group.exceptions:
                log.error("Reddit fetch error: %s", fetch_error)
        return items

    async def scan(self) -> list[RedditFlaggedItem] | None:
        """Scan the configured Reddit user's content for toxic language."""
        items = await self._fetch_items()
        if not items:
            log.info("🤖 Reddit: No items to analyze")
            return None
        log.info("🤖 Reddit:  Analyzing %d items...", len(items))
        client = await get_http_client()
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_API_CALLS)

        async def throttled_check(text: str) -> ToxicityScores:
            async with semaphore:
                result = await self._check_toxicity(client, text, self.config.api_key or "")
                await asyncio.sleep(0)  # Yield to prevent blocking the Discord heartbeat
                return result

        score_tasks: list[asyncio.Task[ToxicityScores]] = []
        async with asyncio.TaskGroup() as tg:
            score_tasks = [tg.create_task(throttled_check(text)) for _, _, text, _ in items]
        scores = [t.result() for t in score_tasks]

        flagged: list[RedditFlaggedItem] = []
        for (kind, sub, text, ts), item_scores in zip(items, scores, strict=True):
            if any(s >= self.config.threshold for s in item_scores.values()):
                dt = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
                entry: RedditFlaggedItem = {
                    "timestamp": dt,
                    "type": kind,
                    "subreddit": str(sub),
                    "content": text[:500],
                    **item_scores,  # type: ignore[typeddict-item]
                }
                flagged.append(entry)

        if flagged:
            buffer = io.StringIO()
            writer = csv.DictWriter(
                buffer,
                fieldnames=["timestamp", "type", "subreddit", "content", *ATTRIBUTES],
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
    async def scan_user(config: ScanConfig) -> ScanResult:
        """Run an account scan and return a structured ScanResult.

        Results are cached by (username, mode) for CACHE_TTL seconds.
        """
        cache_key = f"{config.username}:{config.mode}"
        if (cached := await get_cached_result(cache_key)) is not None:
            return cached

        errors: list[str] = []
        do_sherlock = config.mode in ("sherlock", "both")
        do_reddit = config.mode in ("reddit", "both")

        if do_sherlock and not await SherlockScanner.available():
            errors.append("Sherlock not installed")
            do_sherlock = False

        if do_reddit and not all((config.api_key, config.client_id, config.client_secret)):
            if config.mode == "reddit":
                errors.append("Reddit mode requires API credentials")
            do_reddit = False

        if not do_sherlock and not do_reddit:
            errors.append("No valid scan modes configured")
            return ScanResult(username=config.username, sherlock=None, reddit=None, errors=errors)

        # Inner helpers capture `errors` by closure — each handles its own exceptions
        # so TaskGroup never receives an unhandled exception.
        async def _run_sherlock() -> list[SherlockResult]:
            try:
                return await SherlockScanner().scan(
                    config.username,
                    config.sherlock_timeout,
                    config.verbose,
                    config.output_sherlock.parent,
                )
            except Exception as exc:
                errors.append(f"sherlock failed: {exc}")
                return []

        async def _run_reddit() -> list[RedditFlaggedItem] | None:
            try:
                return await RedditScanner(config).scan()
            except Exception as exc:
                errors.append(f"reddit failed: {exc}")
                return None

        sherlock_task: asyncio.Task[list[SherlockResult]] | None = None
        reddit_task: asyncio.Task[list[RedditFlaggedItem] | None] | None = None

        async with asyncio.TaskGroup() as tg:
            if do_sherlock:
                sherlock_task = tg.create_task(_run_sherlock())
            if do_reddit:
                reddit_task = tg.create_task(_run_reddit())

        out = ScanResult(
            username=config.username,
            sherlock=sherlock_task.result() if sherlock_task is not None else None,
            reddit=reddit_task.result() if reddit_task is not None else None,
            errors=errors,
        )
        await set_cached_result(cache_key, out)
        return out


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
    parser.add_argument(
        "--output-reddit",
        type=Path,
        default=Path("reddit_flagged.csv"),
        help="Reddit output file",
    )
    parser.add_argument(
        "--output-sherlock",
        type=Path,
        default=Path("sherlock_results.json"),
        help="Sherlock output file",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    config = ScanConfig(**vars(args))

    try:
        results = await ScannerAPI.scan_user(config)

        if results["sherlock"]:
            json_content = orjson.dumps(results["sherlock"], option=orjson.OPT_INDENT_2)
            async with aiofiles.open(config.output_sherlock, "wb") as f:
                await f.write(json_content)
            log.info(
                "🔎 Sherlock: Found %d accounts → %s",
                len(results["sherlock"]),
                config.output_sherlock,
            )

        for err in results["errors"]:
            log.error("Error: %s", err)
    finally:
        await close_http_client()


def main() -> None:
    """Main entry point for CLI execution."""
    uvloop.install()
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        log.info("\nInterrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    main()

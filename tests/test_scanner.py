"""Tests for account_scanner core logic."""

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from account_scanner import RateLimiter, RedditScanner, ScanConfig, SherlockScanner

DEFAULT_THRESHOLD = 0.7


def test_config_defaults() -> None:
    cfg = ScanConfig(username="test")
    assert cfg.username == "test"
    assert cfg.mode == "both"
    assert cfg.threshold == DEFAULT_THRESHOLD


def test_config_sanitises_username() -> None:
    cfg = ScanConfig(username="te st/../bad")
    assert "/" not in cfg.username
    assert " " not in cfg.username


def test_config_sets_default_user_agent() -> None:
    cfg = ScanConfig(username="alice")
    assert cfg.user_agent is not None
    assert "alice" in cfg.user_agent


def test_rate_limiter_delay() -> None:
    limiter = RateLimiter(rate_per_min=60.0)
    assert limiter.delay == 1.0


def test_rate_limiter_delay_custom() -> None:
    limiter = RateLimiter(rate_per_min=30.0)
    assert limiter.delay == 2.0


def test_rate_limiter_initial_last_call() -> None:
    limiter = RateLimiter(rate_per_min=60.0)
    assert limiter.last_call == 0.0


async def test_sherlock_available_returns_bool() -> None:
    result = await SherlockScanner.available()
    assert isinstance(result, bool)


def test_sherlock_available_sync_returns_bool() -> None:
    result = SherlockScanner.available_sync()
    assert isinstance(result, bool)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("Claimed", True),
        ("Available", False),
        ("Not Found", False),
        ("Invalid", False),
        ("Unchecked", False),
        ("Found!", True),
        ("CLAIMED", True),
        ("found!", True),
    ],
)
def test_sherlock_is_claimed(status: str, expected: bool) -> None:
    assert SherlockScanner._is_claimed(status) == expected


async def test_rate_limiter_no_sleep_on_first_call() -> None:
    limiter = RateLimiter(rate_per_min=60.0)
    with (
        patch("time.monotonic", return_value=100.0),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        await limiter.wait()
        mock_sleep.assert_not_called()
        assert limiter.last_call == 100.0


async def test_rate_limiter_sleeps_when_called_too_soon() -> None:
    limiter = RateLimiter(rate_per_min=60.0)  # 1s delay
    limiter.last_call = 100.0
    # now=100.5, elapsed=0.5 → needs 0.5s sleep
    with (
        patch("time.monotonic", side_effect=[100.5, 100.5]),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        await limiter.wait()
        mock_sleep.assert_called_once_with(pytest.approx(0.5))
        assert limiter.last_call == 100.5


async def test_rate_limiter_no_sleep_after_full_delay() -> None:
    limiter = RateLimiter(rate_per_min=60.0)
    limiter.last_call = 100.0
    # now=101.5, elapsed=1.5 → no sleep needed
    with (
        patch("time.monotonic", return_value=101.5),
        patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
    ):
        await limiter.wait()
        mock_sleep.assert_not_called()
        assert limiter.last_call == 101.5


async def test_rate_limiter_updates_last_call_after_sleep() -> None:
    limiter = RateLimiter(rate_per_min=60.0)
    limiter.last_call = 100.0
    with (
        patch("time.monotonic", side_effect=[100.2, 100.8]),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        await limiter.wait()
        assert limiter.last_call == 100.8


def test_sherlock_parse_stdout_empty() -> None:
    assert SherlockScanner._parse_stdout("") == []


def test_sherlock_parse_stdout_no_urls() -> None:
    assert SherlockScanner._parse_stdout("no urls here\njust text") == []


def test_sherlock_parse_stdout_valid() -> None:
    text = "[+] GitHub: https://github.com/alice"
    results = SherlockScanner._parse_stdout(text)
    assert len(results) == 1
    assert results[0]["platform"] == "GitHub"
    assert results[0]["url"] == "https://github.com/alice"
    assert results[0]["status"] == "Claimed"
    assert results[0]["response_time"] is None


def test_sherlock_parse_stdout_deduplicates() -> None:
    text = "[+] GitHub: https://github.com/alice\n[+] GitHub: https://github.com/alice"
    results = SherlockScanner._parse_stdout(text)
    assert len(results) == 1


async def test_sherlock_scan_command_order() -> None:
    captured_cmd: tuple[str, ...] | None = None

    class FakeProcess:
        def __init__(self) -> None:
            self.returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return (b"[+] GitHub: https://github.com/alice\n", b"")

    async def fake_create_subprocess_exec(*cmd: str, **kwargs: object) -> FakeProcess:
        nonlocal captured_cmd
        captured_cmd = cmd
        assert kwargs["stdout"] == asyncio.subprocess.PIPE
        assert kwargs["stderr"] == asyncio.subprocess.PIPE
        return FakeProcess()

    with patch("account_scanner.asyncio.create_subprocess_exec", side_effect=fake_create_subprocess_exec):
        results = await SherlockScanner().scan("alice", timeout_seconds=120, verbose=False)

    assert results[0]["url"] == "https://github.com/alice"
    assert captured_cmd == (
        "sherlock",
        "--timeout",
        "120",
        "--no-color",
        "--print-found",
        "--",
        "alice",
    )


async def test_sherlock_scan_timeout_recovery() -> None:
    class FakeReader:
        def __init__(self, data: bytes) -> None:
            self._data = data

        async def read(self) -> bytes:
            return self._data

    class FakeProcess:
        def __init__(self) -> None:
            self.stdout = FakeReader(b"[+] GitHub: https://github.com/alice\n")
            self.stderr = FakeReader(b"")
            self.returncode = -9
            self.killed = False
            self.waited = False

        async def communicate(self) -> tuple[bytes, bytes]:
            raise TimeoutError

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> None:
            self.waited = True

    proc = FakeProcess()

    with patch("account_scanner.asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        results = await SherlockScanner().scan("alice", timeout_seconds=1, verbose=False)

    assert proc.killed is True
    assert proc.waited is True
    assert results == [
        {
            "platform": "GitHub",
            "url": "https://github.com/alice",
            "status": "Claimed",
            "response_time": None,
        }
    ]


async def test_reddit_fetch_items_uses_reddit_oauth_api(monkeypatch: pytest.MonkeyPatch) -> None:
    client_id = "client-id"
    client_secret = "client-secret"
    scanner = RedditScanner(
        ScanConfig(
            username="alice",
            client_id=client_id,
            client_secret=client_secret,
            user_agent="account-scanner-test",
        )
    )
    requests: list[tuple[str, str]] = []

    async def fake_post(
        self: httpx.AsyncClient, url: str, **kwargs: object
    ) -> httpx.Response:
        requests.append(("POST", url))
        assert kwargs["data"] == {"grant_type": "client_credentials"}
        assert kwargs["auth"] == (client_id, client_secret)
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"access_token": "token"},
        )

    async def fake_get(
        self: httpx.AsyncClient, url: str, **kwargs: object
    ) -> httpx.Response:
        requests.append(("GET", url))
        assert kwargs["params"]["sort"] == "new"
        assert kwargs["params"]["raw_json"] == 1
        assert self.headers["Authorization"] == "Bearer token"
        if url == "https://oauth.reddit.com/user/alice/comments":
            assert kwargs["params"]["limit"] == scanner.config.comments
            return httpx.Response(
                200,
                request=httpx.Request("GET", url),
                json={
                    "data": {
                        "children": [
                            {
                                "data": {
                                    "subreddit": "python",
                                    "body": "hello",
                                    "created_utc": 123.0,
                                }
                            }
                        ]
                    }
                },
            )
        assert url == "https://oauth.reddit.com/user/alice/submitted"
        assert kwargs["params"]["limit"] == scanner.config.posts
        return httpx.Response(
            200,
            request=httpx.Request("GET", url),
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "subreddit": "asyncio",
                                "title": "post",
                                "selftext": "body",
                                "created_utc": 456.0,
                            }
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    items = await scanner._fetch_items()

    assert items == [
        ("comment", "python", "hello", 123.0),
        ("post", "asyncio", "post\nbody", 456.0),
    ]
    assert requests == [
        ("POST", "https://www.reddit.com/api/v1/access_token"),
        ("GET", "https://oauth.reddit.com/user/alice/comments"),
        ("GET", "https://oauth.reddit.com/user/alice/submitted"),
    ]


async def test_reddit_fetch_items_returns_none_on_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_id = "client-id"
    client_secret = "client-secret"
    scanner = RedditScanner(
        ScanConfig(
            username="alice",
            client_id=client_id,
            client_secret=client_secret,
        )
    )

    async def fake_post(
        self: httpx.AsyncClient, url: str, **kwargs: object
    ) -> httpx.Response:
        return httpx.Response(
            401,
            request=httpx.Request("POST", url),
            json={"message": "Unauthorized"},
        )

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    assert await scanner._fetch_items() is None


async def test_reddit_fetch_items_returns_none_when_credentials_missing() -> None:
    scanner = RedditScanner(ScanConfig(username="alice"))

    assert await scanner._fetch_items() is None

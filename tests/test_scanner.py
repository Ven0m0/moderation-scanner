"""Tests for account_scanner core logic."""

from unittest.mock import AsyncMock, patch

import pytest

from account_scanner import RateLimiter, ScanConfig, SherlockScanner

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

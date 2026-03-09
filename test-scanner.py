#!/usr/bin/env python3
"""Basic tests for account scanner."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from account_scanner import RateLimiter, ScanConfig, SherlockScanner

DEFAULT_THRESHOLD = 0.7


def test_config_validation() -> None:
    """Test config defaults."""
    cfg = ScanConfig(username="test")
    assert cfg.username == "test"
    assert cfg.mode == "both"
    assert cfg.threshold == DEFAULT_THRESHOLD


def test_rate_limiter_init() -> None:
    """Test rate limiter initialization."""
    limiter = RateLimiter(60.0)
    assert limiter.delay == 1.0


def test_sherlock_available() -> None:
    """Test Sherlock availability check."""
    result = SherlockScanner.available()
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
    ],
)
def test_sherlock_status(status: str, expected: bool) -> None:
    """Test Sherlock status detection."""
    assert SherlockScanner._is_claimed(status) == expected


@pytest.mark.anyio
async def test_rate_limiter_wait_immediate():
    """Test that RateLimiter.wait executes immediately on first call."""
    limiter = RateLimiter(60.0)
    with patch("time.monotonic", return_value=100.0), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait()
        mock_sleep.assert_not_called()
        assert limiter.last_call == 100.0


@pytest.mark.anyio
async def test_rate_limiter_wait_sleep():
    """Test that RateLimiter.wait sleeps when called too soon."""
    limiter = RateLimiter(60.0)  # 1s delay
    limiter.last_call = 100.0
    # now=100.5, elapsed=0.5, needs 0.5s sleep
    with patch("time.monotonic", side_effect=[100.5, 100.5]), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait()
        mock_sleep.assert_called_once_with(0.5)
        assert limiter.last_call == 100.5


@pytest.mark.anyio
async def test_rate_limiter_wait_no_sleep_after_delay():
    """Test that RateLimiter.wait doesn't sleep after sufficient time."""
    limiter = RateLimiter(60.0)
    limiter.last_call = 100.0
    # now=101.5, elapsed=1.5, no sleep needed
    with patch("time.monotonic", return_value=101.5), \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await limiter.wait()
        mock_sleep.assert_not_called()
        assert limiter.last_call == 101.5


@pytest.mark.anyio
async def test_rate_limiter_wait_updates_last_call():
    """Test that RateLimiter.wait updates last_call after sleep."""
    limiter = RateLimiter(60.0)
    limiter.last_call = 100.0
    with patch("time.monotonic", side_effect=[100.2, 100.8]), \
         patch("asyncio.sleep", new_callable=AsyncMock):
        await limiter.wait()
        assert limiter.last_call == 100.8

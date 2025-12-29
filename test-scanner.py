#!/usr/bin/env python3
"""Basic tests for account scanner."""

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

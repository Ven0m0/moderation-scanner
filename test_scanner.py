#!/usr/bin/env python3
"""Basic smoke tests for account scanner (root-level, kept for backwards compat)."""

from account_scanner import RateLimiter, ScanConfig, SherlockScanner

DEFAULT_THRESHOLD = 0.7


def test_config_validation() -> None:
    cfg = ScanConfig(username="test")
    assert cfg.username == "test"
    assert cfg.mode == "both"
    assert cfg.threshold == DEFAULT_THRESHOLD


def test_rate_limiter_init() -> None:
    limiter = RateLimiter(rate_per_min=60.0)
    assert limiter.delay == 1.0


async def test_sherlock_available() -> None:
    result = await SherlockScanner.available()
    assert isinstance(result, bool)

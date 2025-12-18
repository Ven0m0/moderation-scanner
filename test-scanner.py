"""Tests for account scanner."""
import pytest
from account_scanner import RateLimiter, ScanConfig, SherlockScanner


def test_scan_config_defaults():
  """Test ScanConfig default values."""
  config = ScanConfig(username="test_user")
  assert config.username == "test_user"
  assert config.mode == "both"
  assert config.comments == 50
  assert config.posts == 20
  assert config.threshold == 0.7
  assert "test_user" in config.user_agent


def test_scan_config_custom():
  """Test ScanConfig custom values."""
  config = ScanConfig(
    username="custom",
    mode="reddit",
    comments=100,
    threshold=0.9,
  )
  assert config.username == "custom"
  assert config.mode == "reddit"
  assert config.comments == 100
  assert config.threshold == 0.9


@pytest.mark.asyncio
async def test_rate_limiter():
  """Test rate limiter delays correctly."""
  import time
  limiter = RateLimiter(rate_per_min=120.0)  # 2/sec
  
  start = time.monotonic()
  await limiter.wait()
  await limiter.wait()
  elapsed = time.monotonic() - start
  
  # Should take at least 0.5s (1/2 calls per second)
  assert elapsed >= 0.45


def test_sherlock_parse_stdout():
  """Test Sherlock stdout parsing."""
  scanner = SherlockScanner()
  stdout = """
  [+] GitHub: https://github.com/test
  [+] Twitter: https://twitter.com/test
  [-] Facebook: Not Found
  """
  results = scanner._parse_stdout(stdout)
  
  assert len(results) == 2
  assert results[0]["platform"] == "GitHub"
  assert results[0]["url"] == "https://github.com/test"
  assert results[1]["platform"] == "Twitter"


def test_sherlock_is_claimed():
  """Test Sherlock status detection."""
  scanner = SherlockScanner()
  
  assert scanner._is_claimed("Claimed")
  assert scanner._is_claimed("Found")
  assert not scanner._is_claimed("Not Found")
  assert not scanner._is_claimed("Available")
  assert not scanner._is_claimed("Invalid")
  assert not scanner._is_claimed("Unchecked")


@pytest.mark.parametrize(
  "status,expected",
  [
    ("Claimed", True),
    ("Not Found", False),
    ("Available", False),
    ("Invalid Username", False),
    ("Unchecked", False),
    ("Unknown", False),
  ],
)
def test_sherlock_status_detection(status: str, expected: bool):
  """Parametrized test for status detection."""
  scanner = SherlockScanner()
  assert scanner._is_claimed(status) == expected

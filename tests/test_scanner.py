import unittest
from account_scanner import RateLimiter, ScanConfig, SherlockScanner

DEFAULT_THRESHOLD = 0.7

class TestScanner(unittest.TestCase):
    def test_config_validation(self):
        """Test config defaults."""
        cfg = ScanConfig(username="test")
        self.assertEqual(cfg.username, "test")
        self.assertEqual(cfg.mode, "both")
        self.assertEqual(cfg.threshold, DEFAULT_THRESHOLD)

    def test_rate_limiter_init(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(60.0)
        self.assertEqual(limiter.delay, 1.0)

    def test_sherlock_available(self):
        """Test Sherlock availability check."""
        result = SherlockScanner.available()
        self.assertIsInstance(result, bool)

if __name__ == "__main__":
    unittest.main()

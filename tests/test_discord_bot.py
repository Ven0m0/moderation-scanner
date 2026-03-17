import logging
import os
import unittest
from unittest.mock import patch

from discord_bot import BotConfig, ConfigurationError


class TestBotConfig(unittest.TestCase):
    def setUp(self):
        # Disable logging to keep test output clean
        logging.disable(logging.CRITICAL)

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def test_validate_missing_token(self):
        """Test that validate raises ConfigurationError when DISCORD_BOT_TOKEN is missing."""
        with patch.dict(os.environ, {}, clear=True):
            config = BotConfig()
            with self.assertRaises(ConfigurationError) as cm:
                config.validate()
            self.assertEqual(str(cm.exception), "DISCORD_BOT_TOKEN is required")

    def test_validate_with_token(self):
        """Test that validate passes when DISCORD_BOT_TOKEN is present."""
        with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "test_token"}, clear=True):
            config = BotConfig()
            # Should not raise
            config.validate()
            self.assertEqual(config.discord_token, "test_token")

    def test_parse_admin_ids(self):
        """Test parsing of ADMIN_USER_IDS environment variable."""
        # Valid input
        with patch.dict(os.environ, {"ADMIN_USER_IDS": "123, 456"}, clear=True):
            config = BotConfig()
            self.assertEqual(config.admin_user_ids, {123, 456})

        # Empty input
        with patch.dict(os.environ, {"ADMIN_USER_IDS": ""}, clear=True):
            config = BotConfig()
            self.assertEqual(config.admin_user_ids, set())

        # Invalid input (should log warning and return empty set)
        with patch.dict(os.environ, {"ADMIN_USER_IDS": "abc, 123"}, clear=True):
            config = BotConfig()
            self.assertEqual(config.admin_user_ids, set())

    def test_parse_log_channel(self):
        """Test parsing of LOG_CHANNEL_ID environment variable."""
        cases = {
            "valid input": ("789", 789),
            "empty input": ("", None),
            "invalid input": ("abc", None),
        }
        for name, (env_val, expected) in cases.items():
            with (
                self.subTest(name),
                patch.dict(os.environ, {"LOG_CHANNEL_ID": env_val}, clear=True),
            ):
                config = BotConfig()
                self.assertEqual(config.log_channel_id, expected)

    def test_has_reddit_config(self):
        """Test that has_reddit_config correctly identifies complete Reddit setup."""
        # All set
        env = {
            "PERSPECTIVE_API_KEY": "key",
            "REDDIT_CLIENT_ID": "id",
            "REDDIT_CLIENT_SECRET": "secret",
        }
        with patch.dict(os.environ, env, clear=True):
            config = BotConfig()
            self.assertTrue(config.has_reddit_config())

        # Missing one
        for key in env:
            bad_env = env.copy()
            del bad_env[key]
            with patch.dict(os.environ, bad_env, clear=True):
                config = BotConfig()
                self.assertFalse(
                    config.has_reddit_config(), f"Should be False when {key} is missing"
                )


if __name__ == "__main__":
    unittest.main()

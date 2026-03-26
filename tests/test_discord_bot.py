"""Tests for discord_bot configuration and validation."""

import logging
import os
from collections.abc import Generator
from unittest.mock import patch

import pytest

from discord_bot import BotConfig, ConfigurationError


@pytest.fixture(autouse=True)
def _silence_logs() -> Generator[None]:
    logging.disable(logging.CRITICAL)
    yield
    logging.disable(logging.NOTSET)


def test_validate_raises_when_token_missing() -> None:
    with patch.dict(os.environ, {}, clear=True):
        config = BotConfig()
        with pytest.raises(ConfigurationError, match="DISCORD_BOT_TOKEN is required"):
            config.validate()


def test_validate_passes_with_token() -> None:
    with patch.dict(os.environ, {"DISCORD_BOT_TOKEN": "test_token"}, clear=True):
        config = BotConfig()
        config.validate()  # must not raise
        assert config.discord_token == "test_token"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("123, 456", {123, 456}),
        ("", set()),
        ("  42  ", {42}),
    ],
)
def test_parse_admin_ids_valid(raw: str, expected: set[int]) -> None:
    with patch.dict(os.environ, {"ADMIN_USER_IDS": raw}, clear=True):
        config = BotConfig()
        assert config.admin_user_ids == expected


def test_parse_admin_ids_invalid_returns_empty() -> None:
    with patch.dict(os.environ, {"ADMIN_USER_IDS": "abc, 123"}, clear=True):
        config = BotConfig()
        assert config.admin_user_ids == set()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("789", 789),
        ("", None),
        ("abc", None),
    ],
)
def test_parse_log_channel(raw: str, expected: int | None) -> None:
    with patch.dict(os.environ, {"LOG_CHANNEL_ID": raw}, clear=True):
        config = BotConfig()
        assert config.log_channel_id == expected


def test_has_reddit_config_all_set() -> None:
    env = {
        "PERSPECTIVE_API_KEY": "key",
        "REDDIT_CLIENT_ID": "id",
        "REDDIT_CLIENT_SECRET": "secret",
    }
    with patch.dict(os.environ, env, clear=True):
        assert BotConfig().has_reddit_config() is True


@pytest.mark.parametrize(
    "missing_key", ["PERSPECTIVE_API_KEY", "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET"]
)
def test_has_reddit_config_missing_one(missing_key: str) -> None:
    env = {
        "PERSPECTIVE_API_KEY": "key",
        "REDDIT_CLIENT_ID": "id",
        "REDDIT_CLIENT_SECRET": "secret",
    }
    del env[missing_key]
    with patch.dict(os.environ, env, clear=True):
        assert BotConfig().has_reddit_config() is False

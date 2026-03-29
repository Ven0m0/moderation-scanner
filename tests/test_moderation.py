"""Tests for the moderation cog."""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation import ModerationCog


@pytest.mark.anyio
async def test_send_detailed_results_escapes_mentions():
    """Test that username is properly escaped in detailed results to prevent mention injection."""
    bot = MagicMock()
    bot.config.perspective_key = "test"
    bot.config.reddit_client_id = "test"
    bot.config.reddit_client_secret = "test"
    bot.config.reddit_user_agent = "test"

    cog = ModerationCog(bot)

    ctx = AsyncMock(spec=discord.Interaction)
    ctx.followup.send = AsyncMock()

    username = "<@123456789> @everyone"
    results = {
        "sherlock": [{"platform": "TestPlatform", "url": "http://test.com/user"}],
        "reddit": [],
    }

    await cog._send_detailed_results(ctx, username, results)

    # Check that followup.send was called
    ctx.followup.send.assert_called_once()

    # Get the text sent
    sent_text = ctx.followup.send.call_args[0][0]

    # Original username should not be in the text unescaped
    assert "<@123456789>" not in sent_text

    # The escaped version should be in the text
    escaped_username = discord.utils.escape_markdown(
        discord.utils.escape_mentions(username)
    ).replace("<@", "<\\@")
    assert escaped_username in sent_text
    assert "**🔎 Sherlock OSINT Results for " + escaped_username + ":**" in sent_text


@pytest.mark.anyio
async def test_send_detailed_results_escapes_mentions_reddit():
    """Test that username is properly escaped in detailed results for Reddit to prevent mention injection."""
    bot = MagicMock()
    cog = ModerationCog(bot)

    ctx = AsyncMock(spec=discord.Interaction)
    ctx.followup.send = AsyncMock()

    username = "<@123456789> @everyone"
    results = {
        "reddit": [
            {
                "content": "Test content",
                "timestamp": "2023-01-01",
                "type": "comment",
                "subreddit": "test",
            }
        ]
    }

    await cog._send_detailed_results(ctx, username, results)

    # Check that followup.send was called
    ctx.followup.send.assert_called_once()

    # Get the text sent
    sent_text = ctx.followup.send.call_args[0][0]

    # Original username should not be in the text unescaped
    assert "<@123456789>" not in sent_text

    # The escaped version should be in the text
    escaped_username = discord.utils.escape_markdown(
        discord.utils.escape_mentions(username)
    ).replace("<@", "<\\@")
    assert escaped_username in sent_text
    assert "**🤖 Reddit Toxicity Analysis for " + escaped_username + ":**" in sent_text

"""Tests for the moderation cog."""

from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs.moderation import ModerationCog, chunk_message


def test_chunk_message_empty_input():
    """Test chunk_message with empty input lines."""
    # Without header
    assert chunk_message([]) == []
    # With header
    assert chunk_message([], header="Header") == ["Header"]


def test_chunk_message_simple_fits():
    """Test chunk_message when all lines fit in a single chunk."""
    lines = ["line1", "line2", "line3"]
    # "line1\nline2\nline3" length is 5+1+5+1+5 = 17
    assert chunk_message(lines, max_length=20) == ["line1\nline2\nline3"]


def test_chunk_message_splits_by_max_length():
    """Test chunk_message splits lines across multiple chunks based on max_length."""
    lines = ["line1", "line2", "line3"]
    # max_length=10: "line1" (5) fits, "line1\nline2" (11) exceeds.
    # Chunk 1: "line1", Chunk 2: "line2", Chunk 3: "line3"
    assert chunk_message(lines, max_length=10) == ["line1", "line2", "line3"]


def test_chunk_message_exact_max_length():
    """Test chunk_message when combined length exactly matches max_length."""
    lines = ["line1", "line2"]
    # "line1\nline2" length is 11
    assert chunk_message(lines, max_length=11) == ["line1\nline2"]
    assert chunk_message(lines, max_length=10) == ["line1", "line2"]


def test_chunk_message_with_header():
    """Test chunk_message includes the header in the first chunk."""
    lines = ["line1", "line2"]
    header = "Header"
    # "Header\nline1" (12), "Header\nline1\nline2" (18)
    assert chunk_message(lines, header=header, max_length=12) == ["Header\nline1", "line2"]
    assert chunk_message(lines, header=header, max_length=18) == ["Header\nline1\nline2"]


def test_chunk_message_long_lines():
    """Test chunk_message behavior when individual lines or header exceed max_length."""
    # Line exceeds max_length - it should still be included as its own chunk
    assert chunk_message(["verylongline"], max_length=5) == ["verylongline"]

    # Header exceeds max_length - it should be its own chunk
    assert chunk_message(["line1"], header="verylongheader", max_length=5) == [
        "verylongheader",
        "line1",
    ]


def test_chunk_message_strips_whitespace():
    """Test chunk_message strips trailing whitespace from header and lines."""
    lines = ["line1  ", "  line2  "]
    header = "Header  "
    # Expected: "Header\nline1\n  line2"
    # Length: 6 + 1 + 5 + 1 + 7 = 20
    assert chunk_message(lines, header=header, max_length=20) == ["Header\nline1\n  line2"]


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

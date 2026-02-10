"""Moderation cog - handles account scanning and moderation commands."""

import asyncio
import logging
import re
from collections import deque
from pathlib import Path
from typing import Final

import discord
from discord import app_commands
from discord.ext import commands

from account_scanner import (
    RateLimiter,
    ScanConfig,
    ScannerAPI,
    SherlockScanner,
)

log = logging.getLogger(__name__)

# Constants
MAX_SCAN_LENGTH: Final = 50  # Maximum username length
SCAN_TIMEOUT: Final = 300  # 5 minutes timeout for scans
SCANS_DIR: Final = Path("./scans")

# Global Rate Limiter for Perspective API (60 req/min)
GLOBAL_LIMITER = RateLimiter(rate_per_min=60.0)

# Performance-optimized cooldown system using deque for O(1) cleanup
_scan_cooldowns: dict[int, float] = {}
_cooldown_queue: deque[tuple[float, int]] = deque()
COOLDOWN_SECONDS = 30


class ModerationCog(commands.Cog, name="Moderation"):
    """Cog for moderation and account scanning commands."""

    def __init__(self, bot: commands.Bot) -> None:
        """Initialize the moderation cog.

        Args:
            bot: The Discord bot instance.
        """
        self.bot = bot
        self.config = bot.config  # Access config from bot instance
        log.info("Moderation cog initialized")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Called when the cog is ready."""
        # Create scans directory
        SCANS_DIR.mkdir(exist_ok=True)
        log.info("Moderation cog ready - Scans directory: %s", SCANS_DIR.absolute())

    def check_cooldown(self, user_id: int) -> tuple[bool, float]:
        """Check if user is on cooldown with lazy cleanup.

        Args:
            user_id: The Discord user ID to check.

        Returns:
            Tuple of (is_on_cooldown, seconds_remaining).
        """
        now = asyncio.get_event_loop().time()

        # Lazy cleanup: Remove expired entries from front of queue (O(1) amortized)
        while _cooldown_queue and now - _cooldown_queue[0][0] >= COOLDOWN_SECONDS:
            ts, uid = _cooldown_queue.popleft()
            # Only delete if this is the most recent cooldown for this user
            if uid in _scan_cooldowns and _scan_cooldowns[uid] == ts:
                del _scan_cooldowns[uid]

        # Check cooldown
        if user_id in _scan_cooldowns:
            elapsed = now - _scan_cooldowns[user_id]
            if elapsed < COOLDOWN_SECONDS:
                return True, COOLDOWN_SECONDS - elapsed
        return False, 0.0

    def update_cooldown(self, user_id: int) -> None:
        """Update cooldown timestamp for user.

        Args:
            user_id: The Discord user ID to update.
        """
        now = asyncio.get_event_loop().time()
        _scan_cooldowns[user_id] = now
        _cooldown_queue.append((now, user_id))

    async def _send_detailed_results(self, ctx, username: str, results: dict) -> None:
        """Helper to send detailed text results.

        Args:
            ctx: The command context or interaction.
            username: The username that was scanned.
            results: The scan results dictionary.
        """
        # Sherlock results
        if results.get("sherlock"):
            lines = [
                f"{account['platform']}: {account['url']}" for account in results["sherlock"]
            ]
            sherlock_text = (
                f"**🔎 Sherlock OSINT Results for {username}:**\n```\n" + "\n".join(lines) + "\n```"
            )

            if len(sherlock_text) > 1900:
                chunks = []
                chunk_lines = [f"**🔎 Sherlock OSINT Results for {username}:**\n```"]
                current_length = len(chunk_lines[0])

                for line in lines:
                    line_with_newline = line + "\n"
                    if current_length + len(line_with_newline) + 3 > 1900:  # 3 for closing ```
                        chunk_lines.append("```")
                        chunks.append("\n".join(chunk_lines))
                        chunk_lines = ["```", line]
                        current_length = len("```\n") + len(line)
                    else:
                        chunk_lines.append(line)
                        current_length += len(line_with_newline)

                chunk_lines.append("```")
                chunks.append("\n".join(chunk_lines))

                for chunk in chunks:
                    if isinstance(ctx, discord.Interaction):
                        await ctx.followup.send(chunk)
                    else:
                        await ctx.send(chunk)
            else:
                if isinstance(ctx, discord.Interaction):
                    await ctx.followup.send(sherlock_text)
                else:
                    await ctx.send(sherlock_text)

        # Reddit results
        if results.get("reddit"):
            reddit_chunks = []
            current_lines = [f"**🤖 Reddit Toxicity Analysis for {username}:**"]
            current_length = len(current_lines[0]) + 1  # +1 for newline

            for item in results["reddit"]:
                content_preview = item["content"][:200] + (
                    "..." if len(item["content"]) > 200 else ""
                )
                item_lines = [
                    "```",
                    f"Time: {item['timestamp']}",
                    f"Type: {item['type']} | Subreddit: r/{item['subreddit']}",
                    f"Toxicity: {item['TOXICITY']:.2f} | Insult: {item['INSULT']:.2f} | "
                    f"Profanity: {item['PROFANITY']:.2f} | Sexual: {item['SEXUALLY_EXPLICIT']:.2f}",
                    f"Content: {content_preview}",
                    "```",
                ]
                item_text = "\n".join(item_lines) + "\n"

                if current_length + len(item_text) > 1900:
                    reddit_chunks.append("\n".join(current_lines))
                    current_lines = [item_text.rstrip()]
                    current_length = len(current_lines[0])
                else:
                    current_lines.append(item_text.rstrip())
                    current_length += len(item_text)

            if current_lines:
                reddit_chunks.append("\n".join(current_lines))

            for chunk in reddit_chunks:
                if isinstance(ctx, discord.Interaction):
                    await ctx.followup.send(chunk)
                else:
                    await ctx.send(chunk)

    @commands.hybrid_command(
        name="scan",
        description="Scan a user across platforms for moderation purposes",
    )
    @commands.has_permissions(moderate_members=True)
    @commands.cooldown(1, 30, commands.BucketType.user)
    @app_commands.describe(
        username="Target username to scan (max 50 characters)",
        mode="Scan mode: sherlock (OSINT), reddit (toxicity), or both",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Both (Reddit + Sherlock)", value="both"),
            app_commands.Choice(name="Sherlock (OSINT only)", value="sherlock"),
            app_commands.Choice(name="Reddit (Toxicity only)", value="reddit"),
        ]
    )
    async def scan(
        self,
        ctx: commands.Context,
        username: str,
        mode: str = "both",
    ) -> None:
        """Scan a user across platforms for moderation purposes.

        Args:
            ctx: The command context.
            username: The username to scan.
            mode: The scan mode (sherlock, reddit, or both).
        """
        # Handle interaction vs context for cooldown
        user_id = ctx.author.id if isinstance(ctx, commands.Context) else ctx.interaction.user.id

        # For slash commands, check cooldown manually
        if isinstance(ctx, commands.Context) and ctx.interaction:
            on_cooldown, remaining = self.check_cooldown(user_id)
            if on_cooldown:
                await ctx.send(
                    f"⏱️ Cooldown: try again in {remaining:.1f}s",
                    ephemeral=True,
                )
                return

        if len(username) > MAX_SCAN_LENGTH:
            await ctx.send(
                f"❌ Username too long (max {MAX_SCAN_LENGTH} characters)",
                ephemeral=True,
            )
            return

        if mode not in ("sherlock", "reddit", "both"):
            await ctx.send("❌ Mode must be: sherlock, reddit, or both", ephemeral=True)
            return

        if mode in ("reddit", "both") and not self.config.has_reddit_config():
            await ctx.send("❌ Reddit scanning not configured on this bot", ephemeral=True)
            return

        if mode in ("sherlock", "both") and not SherlockScanner.available():
            await ctx.send("❌ Sherlock not available on this bot", ephemeral=True)
            return

        # Update cooldown for slash commands
        if isinstance(ctx, commands.Context) and ctx.interaction:
            self.update_cooldown(user_id)

        # Sanitize username for filename safety
        safe_username = re.sub(r"[^\w\-]", "_", username)

        await ctx.send(f"🔍 Scanning **{username}** (mode: {mode})...")
        log.info(
            "Scan requested by %s (ID: %s) for user '%s' (mode: %s)",
            ctx.author.name,
            ctx.author.id,
            username,
            mode,
        )

        scan_config = ScanConfig(
            username=username,
            mode=mode,
            api_key=self.config.perspective_key,
            client_id=self.config.reddit_client_id,
            client_secret=self.config.reddit_client_secret,
            user_agent=self.config.reddit_user_agent,
            limiter=GLOBAL_LIMITER,
            output_reddit=SCANS_DIR / f"{safe_username}_reddit.csv",
            output_sherlock=SCANS_DIR / f"{safe_username}_sherlock.json",
            verbose=True,
        )

        try:
            results = await asyncio.wait_for(
                ScannerAPI.scan_user(username, scan_config),
                timeout=SCAN_TIMEOUT,
            )

            embed = discord.Embed(
                title=f"Scan Results: {username}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}")

            if mode in ("sherlock", "both"):
                sherlock_results = results.get("sherlock")
                if sherlock_results:
                    platforms = len(sherlock_results)
                    embed.add_field(
                        name="🔎 Sherlock OSINT",
                        value=f"✅ Found on **{platforms}** platforms",
                        inline=False,
                    )
                elif sherlock_results == []:
                    embed.add_field(
                        name="🔎 Sherlock OSINT",
                        value="❌ No accounts found",
                        inline=False,
                    )

            if mode in ("reddit", "both"):
                if results.get("reddit"):
                    flagged = len(results["reddit"])
                    status = "⚠️ Toxic content detected" if flagged > 0 else "✅ Clean"
                    embed.add_field(
                        name="🤖 Reddit Analysis",
                        value=f"{status} (**{flagged}** flagged items)",
                        inline=False,
                    )
                elif "reddit" in results:
                    embed.add_field(
                        name="🤖 Reddit Analysis",
                        value="✅ No toxic content found",
                        inline=False,
                    )

            if results.get("errors"):
                error_text = "\n".join(f"• {err}" for err in results["errors"])
                embed.add_field(
                    name="⚠️ Issues",
                    value=error_text[:1024],
                    inline=False,
                )

            # Edit the original message with the embed
            if isinstance(ctx, commands.Context):
                # For prefix commands, we need to edit the last message we sent
                async for msg in ctx.channel.history(limit=10):
                    if msg.author == self.bot.user and msg.content.startswith("🔍"):
                        await msg.edit(content=None, embed=embed)
                        break
            else:
                # For slash commands
                await ctx.interaction.edit_original_response(content=None, embed=embed)

            await self._send_detailed_results(ctx, username, results)
            log.info("Scan completed for user '%s'", username)

        except TimeoutError:
            await ctx.send(f"⏱️ Scan timed out after {SCAN_TIMEOUT}s. Try a simpler scan mode.")
            log.warning("Scan timeout for user '%s'", username)
        except (discord.HTTPException, discord.DiscordException):
            log.exception("Discord error during scan for user '%s'", username)
            try:
                await ctx.send("❌ Discord API error occurred. Please try again.")
            except (discord.HTTPException, discord.DiscordException):
                log.debug(
                    "Failed to send Discord API error message to user during scan for '%s'",
                    username,
                    exc_info=True,
                )
        except (OSError, ValueError, RuntimeError):
            log.exception("Scan error for user '%s'", username)
            await ctx.send("❌ Scan failed. Check bot logs for details.")


async def setup(bot: commands.Bot) -> None:
    """Load the moderation cog.

    Args:
        bot: The Discord bot instance.
    """
    await bot.add_cog(ModerationCog(bot))

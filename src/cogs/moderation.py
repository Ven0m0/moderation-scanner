"""Moderation cog - handles account scanning and moderation commands."""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord
from discord import app_commands
from discord.ext import commands

from account_scanner import (
    RateLimiter,
    ScanConfig,
    ScanResult,
    SherlockScanner,
    scan_user,
)

if TYPE_CHECKING:
    from discord_bot import BotConfig, ModerationBot

log = logging.getLogger(__name__)

MAX_SCAN_LENGTH: Final = 50
SCAN_TIMEOUT: Final = 300
SCANS_DIR: Final = Path("./scans")

GLOBAL_LIMITER = RateLimiter(rate_per_min=60.0)

_scan_cooldowns: dict[int, float] = {}
_cooldown_queue: deque[tuple[float, int]] = deque()
COOLDOWN_SECONDS = 30


def chunk_message(lines: list[str], header: str = "", max_length: int = 1900) -> list[str]:
    """Chunk lines of text into messages respecting max_length."""
    chunks: list[str] = []

    # Track current_len as the exact length of "\n".join(current_lines).
    if header:
        header_stripped = header.rstrip()
        current_lines: list[str] = [header_stripped]
        current_len = len(header_stripped)
    else:
        current_lines = []
        current_len = 0

    for line in lines:
        stripped = line.rstrip()
        # If there are existing lines, a newline separator will be inserted.
        separator_len = 1 if current_lines else 0
        prospective_len = current_len + separator_len + len(stripped)

        if prospective_len > max_length:
            if current_lines:
                chunks.append("\n".join(current_lines))
            current_lines = [stripped]
            current_len = len(stripped)
        else:
            if current_lines:
                current_lines.append(stripped)
            else:
                current_lines = [stripped]
            current_len = prospective_len

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


class ModerationCog(commands.Cog, name="Moderation"):
    """Cog for moderation and account scanning commands."""

    def __init__(self, bot: ModerationBot) -> None:
        self.bot = bot
        self.config: BotConfig = bot.config
        log.info("Moderation cog initialized")

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        """Create the scans directory on first ready."""
        SCANS_DIR.mkdir(exist_ok=True)
        log.info("Moderation cog ready - Scans directory: %s", SCANS_DIR.absolute())

    def check_cooldown(self, user_id: int) -> tuple[bool, float]:
        """Return (is_on_cooldown, seconds_remaining) for *user_id*."""
        now = asyncio.get_running_loop().time()
        while _cooldown_queue and now - _cooldown_queue[0][0] >= COOLDOWN_SECONDS:
            ts, uid = _cooldown_queue.popleft()
            if uid in _scan_cooldowns and _scan_cooldowns[uid] == ts:
                del _scan_cooldowns[uid]
        if user_id in _scan_cooldowns:
            elapsed = now - _scan_cooldowns[user_id]
            if elapsed < COOLDOWN_SECONDS:
                return True, COOLDOWN_SECONDS - elapsed
        return False, 0.0

    def update_cooldown(self, user_id: int) -> None:
        """Record a new cooldown timestamp for *user_id*."""
        now = asyncio.get_running_loop().time()
        _scan_cooldowns[user_id] = now
        _cooldown_queue.append((now, user_id))

    async def _send_detailed_results(
        self,
        ctx: commands.Context[Any] | discord.Interaction,
        username: str,
        results: ScanResult,
    ) -> None:
        """Send detailed scan results as chunked Discord messages."""

        async def _send(text: str) -> None:
            if isinstance(ctx, discord.Interaction):
                await ctx.followup.send(text)
            else:
                await ctx.send(text)

        if results.get("sherlock"):
            sherlock = results["sherlock"]
            assert sherlock is not None
            lines = [f"{a['platform']}: {a['url']}" for a in sherlock]
            # Remove direct mentions like <@123>
            clean_username = discord.utils.escape_markdown(
                discord.utils.escape_mentions(username)
            ).replace("<@", "<\\@")
            header = f"**🔎 Sherlock OSINT Results for {clean_username}:**\n```\n"
            full_text = header + "\n".join(lines) + "\n```"
            if len(full_text) <= 1900:
                await _send(full_text)
            else:
                chunks = chunk_message(lines, header=header, max_length=1900)
                for i in range(len(chunks)):
                    if i > 0 and not chunks[i].startswith("```"):
                        chunks[i] = "```\n" + chunks[i]
                    if not chunks[i].endswith("```"):
                        chunks[i] = chunks[i] + "\n```"
                for chunk in chunks:
                    await _send(chunk)

        if results.get("reddit"):
            reddit = results["reddit"]
            assert reddit is not None
            clean_username = discord.utils.escape_markdown(
                discord.utils.escape_mentions(username)
            ).replace("<@", "<\\@")
            items: list[str] = []
            for item in reddit:
                preview = item["content"][:200] + ("..." if len(item["content"]) > 200 else "")
                item_text = (
                    "```\n"
                    f"Time: {item['timestamp']}\n"
                    f"Type: {item['type']} | Subreddit: r/{item['subreddit']}\n"
                    f"Toxicity: {item.get('TOXICITY', 0):.2f} | "
                    f"Insult: {item.get('INSULT', 0):.2f} | "
                    f"Profanity: {item.get('PROFANITY', 0):.2f} | "
                    f"Sexual: {item.get('SEXUALLY_EXPLICIT', 0):.2f}\n"
                    f"Content: {preview}\n"
                    "```"
                )
                items.append(item_text)

            header = f"**🤖 Reddit Toxicity Analysis for {clean_username}:**"
            reddit_chunks = chunk_message(items, header=header, max_length=1900)
            for chunk in reddit_chunks:
                await _send(chunk)

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
        ctx: commands.Context[Any],
        username: str,
        mode: str = "both",
    ) -> None:
        """Scan a user across platforms for moderation purposes."""
        user_id = ctx.author.id if isinstance(ctx, commands.Context) else ctx.interaction.user.id

        if isinstance(ctx, commands.Context) and ctx.interaction:
            on_cooldown, remaining = self.check_cooldown(user_id)
            if on_cooldown:
                await ctx.send(f"⏱️ Cooldown: try again in {remaining:.1f}s", ephemeral=True)
                return

        if len(username) > MAX_SCAN_LENGTH:
            await ctx.send(
                f"❌ Username too long (max {MAX_SCAN_LENGTH} characters)", ephemeral=True
            )
            return

        if mode not in ("sherlock", "reddit", "both"):
            await ctx.send("❌ Mode must be: sherlock, reddit, or both", ephemeral=True)
            return

        if mode in ("reddit", "both") and not self.config.has_reddit_config():
            await ctx.send("❌ Reddit scanning not configured on this bot", ephemeral=True)
            return

        if mode in ("sherlock", "both") and not await SherlockScanner.available():
            await ctx.send("❌ Sherlock not available on this bot", ephemeral=True)
            return

        if isinstance(ctx, commands.Context) and ctx.interaction:
            self.update_cooldown(user_id)

        safe_username = re.sub(r"[^\w\-]", "_", username)
        clean_username = discord.utils.escape_markdown(
            discord.utils.escape_mentions(username)
        ).replace("<@", "<\\@")
        status_message: discord.Message | None = None
        if ctx.interaction:
            await ctx.send(
                f"🔍 Scanning **{clean_username}** (mode: {mode})...",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        else:
            status_message = await ctx.send(
                f"🔍 Scanning **{clean_username}** (mode: {mode})...",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        log.info(
            "Scan requested by %s (ID: %s) for user '%s' (mode: %s)",
            ctx.author.name,
            ctx.author.id,
            username,
            mode,
        )

        scan_config = ScanConfig(
            username=username,
            mode=mode,  # type: ignore[arg-type]
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
                scan_user(scan_config),
                timeout=SCAN_TIMEOUT,
            )

            embed = discord.Embed(
                title=f"Scan Results: {clean_username}",
                color=discord.Color.blue(),
                timestamp=discord.utils.utcnow(),
            )
            embed.set_footer(text=f"Requested by {ctx.author.name}")

            if mode in ("sherlock", "both"):
                sherlock_results = results.get("sherlock")
                if sherlock_results:
                    embed.add_field(
                        name="🔎 Sherlock OSINT",
                        value=f"✅ Found on **{len(sherlock_results)}** platforms",
                        inline=False,
                    )
                elif sherlock_results == []:
                    embed.add_field(
                        name="🔎 Sherlock OSINT",
                        value="❌ No accounts found",
                        inline=False,
                    )

            if mode in ("reddit", "both"):
                reddit_res = results.get("reddit")
                if reddit_res:
                    flagged = len(reddit_res)
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
                embed.add_field(name="⚠️ Issues", value=error_text[:1024], inline=False)

            if ctx.interaction:
                await ctx.interaction.edit_original_response(content=None, embed=embed)
            else:
                assert status_message is not None
                try:
                    await status_message.edit(content=None, embed=embed)
                except (discord.NotFound, discord.Forbidden):
                    # If the status message was deleted or permissions changed, fall back to a new message
                    await ctx.send(embed=embed)

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
                    "Failed to send Discord API error message during scan for '%s'",
                    username,
                    exc_info=True,
                )
        except (OSError, ValueError, RuntimeError):
            log.exception("Scan error for user '%s'", username)
            await ctx.send("❌ Scan failed. Check bot logs for details.")


async def setup(bot: commands.Bot) -> None:
    """Load the moderation cog."""
    await bot.add_cog(ModerationCog(bot))
